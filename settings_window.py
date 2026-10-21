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
"""
from __future__ import annotations

import traceback

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# 预留：配置成真实仓库地址后，"打开 GitHub 仓库"按钮才会真正跳转。
# 注意：仓库地址统一由 main.py 的 APP_REPO_URL 提供并通过构造函数传入，
# 这里不再保留第二个 GITHUB_REPO_URL 常量，避免两处地址不一致。


class SettingsWindow(QDialog):
    """设置与调试窗口。

    注意：关闭（X / Esc）时必须复位调试状态并让主窗口恢复真实数据刷新，
    所以复位逻辑写成幂等的 _reset_on_close()，closeEvent 和 reject() 都会调用。
    """

    def __init__(self, reader, panel, app_version: str,
                 repo_url: str = "", author: str = "",
                 auto_dock_available: bool = True, credits=None) -> None:
        super().__init__(panel)
        self._reader = reader
        self._panel = panel
        self._app_version = app_version
        self._repo_url = repo_url
        self._author = author
        self._auto_dock_available = auto_dock_available
        # 制作人员署名由 main.CREDITS 通过构造函数传入，避免两处维护同一份名单
        self._credits = list(credits or [])

        self.setWindowTitle("设置与调试")
        self.setMinimumWidth(460)

        # 内容整体放进滚动区：设置窗口内容很高（约 800+ px），
        # 1080p + 150% 缩放时逻辑可用高度只有约 720 px，不限制会被 Windows 摆到奇怪位置、
        # 甚至压住任务栏上的挂件。这里限制最大高度并允许滚动，保证低分辨率也能完整操作。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll)
        content = QWidget()
        self._scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setSpacing(8)

        # 建立淡入淡出动画用的对象（懒创建）；重置时对内容区做 200ms + 200ms 过渡
        self._fade_effect = None
        self._fade_anim = None

        # ---- 设置锁（顶部）：锁上才把配置写进 JSON，重启保留 ----
        lock_row = QHBoxLayout()
        self._lock_btn = QToolButton()
        self._lock_btn.setText("🔓")
        self._lock_btn.setToolTip(
            "锁定设置：重启后保留当前配置；解锁：重启后恢复默认配置")
        self._lock_btn.clicked.connect(self._on_lock_clicked)
        lock_row.addWidget(self._lock_btn)
        lock_hint = QLabel("锁定后：修改界面模式/刻度/槽位会立即保存，重启保留；"
                           "解锁后：只在本进程生效，重启恢复默认。")
        lock_hint.setStyleSheet("color: #8C919B;")
        lock_hint.setWordWrap(True)
        lock_row.addWidget(lock_hint, 1)
        root.addLayout(lock_row)

        # ---- 界面模式：挂件（默认）/ 大面板，切换立即生效 ----
        mode_box = QGroupBox("界面模式")
        mode_box.setToolTip("切换大面板模式或任务栏挂件模式")
        mode_row = QHBoxLayout(mode_box)
        self._mode_widget = QRadioButton("任务栏挂件模式")
        self._mode_panel = QRadioButton("大面板模式")
        self._mode_widget.setToolTip("切换大面板模式或任务栏挂件模式")
        self._mode_panel.setToolTip("切换大面板模式或任务栏挂件模式")
        self._mode_widget.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_widget)
        mode_group.addButton(self._mode_panel)
        mode_row.addWidget(self._mode_widget)
        mode_row.addWidget(self._mode_panel)
        mode_row.addStretch(1)
        root.addWidget(mode_box)
        self._mode_widget.toggled.connect(self._on_layout_mode_toggled)
        self._mode_panel.toggled.connect(self._on_layout_mode_toggled)

        # ---- 系统信息（只读）：挂件模式下这是唯一能看到开机时长/系统版本的地方 ----
        info_box = QGroupBox("系统信息")
        info_layout = QVBoxLayout(info_box)
        self._boot_info = QLabel("开机时长：读取失败")
        self._os_info = QLabel("系统版本：读取失败")
        info_layout.addWidget(self._boot_info)
        info_layout.addWidget(self._os_info)
        root.addWidget(info_box)

        # ---- 调试模式总开关（始终可点击；关闭时子控件全部置灰）----
        debug_box = QGroupBox("调试")
        debug_row = QHBoxLayout(debug_box)
        self._debug_check = QCheckBox("调试模式")
        self._debug_check.setToolTip("仅用于测试圆环显示，不保存且关闭设置后失效")
        self._hint_label = QLabel("请先开启调试模式")
        debug_row.addWidget(self._debug_check)
        debug_row.addWidget(self._hint_label)
        debug_row.addStretch(1)
        root.addWidget(debug_box)

        # ---- 各项调试行：名称 + 滑块 + 数值框 + 应用/恢复 ----
        rows_box = QGroupBox("各项调试值（0~100）")
        grid = QGridLayout(rows_box)
        grid.addWidget(QLabel("项目"), 0, 0)
        grid.addWidget(QLabel("滑块"), 0, 1)
        grid.addWidget(QLabel("数值"), 0, 2)
        grid.addWidget(QLabel("操作"), 0, 3)

        self._sliders = {}
        self._spins = {}
        self._apply_btns = {}
        self._restore_btns = {}
        # 调试项 = 动态数据池里除齿轮外的全部数据项（含 D盘、总盘等新增项）。
        # 不能再用 reader.items 的固定五项，否则新增磁盘项无法调试。
        debug_items = [(key, label) for key, label in self._panel.available_slot_items()
                       if key != "gear"]
        for row, (key, label) in enumerate(debug_items, start=1):
            grid.addWidget(QLabel(label), row, 0)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setMinimumWidth(150)
            grid.addWidget(slider, row, 1)

            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setFixedWidth(64)
            grid.addWidget(spin, row, 2)

            btn_row = QHBoxLayout()
            apply_btn = QPushButton("应用调试值")
            restore_btn = QPushButton("恢复真实值")
            btn_row.addWidget(apply_btn)
            btn_row.addWidget(restore_btn)
            grid.addLayout(btn_row, row, 3)

            # 滑块与数值框双向同步；值相同时 Qt 不会重复发信号，不会形成死循环
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            apply_btn.clicked.connect(lambda _checked=False, k=key: self._on_apply(k))
            restore_btn.clicked.connect(lambda _checked=False, k=key: self._on_restore(k))

            self._sliders[key] = slider
            self._spins[key] = spin
            self._apply_btns[key] = apply_btn
            self._restore_btns[key] = restore_btn

        root.addWidget(rows_box)

        # ---- 五项检测开关（默认全开；关闭后主窗口对应环显示红叉 + 检测已关闭）----
        detect_box = QGroupBox("启用检测")
        detect_row = QHBoxLayout(detect_box)
        self._detect_checks = {}
        for item in self._reader.items:
            check = QCheckBox(item.name)
            check.setToolTip("关闭后该项圆环将显示红叉，用于测试失败状态")
            check.setChecked(self._reader.enabled.get(item.key, True))
            check.toggled.connect(lambda checked, k=item.key: self._on_toggle_detect(k, checked))
            detect_row.addWidget(check)
            self._detect_checks[item.key] = check
        detect_row.addStretch(1)
        root.addWidget(detect_box)

        # ---- 挂件槽位：5 个位置全部可配，每项互斥、可放齿轮 ----
        self._slot_box = QGroupBox("挂件环配置")
        slot_layout = QVBoxLayout(self._slot_box)
        slot_tip = QLabel("5 个槽位全部可配：可选 CPU / GPU / 内存 / C盘 / 总盘 / "
                          "各固定磁盘 / 电池 / 齿轮，五个位置不能重复。"
                          "默认 CPU + GPU + 内存 + C盘 + 齿轮。")
        slot_tip.setWordWrap(True)
        slot_tip.setStyleSheet("color: #8C919B;")
        slot_layout.addWidget(slot_tip)

        slot_grid = QGridLayout()
        self._slot_combos = []
        for index in range(5):
            slot_grid.addWidget(QLabel(f"第 {index + 1} 位"), index, 0)
            combo = QComboBox()
            combo.setMinimumWidth(120)      # 防止选项文本变化时被布局挤成 0 宽
            combo.setToolTip("选择该位置显示的数据项")
            combo.currentIndexChanged.connect(self._on_slot_combo_changed)
            slot_grid.addWidget(combo, index, 1)
            self._slot_combos.append(combo)
        self._reset_slots_btn = QPushButton("恢复默认环配置")
        self._reset_slots_btn.setToolTip("重置五个槽位为默认配置（CPU / GPU / 内存 / C盘 / 齿轮）")
        self._reset_slots_btn.setIcon(QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_BrowserReload))
        self._reset_slots_btn.setIconSize(QSize(16, 16))
        self._reset_slots_btn.clicked.connect(self._on_reset_slots)
        slot_grid.addWidget(self._reset_slots_btn, 5, 1)
        slot_layout.addLayout(slot_grid)

        self._slot_hint = QLabel("仅任务栏挂件模式支持自定义环")
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
        look_box = QGroupBox("外观")
        look_layout = QVBoxLayout(look_box)
        self._show_ticks_check = QCheckBox("显示环形刻度")
        self._show_ticks_check.setToolTip("控制圆环上是否显示刻度线")
        self._show_ticks_check.setChecked(self._panel.show_ticks_enabled())
        self._show_ticks_check.toggled.connect(self._on_show_ticks_toggled)
        look_layout.addWidget(self._show_ticks_check)
        ticks_hint = QLabel("关闭后只隐藏环形外圈的刻度线，底环、进度弧与环内名称照常显示。")
        ticks_hint.setStyleSheet("color: #8C919B;")
        ticks_hint.setWordWrap(True)
        look_layout.addWidget(ticks_hint)
        root.addWidget(look_box)

        # ---- 任务栏吸附（第二阶段）：状态不持久化，重启恢复默认勾选 ----
        dock_box = QGroupBox("任务栏吸附")
        dock_layout = QVBoxLayout(dock_box)
        self._auto_dock_check = QCheckBox("自动吸附到任务栏")
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
        root.addWidget(dock_box)
        if not self._auto_dock_available:
            # 总开关 AUTO_DOCK_ENABLED = False：完全回到第一阶段行为，复选框禁用
            self._auto_dock_check.setEnabled(False)
            self._auto_dock_check.setToolTip("AUTO_DOCK_ENABLED = False，已回到第一阶段行为")
        self._auto_dock_check.toggled.connect(self._on_auto_dock_toggled)

        # ---- GitHub 按钮（打开 APP_REPO_URL 指向的真实仓库地址）----
        self._github_btn = QPushButton("打开 GitHub 仓库")
        self._github_btn.setToolTip("在浏览器中打开项目仓库")
        self._github_btn.clicked.connect(self._on_github)
        root.addWidget(self._github_btn)

        # ---- 关于（只读）：作者与仓库地址，字号比正文小一号、颜色 #8C919B ----
        about_box = QGroupBox("关于")
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
            credits_title = QLabel("制作人员")
            credits_title.setStyleSheet("color: #8C919B; font-size: 11px;")
            about_layout.addWidget(credits_title)
        for role, member in self._credits:
            credit_label = QLabel(f"{role}：{member}")
            credit_label.setStyleSheet("color: #8C919B; font-size: 11px;")
            about_layout.addWidget(credit_label)
            self._credits_labels.append(credit_label)
        about_layout.setSpacing(2)          # 行距紧凑，避免四行占太多高度
        root.addWidget(about_box)

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
        root.addWidget(self._reset_all_btn)

        # 初始状态：调试模式关闭，五项调试子控件全部禁用
        self._debug_check.toggled.connect(self._on_debug_toggled)
        self._set_debug_widgets_enabled(False)
        self._sync_lock_button()

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
            max_h = max(400, avail.height() - 80)
            self.setMinimumHeight(400)
            self.setMaximumHeight(max_h)

            # 尺寸以内容 sizeHint 为准：宽度不足会把控件挤扁，高度超过上限则滚动
            frame = 2 * self._scroll.frameWidth()
            content = self._scroll.widget()
            hint = content.sizeHint() if content is not None else self.sizeHint()
            width = max(self.minimumWidth(), hint.width() + frame)
            height = min(max(400, hint.height() + frame), max_h)
            self.resize(width, height)
            self._scroll.verticalScrollBar().setValue(0)   # 每次打开都从顶部开始
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------------ 状态同步

    def _set_debug_widgets_enabled(self, enabled: bool) -> None:
        """统一开启/禁用五项调试子控件（滑块、数值框、两个按钮）。

        注意：只禁用子控件，总开关本身永远保持可点击，
        否则关掉调试后就没法再打开。
        """
        for widgets in (self._sliders, self._spins, self._apply_btns, self._restore_btns):
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
        except Exception:
            traceback.print_exc()

    def hideEvent(self, event) -> None:
        """任何隐藏路径都会走到这里，统一复位，避免漏掉某条路径。

        注意：X 关闭、Esc、reject()、直接 hide() 最终都会触发隐藏事件，
        因此复位主要在这里兜底；closeEvent / reject 里的调用保留也无害（幂等）。
        """
        super().hideEvent(event)
        try:
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
        except Exception:
            traceback.print_exc()

    def _on_apply(self, key: str) -> None:
        """应用某一项的调试值：仅在调试模式开启时生效。"""
        try:
            if not self._debug_check.isChecked():
                return
            self._reader.debug_active = True
            self._reader.debug_values[key] = float(self._spins[key].value())
            self._reader.apply_state()
            self._panel.update()
        except Exception:
            traceback.print_exc()

    def _on_restore(self, key: str) -> None:
        """把某一项恢复为真实读数（不关闭整个调试模式）。"""
        try:
            self._reader.debug_values.pop(key, None)
            self._reader.apply_state()
            self._panel.update()
            # 数值框跟着回到真实值，方便用户确认
            spin = self._spins.get(key)
            if spin is not None:
                spin.setValue(self._reader.real_value(key))
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
        """按当前模式启用/禁用相关区域（挂件配置、吸附开关）。"""
        try:
            widget = self._panel.layout_mode() == "widget"
            self._slot_box.setEnabled(widget)
            self._slot_hint.setVisible(not widget)
            self._widget_bg_hint.setVisible(
                widget and not self._panel.widget_background_transparent())
            self._auto_dock_check.setEnabled(widget and self._auto_dock_available)
            self._auto_dock_mode_hint.setVisible(not widget)
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
