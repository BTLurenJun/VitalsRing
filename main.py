# -*- coding: utf-8 -*-
"""VitalsRing（环脉）主窗口 —— 第一阶段第 4 轮。

已完成范围：无边框置顶小窗 + 五个 QPainter 自绘环 + 两个文本行 + 失败红叉 + 版本号（第 1 轮）；
            点击环形/文字列表互切 + 两个文本行折叠展开（第 2 轮）；
            设置窗口 + 调试模式 + 五项调试值 + 五项检测开关 + GitHub 预留按钮（第 3 轮）；
            第 4 轮：背景半透明降级 + 白条修复（背景画满整矩形 + 不透明遮罩裁角）。
本轮不含：任务栏吸附定位（第二阶段）。
安全边界：仅读取并显示系统信息，不修改任何系统设置、不写注册表、不删除文件。
"""
from __future__ import annotations

import ctypes
import math
import sys
import traceback
from ctypes import wintypes

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QRegion
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from readers import ItemData, SystemReader
from settings_window import SettingsWindow

# 版本号规则（总需求第十三条）：0.10.轮次.修改次数
# 第 4 轮起始 0.10.04.01，本轮内每次按反馈修改第四位递增
APP_VERSION = "0.10.04.02"
APP_AUTHOR = "BTLurenJun"                                    # 作者署名
APP_REPO_URL = "https://github.com/BTLurenJun/VitalsRing"    # 项目仓库地址

# 调试日志总开关：发布版保持 False，避免带控制台的 python.exe 每次刷新都刷屏。
# 排查"窗口闪一下消失"这类问题时，临时改成 True 即可看到拖动/显示/隐藏的轨迹。
DEBUG_LOG = False

# 环形配色（总需求第七条）：<60% 绿，60%~85% 黄，>85% 红；电池 <20% 红，充电中可用绿或蓝
COLOR_GREEN = QColor("#43A047")
COLOR_YELLOW = QColor("#FBC02D")
COLOR_RED = QColor("#E53935")
COLOR_CHARGING = QColor("#29B6F6")

# 若实际运行时出现黑底、白条或闪烁，把下面开关改为 True 即可强制使用不透明兜底背景
FORCE_OPAQUE_BACKGROUND = False


def _value_color(item: ItemData) -> QColor:
    """给出进度弧颜色。

    注意：电池不能复用"占用率"阈值——占用率高是坏事、电量高是好事，
    共用同一套阈值会出现"电量 90% 反而标红"的语义错误，因此电池单独一条分支。
    """
    value = item.value if item.value is not None else 0.0
    if item.key == "battery":
        if item.charging:
            return COLOR_CHARGING                 # 充电中：用蓝色表示"正在补充"
        if value < 20:
            return COLOR_RED                      # 只有低电量才标红
        return COLOR_GREEN
    if value < 60:
        return COLOR_GREEN
    if value <= 85:
        return COLOR_YELLOW
    return COLOR_RED


def _dwm_composition_enabled() -> bool:
    """查询桌面合成（DWM）是否开启——只读的 Win32 调用。

    合成关闭时半透明窗口会渲染成黑底，因此要提前判断，直接走不透明兜底方案。
    """
    try:
        enabled = ctypes.c_int(0)
        hr = ctypes.windll.dwmapi.DwmIsCompositionEnabled(ctypes.byref(enabled))
        return hr == 0 and enabled.value != 0
    except Exception:
        return False


def _resolve_system_bg_color() -> QColor:
    """读取 Windows 系统着色颜色，作为半透明不可用时的兜底背景色。

    - 只读调用，不修改任何系统设置；只在启动时执行一次并缓存，避免高频重复取色；
    - 取色失败时返回固定深灰，保证程序不崩溃、不出现黑底/白条。
    """
    try:
        value = ctypes.c_uint32(0)
        opaque = ctypes.c_int(0)
        hr = ctypes.windll.dwmapi.DwmGetColorizationColor(
            ctypes.byref(value), ctypes.byref(opaque)
        )
        if hr == 0:
            raw = int(value.value)
            # 注意：DwmGetColorizationColor 返回的是 0xAARRGGBB（高位是 alpha），
            # 不是 0x00BBGGRR；若按 BGR 拆通道会导致红蓝互换，兜底背景发棕
            r = (raw >> 16) & 0xFF
            g = (raw >> 8) & 0xFF
            b = raw & 0xFF                       # 高 8 位 alpha 直接丢弃
            return QColor(r, g, b).darker(180)   # 适当压暗，避免小面板背景过亮影响读数
    except Exception:
        pass
    return QColor("#1E1E1E")                 # 最终兜底：固定深灰


