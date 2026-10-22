# -*- coding: utf-8 -*-
"""VitalsRing（环脉）"设置与调试"窗口 —— 第一阶段第 3 轮起，第 5、6 轮扩展。

职责：界面模式、调试模式与各项调试值、各项检测开关、挂件槽位、外观、任务栏吸附、
     设置锁、恢复默认设置、GitHub 按钮与「关于 / 制作人员」区。
约定：
- 只用 PyQt6 自带控件，不引入任何第三方库；
- 本窗口不创建任何定时器，关闭后不留刷新任务（刷新仍由主窗口那唯一的定时器负责）；
- 调试值不持久化：关闭窗口时清空，重新打开一律回到"调试模式关闭"。
- 第 4 轮：补充『关于』区与真实仓库地址。
- 第二阶段：补充"自动吸附到任务栏"开关与定位状态提示。
- 第 5 轮：设置锁（JSON 持久化）、恢复默认设置淡入淡出动画、动态磁盘槽位。
- 第 6 轮：五槽位全可配、调试项适配动态磁盘、两个恢复按钮加图标、制作人员署名。
- 第 7 轮：外观分组新增「使用拟物化图标」开关，与刻度开关一样受设置锁控制。
- 第 7 轮完全体：新增「图标风格」下拉（多色拟物 / 单色线条），受锁持久化。
"""
from __future__ import annotations

import traceback

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRect, QRectF, QSize,
    Qt, QTimer, QUrl, pyqtProperty, pyqtSignal,
)
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# 预留：配置成真实仓库地址后，"打开 GitHub 仓库"按钮才会真正跳转。
# 注意：仓库地址统一由 main.py 的 APP_REPO_URL 提供并通过构造函数传入，
# 这里不再保留第二个 GITHUB_REPO_URL 常量，避免两处地址不一致。


