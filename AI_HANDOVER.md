# VitalsRing AI 交接档案

> 交接时间：2026-10-21　最新提交：`b9c9cc6`　版本：`0.10.06.07`

## 1. 项目基本盘

- 项目名：**VitalsRing（环脉）**
- 当前版本：**0.10.06.07**（规则：`0.10.轮次.修改次数`）
- 团队代号：发起与全局引导 **BTLurenJun** / AI 架构 **鲸鱼（Whale）** / 代码实现 **闪电（Flash）** / 代码审查 **大白鲨（Shark）**
- 仓库：https://github.com/BTLurenJun/VitalsRing
- 运行：双击 `启动.bat`（GBK + CRLF，**禁止修改**）；或 `.\.venv\Scripts\python.exe main.py`
- 依赖白名单：`PyQt6 / psutil / pynvml`，禁止 pywin32 等新增依赖

## 2. 代码架构

| 文件 | 职责 |
| --- | --- |
| `main.py` | 程序入口、主窗口（无边框 Tool 窗口）、全部 QPainter 绘制、双模式（widget/panel）、任务栏吸附、Win32 只读调用、详情窗口、设置锁读写、`CREDITS` 常量 |
| `readers.py` | 数据读取层：`ItemData` 契约、`SystemReader`（CPU/内存/GPU/C盘/总盘/动态磁盘/电池/开机时长/系统版本）、调试值与检测开关叠加、GPU 降级链（pynvml → nvidia-smi） |
| `settings_window.py` | “设置与调试”窗口：界面模式、调试滑块与检测开关、5 槽位下拉、外观、吸附、设置锁、恢复默认动画、关于/制作人员、Tooltip |

`vitalsring_config.json` 运行时生成于项目根目录，已加入 `.gitignore`，严禁入库。

## 3. 核心红线（绝对不能动）

1. 无边框 + Tool + 置顶窗口（`FramelessWindowHint | Tool | WindowStaysOnTopHint | WindowDoesNotAcceptFocus`），`WA_QuitOnClose=True`。
2. `WA_NoSystemBackground` **绝不能设为 False**（实测会破坏透明，整窗 alpha=255）。
3. 挂件 `paintEvent` 分支最顶端无条件 `fillRect(rect, QColor(0,0,0,1))`——alpha=1 防边缘点击穿透到任务栏。
4. 三枪置顶：mousePress 立即 `_raise_above_taskbar()` + `singleShot(120/500)` 两次 `force=True`；去重窗口 100ms。
5. `_auto_dock_enabled` 只能由用户或 `AUTO_DOCK_ENABLED` 修改；拖动只解除 `_docked`。
6. 禁止新增依赖；所有 Win32 调用必须声明 `argtypes/restype`、try/except、只读或仅作用于本窗口。
7. `vitalsring_config.json` 必须在 `.gitignore`；`启动.bat`、`.venv` 禁止改动/跟踪。
8. 版本号四处同步：`APP_VERSION`、主窗口、设置窗口、README。
9. `paintEvent` 零 Win32、零 I/O；定时器只复用（刷新 2000ms、吸附检查 4000ms）。
10. 环形区不出现数字；红叉不盖中心文字；齿轮不写文字。

## 4. 踩坑记录（防止新分身乱改）

- **详情窗口写死五项**：曾被用户严厉批评。现在 `DetailWindow.content_lines()` 严格按 `panel.slot_keys()` 动态生成，`gear` 跳过；改回固定列表会立刻回归 bug。
- **槽位切换弧长“不动”**：必须保证 `_draw_widget()` 用 `reader.slot_item(key)`；`_read_disks()` 更新的是 `slot_items` 里的同一对象；`set_slot_config()` 后要 `update()`。实测量化验证方式：统计环带内 alpha=255 像素或打印 `span`。
- **调试滑块只覆盖五项**：现在 `apply_state()` 遍历 `items + extra_items`，调试值能接管 `disk_d/disk_total`；改回只遍历 `items` 会让动态磁盘无法调试。
- **下拉框重建丢失/变空白**：`_fill_slot_combo()` 的 `blockSignals(True/False)` 必须在 `try/finally`；找不到当前值时回退 index 0；每个下拉 `setMinimumWidth(120)`。
- **配置解锁顺序漏洞**：`reset_appearance()` 必须先 `set_settings_locked(False)` 再改其它项，最后强制 `_save_config()`，保证 `lock_state=false` + 默认值落盘；解锁后重启必须回默认。
- **动态磁盘枚举缓存**：`psutil.disk_partitions()` 只在 `SystemReader.__init__` 枚举一次；`_read_disks()` 每 10 秒才真正读一次 `disk_usage`，避免休眠外置硬盘阻塞 GUI。插拔硬盘/U 盘后需重启程序。
- **混合 DPI 拖动**：必须增量 `move(pos + delta)`，禁止固定 offset 绝对定位；`_keep_on_screen()` 在 widget+docked 时直接 return，未吸附挂件用 `screen.geometry()`。
- **置顶被任务栏压住**：三枪必须保留；`_raise_above_taskbar` 的 100ms 去重不能改回 1 秒，否则延迟枪会被吞。
- **Qt 未捕获事件异常会直接杀进程**：事件/定时器/绘制回调必须 try/except，`nativeEvent` 不要调用 `super()`。

## 5. 当前配置与界面状态

- 挂件 188×44，吸附任务栏左侧 `(4,1394,188,44)`（2560×1440 本机）。
- 默认槽位：`["cpu", "gpu", "mem", "disk_c", "gear"]`。
- 齿轮位：与数据环共用 `_widget_ring_style()` 的底环颜色/粗细；齿轮直径 `0.55d`、实心布尔路径、中心镂空、无文字、颜色取环中心文字色。
- 刻度默认关闭（`_show_ticks=False`），可在设置「外观」开启。
- 动态数据池：`cpu / gpu / mem / disk_c / disk_total(总盘) / disk_d… / battery / gear`；5 槽全可配、互不重复；设置窗口 5 个下拉动态互斥。
- 调试滑块数量 = 数据池除 gear 外的全部项（本机 7 个），`disk_d / disk_total` 可调试。
- 设置锁：🔒/🔓 顶部按钮；锁上立即写 JSON，解锁写 `lock_state=false` 并在重启回默认。
- 恢复默认设置：淡出 200ms → 重置 → 淡入 200ms，最终 `widget / 刻度关 / 默认槽位 / 吸附开 / 检测全开 / 锁解开`。
- 两个恢复按钮：`SP_BrowserReload` 16×16 图标 + Tooltip。
- 设置窗口与挂件不重叠；详情窗口按槽位动态展示，并使用窗口所在屏幕定位（支持副屏）。
- 大面板模式：固定五项（CPU/内存/GPU/C盘/电池），保留环形/文字切换、折叠、缩放手柄、齿轮按钮。

## 6. 接手步骤建议

1. 先 `git status` 确认干净，`git log --oneline -3` 确认 `b9c9cc6`。
2. 改任何 UI 前先跑一次 `python -m py_compile main.py readers.py settings_window.py`。
3. 验证数据链路时优先打印 `slot_item(key).value / name`、`span`、环带 alpha 像素，不要只靠肉眼。
4. 用户要求“只报告，不要改代码”时严格停下；提交/推送前必须逐项核对，禁止 force push / reset --hard / clean。