class VitalPanel(QWidget):
    """主面板窗口：负责窗口外观、定时刷新与全部自绘内容。

    绘制与读取严格分离：本类的 paintEvent 只消费 SystemReader 已读好的数据，绝不读取系统信息。
    """

    # ---- 布局常量（环直径与间距下限来自需求确认，不允许再调小）----
    PAD = 10                  # 内容与窗口边缘的留白
    D_MAX = 64                # 环直径上限
    D_MIN = 52                # 环直径下限：不得小于 52 像素
    GAP_MIN = 6               # 环间距下限：不得小于 6 像素
    ROW_GAP = 6               # 多行排列时的行间距
    REASON_H = 16             # 环下方"失败原因"文字行高度（始终预留，避免网格跳动）
    TEXT_H = 18               # 文本行高度
    SECTION_GAP = 8           # 环形区与文本行之间的间隔
    VERSION_H = 14            # 版本号行高度
    TICKS = 24                # 刻度线数量：只画短线，不带任何数字标签
    MIN_WIDTH = 240           # 最小宽度：保证 2×2+1 排列时环直径仍不低于 D_MIN
    RESIZE_HOT = 20           # 右下角缩放热区边长：绘制手柄与鼠标命中判定共用这一个矩形
    GEAR_SIZE = 14            # 右下角小齿轮按钮的边长（放在缩放热区左侧，两者不重叠）
    REFRESH_MS = 2000         # 固定刷新间隔 2 秒，禁止更高频率轮询
    LIST_ROW_H = 20           # 文字模式下一行的高度
    CLICK_SLOP = 4            # 判定"点击"还是"拖动"的位移阈值（像素）

    def __init__(self, reader: SystemReader) -> None:
        super().__init__()
        self._reader = reader
        # 鼠标交互状态：拖拽移动 / 右下角调整宽度 / 点击切换
        self._dragging = False
        self._resizing = False
        # 拖动改为增量位移：记录"上一次的全局鼠标位置"，每帧只移动两者的差值。
        # 不用"按下时的固定 offset 做绝对定位"——跨到 DPI 比例不同的屏幕时，
        # Qt 会按比例重算逻辑坐标，绝对定位会算出极远坐标，导致窗口跳飞。
        self._last_global = None
        self._resize_start_x = 0.0
        self._resize_start_w = 0
        self._press_pos = None            # 按下位置，用于区分"点击"与"拖动"
        self._moved = False               # 本次按下后是否真正移动过
        self._pending_action = None       # 松开时可能要执行的点击动作
        # 显示状态：默认环形模式。按需求"切换状态不持久化"，重启后一律回到环形 + 全部展开
        self._list_mode = False           # True = 文字列表模式
        self._boot_collapsed = False      # "开机时长"是否已折叠（只留标题）
        self._os_collapsed = False        # "系统版本"是否已折叠（只留标题）
        self._settings = None             # 设置窗口实例（懒创建、复用，避免每次点击都新建对象）
        # 窗口尺寸/位置的自保标志
        self._fixing_size = False         # 防重入：避免 resizeEvent 里再 resize 造成无限递归

        # ---- 窗口外观设置 ----
        self.setWindowTitle("VitalsRing 电脑状态小面板")
        # 无边框 + 置顶 + 不抢焦点 + 不出现在 Alt+Tab：
        # FramelessWindowHint      去掉标题栏与系统白条；
        # WindowStaysOnTopHint     保持置顶；
        # Tool                     在 Windows 上对应 WS_EX_TOOLWINDOW，使窗口不出现在 Alt+Tab 与任务栏；
        # WindowDoesNotAcceptFocus 让窗口不接受键盘焦点，避免抢走前台窗口的输入焦点。
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        # Tool 窗口默认不带 WA_QuitOnClose：不加这一行的话，关闭窗口后 Qt 不认为
        # "最后一个可退出窗口已关闭"，app.exec() 不会返回，python.exe 会一直驻留后台
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        # 显示窗口时不激活它，进一步避免抢焦点
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # 开启鼠标跟踪：不按键也能收到 mouseMoveEvent，用于把光标变成"斜向双箭头"
        self.setMouseTracking(True)

        # 背景取色只在启动时做一次并缓存（不做高频重复取色）
        self._bg_color = _resolve_system_bg_color()
        self._translucent = False
        if not FORCE_OPAQUE_BACKGROUND and _dwm_composition_enabled():
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            # 注意：不能拿 testAttribute() 当"检测"——属性刚设完必然返回 True，等于没检测。
            # 真正的降级只有两条：DWM 合成检查不通过，或 FORCE_OPAQUE_BACKGROUND 开关打开。
            self._translucent = True
        else:
            # 不透明兜底：关掉系统背景擦除，避免窗口首次显示时闪一下默认白底/灰底。
            # 背景完全由 _draw_background() 自己画，不会再露出系统底色。
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # 原生样式兜底只做一次（showEvent 中调用），这里先置标志
        self._native_style_applied = False

        self.setMinimumWidth(self.MIN_WIDTH)
        # 最大宽度直接取"五环排成一排"所需的宽度（5*D_MAX + 4*GAP_MIN + 2*PAD ≈ 364）。
        # 注意：再宽没有任何意义——环只会居中、两侧留白，窗口会被拉成横跨屏幕的长条，
        # 还会把右下角的缩放手柄推到屏幕可见范围之外，导致"手柄拉不动"。
        self._max_width = self._five_in_row_width()
        # 初始宽度刻意留出 44 像素余量（约 320）：这样向右拖能看到"变宽"的效果，
        # 向左拖也能缩到 240 触发 2×2+1，两个方向都能验证缩放功能；
        # 上限仍是 _max_width——五环一排刚好放下，再宽只会两侧留白。
        # 所有尺寸入口统一走 _clamp_width()，不在这里另写一套钳制规则。
        initial_width = self._clamp_width(self._max_width - 44)
        self.resize(initial_width, self.heightForWidth(initial_width))
        # 先按当前模式算一次圆角遮罩：不透明兜底时首帧就不会露出四角底色
        self._apply_round_mask()

        # 定时器只创建一次并长期复用：每次刷新都不新建 QTimer / 线程 / 对象（总需求第三条）
        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self._on_refresh_tick)
        self._timer.start()

        # 右键菜单只创建一次并复用：每次右键都 new QMenu 会作为子对象一直挂在窗口上，越点越多
        self._menu = QMenu(self)
        self._menu.addAction("退出 VitalsRing").triggered.connect(QApplication.instance().quit)

    # ------------------------------------------------------------------ 刷新

    def _on_refresh_tick(self) -> None:
        """定时刷新：先读取数据，再请求重绘。读取与绘制分离，读取失败也不影响绘制。

        注意：PyQt6 中槽函数若抛出未捕获异常会直接终止整个进程，
        因此这里加最外层兜底，只把堆栈打印到 stderr（不弹窗），保证界面永不崩溃。
        调试模式开启时跳过真实读取：调试值是人为设定，不能被 2 秒刷新覆盖。
        """
        try:
            if self._reader.debug_active:
                self.update()
                return
            self._reader.refresh()
            self.update()
        except Exception:
            traceback.print_exc()

    def pause_refresh(self) -> None:
        """暂停主窗口的真实数据刷新（调试模式期间调用）。"""
        try:
            self._timer.stop()
        except Exception:
            traceback.print_exc()

    def resume_refresh(self) -> None:
        """恢复真实数据刷新：立即读一次并重新启动定时器。

        注意：主窗口此时若被隐藏或最小化，只读数据、不启动定时器，
        避免看不见的时候白耗 CPU；等 showEvent 时再启动。
        """
        try:
            self._reader.refresh()
            self.update()
            if self.isVisible() and not self.isMinimized() and not self._timer.isActive():
                self._timer.start()
        except Exception:
            traceback.print_exc()

    def hideEvent(self, event) -> None:
        """窗口隐藏时暂停定时刷新，避免看不见时仍白耗 CPU/内存（总需求第三条）。"""
        if DEBUG_LOG:
            print("[window] hideEvent")
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        """窗口重新显示时恢复刷新，并立即刷新一次，避免显示上一轮的旧数据。

        注意：这里复用 _on_refresh_tick()，而不是再写一遍 refresh/update，
        这样首次刷新也走同一套 try/except 兜底。
        """
        super().showEvent(event)
        if DEBUG_LOG:
            print("[window] showEvent")
        # 首次显示时做一次原生样式兜底：去掉标题栏/粗边框、保持工具窗口与不抢焦点
        if not self._native_style_applied:
            self._native_style_applied = True
            self._apply_native_window_style()
        # 兜底：显示时按当前尺寸重算遮罩，
        # 防止隐藏期间改过尺寸或跨屏 DPI 变化后遮罩仍是旧尺寸
        self._apply_round_mask()
        self._on_refresh_tick()
        # 调试模式期间不启动定时器，否则真实读数会把调试值冲掉
        if not self._reader.debug_active and not self._timer.isActive():
            self._timer.start()

    def changeEvent(self, event) -> None:
        """最小化时同样暂停刷新；从最小化恢复时再启动定时器。

        注意：恢复条件要带上"未在调试模式"，与 showEvent 保持一致——
        调试期间真实读取是被暂停的，定时器若空转只会白耗 CPU。
        """
        try:
            if event.type() == QEvent.Type.WindowStateChange:
                if self.isMinimized():
                    self._timer.stop()
                elif (not self._reader.debug_active and not self._timer.isActive()
                      and self.isVisible()):
                    self._timer.start()
        except Exception:
            traceback.print_exc()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        """关闭窗口时停表并显式退出。

        注意：Tool 窗口不参与 Qt 的"最后一个窗口关闭即退出"机制，
        只停表的话 app.exec() 不会返回、python 进程会一直驻留后台，所以这里必须显式 quit()。
        """
        self._timer.stop()
        QApplication.instance().quit()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        """尺寸变化保险：窗口被任何路径拉得比 _max_width 还宽时，强制收回来。

        注意：这里必须用防重入标志——resize() 会再次触发 resizeEvent，
        不加标志就会无限递归调用自己。super() 放在 try 外，避免异常时漏掉基类处理。
        """
        super().resizeEvent(event)
        try:
            # 尺寸一变，圆角遮罩也要跟着重算；否则不透明模式下四角会露出旧尺寸的底色
            self._apply_round_mask()
            if not self._fixing_size and self.width() > self._max_width:
                # 防止任何路径把窗口拉成横跨屏幕的长条；尺寸同样走 _clamp_width()
                fixed_w = self._clamp_width(self._max_width)
                self._fixing_size = True
                try:
                    self.resize(fixed_w, self.heightForWidth(fixed_w))
                finally:
                    self._fixing_size = False
        except Exception:
            traceback.print_exc()

    def _screen_for_window(self):
        """返回"窗口中心所在"的那块屏幕，用于尺寸变化后的位置钳制。

        注意：不要用 self.screen()——窗口跨在两屏之间时它会飘，
        导致缩放或切换模式时窗口被错误地"弹"回另一块屏。
        取不到中心所在屏幕时退回鼠标所在屏幕，再退回主屏。
        """
        center = self.frameGeometry().center()
        screen = QApplication.screenAt(center)
        if screen is not None:
            return screen
        screen = QApplication.screenAt(QCursor.pos())
        if screen is not None:
            return screen
        return QApplication.primaryScreen()

    def _keep_on_screen(self) -> None:
        """把窗口钳制回屏幕可用区域，保证窗口左上角可见、不跑到屏幕外。

        注意：只在越界时收回，不做居中之类的主动移动。
        用窗口中心所在的屏幕做钳制目标，避免跨屏时被错误地拉回另一块屏。
        拖动分支不调用它（拖动过程不钳制），这里只服务于"改变尺寸后可能被顶出屏幕"的场景。
        """
        try:
            screen = self._screen_for_window()
            if screen is None:
                return
            area = screen.availableGeometry()
            width = self._clamp_width(self.width())
            x = min(max(self.x(), area.left()), area.right() - width)
            y = min(max(self.y(), area.top()), area.bottom() - self.height())
            self.move(max(area.left(), x), max(area.top(), y))
        except Exception:
            # 混合 DPI 下屏幕几何偶尔会出现异常值；这里兜住，避免缩放/切换模式时直接把进程带崩
            traceback.print_exc()

    def _ensure_reachable(self) -> None:
        """确保窗口至少有一块足够大的区域留在某块屏幕上，防止完全跑出屏幕后找不回来。

        注意：必须逐块屏幕判断是否有交集，不能用"所有屏幕的并集包围盒"——
        多显示器并集里可能包含不属于任何屏幕的空洞（分辨率不同、上下错位、屏幕间有间隙），
        窗口会被判成"可见"而实际已经掉进洞里、完全消失。

        当前状态：**已停用（不再被调用）**。混合 DPI 环境下逻辑坐标与物理坐标不一致，
        用坐标做"救援"反而会把窗口搬到同样看不见的位置；增量拖动已经保证不会跳飞，
        因此松开鼠标时只打日志、不做坐标救援。函数保留是为了日后在单 DPI 场景需要时能重新启用。
        """
        win = self.frameGeometry()
        min_visible = 60          # 至少要有 60×60 留在某块屏上，用户才点得到
        for s in QApplication.screens():
            inter = s.availableGeometry().intersected(win)
            if inter.width() >= min_visible and inter.height() >= min_visible:
                return            # 有足够可见区域，不动它
        # 与所有屏幕的交集都不够：移到鼠标所在屏幕的可用区域中央
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.center().y() - self.height() // 2
        self.move(
            max(area.left(), min(x, area.right() - self.width() + 1)),
            max(area.top(), min(y, area.bottom() - self.height() + 1)),
        )

    # ------------------------------------------------------------------ 布局

    def _five_in_row_width(self) -> int:
        """五环排成一排所需的窗口宽度。"""
        return int(5 * self.D_MAX + 4 * self.GAP_MIN + 2 * self.PAD)

    def _clamp_width(self, width: int) -> int:
        """把宽度统一钳制到 [MIN_WIDTH, _max_width]，任何入口都先过这一道。

        好处：无论调用方传进来 0、负数、3840 还是旧的超宽值，环都只会在
        "一排 364"以内铺满，不会出现两侧留白或算错位置。
        """
        return int(max(self.MIN_WIDTH, min(self._max_width, width)))

    def _ring_grid(self, width: int):
        """根据窗口宽度决定排列方式，返回 (行数, 环直径)。

        规则（已与用户确认）：优先一排 5 个；放不下时改为 2×2+1 三行排列，顺序不变。
        环直径始终限制在 [D_MIN, D_MAX] 之间，绝不为了塞下窗口把环缩到看不清。

        入口先钳制宽度：保证环永远只在"一排 364"以内铺满，不会出现居中留白。
        """
        width = self._clamp_width(width)
        content = max(1, width - 2 * self.PAD)
        # 一排 5 个：需要 5 个环 + 4 个间距
        if content >= 5 * self.D_MIN + 4 * self.GAP_MIN:
            d = min(self.D_MAX, (content - 4 * self.GAP_MIN) / 5.0)
            return 1, max(self.D_MIN, int(d))
        # 放不下则改成 2×2+1：每行最多 2 个（第五个单独一行）
        d = min(self.D_MAX, (content - self.GAP_MIN) / 2.0)
        return 3, max(self.D_MIN, int(d))

    def _ring_positions(self, width: int):
        """计算五个环各自的左上角坐标，返回 [(x, y, d) × 5]，顺序固定为 CPU/内存/GPU/C盘/电池。

        入口先钳制宽度：与 _ring_grid 用同一套宽度口径，避免"用宽宽算位置、用窄窄算直径"的错位。
        """
        width = self._clamp_width(width)
        rows, d = self._ring_grid(width)
        content = width - 2 * self.PAD
        positions = []
        if rows == 1:
            total = 5 * d + 4 * self.GAP_MIN
            x0 = self.PAD + (content - total) / 2.0
            for i in range(5):
                positions.append((x0 + i * (d + self.GAP_MIN), float(self.PAD), d))
        else:
            # 2×2+1：前四个排成 2×2，第五个单独一行居中，顺序不变
            cell_h = d + self.REASON_H
            row_w = 2 * d + self.GAP_MIN
            x0 = self.PAD + (content - row_w) / 2.0
            for idx in range(5):
                if idx < 4:
                    r, c = divmod(idx, 2)
                    x = x0 + c * (d + self.GAP_MIN)
                    y = float(self.PAD + r * (cell_h + self.ROW_GAP))
                else:
                    x = self.PAD + (content - d) / 2.0
                    y = float(self.PAD + 2 * (cell_h + self.ROW_GAP))
                positions.append((x, y, d))
        return positions

    def _block_bottom(self, width: int) -> float:
        """返回环形区/文字列表区的底部 y 坐标。

        两种模式都要能算：绘制时用它给下方文本行定位，点击时用它判定点在哪个文本行上。
        """
        if self._list_mode:
            return float(self.PAD + 5 * self.LIST_ROW_H)
        positions = self._ring_positions(width)
        return max(y + d + self.REASON_H for (_x, y, d) in positions)

    def heightForWidth(self, width: int) -> int:
        """根据宽度与当前模式计算窗口高度，保证内容不被裁切、切换模式时不跳动。

        入口先钳制宽度：防止外界传进 0、负数、3840 之类的极端值，导致算高时崩掉或错位。

        注意：文本行折叠后仍占一行（只留标题），所以这里固定按两行计算，
        高度不随折叠变化——折叠只隐藏内容，不会让窗口高度抖一下。
        """
        width = self._clamp_width(width)
        if self._list_mode:
            block_h = 5 * self.LIST_ROW_H
        else:
            rows, d = self._ring_grid(width)
            cell_h = d + self.REASON_H
            block_h = rows * cell_h + (rows - 1) * self.ROW_GAP
        return int(
            self.PAD
            + block_h
            + self.SECTION_GAP
            + 2 * self.TEXT_H
            + self.SECTION_GAP
            + self.VERSION_H
            + self.PAD
        )

    # ------------------------------------------------------------------ 绘制

    def paintEvent(self, event) -> None:
        """只做轻量绘制：不读系统信息、不扫文件、不做哈希、不发网络请求。

        按当前模式二选一：环形模式画五环（绝不含数字），文字模式画五行"名称+百分比"。
        注意：PyQt6 里绘制函数抛未捕获异常会直接终止进程，因此整段包 try/except，
        并用 finally 保证 painter.end() 一定被调用（否则可能残留绘制状态）。
        """
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            self._draw_background(painter)

            block_bottom = self._block_bottom(self.width())
            if self._list_mode:
                self._draw_list(painter)
            else:
                for item, (x, y, d) in zip(self._reader.items, self._ring_positions(self.width())):
                    self._draw_ring_item(painter, item, x, y, d)
            self._draw_text_rows(painter, block_bottom)
            self._draw_gear(painter)
            self._draw_resize_hint(painter)
        except Exception:
            traceback.print_exc()
        finally:
            painter.end()

    def _draw_list(self, painter: QPainter) -> None:
        """文字模式：逐行显示"名称 + 百分比"；失败项显示"名称 + 原因"，不显示百分比。

        注意：百分比数字只允许出现在文字模式；环形模式绝不能出现任何数字。
        """
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        y = float(self.PAD)
        for item in self._reader.items:
            if item.is_ok:
                painter.setPen(QColor(200, 205, 212))
                text = f"{item.name}：{int(round(item.value or 0.0))}%"
            else:
                painter.setPen(COLOR_RED)
                text = f"{item.name}：{item.reason or '读取失败'}"
            painter.drawText(
                QRectF(self.PAD, y, self.width() - 2 * self.PAD, self.LIST_ROW_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            y += self.LIST_ROW_H

    def _draw_background(self, painter: QPainter) -> None:
        """绘制圆角背景：半透明可用时用深色半透明，不可用时用系统着色/固定深灰兜底。

        注意：矩形必须覆盖整个 self.rect()，不能内缩 0.5 像素——
        内缩会留下 1 像素未绘制的边，在部分系统上表现为一圈细白条。
        圆角本身由 drawRoundedRect 负责；不透明模式下四角由窗口遮罩裁掉（见 _apply_round_mask）。
        """
        rect = QRectF(self.rect())
        if self._translucent:
            painter.setBrush(QColor(20, 22, 26, 200))   # 深色半透明圆角背景
        else:
            painter.setBrush(self._bg_color)            # 不透明兜底，杜绝黑底/白条
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 12, 12)

    def _apply_round_mask(self) -> None:
        """半透明不可用时，用窗口遮罩裁出圆角。

        注意：不透明窗口没法用 alpha 做圆角，四角会露出系统默认底色（常见就是白角/黑角），
        看起来像"白条"。这里用 QRegion 遮罩把四角裁掉，既保留圆角外观，也不会露出底色。
        半透明模式不用遮罩——遮罩会让圆弧边缘出现锯齿，交给 alpha 处理更平滑。

        注意：setMask 同时裁剪鼠标命中，四角 12px 弧区点不到。当前齿轮按钮、缩放手柄斜线、
        版本号都不在该区域（手柄 6 个端点已确认在遮罩内）；以后往窗口角落加控件时必须避开这 12px 弧区。
        """
        try:
            if self._translucent:
                self.clearMask()
                return
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 12, 12)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        except Exception:
            traceback.print_exc()

    def _apply_native_window_style(self) -> None:
        """用 Win32 API 再确认一次"无边框、无白条、不进 Alt+Tab"的窗口样式。

        注意：
        - 只修改本窗口自己的样式位（hwnd 就是本窗口），不碰系统设置、注册表、任务栏配置；
        - Qt 在正常环境下已设好这些标志，本函数等于兜底（无变化），只有个别系统才真正生效；
          保留它是为了满足"必要时用 Win32 兜底"的需求；
        - GWL_STYLE / GWL_EXSTYLE 是 32 位值，必须用 32 位 API。64 位下 GetWindowLongPtrW
          若不声明 restype 会被 ctypes 按 c_int 截断（0x96000000 会变成负数）；
          HWND 若不声明 argtypes 会被按 c_int 传，句柄超过 2³¹ 直接 OverflowError，
          被外层 except 吞掉后样式静默失效；
        - SetWindowLong 之后必须 SetWindowPos(..., SWP_FRAMECHANGED) 样式才会立即生效。
        """
        try:
            if sys.platform != "win32":
                return
            hwnd = int(self.winId())
            if not hwnd:
                return

            # use_last_error=True 才能让 ctypes.get_last_error() 拿到真实的 Win32 错误码
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_long = user32.GetWindowLongW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = wintypes.LONG
            set_long = user32.SetWindowLongW
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
            set_long.restype = wintypes.LONG
            set_pos = user32.SetWindowPos
            set_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
            set_pos.restype = wintypes.BOOL

            GWL_STYLE, GWL_EXSTYLE = -16, -20
            WS_POPUP, WS_CAPTION, WS_THICKFRAME = 0x80000000, 0x00C00000, 0x00040000
            WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00000080, 0x08000000

            style = get_long(hwnd, GWL_STYLE)
            style = (style | WS_POPUP) & ~WS_CAPTION & ~WS_THICKFRAME
            ex_style = get_long(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            set_long(hwnd, GWL_STYLE, style)
            set_long(hwnd, GWL_EXSTYLE, ex_style)

            SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x0001, 0x0002, 0x0004
            SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x0010, 0x0020
            ok = set_pos(
                hwnd, None, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
            if not ok and DEBUG_LOG:
                print("SetWindowPos failed:", ctypes.get_last_error())
        except Exception:
            traceback.print_exc()

    def _draw_ring_item(self, painter: QPainter, item: ItemData, x: float, y: float, d: int) -> None:
        """绘制单个环：灰色底环 + 低对比度刻度线 + 彩色进度弧（或失败红叉）+ 中心名称。"""
        cx = x + d / 2.0
        cy = y + d / 2.0
        outer = d / 2.0 - 5.0                                  # 外沿留 5 像素给刻度线
        thickness = min(9.0, max(4.0, d * 0.13))               # 环带粗细随直径微调
        r_mid = outer - thickness / 2.0                        # 底环与进度弧的中心半径

        # 1) 灰色底环：始终绘制，作为"空环"的视觉基础
        painter.setPen(QPen(QColor(255, 255, 255, 38), thickness))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r_mid, r_mid)

        # 2) 低对比度刻度线：只画短线，绝不允许出现任何数字标签
        painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
        step = 360.0 / self.TICKS
        for i in range(self.TICKS):
            ang = math.radians(90.0 - i * step)
            dx, dy = math.cos(ang), -math.sin(ang)              # 屏幕坐标 y 向下，故取负
            painter.drawLine(
                QPointF(cx + dx * (outer + 1.5), cy + dy * (outer + 1.5)),
                QPointF(cx + dx * (outer + 4.5), cy + dy * (outer + 4.5)),
            )

        # 3) 进度弧（从正上方开始、顺时针增长）或失败红叉
        if item.is_ok:
            painter.setPen(
                QPen(_value_color(item), thickness,
                     Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            rect = QRectF(cx - r_mid, cy - r_mid, 2 * r_mid, 2 * r_mid)
            # QPainter 角度单位是 1/16 度；90*16 表示从正上方起算，负跨度表示顺时针
            span = -int(round((item.value or 0.0) / 100.0 * 360 * 16))
            if span != 0:
                painter.drawArc(rect, 90 * 16, span)
        else:
            self._draw_fail_cross(painter, cx, cy, outer, thickness)

        # 4) 环中心只显示项目名称：环形区域内不得出现任何数字字符
        painter.setPen(QColor(230, 233, 238))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(QRectF(x, y, d, d), Qt.AlignmentFlag.AlignCenter, item.name)

        # 5) 失败原因显示在环下方；正常项不显示
        if not item.is_ok:
            painter.setPen(COLOR_RED)
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(
                QRectF(x, y + d, d, self.REASON_H),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                item.reason or "读取失败",
            )

    def _draw_fail_cross(self, painter: QPainter, cx: float, cy: float,
                         outer: float, thickness: float) -> None:
        """绘制失败红叉：只覆盖环形区域，绝不盖住中心文字（总需求第八条）。

        做法：把"外圆减去内圆"的路径设为裁剪区，再画两条对角线；
        这样红叉只会落在环带范围内，中心的项目名称始终可读。
        """
        cross_inner = max(14.0, outer * 0.5)          # 内圈半径：保证与中心文字留出安全距离
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), outer, outer)
        hole = QPainterPath()
        hole.addEllipse(QPointF(cx, cy), cross_inner, cross_inner)

        painter.save()
        painter.setClipPath(clip.subtracted(hole), Qt.ClipOperation.ReplaceClip)
        painter.setPen(QPen(COLOR_RED, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        reach = outer * 0.95                          # 端点略超出圆外，由裁剪路径裁成圆弧内
        painter.drawLine(QPointF(cx - reach, cy - reach), QPointF(cx + reach, cy + reach))
        painter.drawLine(QPointF(cx - reach, cy + reach), QPointF(cx + reach, cy - reach))
        painter.restore()

    def _draw_text_rows(self, painter: QPainter, block_bottom: float) -> None:
        """绘制环形/列表下方两个文本行与版本号。

        文本行始终显示、不参与环形/文字切换；读取失败时只显示"读取失败"，不画红叉。
        折叠后只保留标题（内容隐藏），行本身仍占位，因此窗口高度不随折叠变化。
        """
        y = block_bottom + self.SECTION_GAP
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(200, 205, 212))
        # (标题, 完整内容, 是否已折叠)
        rows = (
            ("开机时长", self._reader.boot_text, self._boot_collapsed),
            ("系统版本", self._reader.os_text, self._os_collapsed),
        )
        for title, full_text, collapsed in rows:
            painter.drawText(
                QRectF(self.PAD, y, self.width() - 2 * self.PAD, self.TEXT_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title if collapsed else full_text,
            )
            y += self.TEXT_H

        # 版本号用界面文字显示，不弹窗（总需求第十三条）
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QColor(140, 145, 155))
        painter.drawText(
            # 右侧依次减去缩放热区和齿轮按钮的宽度：两者都在右下角，不减就会被压住
            QRectF(self.PAD, self.height() - self.PAD - self.VERSION_H,
                   self.width() - 2 * self.PAD - self.RESIZE_HOT - self.GEAR_SIZE - 4,
                   self.VERSION_H),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"版本 {APP_VERSION}",
        )

    def _gear_rect(self) -> QRectF:
        """小齿轮按钮的矩形。

        注意：绘制与鼠标命中共用这一个矩形（和缩放手柄同一原则），
        并且刻意放在缩放热区左侧，避免和右下角缩放手柄抢同一块区域。
        """
        return QRectF(
            float(self.width() - self.PAD - self.RESIZE_HOT - self.GEAR_SIZE),
            float(self.height() - self.PAD - self.GEAR_SIZE),
            float(self.GEAR_SIZE),
            float(self.GEAR_SIZE),
        )

    def _draw_gear(self, painter: QPainter) -> None:
        """用 QPainter 画小齿轮（圆环 + 8 根齿），始终显示、不参与环形/文字切换。

        说明：不引入图标文件或第三方资源，纯矢量绘制，缩放不糊。
        """
        rect = self._gear_rect()
        center = rect.center()
        radius = rect.width() / 2.0
        inner = radius * 0.62
        painter.save()
        painter.setPen(QPen(QColor(200, 205, 212), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, inner, inner)
        for i in range(8):
            ang = math.radians(i * 45.0)
            dx, dy = math.cos(ang), math.sin(ang)
            painter.drawLine(
                QPointF(center.x() + dx * inner, center.y() + dy * inner),
                QPointF(center.x() + dx * radius, center.y() + dy * radius),
            )
        painter.restore()

    def _resize_hot_rect(self) -> QRectF:
        """返回窗口右下角的缩放热区矩形。

        注意：绘制手柄与鼠标命中判定必须共用这一个矩形——
        如果两边各算各的，就会出现"手柄看得见、鼠标点不中"的问题。
        """
        return QRectF(
            float(self.width() - self.RESIZE_HOT),
            float(self.height() - self.RESIZE_HOT),
            float(self.RESIZE_HOT),
            float(self.RESIZE_HOT),
        )

    def _draw_resize_hint(self, painter: QPainter) -> None:
        """在缩放热区里画标准的右下角缩放手柄（三条 45° 平行斜线）。

        每条线都从"底边上某点"连到"右边上对应点"，越靠外的线越长，整体贴着热区右下角，
        看起来才像缩放柄，而不是偏在一边的小三角。
        注意：三条线必须全部落在 _resize_hot_rect() 内、并且右下角对齐，
        这样才能保证"看得见的斜线区域 = 点得中的热区"。
        """
        rect = self._resize_hot_rect().adjusted(3, 3, -3, -3)   # 内缩 3 像素，线条不贴边
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        for k in (5, 10, 15):
            painter.drawLine(
                QPointF(rect.right() - k, rect.bottom()),
                QPointF(rect.right(), rect.bottom() - k),
            )

    # ------------------------------------------------------------------ 鼠标交互

    def mousePressEvent(self, event) -> None:
        """左键按下：右下角热区调整宽度，其余区域既可能拖动窗口、也可能是"点击切换"。

        注意：这里不能立刻执行切换动作——按下就切换的话，拖动窗口时会被误触发，
        因此只记录"候选动作"，等到松开时再判断这次到底是点击还是拖动。
        """
        try:
            if DEBUG_LOG:
                print(f"[press] pos=({event.position().x():.0f},{event.position().y():.0f}) "
                      f"dpr={self.devicePixelRatioF():.2f}")
            if event.button() != Qt.MouseButton.LeftButton:
                return
            pos = event.position()
            self._press_pos = pos
            self._moved = False
            self._pending_action = None
            # 命中判定与 _draw_resize_hint() 共用同一个矩形，保证"看得见"就"点得中"
            if self._resize_hot_rect().contains(pos):
                self._resizing = True
                self._resize_start_x = event.globalPosition().x()
                self._resize_start_w = self.width()
                return
            self._dragging = True
            # 记录按下时的全局鼠标位置，后续拖动只累加相邻两次位置的差值
            self._last_global = event.globalPosition().toPoint()
            self._pending_action = self._hit_action(pos)
        except Exception:
            # PyQt6 里事件处理函数抛未捕获异常会直接终止进程，表现就是"窗口闪一下消失"
            traceback.print_exc()

    def mouseMoveEvent(self, event) -> None:
        """鼠标移动：悬停时换光标做提示，按住时缩放宽度或拖动窗口。"""
        try:
            # 光标提示：窗口无边框、手柄又很小，靠光标变化告诉用户"这里可以拖大小"。
            # 注意只在没有按住鼠标时改光标——否则拖动途中会不停 unsetCursor，
            # 让斜向双箭头半路闪回默认箭头。这里不 return，继续走下面的缩放/拖动逻辑。
            if not self._resizing and not self._dragging:
                if self._gear_rect().contains(event.position()):
                    # 齿轮是"按钮"，用小手光标提示可点击（优先级高于缩放手柄的斜箭头）
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                elif self._resize_hot_rect().contains(event.position()):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                else:
                    self.unsetCursor()
            if self._resizing:
                delta = event.globalPosition().x() - self._resize_start_x
                new_w = self._clamp_width(int(self._resize_start_w + delta))
                self.resize(new_w, self.heightForWidth(new_w))
                # 缩窄会切到 2×2+1 三行布局、高度向下长，
                # 可能把文本行 / 版本号 / 缩放手柄推出屏幕底部，所以这里收回一次
                self._keep_on_screen()
                return
            if not self._dragging:
                return
            if not self._moved:
                moved = event.position() - self._press_pos
                if abs(moved.x()) + abs(moved.y()) > self.CLICK_SLOP:
                    self._moved = True        # 位移超过阈值：判定为拖动，本次不再执行点击动作
                    if DEBUG_LOG:
                        print(f"[drag] 开始 pos=({self.x()},{self.y()}) "
                              f"dpr={self.devicePixelRatioF():.2f}")
            if not self._moved or self._last_global is None:
                return
            # 必须用增量位移，而不是"固定 offset + 绝对定位"：
            # 窗口跨到 DPI 比例不同的屏幕时，Qt 会按比例重算逻辑坐标，
            # 绝对定位会算出极远坐标、导致窗口跳飞（现象就是闪一下后消失）。
            cur = event.globalPosition().toPoint()
            delta = cur - self._last_global
            self._last_global = cur          # 先更新基准：即使这一帧被丢弃，位移也不会累积成下一次跳跃
            target = self.pos() + delta
            # 混合 DPI 下这里只判断"是否允许这一帧位移"，不搬窗口、不做坐标换算，
            # 避免再次出现跨屏坐标错乱；判断标准是目标位置仍与某块屏幕有足够交集。
            if self._target_still_visible(target):
                self.move(target)
        except Exception:
            # PyQt6 里事件处理函数抛未捕获异常会直接终止进程，表现就是"窗口闪一下消失"
            traceback.print_exc()

    def _target_still_visible(self, target) -> bool:
        """目标位置是否仍与某块屏幕有 ≥60×60 的交集（逐屏判断，不用并集包围盒，不做坐标换算）。

        注意：不能用"所有屏幕的并集包围盒"——并集里可能包含不属于任何屏幕的空洞；
        也不能在这里调用 move()/换算坐标，混合 DPI 下那样会把窗口搬到看不见的位置。
        这里只回答一个问题：这一帧的位移允不允许应用。
        """
        try:
            rect = QRectF(target.x(), target.y(), self.width(), self.height())
            for s in QApplication.screens():
                inter = QRectF(s.availableGeometry()).intersected(rect)
                if inter.width() >= 60 and inter.height() >= 60:
                    return True
            return False
        except Exception:
            traceback.print_exc()
            return True       # 判断本身出错时放行，宁可让用户能拖动，也不要卡死窗口

    def mouseReleaseEvent(self, event) -> None:
        """松开左键：若全程没有移动，就按一次"点击"处理，否则只结束拖动/缩放。"""
        try:
            # 不判按键时，左键按住期间松开右键会误执行待定的模式切换
            if event.button() != Qt.MouseButton.LeftButton:
                return
            if self._dragging and not self._moved and self._pending_action is not None:
                self._apply_action(self._pending_action)
            if self._dragging:
                # 混合 DPI 下逻辑坐标与物理坐标不一致，坐标救援会把窗口搬到看不见的位置，
                # 所以这里不做坐标救援；拖动途中已用 _target_still_visible() 逐帧把关，
                # 保证窗口始终留有足够可见区域。
                if DEBUG_LOG:
                    screen = self.screen()
                    print(f"[drag] 结束 pos=({self.x()},{self.y()}) "
                          f"size={self.width()}x{self.height()} "
                          f"screen={screen.name() if screen else 'None'} "
                          f"dpr={self.devicePixelRatioF():.2f}")
            self._dragging = False
            self._resizing = False
            self._pending_action = None
        except Exception:
            # PyQt6 里事件处理函数抛未捕获异常会直接终止进程，表现就是"窗口闪一下消失"
            traceback.print_exc()

    def _hit_action(self, pos):
        """判断按下的位置落在哪个可点击区域，返回动作名；不属于任何区域则返回 None。

        可点击区域有三类：
        0) 右下角小齿轮 → 打开"设置与调试"窗口（不参与环形/文字切换）；
        1) 五环（环形模式）或五行列表（文字模式）→ 切换显示模式；
        2) 下方"开机时长""系统版本"两行 → 折叠或展开该行内容。
        注意：齿轮判断必须放在最前面，保证点齿轮永远不会误触发模式切换。
        """
        width = self.width()
        if self._gear_rect().contains(QPointF(pos.x(), pos.y())):
            return "settings"
        if self._list_mode:
            if (self.PAD <= pos.x() <= width - self.PAD
                    and self.PAD <= pos.y() <= self.PAD + 5 * self.LIST_ROW_H):
                return "mode"
        else:
            for (x, y, d) in self._ring_positions(width):
                if x <= pos.x() <= x + d and y <= pos.y() <= y + d + self.REASON_H:
                    return "mode"
        block_bottom = self._block_bottom(width)
        text_top = block_bottom + self.SECTION_GAP
        if self.PAD <= pos.x() <= width - self.PAD:
            if text_top <= pos.y() <= text_top + self.TEXT_H:
                return "boot"
            if text_top + self.TEXT_H <= pos.y() <= text_top + 2 * self.TEXT_H:
                return "os"
        return None

    def _apply_action(self, action) -> None:
        """执行一次点击动作：打开设置窗口、切换环形/文字模式，或折叠某个文本行。

        注意：切换后一次性把窗口高度改成新内容所需的高度，只调用一次 resize，
        避免出现"先矮后高"的闪动或白条。打开设置窗口不改变主窗口尺寸。
        """
        if action == "settings":
            self._open_settings()
            return
        if action == "mode":
            self._list_mode = not self._list_mode
        elif action == "boot":
            self._boot_collapsed = not self._boot_collapsed
        elif action == "os":
            self._os_collapsed = not self._os_collapsed
        else:
            return
        # 宽度统一钳制：避免任何路径沿用旧的超宽值，把窗口拉成长条
        w = self._clamp_width(self.width())
        self.resize(w, self.heightForWidth(w))
        self.update()
        self._keep_on_screen()            # 高度变化后可能顶出屏幕底部，这里收回来

    def _open_settings(self) -> None:
        """打开"设置与调试"窗口（懒创建一次，后续复用同一实例）。

        注意：复用实例可以避免反复新建窗口导致对象累积；
        每次显示时设置窗口自己会把调试模式复位为关闭。
        """
        try:
            if self._settings is None:
                # 作者与仓库地址统一来自本文件顶部常量，避免在设置窗口里再定义一份
                self._settings = SettingsWindow(
                    self._reader, self, APP_VERSION,
                    repo_url=APP_REPO_URL, author=APP_AUTHOR,
                )
            self._settings.show()
            self._settings.raise_()
            self._settings.activateWindow()
        except Exception:
            traceback.print_exc()

    def contextMenuEvent(self, event) -> None:
        """右键菜单：本窗口唯一的退出入口。

        注意：窗口无边框、不进任务栏、且设置了不接受焦点，
        所以既没有关闭按钮、Alt+F4 也对它无效，必须提供右键菜单才能退出。
        菜单对象在 __init__ 里只创建一次并复用，避免每次右键都新建一个子对象。
        """
        try:
            self._menu.exec(event.globalPos())
        except Exception:
            # 同上：事件处理函数异常不能让它把进程带崩
            traceback.print_exc()


def main() -> int:
    """程序入口：创建应用、显示主面板并进入事件循环。"""
    app = QApplication(sys.argv)
    reader = SystemReader()
    panel = VitalPanel(reader)
    # 默认放到屏幕右上角（第二阶段再做任务栏左侧空白区域的自动吸附定位）
    screen = app.primaryScreen().availableGeometry()
    panel.move(screen.right() - panel.width() - 20, screen.top() + 20)
    panel.show()
    # show() 会同步触发 showEvent，而 showEvent 内部已经调用 _on_refresh_tick() 做首次刷新，
    # 因此这里不再重复读一次数据。注意：这也意味着读取耗时会计入"窗口出现"的时间；
    # 若以后确实需要"先出窗口再读数"，可改为 QTimer.singleShot(0, panel._on_refresh_tick) 延迟执行。
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
