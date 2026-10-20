# -*- coding: utf-8 -*-
"""VitalsRing（环脉）"设置与调试"窗口 —— 第一阶段第 3 轮。

职责：提供调试模式总开关、五项调试值、五项检测开关、GitHub 预留按钮。
约定：
- 只用 PyQt6 自带控件，不引入任何第三方库；
- 本窗口不创建任何定时器，关闭后不留刷新任务（刷新仍由主窗口那唯一的定时器负责）；
- 调试值不持久化：关闭窗口时清空，重新打开一律回到"调试模式关闭"。
- 第 4 轮：补充『关于』区与真实仓库地址。
- 第二阶段：补充"自动吸附到任务栏"开关与定位状态提示。
"""
from __future__ import annotations

import traceback

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

# 挂件可配槽位的选项池（顺序与 label 需与 main.py 的 SLOT_POOL / SLOT_LABELS 保持一致）
SLOT_POOL_ITEMS = (("mem", "内存"), ("disk", "C盘"), ("battery", "电池"))

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
                 auto_dock_available: bool = True) -> None:
        super().__init__(panel)
        self._reader = reader
        self._panel = panel
        self._app_version = app_version
        self._repo_url = repo_url
        self._author = author
        self._auto_dock_available = auto_dock_available

        self.setWindowTitle("设置与调试")
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ---- 界面模式：挂件（默认）/ 大面板，切换立即生效、不持久化 ----
        mode_box = QGroupBox("界面模式")
        mode_row = QHBoxLayout(mode_box)
        self._mode_widget = QRadioButton("任务栏挂件模式")
        self._mode_panel = QRadioButton("大面板模式")
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
        self._hint_label = QLabel("请先开启调试模式")
        debug_row.addWidget(self._debug_check)
        debug_row.addWidget(self._hint_label)
        debug_row.addStretch(1)
        root.addWidget(debug_box)

        # ---- 五项调试行：名称 + 滑块 + 数值框 + 应用/恢复 ----
        rows_box = QGroupBox("五项调试值（0~100）")
        grid = QGridLayout(rows_box)
        grid.addWidget(QLabel("项目"), 0, 0)
        grid.addWidget(QLabel("滑块"), 0, 1)
        grid.addWidget(QLabel("数值"), 0, 2)
        grid.addWidget(QLabel("操作"), 0, 3)

        self._sliders = {}
        self._spins = {}
        self._apply_btns = {}
        self._restore_btns = {}
        for row, item in enumerate(self._reader.items, start=1):
            grid.addWidget(QLabel(item.name), row, 0)

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
            apply_btn.clicked.connect(lambda _checked=False, k=item.key: self._on_apply(k))
            restore_btn.clicked.connect(lambda _checked=False, k=item.key: self._on_restore(k))

            self._sliders[item.key] = slider
            self._spins[item.key] = spin
            self._apply_btns[item.key] = apply_btn
            self._restore_btns[item.key] = restore_btn

        root.addWidget(rows_box)

        # ---- 五项检测开关（默认全开；关闭后主窗口对应环显示红叉 + 检测已关闭）----
        detect_box = QGroupBox("启用检测")
        detect_row = QHBoxLayout(detect_box)
        self._detect_checks = {}
        for item in self._reader.items:
            check = QCheckBox(item.name)
            check.setChecked(self._reader.enabled.get(item.key, True))
            check.toggled.connect(lambda checked, k=item.key: self._on_toggle_detect(k, checked))
            detect_row.addWidget(check)
            self._detect_checks[item.key] = check
        detect_row.addStretch(1)
        root.addWidget(detect_box)

        # ---- 挂件环配置：只有第 2 位、第 4 位可配（3 选 2，不重复）----
        self._slot_box = QGroupBox("挂件环配置")
        slot_layout = QVBoxLayout(self._slot_box)
        slot_tip = QLabel("CPU（第1位）、GPU（第3位）、设置（第5位）固定不可改；"
                          "第2位和第4位可从“内存 / C盘 / 电池”中选择，两项不能重复。"
                          "默认内存 + C盘。")
        slot_tip.setWordWrap(True)
        slot_tip.setStyleSheet("color: #8C919B;")
        slot_layout.addWidget(slot_tip)

        slot_row = QHBoxLayout()
        slot_row.addWidget(QLabel("第 2 个环"))
        self._slot1_combo = QComboBox()
        slot_row.addWidget(self._slot1_combo)
        slot_row.addWidget(QLabel("第 4 个环"))
        self._slot3_combo = QComboBox()
        slot_row.addWidget(self._slot3_combo)
        self._reset_slots_btn = QPushButton("恢复默认")
        slot_row.addWidget(self._reset_slots_btn)
        slot_layout.addLayout(slot_row)

        self._slot_hint = QLabel("仅任务栏挂件模式支持自定义环")
        self._slot_hint.setStyleSheet("color: #8C919B;")
        slot_layout.addWidget(self._slot_hint)
        root.addWidget(self._slot_box)

        self._slot1_combo.currentIndexChanged.connect(self._on_slot_combo_changed)
        self._slot3_combo.currentIndexChanged.connect(self._on_slot_combo_changed)
        self._reset_slots_btn.clicked.connect(self._on_reset_slots)

        # ---- 任务栏吸附（第二阶段）：状态不持久化，重启恢复默认勾选 ----
        dock_box = QGroupBox("任务栏吸附")
        dock_layout = QVBoxLayout(dock_box)
        self._auto_dock_check = QCheckBox("自动吸附到任务栏")
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
        root.addWidget(about_box)

        # ---- 版本号（与主窗口显示同一四段版本号）----
        self._version_label = QLabel(f"版本 {self._app_version}")
        root.addWidget(self._version_label)

        # 初始状态：调试模式关闭，五项调试子控件全部禁用
        self._debug_check.toggled.connect(self._on_debug_toggled)
        self._set_debug_widgets_enabled(False)

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
            # 同步界面模式与挂件环配置（这两个状态都不持久化）
            self.sync_layout_mode(self._panel.layout_mode())
            self.sync_slot_combos()
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
            self._auto_dock_check.setEnabled(widget and self._auto_dock_available)
            self._auto_dock_mode_hint.setVisible(not widget)
        except Exception:
            traceback.print_exc()

    def _fill_slot_combo(self, combo, current: str, exclude: str) -> None:
        """填一个下拉：可选 = 池里除"另一个槽已选项"之外的 2 项。"""
        combo.blockSignals(True)
        combo.clear()
        for key, label in SLOT_POOL_ITEMS:
            if key == exclude:
                continue
            combo.addItem(label, key)
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _refresh_slot_combos(self) -> None:
        """按主窗口当前配置刷新两个下拉（各自排除另一个槽已选项）。"""
        try:
            keys = self._panel.slot_keys()
            slot1, slot3 = keys[1], keys[3]
            self._fill_slot_combo(self._slot1_combo, slot1, exclude=slot3)
            self._fill_slot_combo(self._slot3_combo, slot3, exclude=slot1)
        except Exception:
            traceback.print_exc()

    def sync_slot_combos(self) -> None:
        """供主窗口 set_slot_config 反向同步下拉（例如恢复默认后）。"""
        self._refresh_slot_combos()

    def _on_slot_combo_changed(self, _index: int = 0) -> None:
        """任一下拉变更：立即刷新另一个下拉并应用新配置。"""
        try:
            k1 = self._slot1_combo.currentData()
            k3 = self._slot3_combo.currentData()
            if not k1 or not k3 or k1 == k3:
                return
            if self._panel.set_slot_config(["cpu", k1, "gpu", k3, "settings"]):
                self._refresh_slot_combos()
        except Exception:
            traceback.print_exc()

    def _on_reset_slots(self) -> None:
        """恢复默认：内存 + C盘。"""
        try:
            if self._panel.set_slot_config(["cpu", "mem", "gpu", "disk", "settings"]):
                self._refresh_slot_combos()
        except Exception:
            traceback.print_exc()

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
