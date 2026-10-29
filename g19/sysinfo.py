"""Collecte des infos système : CPU/RAM/réseau/disques via psutil, GPU via les compteurs PDH Windows
(mêmes compteurs que le Gestionnaire des tâches, donc compatibles AMD/NVIDIA/Intel)."""
import ctypes
import platform
import re
import time
import winreg
from collections import deque
from ctypes import wintypes

import psutil

# --- PDH (Performance Data Helper) -------------------------------------------------------------

_pdh = ctypes.WinDLL("pdh.dll")
PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2


class _Value(ctypes.Union):
    _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double),
                ("largeValue", ctypes.c_longlong)]


class _FmtValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("v", _Value)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", _FmtValue)]


for _fn in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData",
            "PdhGetFormattedCounterArrayW"):
    getattr(_pdh, _fn).restype = ctypes.c_ulong


class PdhQuery:
    """Une requête PDH avec des compteurs à instances génériques (« * »)."""

    def __init__(self, paths):
        self.q = ctypes.c_void_p()
        if _pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.q)) != 0:
            raise OSError("PdhOpenQuery")
        self.counters = {}
        for key, path in paths.items():
            c = ctypes.c_void_p()
            if _pdh.PdhAddEnglishCounterW(self.q, path, 0, ctypes.byref(c)) == 0:
                self.counters[key] = c
        _pdh.PdhCollectQueryData(self.q)

    def collect(self):
        _pdh.PdhCollectQueryData(self.q)
        return {k: self._array(c) for k, c in self.counters.items()}

    @staticmethod
    def _array(counter):
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        fmt = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        if _pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size),
                                             ctypes.byref(count), None) != PDH_MORE_DATA:
            return {}
        buf = (ctypes.c_byte * size.value)()
        if _pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size),
                                             ctypes.byref(count), buf) != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_Item))
        return {items[i].szName: items[i].FmtValue.v.doubleValue for i in range(count.value)}


# --- Infos statiques ---------------------------------------------------------------------------

def _gpu_info():
    """(nom, VRAM totale en octets) de la plus grosse carte, depuis le registre."""
    best = ("GPU", 0)
    cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls)
    except OSError:
        return best
    for i in range(64):
        try:
            sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
        except OSError:
            break
        try:
            mem, _ = winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")
            if isinstance(mem, bytes):
                mem = int.from_bytes(mem, "little")
            name, _ = winreg.QueryValueEx(sub, "DriverDesc")
            if mem > best[1]:
                best = (name, mem)
        except OSError:
            pass
    return best


def _cpu_name():
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name = winreg.QueryValueEx(k, "ProcessorNameString")[0]
    except OSError:
        name = platform.processor()
    name = re.sub(r"\(R\)|\(TM\)|CPU|Processor|\d+-Core|@.*", "", name, flags=re.I)
    return " ".join(name.replace("AMD ", "").replace("Intel ", "").split())


def _short_gpu(name):
    for prefix in ("AMD Radeon ", "NVIDIA GeForce ", "NVIDIA ", "Intel(R) ", "AMD "):
        name = name.replace(prefix, "")
    return name


# --- Collecteur --------------------------------------------------------------------------------

class SystemStats:
    HISTORY = 60

    def __init__(self):
        self.cpu_name = _cpu_name()
        gpu_name, self.vram_total = _gpu_info()
        self.gpu_name = _short_gpu(gpu_name)
        self.cpu_hist = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.gpu_hist = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.cpu = 0.0
        self.cores = []
        self.gpu = 0.0
        self.vram_used = 0
        self.ram = psutil.virtual_memory()
        self.net_down = self.net_up = 0.0
        self.disk_read = self.disk_write = 0.0
        self.disks = []
        self.boot = psutil.boot_time()
        try:
            self._pdh = PdhQuery({
                "util": r"\GPU Engine(*)\Utilization Percentage",
                "mem": r"\GPU Adapter Memory(*)\Dedicated Usage",
            })
        except OSError:
            self._pdh = None
        psutil.cpu_percent(percpu=True)
        self._net = psutil.net_io_counters()
        self._disk = psutil.disk_io_counters()
        self._t = time.monotonic()
        self._disk_t = 0.0

    def sample(self):
        now = time.monotonic()
        dt = max(now - self._t, 1e-3)
        self._t = now

        self.cores = psutil.cpu_percent(percpu=True)
        self.cpu = sum(self.cores) / len(self.cores)
        self.cpu_hist.append(self.cpu)
        self.ram = psutil.virtual_memory()

        net = psutil.net_io_counters()
        self.net_down = (net.bytes_recv - self._net.bytes_recv) / dt
        self.net_up = (net.bytes_sent - self._net.bytes_sent) / dt
        self._net = net

        disk = psutil.disk_io_counters()
        if disk and self._disk:
            self.disk_read = (disk.read_bytes - self._disk.read_bytes) / dt
            self.disk_write = (disk.write_bytes - self._disk.write_bytes) / dt
        self._disk = disk

        if now - self._disk_t > 30:  # l'occupation disque bouge peu
            self._disk_t = now
            self.disks = []
            for part in psutil.disk_partitions():
                if "fixed" in part.opts or part.fstype:
                    try:
                        u = psutil.disk_usage(part.mountpoint)
                    except OSError:
                        continue
                    self.disks.append((part.mountpoint.rstrip("\\"), u.percent))

        if self._pdh:
            data = self._pdh.collect()
            engines = {}
            for name, val in data.get("util", {}).items():
                m = re.search(r"(luid_\w+?_phys_\d+_eng_\d+)", name)
                if m:
                    engines[m.group(1)] = engines.get(m.group(1), 0.0) + val
            self.gpu = min(max(engines.values(), default=0.0), 100.0)
            self.vram_used = max(data.get("mem", {}).values(), default=0)
        self.gpu_hist.append(self.gpu)

    @property
    def uptime(self):
        return time.time() - self.boot
