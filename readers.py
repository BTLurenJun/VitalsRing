# -*- coding: utf-8 -*-
"""VitalsRing（环脉）数据读取层。

职责：只读采集 CPU / 内存 / GPU / C 盘 / 电池 / 开机时长 / 系统版本。
约定：
- 本模块不做任何界面绘制，实现"数据读取与界面绘制分离"（总需求第三条）；
- 所有异常在内部消化，转成"失败状态 + 原因"，保证界面永不崩溃；
- 不修改系统设置、不写注册表、不删除文件、不访问项目根目录之外的路径。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Optional

import psutil

# 状态常量：界面层据此决定是否画红叉、以及显示什么原因（总需求第八条）
STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_UNSUPPORTED = "unsupported"
STATUS_NO_BATTERY = "no_battery"
STATUS_DISABLED = "disabled"  # 第 3 轮"检测已关闭"使用，本轮先预留，避免后续重构绘制逻辑


@dataclass
class ItemData:
    """单个指标的统一数据结构，是读取层与界面层之间的唯一契约。

    这样设计的目的是：第 3 轮加入"检测已关闭"等新状态时，界面绘制代码无需改动。
    """

    key: str                                # 内部标识：cpu / mem / gpu / disk / battery
    name: str                               # 环中心显示的名称（不含任何数字）
    value: Optional[float] = None           # 占用率 0~100，失败时为 None
    status: str = STATUS_OK                 # 见上方状态常量
    reason: Optional[str] = None            # 失败原因文案：读取失败 / 不支持 / 无电池 / 检测已关闭
    charging: bool = False                  # 仅电池使用：是否正在充电

    @property
    def is_ok(self) -> bool:
        """是否处于可正常显示的状态（有值且无错误）。"""
        return self.status == STATUS_OK and self.value is not None


class GpuReader:
    """GPU 占用率读取器：优先 pynvml，其次 nvidia-smi。

    重要约定（总需求第三、九条）：
    - pynvml 只在构造时初始化一次并缓存句柄，绝不在每 2 秒的刷新里重复初始化；
    - 只有"找不到 nvidia-smi"（FileNotFoundError）才判定为"不支持"并永久缓存；
      nvidia-smi 返回非 0、超时等一律按瞬时"读取失败"处理，拉长间隔后重试；
    - nvidia-smi 需要启动子进程（属于偏耗时的调用），因此加超时并降到 10 秒刷新一次。
    """

    NVML_INTERVAL = 2.0        # pynvml 读取很轻，跟随主刷新节奏（2 秒）
    SMI_INTERVAL = 10.0        # nvidia-smi 较重，降频，减少对主界面流畅度的影响
    SMI_RETRY_INTERVAL = 60.0  # nvidia-smi 瞬时失败后的重试间隔，避免反复启动子进程
    NVML_FAIL_LIMIT = 3        # NVML 连续失败达到该次数才降级，防止一次抖动就永久判死

    def __init__(self) -> None:
        self._pynvml = None                    # 缓存已成功初始化的 pynvml 模块
        self._handle = None                    # 缓存第 0 号 GPU 句柄
        self._backend = "none"                 # 当前可用的后端：nvml / smi / none
        self._final_reason = None              # 已确认"不支持"的终态原因（非空即不再探测）
        self._interval = self.NVML_INTERVAL
        self._last_probe = -1e9                # 负无穷大，保证首次刷新立即探测一次
        self._nvml_fail_count = 0              # NVML 连续失败计数（成功一次即清零）
        self._cached_value: Optional[float] = None
        self._cached_status = STATUS_UNSUPPORTED
        self._cached_reason: Optional[str] = "不支持"
        self._init_nvml()

    def _init_nvml(self) -> None:
        """初始化 pynvml：只执行一次，成败都缓存，避免每 2 秒重复初始化。"""
        try:
            # pynvml 这个包名自身会打印一条"已弃用，建议改用 nvidia-ml-py"的 FutureWarning；
            # 这里只屏蔽这一条告警，避免控制台出现让人误以为出错的提示，功能完全不受影响
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import pynvml                   # 延迟导入：未安装时不报错，程序照常运行
        except Exception:
            return                              # 没装 pynvml 属正常情况，改用 nvidia-smi 兜底
        try:
            pynvml.nvmlInit()                   # NVML 在进程内只需初始化一次，之后一直复用
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._pynvml = pynvml
            self._backend = "nvml"
        except Exception:
            # 有库但初始化失败（多为无 NVIDIA 显卡/驱动）：不缓存为终态，留给 nvidia-smi 一次机会
            self._pynvml = None
            self._backend = "none"

    def refresh(self, item: "ItemData", now: Optional[float] = None) -> None:
        """把最新的 GPU 状态写入传入的数据对象。

        就地更新（不新建对象），并且带自身刷新节流，减少无意义的重复探测。
        """
        # 用 time.monotonic()（单调时钟）而不是 time.time()：不受用户改系统时间影响，
        # 保证刷新节流的时间差计算不会被时钟跳变打乱
        now = time.monotonic() if now is None else now
        if self._final_reason is None and now - self._last_probe >= self._interval:
            # 先记时间再探测：探测可能耗时（nvidia-smi 要起子进程），
            # 先赋值可避免这段耗时期间被重复触发
            self._last_probe = now
            self._probe()
        item.value = self._cached_value
        item.status = self._cached_status
        item.reason = self._cached_reason
        item.charging = False

    def _probe(self) -> None:
        """真正探测一次 GPU 占用率，结果写入内部缓存。"""
        # 第一步：优先使用 pynvml（构造时已初始化，这里只做读取）
        if self._backend == "nvml":
            try:
                util = self._pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            except Exception:
                # 单次失败可能只是驱动忙、GPU 重置等瞬时抖动，所以先计数：
                # 连续失败达到上限才降级到 nvidia-smi，避免一次抖动就把 GPU 显示永久锁死
                self._nvml_fail_count += 1
                if self._nvml_fail_count >= self.NVML_FAIL_LIMIT:
                    self._backend = "none"
                self._cache(STATUS_FAILED, None, "读取失败")
                return
            self._nvml_fail_count = 0          # 读数成功即清零，保证计数统计的是"连续"失败
            self._cache(STATUS_OK, float(util.gpu), None)
            return
        # 第二步：nvidia-smi 兜底
        value, reason = self._run_smi()
        if value is None:
            if reason == "不支持":
                # 连 nvidia-smi 都找不到：确认本机没有 NVIDIA 环境，永久缓存，不再重试
                self._final_reason = reason
                self._cache(STATUS_UNSUPPORTED, None, reason)
            else:
                # 超时/异常等瞬时失败：不写终态，把间隔拉长到 60 秒后再试一次，
                # 既满足"失败不反复重试"，又不会被一次抖动永久判死
                self._interval = self.SMI_RETRY_INTERVAL
                self._cache(STATUS_FAILED, None, reason)
            return
        self._backend = "smi"                  # nvidia-smi 可用，但按降频间隔刷新
        self._nvml_fail_count = 0              # 已切换后端，清空 NVML 失败计数
        self._interval = self.SMI_INTERVAL
        self._cache(STATUS_OK, value, None)

    def _cache(self, status: str, value: Optional[float], reason: Optional[str]) -> None:
        """缓存本次探测结果，供后续刷新直接复用。"""
        self._cached_status = status
        self._cached_value = value
        self._cached_reason = reason

    @staticmethod
    def _run_smi():
        """调用 nvidia-smi 读取占用率，返回 (数值或 None, 失败原因或 None)。

        注意：该调用发生在 GUI 线程里，超时必须短——否则一旦 nvidia-smi 卡住，
        整个界面都会跟着卡顿，所以这里只给 1 秒；失败后由上层决定降频或不再重试。
        """
        cmd = ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
        try:
            # CREATE_NO_WINDOW 是 Windows 的进程创建标志位，用于避免弹出黑色控制台窗口
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=1.0, creationflags=flags
            )
        except FileNotFoundError:
            return None, "不支持"                # 找不到 nvidia-smi：本机没有 NVIDIA 驱动环境
        except subprocess.TimeoutExpired:
            return None, "读取失败"              # 超时直接判失败，不再重试
        except Exception:
            return None, "读取失败"
        if proc.returncode != 0:
            # 注意：不能把非 0 返回当作"不支持"——混合显卡笔记本的独显休眠时，
            # nvidia-smi 常返回非 0；若写成"不支持"会被上层缓存成永久终态，
            # 之后独显唤醒也不会再恢复显示。这里按瞬时失败处理，允许 60 秒后重试。
            return None, "读取失败"
        try:
            return float(proc.stdout.strip().splitlines()[0]), None
        except Exception:
            return None, "读取失败"


class SystemReader:
    """系统信息读取器：一次 refresh() 采集全部指标，界面层整体消费。

    性能要点：除 GPU 外的读取都是很轻的调用；GPU 有独立缓存与降频策略，
    因此每 2 秒调用一次 refresh() 不会造成明显占用。
    """

    def __init__(self) -> None:
        self.gpu_reader = GpuReader()
        # 大面板/详情固定五项：CPU、内存、GPU、C盘、电池（顺序不得随意调整）
        # 注意：C 盘 key 由旧版 "disk" 改为 "disk_c"，与挂件槽位命名统一。
        self.items = [
            ItemData("cpu", "CPU"),
            ItemData("mem", "内存"),
            ItemData("gpu", "GPU"),
            ItemData("disk_c", "C盘"),
            ItemData("battery", "电池"),
        ]
        self._items_by_key = {item.key: item for item in self.items}

        # ---- 第六轮：挂件槽位的动态数据池 ----
        # 磁盘枚举只在构造时做一次并缓存：psutil.disk_partitions() 要枚举卷，
        # 若放进每 2 秒的 refresh() 会明显抬高 CPU；刷新时只对缓存里的挂载点调 disk_usage()。
        self._disk_partitions = self._enumerate_fixed_partitions()
        # disk_total 聚合所有固定磁盘；其余固定盘按盘符单独成项（disk_d / disk_e ...）
        # 名称用"总盘"而不是"总盘"：挂件小环只有 34px，三字名容易溢出环外
        self.extra_items = [ItemData("disk_total", "总盘")]
        seen_keys = {item.key for item in self.extra_items}
        for key, label, _mount in self._disk_partitions:
            if key == "disk_c" or key in seen_keys:
                continue
            self.extra_items.append(ItemData(key, label))
            seen_keys.add(key)
        # 槽位 key -> ItemData（五项固定 + 总盘 + 动态磁盘）；gear 由界面层单独绘制
        self.slot_items = dict(self._items_by_key)
        for item in self.extra_items:
            self.slot_items[item.key] = item
        # 槽位选项顺序：cpu → gpu → mem → disk_c → disk_total → disk_d… → battery
        self._slot_order = ["cpu", "gpu", "mem", "disk_c", "disk_total"]
        for key, _label, _mount in self._disk_partitions:
            if key != "disk_c" and key not in self._slot_order:
                self._slot_order.append(key)
        self._slot_order.append("battery")

        # 两个文本行的初始值与读取失败时的文案保持一致
        self.boot_text = "开机时长：读取失败"
        self.os_text = "系统版本：读取失败"

        # 第 3 轮新增：检测开关与调试值
        # enabled: 每项是否启用检测（默认全开），关闭后该环显示"检测已关闭"
        self.enabled = {item.key: True for item in self.items}
        # debug_active: 调试模式总开关状态；调试值只在该开关打开时生效，且不持久化
        self.debug_active = False
        # debug_values: key -> 0~100 的调试值，仅在点"应用调试值"后填入
        self.debug_values = {}
        # _real_snapshot: 最近一次真实读取的结果，用于"恢复真实值"和关闭调试时立即还原
        self._real_snapshot = {}
        # 磁盘读取降频时间戳：磁盘（尤其休眠中的外置硬盘）可能让 disk_usage() 阻塞，
        # 因此最多 10 秒真正读一次，其余 2 秒刷新沿用上次缓存值，避免卡住 GUI。
        self._last_disk_read = 0.0

    @staticmethod
    def _drive_letter(mountpoint: str):
        """从挂载点取盘符：Windows 的 "D:\\" → "D"；取不到返回 None。"""
        try:
            drive, _ = os.path.splitdrive(mountpoint or "")
            if drive and len(drive) >= 2 and drive[1] == ":":
                return drive[0].upper()
        except Exception:
            pass
        return None

    def _enumerate_fixed_partitions(self):
        """枚举固定磁盘并缓存，返回 [(key, 显示名, 挂载点)]。

        过滤规则（总需求第六轮）：
        - 光驱：opts 含 cdrom → 跳过；
        - 可移动盘：opts 含 removable → 跳过；
        - fstype 为空 → 跳过；
        - C 盘单独用 disk_c 表示，其余按 disk_{盘符小写} 命名（如 disk_d）。
        本函数只在构造时调用一次，刷新时不会重复枚举，避免抬高 CPU。
        """
        result = []
        seen = set()
        try:
            parts = psutil.disk_partitions(all=False)
        except Exception:
            parts = []
        for part in parts:
            try:
                opts = (getattr(part, "opts", "") or "").lower()
                if "cdrom" in opts or "removable" in opts:
                    continue
                if not (getattr(part, "fstype", "") or "").strip():
                    continue
                letter = self._drive_letter(getattr(part, "mountpoint", ""))
                if letter is None:
                    continue
                key = "disk_c" if letter == "C" else f"disk_{letter.lower()}"
                if key in seen:
                    continue
                label = "C盘" if letter == "C" else f"{letter}盘"
                result.append((key, label, part.mountpoint))
                seen.add(key)
            except Exception:
                continue
        # 兜底：psutil 没列出 C 盘时也要保证 C 盘可读，否则 disk_c 会永远没有数据
        if "disk_c" not in seen:
            result.insert(0, ("disk_c", "C盘", "C:\\"))
        return result

    def available_slot_items(self):
        """设置窗口用：返回全部可选槽位项 [(key, 显示名)]，最后附加齿轮。"""
        labels = {item.key: item.name for item in self.items}
        labels.update({item.key: item.name for item in self.extra_items})
        out = [(key, labels.get(key, key)) for key in self._slot_order]
        out.append(("gear", "齿轮"))
        return out

    def available_slot_keys(self):
        """全部可选槽位 key（含 gear），供 main.py 校验配置。"""
        return [key for key, _label in self.available_slot_items()]

    def slot_item(self, key: str):
        """按槽位 key 取数据对象；gear 不是数据项，返回 None。"""
        return self.slot_items.get(key)

    def refresh(self) -> None:
        """刷新全部指标；失败只更新数据对象状态，不抛异常、不重建界面控件。"""
        self._read_cpu(self._items_by_key["cpu"])
        self._read_memory(self._items_by_key["mem"])
        self.gpu_reader.refresh(self._items_by_key["gpu"])
        self._read_disks()                 # C 盘 + 总盘 + 动态磁盘一次算完
        self._read_battery(self._items_by_key["battery"])
        self._read_boot_text()
        self._read_os_text()
        # 读取完先存一份真实快照，再叠加"检测关闭/调试值"。
        # 注意：快照必须覆盖全部数据项（固定五项 + 动态磁盘 + 总盘），
        # 否则调试模式无法接管 D盘/总盘，切换后也拿不到真实值。
        self._real_snapshot = {
            item.key: (item.value, item.status, item.reason, item.charging)
            for item in (list(self.items) + list(self.extra_items))
        }
        self.apply_state()

    def apply_state(self) -> None:
        """把"检测开关 + 调试值"叠加到真实快照上，得到当前应显示的数据。

        优先级：检测关闭 > 调试值 > 真实数据。
        注意：检测关闭时该项调试值不生效（总需求：检测关闭时调试值不生效），
        因此必须先判 enabled，再判 debug_values。
        """
        # 遍历全部数据项：固定五项 + 动态磁盘 + 总盘。
        # 动态项不在 enabled 字典里（默认 True），但必须同样受调试值接管，
        # 否则在调试模式里拉 D盘/总盘滑块，挂件弧长不会跟着变。
        for item in (list(self.items) + list(self.extra_items)):
            if not self.enabled.get(item.key, True):
                item.value = None
                item.status = STATUS_DISABLED
                item.reason = "检测已关闭"
                item.charging = False
                continue
            if self.debug_active and item.key in self.debug_values:
                item.value = float(self.debug_values[item.key])
                item.status = STATUS_OK
                item.reason = None
                item.charging = False          # 调试值不保留充电语义，避免出现"假充电"配色
                continue
            real = self._real_snapshot.get(item.key)
            if real is not None:
                item.value, item.status, item.reason, item.charging = real

    def real_value(self, key: str) -> int:
        """取最近一次真实读数（0~100 整数），供设置窗口把滑块初始化到当前值。"""
        real = self._real_snapshot.get(key)
        if real is None or real[0] is None:
            return 0
        return int(round(float(real[0])))

    @staticmethod
    def _set(item: ItemData, value: Optional[float], status: str,
             reason: Optional[str] = None, charging: bool = False) -> None:
        """就地更新指标对象：避免每次刷新新建对象（总需求第三条）。"""
        item.value = value
        item.status = status
        item.reason = reason
        item.charging = charging

    def _read_cpu(self, item: ItemData) -> None:
        """读取 CPU 总占用率。

        注意：interval=None 表示非阻塞——用两次调用之间的时间差计算占用率，
        不会像 interval=1 那样阻塞线程，因此适合放在 2 秒定时刷新里。
        另外，interval=None 的第一次调用因为没有历史采样，会返回 0.0，
        所以首帧显示 0% 属于正常现象（不是读取失败），2 秒后即为真实数值。
        """
        try:
            self._set(item, float(psutil.cpu_percent(interval=None)), STATUS_OK)
        except Exception:
            self._set(item, None, STATUS_FAILED, "读取失败")

    def _read_memory(self, item: ItemData) -> None:
        """读取物理内存使用率。"""
        try:
            self._set(item, float(psutil.virtual_memory().percent), STATUS_OK)
        except Exception:
            self._set(item, None, STATUS_FAILED, "读取失败")

    def _read_disks(self) -> None:
        """读取所有固定磁盘：C 盘、总盘、动态磁盘一次算完。

        注意：
        - 挂载点列表来自构造时的缓存，这里只做轻量的 psutil.disk_usage() 调用；
        - 单个磁盘不可读只影响它自己（显示红叉），不拖累其它磁盘；
        - 总盘 = 所有固定磁盘 used 之和 / total 之和，只用只读的容量信息。
        - 降频：距上次真正读取不足 10 秒就直接返回，沿用缓存值；
          避免休眠中的外置硬盘在 2 秒定时器回调里阻塞 GUI（插拔硬盘后需重启程序）。
        """
        now = time.monotonic()
        if now - self._last_disk_read < 10.0:
            return
        self._last_disk_read = now
        total_bytes = 0.0
        used_bytes = 0.0
        any_ok = False
        seen_c = False
        for key, _label, mount in self._disk_partitions:
            item = self.slot_items.get(key)
            if item is None:
                continue
            if key == "disk_c":
                seen_c = True
            try:
                usage = psutil.disk_usage(mount)
            except Exception:
                self._set(item, None, STATUS_FAILED, "读取失败")
                continue
            self._set(item, float(usage.percent), STATUS_OK)
            total_bytes += float(usage.total)
            used_bytes += float(usage.used)
            any_ok = True

        # 兜底：缓存里没有 C 盘（枚举失败）时单独读一次，保证 disk_c 不会永远空白
        if not seen_c:
            try:
                usage = psutil.disk_usage("C:\\")
                self._set(self._items_by_key["disk_c"], float(usage.percent), STATUS_OK)
                total_bytes += float(usage.total)
                used_bytes += float(usage.used)
                any_ok = True
            except Exception:
                self._set(self._items_by_key["disk_c"], None, STATUS_FAILED, "读取失败")

        total_item = self.slot_items["disk_total"]
        if any_ok and total_bytes > 0:
            percent = used_bytes / total_bytes * 100.0
            self._set(total_item, max(0.0, min(100.0, percent)), STATUS_OK)
        else:
            self._set(total_item, None, STATUS_FAILED, "读取失败")

    def _read_battery(self, item: ItemData) -> None:
        """读取电池电量。

        台式机等无电池设备会返回 None：此时显示"无电池"（属于正常情况），
        而不是按"读取失败"处理，避免误导用户以为程序出错。
        """
        try:
            battery = psutil.sensors_battery()
        except Exception:
            self._set(item, None, STATUS_FAILED, "读取失败")
            return
        if battery is None:
            self._set(item, None, STATUS_NO_BATTERY, "无电池")
            return
        self._set(item, float(battery.percent), STATUS_OK, None, bool(battery.power_plugged))

    def _read_boot_text(self) -> None:
        """计算开机时长并格式化为中文文案。"""
        try:
            minutes = int((time.time() - psutil.boot_time()) // 60)
            self.boot_text = f"开机时长：{minutes // 60}小时{minutes % 60}分钟"
        except Exception:
            self.boot_text = "开机时长：读取失败"

    def _read_os_text(self) -> None:
        """读取 Windows 版本号。

        失败时只显示"读取失败"文字，不画红叉（总需求第十一条）。
        """
        try:
            # sys.getwindowsversion() 是 Python 标准库对 Win32 版本查询接口的封装，只读
            ver = sys.getwindowsversion()
            build = int(ver.build)
            if build >= 22000:
                name = "Windows 11"              # 内部版本号 22000 起为 Windows 11
            elif int(ver.major) == 10:
                name = "Windows 10"
            else:
                name = f"Windows {int(ver.major)}"
            self.os_text = f"系统版本：{name} {build}"
        except Exception:
            self.os_text = "系统版本：读取失败"
