# -*- coding: utf-8 -*-
"""VitalsRing（环脉）"设置与调试"窗口 —— 第一阶段第 3 轮。

职责：提供调试模式总开关、五项调试值、五项检测开关、GitHub 预留按钮。
约定：
- 只用 PyQt6 自带控件，不引入任何第三方库；
- 本窗口不创建任何定时器，关闭后不留刷新任务（刷新仍由主窗口那唯一的定时器负责）；
- 调试值不持久化：关闭窗口时清空，重新打开一律回到"调试模式关闭"。
"""
from __future__ import annotations

import traceback

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

# 预留：配置成真实仓库地址后，"打开 GitHub 仓库"按钮才会真正跳转。
# 为空时点击只提示"尚未配置"，不打开任何网页、也不崩溃。
GITHUB_REPO_URL = ""


class SettingsWindow(QDialog):
    """设置与调试窗口。

    注意：关闭（X / Esc）时必须复位调试状态并让主窗口恢复真实数据刷新，
    所以复位逻辑写成幂等的 _reset_on_close()，closeEvent 和 reject() 都会调用。
    """

    def __init__(self, reader, panel, app_version: str) -> None:
        super().__init__(panel)
        self._reader = reader
        self._panel = panel
        self._app_version = app_version

        self.setWindowTitle("设置与调试")
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ---- 只读显示系统版本（读取失败时就是"系统版本：读取失败"）----
        self._os_label = QLabel("系统版本：读取失败")
        root.addWidget(self._os_label)

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

        # ---- GitHub 预留按钮 ----
        self._github_btn = QPushButton("打开 GitHub 仓库")
        self._github_btn.clicked.connect(self._on_github)
        root.addWidget(self._github_btn)

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
        """刷新只读文案（系统版本、版本号）。"""
        self._os_label.setText(self._reader.os_text or "系统版本：读取失败")
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
        except Exception:
            traceback.print_exc()

    def closeEvent(self, event) -> None:
        """点 X 关闭：必须先复位调试状态，再交给基类处理。"""
        self._reset_on_close()
        super().closeEvent(event)

    def reject(self) -> None:
        """Esc 走 reject()，不会触发 closeEvent，因此这里也要复位一次。"""
        self._reset_on_close()
        super().reject()

    def _reset_on_close(self) -> None:
        """关闭窗口时复位：关调试模式、子控件置灰、主窗口立即恢复真实数据刷新。

        注意：本方法是幂等的——closeEvent 与 reject 都可能调用它，
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

    def _on_github(self) -> None:
        """打开 GitHub 仓库；地址为空时只提示，不跳转、不崩溃。"""
        try:
            if not GITHUB_REPO_URL.strip():
                QMessageBox.information(self, "提示", "GitHub 仓库尚未配置")
                return
            QDesktopServices.openUrl(QUrl(GITHUB_REPO_URL))
        except Exception:
            traceback.print_exc()