# 第 7 轮定稿：现代深色 QSS。QSS 不支持 box-shadow，
# 卡片阴影统一用 QGraphicsDropShadowEffect 实现（见 _apply_card_shadow）。
SETTINGS_QSS = """
QDialog { background-color: #0d1117; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
#settingsContent { background-color: #0d1117; }
#settingsTitleBar {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
}
#debugRowsCard {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
}
QGroupBox {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #e6edf3;
    background-color: #161b22;
}
QLabel { color: #c9d1d9; }
QComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 5px 26px 5px 10px;
    color: #e6edf3;
    min-height: 22px;
}
QComboBox:hover { border-color: #58a6ff; }
QComboBox:disabled { color: #6e7681; border-color: #21262d; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
    color: #e6edf3;
    outline: 0;
}
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 4px 10px;
    color: #e6edf3;
}
QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
QPushButton:pressed { background-color: #161b22; }
QPushButton:disabled { color: #6e7681; background-color: #161b22; border-color: #21262d; }
QToolButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 16px;
}
QToolButton:hover { background-color: #30363d; }
QRadioButton { color: #c9d1d9; spacing: 8px; }
QRadioButton::indicator {
    width: 16px; height: 16px;
    border: 2px solid #30363d;
    border-radius: 9px;
    background-color: transparent;
}
QRadioButton::indicator:hover {
    border-color: #8b949e;
}
QRadioButton::indicator:checked {
    border: none;
    background-color: #3b82f6;
    border-radius: 8px;
}
QSlider::groove:horizontal { height: 4px; background: #30363d; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #58a6ff; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: #f0f6fc; border: 1px solid #8b949e;
}
QSlider::handle:horizontal:hover {
    background: #ffffff; border-color: #58a6ff;
}
QSlider::handle:horizontal:pressed {
    background: #3b82f6; border-color: #ffffff;
}
QSpinBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 3px 6px;
    color: #e6edf3;
}
QSpinBox:hover, QSpinBox:focus {
    border-color: #58a6ff;
    background-color: #0d1117;
}
QScrollBar:vertical { background: #0d1117; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #30363d; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class ToggleSwitch(QWidget):
    """iOS 风格滑动开关：自绘圆角轨道 + 白色圆点 + 160ms 平滑动画。

    保留 QCheckBox 的常用接口（setChecked / isChecked / toggled / blockSignals），
    这样设置窗口原有的同步逻辑不用重写。
    """

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checked = False
        self._knob = 0.0
        self._stretch = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        # 0.10.07.13：位移 250ms OutExpo；拉伸回弹用 InExpo，末段瞬间收回正圆
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._stretch_anim = QPropertyAnimation(self, b"stretch", self)
        self._stretch_anim.setDuration(250)
        self._stretch_anim.setEasingCurve(QEasingCurve.Type.InExpo)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _get_knob(self):
        return self._knob

    def _set_knob(self, value):
        # OutExpo 无过冲；夹在 ±0.12 内，避免极端情况下甩出轨道
        self._knob = max(-0.12, min(1.12, float(value)))
        self.update()

    knob = pyqtProperty(float, _get_knob, _set_knob)

    def _get_stretch(self):
        return self._stretch

    def _set_stretch(self, value):
        self._stretch = max(0.0, min(1.0, float(value)))
        self.update()

    stretch = pyqtProperty(float, _get_stretch, _set_stretch)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._anim.stop()
        self._stretch_anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()
        # 挤压拉伸：开始瞬间 1.0，250ms 内收回 0.0（InExpo 让末段快速回弹）
        self._stretch = 1.0
        self._stretch_anim.setStartValue(1.0)
        self._stretch_anim.setEndValue(0.0)
        self._stretch_anim.start()
        self.toggled.emit(checked)

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if not self.isEnabled():
                track = QColor("#21262d")
            elif self._checked:
                track = QColor("#3b82f6")
            else:
                track = QColor("#30363d")
            painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(1, 1, 42, 22), 11, 11)
            # iOS 挤压拉伸：_stretch=1 时圆点变宽变扁，0 时回正圆
            knob_d = 18.0
            knob_w = knob_d * (1.0 + self._stretch * 0.35)
            knob_h = knob_d / (1.0 + self._stretch * 0.25)
            x = 2.0 + self._knob * (44.0 - 4.0 - knob_w)
            y = (24.0 - knob_h) / 2.0
            center = QPointF(x + knob_w / 2.0, y + knob_h / 2.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 60))
            painter.drawEllipse(QPointF(center.x() + 0.6, center.y() + 1.0),
                                knob_w / 2.0, knob_h / 2.0)
            painter.setBrush(QColor("#f0f6fc"))
            painter.drawEllipse(center, knob_w / 2.0, knob_h / 2.0)
        except Exception:
            traceback.print_exc()
        finally:
            painter.end()

    def mouseReleaseEvent(self, event) -> None:
        try:
            if (self.isEnabled()
                    and event.button() == Qt.MouseButton.LeftButton):
                self.toggle()
        except Exception:
            traceback.print_exc()

    def keyPressEvent(self, event) -> None:
        try:
            if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return,
                               Qt.Key.Key_Enter):
                self.toggle()
                return
        except Exception:
            traceback.print_exc()
        super().keyPressEvent(event)


class ToggleRow(QWidget):
    """滑动开关 + 文案的一行；对外保持 QCheckBox 的常用接口。"""

    toggled = pyqtSignal(bool)

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._toggle = ToggleSwitch()
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        layout.addWidget(self._toggle)
        layout.addWidget(self._label, 1)
        self._toggle.toggled.connect(self.toggled.emit)

    def setChecked(self, checked: bool) -> None:
        self._toggle.setChecked(checked)

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def blockSignals(self, block: bool) -> bool:
        # 必须同时屏蔽子开关，否则父行被 block 后子信号仍会发出去
        result = super().blockSignals(block)
        self._toggle.blockSignals(block)
        return result

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._toggle.setEnabled(enabled)
        self._label.setEnabled(enabled)

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self._toggle.setToolTip(text)
        self._label.setToolTip(text)

    def mouseReleaseEvent(self, event) -> None:
        try:
            # 点在开关本身上时由 ToggleSwitch 自己处理，避免双击式反向切换
            if self._toggle.geometry().contains(event.position().toPoint()):
                return
            if (self.isEnabled()
                    and event.button() == Qt.MouseButton.LeftButton):
                self._toggle.toggle()
        except Exception:
            traceback.print_exc()


class ModernComboBox(QComboBox):
    """无系统凸起边框的下拉框：QSS 隐藏原生箭头，右侧自绘极简 ▾。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(30)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QColor("#8C919B"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(
                QRectF(self.width() - 24, 0, 18, self.height()),
                Qt.AlignmentFlag.AlignCenter, "▾")
        except Exception:
            traceback.print_exc()
        finally:
            painter.end()


class SmoothSlider(QSlider):
    """跟手滑块：手柄拖动实时更新；点击轨道用 100ms OutCubic 平滑到目标值。"""

    def __init__(self, orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setTracking(True)
        self._click_anim = None

    def mousePressEvent(self, event) -> None:
        try:
            if event.button() != Qt.MouseButton.LeftButton:
                super().mousePressEvent(event)
                return
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt,
                QStyle.SubControl.SC_SliderHandle, self)
            if handle.contains(event.position().toPoint()):
                # 按在手柄上：交给原生拖动，setTracking(True) 保证实时跟手
                super().mousePressEvent(event)
                return
            # 点击轨道：不要瞬间跳值，100ms OutCubic 平滑过去
            target = self.style().sliderValueFromPosition(
                self.minimum(), self.maximum(),
                int(event.position().x()), self.width())
            if self._click_anim is not None:
                self._click_anim.stop()
            anim = QPropertyAnimation(self, b"value", self)
            anim.setDuration(100)
            anim.setStartValue(self.value())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._click_anim = anim
            anim.start()
            event.accept()
        except Exception:
            traceback.print_exc()

class TitleBar(QWidget):
    """0.10.07.19 无边框设置窗口的自绘标题栏：深色背景 + 标题 + 关闭按钮 + 拖动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)
        self._drag_offset = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)
        self._title = QLabel("设置与调试")
        self._title.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._title.setStyleSheet(
            "color: #e6edf3; font-size: 13px; font-weight: 600; background: transparent;")
        layout.addWidget(self._title, 1)
        self._close_btn = QToolButton()
        self._close_btn.setText("×")
        self._close_btn.setToolTip("关闭")
        self._close_btn.setFixedSize(32, 26)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; color: #c9d1d9; font-size: 18px; }"
            "QToolButton:hover { background-color: #30363d; border-radius: 4px; }"
            "QToolButton:pressed { background-color: #21262d; }")
        self._close_btn.clicked.connect(self._on_close)
        layout.addWidget(self._close_btn)

    def _on_close(self) -> None:
        try:
            win = self.window()
            if win is not None:
                win.close()
        except Exception:
            traceback.print_exc()

    def mousePressEvent(self, event) -> None:
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.window().pos())
                event.accept()
                return
        except Exception:
            traceback.print_exc()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        try:
            if (self._drag_offset is not None
                    and event.buttons() & Qt.MouseButton.LeftButton):
                self.window().move(
                    event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return
        except Exception:
            traceback.print_exc()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            self._drag_offset = None
            event.accept()
            return
        except Exception:
            traceback.print_exc()
        super().mouseReleaseEvent(event)


class SettingsWindow(QDialog):
    """设置与调试窗口。

    注意：关闭（X / Esc）时必须复位调试状态并让主窗口恢复真实数据刷新，
    所以复位逻辑写成幂等的 _reset_on_close()，closeEvent 和 reject() 都会调用。
    """

    def __init__(self, reader, panel, app_version: str,
                 repo_url: str = "", author: str = "",
                 auto_dock_available: bool = True, credits=None) -> None:
        super().__init__(panel)
        # 0.10.07.19：无边框 + 自绘标题栏，彻底去掉系统标题栏与 DWM 阴影/不可见边框
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._reader = reader
        self._panel = panel
        self._app_version = app_version
        self._repo_url = repo_url
        self._author = author
        self._auto_dock_available = auto_dock_available
        # 制作人员署名由 main.CREDITS 通过构造函数传入，避免两处维护同一份名单
        self._credits = list(credits or [])

        self.setWindowTitle("设置与调试")
        self.setMinimumWidth(640)
        # 第 7 轮定稿：现代深色 QSS（卡片、无边框下拉、圆角按钮、滑动开关）
        self.setStyleSheet(SETTINGS_QSS)

        # 内容整体放进滚动区：设置窗口内容很高（约 800+ px），
        # 1080p + 150% 缩放时逻辑可用高度只有约 720 px，不限制会被 Windows 摆到奇怪位置、
        # 甚至压住任务栏上的挂件。这里限制最大高度并允许滚动，保证低分辨率也能完整操作。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._title_bar = TitleBar(self)
        outer.addWidget(self._title_bar)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll, 1)
        content = QWidget()
        content.setObjectName("settingsContent")
        self._scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 建立淡入淡出动画用的对象（懒创建）；重置时对内容区做 200ms + 200ms 过渡
        self._fade_effect = None
        self._fade_anim = None
        self._open_anim = None
        self._open_geom_anim = None
        self._open_final_geometry = None
        self._open_force_timer = QTimer(self)
        self._open_force_timer.setSingleShot(True)
        self._open_force_timer.timeout.connect(self._force_open_animation_end)
        self._button_anims = {}

        # ---- 设置锁（顶部）：锁上才把配置写进 JSON，重启保留 ----
        lock_row = QHBoxLayout()
        self._lock_btn = QToolButton()
        self._lock_btn.setText("🔓")
        self._lock_btn.setToolTip(
            "锁定设置：重启后保留当前配置；解锁：重启后恢复默认配置")
        self._lock_btn.clicked.connect(self._on_lock_clicked)
        lock_row.addWidget(self._lock_btn)
        lock_hint = QLabel("锁定：修改立即保存，重启保留；"
                           "解锁：仅本次运行生效，重启恢复默认。")
        lock_hint.setStyleSheet("color: #8C919B;")
        lock_hint.setWordWrap(True)
        lock_row.addWidget(lock_hint, 1)
        root.addLayout(lock_row)

        # 第 7 轮 0.10.07.13：左右双列，默认一屏放下
        columns = QHBoxLayout()
        columns.setSpacing(10)
        left_col = QVBoxLayout()
        left_col.setSpacing(8)
        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        columns.addLayout(left_col, 1)
        columns.addLayout(right_col, 1)
        root.addLayout(columns)

        # ---- 界面模式：挂件（默认）/ 大面板，切换立即生效 ----
        mode_box = QGroupBox("🖥️ 界面模式")
        mode_box.setToolTip("切换大面板模式或任务栏挂件模式")
        mode_row = QHBoxLayout(mode_box)
        mode_row.setSpacing(12)
        self._mode_widget = QRadioButton("🖥️ 任务栏挂件模式")
        self._mode_panel = QRadioButton("🖥️ 大面板模式")
        self._mode_widget.setToolTip("切换大面板模式或任务栏挂件模式")
        self._mode_panel.setToolTip("切换大面板模式或任务栏挂件模式")
        self._mode_widget.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_widget)
        mode_group.addButton(self._mode_panel)
        mode_row.addWidget(self._mode_widget)
        mode_row.addWidget(self._mode_panel)
        left_col.addWidget(mode_box)
        self._mode_widget.toggled.connect(self._on_layout_mode_toggled)
        self._mode_panel.toggled.connect(self._on_layout_mode_toggled)

        # ---- 系统信息（只读）：挂件模式下这是唯一能看到开机时长/系统版本的地方 ----
        info_box = QGroupBox("📊 系统信息")
        info_layout = QVBoxLayout(info_box)
        info_layout.setSpacing(8)
        self._boot_info = QLabel("开机时长：读取失败")
        self._os_info = QLabel("系统版本：读取失败")
        info_layout.addWidget(self._boot_info)
        info_layout.addWidget(self._os_info)
        right_col.addWidget(info_box)

        # ---- 调试模式总开关（始终可点击；关闭时子控件全部置灰）----
        debug_box = QGroupBox("🐞 调试")
        debug_row = QHBoxLayout(debug_box)
        debug_row.setSpacing(16)
        self._debug_check = ToggleRow("🐞 调试模式")
        self._debug_check.setToolTip("仅用于测试圆环显示，不保存且关闭设置后失效")
        self._hint_label = QLabel("请先开启调试模式")
        self._hint_label.setStyleSheet("color: #8C919B;")
        debug_row.addWidget(self._debug_check, 1)
        debug_row.addWidget(self._hint_label)
        left_col.addWidget(debug_box)

        # ---- 各项调试值：紧凑双列，每行 [项目][滑块][数值]，默认隐藏 ----
        # 用普通 QWidget 而不是 QGroupBox：QGroupBox 有 title/padding，
        # maximumHeight=0 时仍会留一条，无法做到收起后完全不占高度。
        rows_card = QWidget()
        rows_card.setObjectName("debugRowsCard")
        rows_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rows_card.setMaximumHeight(0)
        rows_card.setVisible(False)
        # 外层只负责 maximumHeight 动画；内层负责 opacity 淡入，避免高度变化时重排
        outer_rows_layout = QVBoxLayout(rows_card)
        outer_rows_layout.setContentsMargins(0, 0, 0, 0)
        outer_rows_layout.setSpacing(0)
        rows_inner = QWidget()
        outer_rows_layout.addWidget(rows_inner)
        rows_layout = QVBoxLayout(rows_inner)
        rows_layout.setContentsMargins(6, 6, 6, 12)
        rows_layout.setSpacing(2)
        rows_title = QLabel("🎚️ 各项调试值（0~100）")
        rows_title.setStyleSheet("color: #C9CED6; font-size: 11px;")
        rows_layout.addWidget(rows_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(0)
        self._sliders = {}
        self._spins = {}
        # 调试项 = 动态数据池里除齿轮外的全部数据项（含 D盘、总盘等新增项）。
        debug_items = [(key, label) for key, label in self._panel.available_slot_items()
                       if key != "gear"]
        debug_icons = {"cpu": "🧠", "gpu": "🎮", "mem": "🧩",
                       "disk_c": "💾", "disk_total": "💽", "battery": "🔋"}
        for idx, (key, label) in enumerate(debug_items):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            name_label = QLabel(f"{debug_icons.get(key, '💽')} {label}")
            name_label.setFixedWidth(46)
            name_label.setStyleSheet("font-size: 11px;")
            slider = SmoothSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setTracking(True)
            slider.setMinimumWidth(60)
            slider.setFixedHeight(22)
            spin = QSpinBox()
            spin.setRange(0, 100)
            # 彻底隐藏原生上下按钮，避免 Windows 深色背景下箭头渲染撕裂
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            # 54px：给数字与内部留白足够空间，避免数字被挤压变形
            spin.setFixedWidth(54)
            spin.setFixedHeight(22)
            row_layout.addWidget(name_label)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(spin)
            row_widget.setFixedHeight(26)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            grid.addWidget(row_widget, idx // 2, idx % 2)
            self._sliders[key] = slider
            self._spins[key] = spin
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        rows_layout.addLayout(grid)

        all_btn_row = QHBoxLayout()
        self._apply_all_btn = QPushButton("应用全部调试值")
        self._restore_all_btn = QPushButton("恢复全部真实值")
        self._apply_all_btn.clicked.connect(self._on_apply_all)
        self._restore_all_btn.clicked.connect(self._on_restore_all)
        self._apply_all_btn.setFixedHeight(28)
        self._restore_all_btn.setFixedHeight(28)
        all_btn_row.addWidget(self._apply_all_btn, 1)
        all_btn_row.addWidget(self._restore_all_btn, 1)
        rows_layout.addLayout(all_btn_row)

        # 内层固定高度：外层 maximumHeight 动画时内容不会被挤压变形
        rows_layout.activate()
        rows_inner.setFixedHeight(max(150, rows_inner.sizeHint().height()))
        self._rows_inner = rows_inner
        # 0.10.07.13：只给 rows_card 外层挂一个 opacity effect；
        # rows_inner 不再挂任何 effect，避免 effect 嵌套导致重影/消失。
        self._rows_effect = QGraphicsOpacityEffect(rows_card)
        self._rows_effect.setOpacity(0.0)
        rows_card.setGraphicsEffect(self._rows_effect)
        self._rows_inner_anim = QPropertyAnimation(
            self._rows_effect, b"opacity", self)
        self._rows_inner_anim.setDuration(250)
        self._rows_inner_anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._rows_opacity_timer = QTimer(self)
        self._rows_opacity_timer.setSingleShot(True)
        self._rows_opacity_timer.timeout.connect(self._start_rows_opacity_in)

        self._rows_box = rows_card
        left_col.addWidget(rows_card)
        # 0.10.07.13：调试卡不再用阴影 effect，只用 QSS 的 border + 背景色

        # 0.10.07.13：高度 0→动态目标 / 动态目标→0，250ms OutExpo
        self._rows_anim = QPropertyAnimation(self._rows_box, b"maximumHeight", self)
        self._rows_anim.setDuration(250)
        self._rows_anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        self._rows_anim.finished.connect(self._on_rows_anim_finished)
        self._rows_force_timer = QTimer(self)
        self._rows_force_timer.setSingleShot(True)
        self._rows_force_timer.timeout.connect(self._force_rows_animation_end)
        self._rows_expanded = False
        # 展开终值不再写死 220：内层固定内容高度 + 12px 上下边距，
        # 调试项变多或不同 DPI 下也不会裁切底部“应用 / 恢复”按钮。
        self._rows_target_height = rows_inner.sizeHint().height() + 12

        # ---- 五项检测开关（默认全开；关闭后主窗口对应环显示红叉 + 检测已关闭）----
        detect_box = QGroupBox("🔍 启用检测")
        detect_grid = QGridLayout(detect_box)
        detect_grid.setHorizontalSpacing(18)
        detect_grid.setVerticalSpacing(8)
        self._detect_checks = {}
        detect_icons = {"cpu": "🧠", "mem": "🧩", "gpu": "🎮",
                        "disk_c": "💾", "battery": "🔋"}
        for idx, item in enumerate(self._reader.items):
            check = ToggleRow(f"{detect_icons.get(item.key, '🔍')} {item.name}")
            check.setToolTip("关闭后该项圆环将显示红叉，用于测试失败状态")
            check.setChecked(self._reader.enabled.get(item.key, True))
            check.toggled.connect(
                lambda checked, k=item.key: self._on_toggle_detect(k, checked))
            detect_grid.addWidget(check, idx // 2, idx % 2)
            self._detect_checks[item.key] = check
        detect_grid.setColumnStretch(0, 1)
        detect_grid.setColumnStretch(1, 1)
        right_col.addWidget(detect_box)

        # ---- 槽位：5 个位置全部可配，挂件与大面板共用，每项互斥、可放齿轮 ----
        self._slot_box = QGroupBox("🧩 环配置（挂件 / 大面板）")
        slot_layout = QVBoxLayout(self._slot_box)
        slot_layout.setSpacing(10)
        # 0.10.07.13：5 个下拉框直接横排，作为底部长条（不额外加说明，保持一屏）
        slot_row = QHBoxLayout()
        slot_row.setSpacing(8)
        self._slot_combos = []
        for index in range(5):
            combo = ModernComboBox()
            combo.setMinimumWidth(92)      # 横排时仍保证文本不被挤成 0 宽
            combo.setToolTip(f"第 {index + 1} 位：选择该位置显示的数据项")
            combo.currentIndexChanged.connect(self._on_slot_combo_changed)
            slot_row.addWidget(combo)
            self._slot_combos.append(combo)
        self._reset_slots_btn = QPushButton("恢复默认")
        self._reset_slots_btn.setToolTip("重置五个槽位为默认配置（CPU / GPU / 内存 / C盘 / 齿轮）")
        self._reset_slots_btn.setIcon(QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_BrowserReload))
        self._reset_slots_btn.setIconSize(QSize(16, 16))
        self._reset_slots_btn.clicked.connect(self._on_reset_slots)
        slot_row.addWidget(self._reset_slots_btn)
        slot_layout.addLayout(slot_row)

        self._slot_hint = QLabel("挂件与大面板共用同一套槽位配置")
        self._slot_hint.setStyleSheet("color: #8C919B;")
        slot_layout.addWidget(self._slot_hint)
        # 系统合成关闭时挂件无法真透明（会变黑），这里给用户一个明确提示
        self._widget_bg_hint = QLabel("当前系统未开启透明效果，挂件使用不透明背景")
        self._widget_bg_hint.setStyleSheet("color: #8C919B;")
        self._widget_bg_hint.setWordWrap(True)
        self._widget_bg_hint.setVisible(False)
        slot_layout.addWidget(self._widget_bg_hint)
        root.addWidget(self._slot_box)

        # ---- 外观：显示环形刻度（两种模式通用，不随模式置灰）----
        # 刻度是环的通用视觉元素，挂件小环与大面板大环共用同一个开关；
        # 不持久化，重启后回到默认勾选。
        look_box = QGroupBox("🎨 外观")
        look_layout = QVBoxLayout(look_box)
        look_layout.setSpacing(12)
        self._show_ticks_check = ToggleRow("📏 显示环形刻度")
        self._show_ticks_check.setToolTip("控制圆环上是否显示刻度线")
        self._show_ticks_check.setChecked(self._panel.show_ticks_enabled())
        self._show_ticks_check.toggled.connect(self._on_show_ticks_toggled)
        look_layout.addWidget(self._show_ticks_check)
        # 第 7 轮：环中心图标/文字切换。默认勾选；与刻度开关一样受设置锁控制，
        # 锁上时由主窗口立即写 JSON，解锁时只在本次运行生效、重启回到默认勾选。
        self._icon_style_check = ToggleRow("✨ 使用拟物化图标")
        self._icon_style_check.setToolTip(
            "勾选后环中心显示拟物图标（下方可选多色/单色）；取消后恢复显示项目名称文字")
        self._icon_style_check.setChecked(self._panel.use_icon_style_enabled())
        self._icon_style_check.toggled.connect(self._on_icon_style_toggled)
        look_layout.addWidget(self._icon_style_check)

        # 第 7 轮完全体：图标风格下拉（多色拟物 / 单色线条）。
        # 默认多色；与图标开关一样受设置锁控制，锁上时由主窗口立即写 JSON。
        style_row = QHBoxLayout()
        style_label = QLabel("🎨 图标风格")
        style_label.setStyleSheet("color: #8C919B;")
        style_row.addWidget(style_label)
        self._icon_style_combo = ModernComboBox()
        self._icon_style_combo.addItem("多色拟物", "color")
        self._icon_style_combo.addItem("单色线条", "line")
        self._icon_style_combo.setMinimumWidth(120)
        self._icon_style_combo.setToolTip(
            "多色拟物：半透明填充 + 微渐变 + 高光；单色线条：1.2px 描边")
        idx = self._icon_style_combo.findData(self._panel.icon_style())
        if idx >= 0:
            self._icon_style_combo.setCurrentIndex(idx)
        self._icon_style_combo.currentIndexChanged.connect(self._on_icon_style_changed)
        style_row.addWidget(self._icon_style_combo)
        style_row.addStretch(1)
        look_layout.addLayout(style_row)
        # 调试卡与外观栏之间留 12px 间距，展开后不再贴着调试卡底边
        left_col.addSpacing(12)
        left_col.addWidget(look_box)

        # ---- 任务栏吸附（第二阶段）：状态不持久化，重启恢复默认勾选 ----
        dock_box = QGroupBox("📌 任务栏吸附")
        dock_layout = QVBoxLayout(dock_box)
        dock_layout.setSpacing(10)
        self._auto_dock_check = ToggleRow("📌 自动吸附到任务栏")
        self._auto_dock_check.setToolTip("取消后挂件将不再固定在任务栏，可自由拖动")
        dock_layout.addWidget(self._auto_dock_check)
        self._dock_hint = QLabel("")
        self._dock_hint.setStyleSheet("color: #8C919B;")
        self._dock_hint.setWordWrap(True)
        dock_layout.addWidget(self._dock_hint)
        self._auto_dock_mode_hint = QLabel("仅任务栏挂件模式支持吸附")
        self._auto_dock_mode_hint.setStyleSheet("color: #8C919B;")
        self._auto_dock_mode_hint.setVisible(False)
        dock_layout.addWidget(self._auto_dock_mode_hint)
        # 0.10.07.13：调试行展开后左列过高，任务栏吸附移到右列以保持 ≤750 无滚动
        right_col.addWidget(dock_box)
        if not self._auto_dock_available:
            # 总开关 AUTO_DOCK_ENABLED = False：完全回到第一阶段行为，复选框禁用
            self._auto_dock_check.setEnabled(False)
            self._auto_dock_check.setToolTip("AUTO_DOCK_ENABLED = False，已回到第一阶段行为")
        self._auto_dock_check.toggled.connect(self._on_auto_dock_toggled)

        # ---- GitHub 按钮（打开 APP_REPO_URL 指向的真实仓库地址）----
        self._github_btn = QPushButton("🐙 打开 GitHub 仓库")
        self._github_btn.setToolTip("在浏览器中打开项目仓库")
        self._github_btn.clicked.connect(self._on_github)

        # ---- 关于（只读）：作者与仓库地址，字号比正文小一号、颜色 #8C919B ----
        about_box = QGroupBox("ℹ️ 关于")
        about_layout = QVBoxLayout(about_box)
        # 作者为空时显示"未填写"，避免出现孤零零的"作者：@"
        self._author_label = QLabel(
            f"作者：{'@' + self._author if self._author else '未填写'}"
        )
        self._repo_label = QLabel(f"仓库：{self._repo_url}")
        for label in (self._author_label, self._repo_label):
            label.setStyleSheet("color: #8C919B; font-size: 11px;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            about_layout.addWidget(label)

        # ---- 制作人员（只读）：四行署名，字号比正文小一号、颜色 #8C919B、行距紧凑 ----
        self._credits_labels = []
        if self._credits:
            credits_title = QLabel("👥 制作人员")
            credits_title.setStyleSheet("color: #8C919B; font-size: 11px;")
            about_layout.addWidget(credits_title)
        for role, member in self._credits:
            credit_label = QLabel(f"{role}：{member}")
            credit_label.setStyleSheet("color: #8C919B; font-size: 11px;")
            about_layout.addWidget(credit_label)
            self._credits_labels.append(credit_label)
        about_layout.setSpacing(2)          # 行距紧凑，避免四行占太多高度
        right_col.addWidget(about_box)
        right_col.addStretch(1)
        right_col.addWidget(self._github_btn)

        # ---- 版本号（与主窗口显示同一四段版本号）----
        self._version_label = QLabel(f"版本 {self._app_version}")
        root.addWidget(self._version_label)

        # ---- 恢复默认设置（底部）：淡出 200ms → 重置 → 淡入 200ms ----
        self._reset_all_btn = QPushButton("恢复默认设置")
        self._reset_all_btn.setToolTip("重置所有外观与配置，恢复初始状态")
        self._reset_all_btn.setIcon(QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_BrowserReload))
        self._reset_all_btn.setIconSize(QSize(16, 16))
        self._reset_all_btn.clicked.connect(self._on_reset_all)
        left_col.addStretch(1)
        left_col.addWidget(self._reset_all_btn)

        # 初始状态：调试模式关闭，五项调试子控件全部禁用
        self._debug_check.toggled.connect(self._on_debug_toggled)
        self._set_debug_widgets_enabled(False)
        self._sync_lock_button()

        # 0.10.07.14：按钮按压视觉交给 QSS 的 :pressed，不再挂阴影 effect
        for button in (self._apply_all_btn, self._restore_all_btn,
                       self._reset_all_btn, self._reset_slots_btn,
                       self._github_btn):
            self._install_button_feedback(button)

    @staticmethod
    def _apply_card_shadow(widget) -> None:
        """给卡片加柔和阴影；效果参数固定，避免不同卡片质感不一致。"""
        try:
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(20)
            effect.setOffset(0, 5)
            effect.setColor(QColor(0, 0, 0, 130))
            widget.setGraphicsEffect(effect)
        except Exception:
            traceback.print_exc()

    def _install_button_feedback(self, button) -> None:
        """按钮按压视觉交给 QSS 的 :pressed，不再创建任何 drop shadow effect。"""
        pass

    def _on_button_pressed(self, button, effect) -> None:
        try:
            for anim in self._button_anims.get(button, ()):
                anim.stop()
            # 阴影变小、偏移变大：视觉上贴合底部并轻微下沉
            effect.setBlurRadius(8)
            effect.setOffset(0, 8)
        except Exception:
            traceback.print_exc()

    def _on_button_released(self, button, effect) -> None:
        try:
            for anim in self._button_anims.get(button, ()):
                anim.stop()
            blur_anim = QPropertyAnimation(effect, b"blurRadius", effect)
            blur_anim.setDuration(120)
            blur_anim.setStartValue(effect.blurRadius())
            blur_anim.setEndValue(20)
            blur_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            offset_anim = QPropertyAnimation(effect, b"offset", effect)
            offset_anim.setDuration(120)
            offset_anim.setStartValue(effect.offset())
            offset_anim.setEndValue(QPointF(0, 5))
            offset_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self._button_anims[button] = (blur_anim, offset_anim)
            blur_anim.start()
            offset_anim.start()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 显示前准备

    def prepare_for_show(self) -> None:
        """显示前按当前屏幕的可用高度限高，并把滚动条回到顶部。

        为什么：本窗口内容实测约 883 px，1080p + 150% 缩放下逻辑可用高度只有约 720 px，
        Windows 会把过高的窗口摆到奇怪位置，甚至压住任务栏上的挂件。
        这里把最大高度限制为「可用高度 - 80」（预留任务栏与缝隙）、最小 400，
        放不下的部分交给 QScrollArea 滚动，低分辨率机器也能完整操作。
        """
        try:
            screen = self._panel.screen() or QApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            # 死命令：设置窗口高度绝不超过 750px；放不下的调试值交给滚动区
            max_h = min(750, max(400, avail.height() - 80))
            self.setMinimumHeight(400)
            self.setMaximumHeight(max_h)

            # 尺寸以内容 sizeHint 为准：宽度不足会把控件挤扁，高度超过上限则滚动
            frame = 2 * self._scroll.frameWidth()
            content = self._scroll.widget()
            hint = content.sizeHint() if content is not None else self.sizeHint()
            # 死命令：宽度约 600~700，双列一屏；高度不超过 750
            width = min(700, max(self.minimumWidth(), hint.width() + frame))
            height = min(max(400, hint.height() + frame), max_h)
            self.resize(width, height)
            self._scroll.verticalScrollBar().setValue(0)   # 每次打开都从顶部开始
        except Exception:
            traceback.print_exc()

    def start_open_animation(self) -> None:
        """由主窗口在 prepare_for_show → show → 贴底定位之后调用。

        此时 geometry 才是最终位置；不要在 showEvent 里提前启动，
        否则先按旧位置做动画、随后又被 _place_settings_window() 搬走，会产生残影。
        """
        self._play_open_fade()

    def _play_open_fade(self) -> None:
        """类 macOS 弹出：仅 opacity 0→1 + y 下移 15px 滑回，250ms OutExpo。

        不改宽高、不固定内容尺寸、不动滚动条策略，避免截图/失焦时窗口消失。
        """
        try:
            self._stop_open_animation()
            # 注意：这里不能再检查 _fade_anim（恢复默认设置的淡出动画）。
            # 打开流程已由主窗口把 windowOpacity 设为 0，若因无关动画仍在跑而提前
            # return，就会留下 opacity=0 的"隐形窗口"，正是本轮要消灭的消失问题。
            final = QRect(self.geometry())
            self._open_final_geometry = final
            self.setWindowOpacity(0.0)
            start = QRect(final.x(), final.y() + 15,
                          final.width(), final.height())
            self.setGeometry(start)

            opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
            opacity_anim.setDuration(250)
            opacity_anim.setStartValue(0.0)
            opacity_anim.setEndValue(1.0)
            opacity_anim.setEasingCurve(QEasingCurve.Type.OutExpo)

            geom_anim = QPropertyAnimation(self, b"geometry", self)
            geom_anim.setDuration(250)
            geom_anim.setStartValue(start)
            geom_anim.setEndValue(final)
            geom_anim.setEasingCurve(QEasingCurve.Type.OutExpo)
            geom_anim.finished.connect(self._finish_open_animation)

            self._open_anim = opacity_anim
            self._open_geom_anim = geom_anim
            self._open_force_timer.start(400)
            opacity_anim.start()
            geom_anim.start()
        except Exception:
            traceback.print_exc()

    def _finish_open_animation(self) -> None:
        """正常结束：强制 opacity=1、回到最终 geometry，并清理可能残留的 scroll effect。"""
        try:
            self._open_force_timer.stop()
            self._open_anim = None
            self._open_geom_anim = None
            self.setWindowOpacity(1.0)
            if self._open_final_geometry is not None:
                self.setGeometry(self._open_final_geometry)
            eff = self._scroll.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                self._scroll.setGraphicsEffect(None)
        except Exception:
            traceback.print_exc()

    def _force_open_animation_end(self) -> None:
        """400ms 保险：无论失焦/截图/动画被打断，都收敛到可见的最终态。"""
        try:
            if self._open_anim is not None:
                self._open_anim.stop()
            if self._open_geom_anim is not None:
                self._open_geom_anim.stop()
            self._open_anim = None
            self._open_geom_anim = None
            self.setWindowOpacity(1.0)
            if self._open_final_geometry is not None:
                self.setGeometry(self._open_final_geometry)
            eff = self._scroll.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                self._scroll.setGraphicsEffect(None)
        except Exception:
            traceback.print_exc()

    def _stop_open_animation(self) -> None:
        """中途关闭/重置时停止弹窗动画，并立即恢复可见的最终状态。"""
        try:
            self._open_force_timer.stop()
            if self._open_anim is not None:
                self._open_anim.stop()
            if self._open_geom_anim is not None:
                self._open_geom_anim.stop()
            self.setWindowOpacity(1.0)
            if self._open_final_geometry is not None:
                self.setGeometry(self._open_final_geometry)
            eff = self._scroll.graphicsEffect()
            if isinstance(eff, QGraphicsOpacityEffect):
                self._scroll.setGraphicsEffect(None)
        except Exception:
            traceback.print_exc()
        finally:
            self._open_anim = None
            self._open_geom_anim = None

    # ------------------------------------------------------------------ 状态同步

    def _set_debug_widgets_enabled(self, enabled: bool) -> None:
        """统一开启/禁用五项调试子控件（滑块、数值框、两个按钮）。

        注意：只禁用子控件，总开关本身永远保持可点击，
        否则关掉调试后就没法再打开。
        """
        for widgets in (self._sliders, self._spins):
            for widget in widgets.values():
                widget.setEnabled(enabled)
        self._hint_label.setVisible(not enabled)

    def _sync_sliders_from_real(self) -> None:
        """把滑块/数值框初始化到最近一次真实读数。

        作用：避免上一次调试值残留到下一次打开（调试值明确要求不持久化）。
        """
        for key, spin in self._spins.items():
            spin.setValue(self._reader.real_value(key))

    def _refresh_labels(self) -> None:
        """刷新只读文案（系统信息、版本号、检测开关）。"""
        self._boot_info.setText(self._reader.boot_text or "开机时长：读取失败")
        self._os_info.setText(self._reader.os_text or "系统版本：读取失败")
        self._version_label.setText(f"版本 {self._app_version}")
        for key, check in self._detect_checks.items():
            check.blockSignals(True)
            check.setChecked(self._reader.enabled.get(key, True))
            check.blockSignals(False)

    # ------------------------------------------------------------------ 事件处理

    def showEvent(self, event) -> None:
        """每次打开都重置为"调试模式关闭"，并同步最新真实读数。"""
        super().showEvent(event)
        try:
            self._refresh_labels()
            self._sync_sliders_from_real()
            self._debug_check.blockSignals(True)
            self._debug_check.setChecked(False)      # 不记住上次状态
            self._debug_check.blockSignals(False)
            self._set_debug_widgets_enabled(False)
            self._collapse_debug_rows_immediate()
            self._reader.debug_active = False
            self._reader.debug_values.clear()
            self._reader.apply_state()
            self._panel.update()
            # 防止历史遗留的"调试已关但主窗口定时器没恢复"导致主窗口不刷新
            self._panel.resume_refresh()
            # 同步"自动吸附"复选框到主窗口当前状态（不持久化，重启回到默认勾选）
            self._auto_dock_check.blockSignals(True)
            self._auto_dock_check.setChecked(self._panel.is_auto_dock_enabled())
            self._auto_dock_check.blockSignals(False)
            self._refresh_dock_hint()
            # 同步界面模式与挂件环配置（锁上时这些状态会被持久化）
            self.sync_layout_mode(self._panel.layout_mode())
            self.sync_slot_combos()
            self.sync_show_ticks()
            self._sync_lock_button()
            self._refresh_mode_dependent_ui()
            # 0.10.07.13：弹入动画由主窗口在贴底定位后调用 start_open_animation()
        except Exception:
            traceback.print_exc()

    def changeEvent(self, event) -> None:
        """失焦（如截图工具抢焦点）时若弹入动画未结束，立即强制收敛到最终态。"""
        super().changeEvent(event)
        try:
            if (event.type() == QEvent.Type.ActivationChange
                    and not self.isActiveWindow()
                    and (self._open_anim is not None
                         or self._open_geom_anim is not None)):
                self._force_open_animation_end()
        except Exception:
            traceback.print_exc()

    def hideEvent(self, event) -> None:
        """任何隐藏路径都会走到这里，统一复位，避免漏掉某条路径。

        注意：X 关闭、Esc、reject()、直接 hide() 最终都会触发隐藏事件，
        因此复位主要在这里兜底；closeEvent / reject 里的调用保留也无害（幂等）。
        """
        super().hideEvent(event)
        try:
            # 0.10.07.22：先取消"恢复默认"的淡出动画，避免窗口隐藏后
            # finished 回调仍在已隐藏窗口上执行 reset_appearance / 刷新 UI。
            if self._fade_anim is not None:
                self._fade_anim.stop()
                self._fade_anim = None
            if self._fade_effect is not None:
                self._scroll.setGraphicsEffect(None)
                self._fade_effect = None
            self._reset_all_btn.setEnabled(True)
            self._stop_open_animation()
            self._reset_on_close()
        except Exception:
            traceback.print_exc()

    def closeEvent(self, event) -> None:
        """点 X 关闭：复位调试状态（hideEvent 也会兜底复位一次，幂等）。"""
        self._reset_on_close()
        super().closeEvent(event)

    def reject(self) -> None:
        """Esc 走 reject()：这里先复位一次，隐藏后 hideEvent 还会再兜底一次。"""
        self._reset_on_close()
        super().reject()

    def _reset_on_close(self) -> None:
        """关闭窗口时复位：关调试模式、子控件置灰、主窗口立即恢复真实数据刷新。

        注意：本方法是幂等的——closeEvent / reject / hideEvent 都可能调用它，
        重复执行不会产生副作用（都只是关开关、清调试值、恢复刷新）。
        """
        try:
            self._debug_check.blockSignals(True)
            self._debug_check.setChecked(False)
            self._debug_check.blockSignals(False)
            self._set_debug_widgets_enabled(False)
            self._collapse_debug_rows_immediate()
            self._reader.debug_active = False
            self._reader.debug_values.clear()
            self._reader.apply_state()
            self._panel.resume_refresh()      # 立即读真实数据并恢复 2 秒定时刷新
            # 关闭后让挂件恢复背景与层级：设置窗口存在期间挂件可能被盖住或背景状态过期，
            # 这里只做绘制/置顶，不改动挂件 geometry（开关设置不允许改变位置与尺寸）
            self._panel.restore_after_settings()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 交互

    def _on_debug_toggled(self, checked: bool) -> None:
        """调试模式总开关。"""
        try:
            self._set_debug_widgets_enabled(checked)
            self._reader.debug_active = bool(checked)
            if checked:
                # 调试期间暂停真实刷新，否则每 2 秒的新读数会把调试值冲掉
                self._panel.pause_refresh()
                self._sync_sliders_from_real()
            else:
                # 关闭调试：清掉调试值、立即恢复真实数据与定时刷新
                self._reader.debug_values.clear()
                self._reader.apply_state()
                self._panel.resume_refresh()
            # 0.10.07.13：高度 0↔动态目标高度 + 内容 opacity 联动
            self._animate_debug_rows(bool(checked))
        except Exception:
            traceback.print_exc()

    def _animate_debug_rows(self, expand: bool) -> None:
        """调试值卡片平滑展开/收起；收起完成后 setVisible(False) 完全不占高度。"""
        try:
            self._rows_anim.stop()
            self._rows_opacity_timer.stop()
            self._rows_inner_anim.stop()
            # 350ms 保险：即使鼠标晃动/失焦/截图打断，也强制收敛
            self._rows_force_timer.start(350)
            if expand:
                # 动态目标高度：内层真实内容高度 + 12px 上下边距，
                # 避免写死 220 导致不同 DPI / 行数变多时底部按钮被裁切。
                target_height = self._rows_inner.sizeHint().height() + 12
                self._rows_target_height = target_height
                self._rows_effect.setOpacity(0.0)
                self._rows_box.setVisible(True)
                self._rows_box.setMaximumHeight(0)
                self._rows_anim.setStartValue(0)
                self._rows_anim.setEndValue(target_height)
                self._rows_expanded = True
                self._rows_anim.start()
                # 高度先动，50ms 后内容淡入
                self._rows_opacity_timer.start(50)
                return
            if not self._rows_box.isVisible():
                self._collapse_debug_rows_immediate()
                return
            self._rows_inner_anim.setStartValue(
                self._rows_effect.opacity())
            self._rows_inner_anim.setEndValue(0.0)
            self._rows_inner_anim.start()
            self._rows_anim.setStartValue(max(0, self._rows_box.height()))
            self._rows_anim.setEndValue(0)
            self._rows_expanded = False
            self._rows_anim.start()
        except Exception:
            traceback.print_exc()

    def _start_rows_opacity_in(self) -> None:
        """高度展开 50ms 后启动内容淡入，避免生硬地一起被拉出来。"""
        try:
            if not self._rows_expanded:
                return
            self._rows_inner_anim.stop()
            self._rows_inner_anim.setStartValue(
                self._rows_effect.opacity())
            self._rows_inner_anim.setEndValue(1.0)
            self._rows_inner_anim.start()
        except Exception:
            traceback.print_exc()

    def _on_rows_anim_finished(self) -> None:
        try:
            if self._rows_expanded:
                # 使用动态目标高度，保证底部“应用 / 恢复”按钮完整可见
                self._rows_box.setMaximumHeight(self._rows_target_height)
            else:
                self._rows_effect.setOpacity(0.0)
                self._rows_box.setVisible(False)
                self._rows_box.setMaximumHeight(0)
        except Exception:
            traceback.print_exc()

    def _force_rows_animation_end(self) -> None:
        """350ms 保险：停止所有调试卡动画，强制写入展开/收起终态。"""
        try:
            self._rows_force_timer.stop()
            self._rows_anim.stop()
            self._rows_opacity_timer.stop()
            self._rows_inner_anim.stop()
            if self._rows_expanded:
                self._rows_box.setVisible(True)
                # 350ms 保险同样收敛到动态目标高度，避免写死 220 裁切按钮
                self._rows_box.setMaximumHeight(self._rows_target_height)
                self._rows_effect.setOpacity(1.0)
            else:
                self._rows_box.setVisible(False)
                self._rows_box.setMaximumHeight(0)
                self._rows_effect.setOpacity(0.0)
        except Exception:
            traceback.print_exc()

    def _collapse_debug_rows_immediate(self) -> None:
        """关闭设置/复位调试时立即收起，不留下动画中的半截卡片。"""
        try:
            if self._rows_anim is not None:
                self._rows_anim.stop()
            if self._rows_force_timer is not None:
                self._rows_force_timer.stop()
            if self._rows_opacity_timer is not None:
                self._rows_opacity_timer.stop()
            if self._rows_inner_anim is not None:
                self._rows_inner_anim.stop()
            self._rows_effect.setOpacity(0.0)
            self._rows_expanded = False
            self._rows_box.setVisible(False)
            self._rows_box.setMaximumHeight(0)
        except Exception:
            traceback.print_exc()

    def _on_apply_all(self) -> None:
        """应用全部调试值：遍历所有滑块，一次性写入 debug_values 并重绘。"""
        try:
            if not self._debug_check.isChecked():
                return
            self._reader.debug_active = True
            for key, spin in self._spins.items():
                self._reader.debug_values[key] = float(spin.value())
            self._reader.apply_state()
            self._panel.update()
        except Exception:
            traceback.print_exc()

    def _on_restore_all(self) -> None:
        """恢复全部真实值：清空调试值并用 _sync_sliders_from_real 回填所有项。"""
        try:
            self._reader.debug_values.clear()
            self._reader.apply_state()
            self._panel.update()
            self._sync_sliders_from_real()
        except Exception:
            traceback.print_exc()

    def _on_toggle_detect(self, key: str, checked: bool) -> None:
        """启用/关闭某项检测；关闭后主窗口对应环显示红叉 + 检测已关闭。"""
        try:
            self._reader.enabled[key] = bool(checked)
            self._reader.apply_state()
            self._panel.update()
        except Exception:
            traceback.print_exc()

    def sync_auto_dock(self, enabled: bool) -> None:
        """主窗口拖动后自动切手动模式时，外部同步复选框（不触发面板回调）。"""
        try:
            self._auto_dock_check.blockSignals(True)
            self._auto_dock_check.setChecked(bool(enabled))
            self._auto_dock_check.blockSignals(False)
            self._refresh_dock_hint()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 界面模式 / 挂件环配置

    def sync_layout_mode(self, mode: str) -> None:
        """外部同步界面模式单选（不触发切换回调）。"""
        try:
            target = self._mode_widget if mode == "widget" else self._mode_panel
            if target.isChecked():
                return
            for radio in (self._mode_widget, self._mode_panel):
                radio.blockSignals(True)
            target.setChecked(True)
            for radio in (self._mode_widget, self._mode_panel):
                radio.blockSignals(False)
            self._refresh_mode_dependent_ui()
        except Exception:
            traceback.print_exc()

    def _on_layout_mode_toggled(self, checked: bool) -> None:
        """切换界面模式：立即调用主窗口 set_layout_mode。

        注意：两个单选都连了这个槽，这里以"谁最终被选中"为准，
        不能只看 checked——取消选中的那次信号也要忽略掉。
        """
        try:
            mode = "widget" if self._mode_widget.isChecked() else "panel"
            if self._panel.layout_mode() == mode:
                self._refresh_mode_dependent_ui()
                return
            self._panel.set_layout_mode(mode)
            self._refresh_mode_dependent_ui()
        except Exception:
            traceback.print_exc()

    def _refresh_mode_dependent_ui(self) -> None:
        """按当前模式启用/禁用相关区域；槽位配置在两种模式下都可用。"""
        try:
            widget = self._panel.layout_mode() == "widget"
            # 第 7 轮：大面板同样支持自定义槽位，不能再按模式禁用整个配置区
            self._slot_box.setEnabled(True)
            self._slot_hint.setVisible(False)
            self._widget_bg_hint.setVisible(
                widget and not self._panel.widget_background_transparent())
            self._auto_dock_check.setEnabled(widget and self._auto_dock_available)
            self._auto_dock_mode_hint.setVisible(not widget)
            # 图标/文字开关在挂件与大面板都生效，这里只负责把复选框同步到真实状态
            self.sync_icon_style()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 显示环形刻度

    def sync_show_ticks(self) -> None:
        """把复选框同步到主窗口当前状态（不触发切换回调）。"""
        try:
            self._show_ticks_check.blockSignals(True)
            self._show_ticks_check.setChecked(self._panel.show_ticks_enabled())
            self._show_ticks_check.blockSignals(False)
        except Exception:
            traceback.print_exc()

    def _on_show_ticks_toggled(self, checked: bool) -> None:
        """「显示环形刻度」开关：只改主窗口绘制，不重建任何控件。"""
        try:
            self._panel.set_show_ticks(bool(checked))
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 拟物化图标

    def sync_icon_style(self) -> None:
        """把图标复选框与风格下拉同步到主窗口当前状态（不触发切换回调）。"""
        try:
            self._icon_style_check.blockSignals(True)
            self._icon_style_check.setChecked(self._panel.use_icon_style_enabled())
            self._icon_style_check.blockSignals(False)
            combo = getattr(self, "_icon_style_combo", None)
            if combo is not None:
                target = self._panel.icon_style()
                # 只有状态不一致时才改下拉，避免用户刚选完时再次 setCurrentIndex
                # 干扰正在关闭的弹出层（弹出层收起问题上一轮已踩过坑）。
                if combo.currentData() != target:
                    combo.blockSignals(True)
                    idx = combo.findData(target)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    combo.blockSignals(False)
        except Exception:
            traceback.print_exc()

    def _on_icon_style_toggled(self, checked: bool) -> None:
        """切换图标/文字：立即重绘主窗口；锁上时由主窗口负责写盘。"""
        try:
            self._panel.set_use_icon_style(bool(checked))
        except Exception:
            traceback.print_exc()

    def _on_icon_style_changed(self, _index: int = 0) -> None:
        """切换多色拟物 / 单色线条：立即重绘主窗口并受锁持久化。"""
        try:
            self._panel.set_icon_style(self._icon_style_combo.currentData())
        except Exception:
            traceback.print_exc()

    def _fill_slot_combo(self, combo, current: str, excludes, options) -> None:
        """填一个下拉：可选 = 全部可用项去掉"另外 4 个槽已选项"。

        注意：blockSignals(True/False) 必须成对，且放在 try/finally 里——
        clear()/addItem() 过程中若抛异常，信号会一直处于屏蔽状态，后续选择全部失灵。
        """
        combo.blockSignals(True)
        try:
            combo.clear()
            for key, label in options:
                if key in excludes:
                    continue
                combo.addItem(label, key)
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.count() > 0:
                combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(False)

    def _refresh_slot_combos(self) -> None:
        """按主窗口当前配置刷新 5 个下拉（每个都排除另外 4 个槽的已选项）。"""
        try:
            keys = self._panel.slot_keys()
            options = self._panel.available_slot_items()
            for index, combo in enumerate(self._slot_combos):
                excludes = tuple(keys[j] for j in range(5) if j != index)
                self._fill_slot_combo(combo, keys[index], excludes, options)
        except Exception:
            traceback.print_exc()

    def sync_slot_combos(self) -> None:
        """供主窗口 set_slot_config 反向同步下拉（例如恢复默认后）。"""
        self._refresh_slot_combos()

    def _on_slot_combo_changed(self, _index: int = 0) -> None:
        """任一下拉变更：立即刷新另外 4 个下拉并应用新配置。"""
        try:
            keys = [combo.currentData() for combo in self._slot_combos]
            if any(not key for key in keys) or len(set(keys)) != 5:
                return
            if self._panel.set_slot_config(keys):
                self._refresh_slot_combos()
        except Exception:
            traceback.print_exc()

    def _on_reset_slots(self) -> None:
        """环配置恢复默认（CPU/GPU/内存/C盘/齿轮），并强制刷新 5 个下拉。

        注意：无论 set_slot_config 是否接受，最后都调用 _refresh_slot_combos()，
        让下拉框显示主窗口的真实当前值，避免"后台改了、界面不动"。
        """
        try:
            self._panel.set_slot_config(self._panel.default_slot_keys())
        except Exception:
            traceback.print_exc()
        finally:
            self._refresh_slot_combos()

    # ------------------------------------------------------------------ 设置锁 / 恢复默认

    def _sync_lock_button(self) -> None:
        """按主窗口锁状态刷新锁按钮图标（🔒 已锁定 / 🔓 未锁定）。"""
        try:
            self._lock_btn.setText("🔒" if self._panel.settings_locked() else "🔓")
        except Exception:
            traceback.print_exc()

    def _on_lock_clicked(self) -> None:
        """切换设置锁：锁上立即保存当前配置；解锁只记 lock_state=False，重启回默认。"""
        try:
            ok = self._panel.set_settings_locked(not self._panel.settings_locked())
            if not ok:
                QMessageBox.warning(
                    self, "提示", "配置写入失败，重启后可能不会记住当前锁状态")
            self._sync_lock_button()
        except Exception:
            traceback.print_exc()

    def _on_reset_all(self) -> None:
        """恢复默认设置：内容区淡出 200ms → 重置 → 淡入 200ms。

        注意：动画期间禁用按钮，避免连续点击叠加多个动画导致界面闪烁。
        """
        try:
            if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
                return
            # 若弹窗动画还在跑，先停掉并恢复内容尺寸/滚动条
            self._stop_open_animation()
            self._reset_all_btn.setEnabled(False)
            effect = QGraphicsOpacityEffect(self._scroll)
            self._scroll.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(200)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.finished.connect(self._apply_defaults_then_fade_in)
            self._fade_effect = effect
            self._fade_anim = anim
            anim.start()
            if anim.state() != QPropertyAnimation.State.Running:
                # 动画没跑起来（极端环境）也要执行重置，绝不让按钮变成摆设
                self._apply_defaults_then_fade_in()
        except Exception:
            traceback.print_exc()
            self._apply_defaults_then_fade_in()

    def _refresh_all_ui(self) -> None:
        """把本窗口所有控件状态强行同步到主窗口当前值（无动画也照样刷新）。"""
        try:
            self.sync_layout_mode(self._panel.layout_mode())
            self.sync_show_ticks()
            self._refresh_slot_combos()
            self._sync_lock_button()
            self._refresh_mode_dependent_ui()
        except Exception:
            traceback.print_exc()

    def _apply_defaults_then_fade_in(self) -> None:
        """淡出结束：执行重置并强制刷新 UI，再淡入。"""
        try:
            # 主窗口重置：大面板、刻度关闭、槽位默认、锁解锁
            self._panel.reset_appearance()
            self._debug_check.setChecked(False)      # 触发放开真实刷新
            self._refresh_all_ui()                   # 关键：后台变量改了必须立刻刷界面
            if self._fade_effect is None:
                self._finish_reset()
                return

            anim = QPropertyAnimation(self._fade_effect, b"opacity", self)
            anim.setDuration(200)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.finished.connect(self._finish_reset)
            self._fade_anim = anim
            anim.start()
            if anim.state() != QPropertyAnimation.State.Running:
                self._finish_reset()
        except Exception:
            traceback.print_exc()
            self._refresh_all_ui()
            self._finish_reset()

    def _finish_reset(self) -> None:
        """淡入结束：移除透明度特效，再次强制刷新 UI，恢复按钮可用。"""
        try:
            self._scroll.setGraphicsEffect(None)
            self._fade_effect = None
            self._fade_anim = None
            self._refresh_all_ui()                   # 收尾再刷一次，确保下拉/单选到位
            self._reset_all_btn.setEnabled(True)
        except Exception:
            traceback.print_exc()
            self._reset_all_btn.setEnabled(True)

    def _on_auto_dock_toggled(self, checked: bool) -> None:
        """勾选/取消"自动吸附到任务栏"，立即生效（状态不持久化）。"""
        try:
            self._panel.set_auto_dock(bool(checked))
            self._refresh_dock_hint()
        except Exception:
            traceback.print_exc()

    def _refresh_dock_hint(self) -> None:
        """显示吸附状态/回退提示：定位失败时让用户知道为什么没吸附。"""
        try:
            status = self._panel.dock_status()
            enabled = self._auto_dock_check.isChecked()
            self._dock_hint.setText(status if enabled else "")
            self._dock_hint.setVisible(bool(enabled) and status not in ("", "已吸附到任务栏"))
        except Exception:
            traceback.print_exc()

    def _on_github(self) -> None:
        """打开 GitHub 仓库；地址为空时只提示，不跳转、不崩溃。"""
        try:
            if not (self._repo_url or "").strip():
                QMessageBox.information(self, "提示", "GitHub 仓库尚未配置")
                return
            QDesktopServices.openUrl(QUrl(self._repo_url))
        except Exception:
            traceback.print_exc()
