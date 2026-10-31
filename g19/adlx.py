"""FPS du jeu au premier plan mesurés par le pilote AMD (ADLX, amdadlx64.dll), sans rien injecter
dans le jeu : utile quand RTSS ne peut pas s'y accrocher (CS2 en mode de confiance, anti-triche…).

ADLX est une API C++ ; on appelle ses tables de méthodes virtuelles directement (indices tirés
des en-têtes du SDK : ISystem.h, IPerformanceMonitoring.h)."""
import ctypes
import threading
import time
from ctypes import POINTER, byref, c_int, c_int64, c_long, c_uint64, c_void_p

RETRY = 60              # s avant de retenter si ADLX n'a pas pu démarrer
STALE_MS = 3000         # mesure plus vieille : le jeu ne rend plus d'images

# IADLXInterface : 0 Acquire, 1 Release, 2 QueryInterface
_RELEASE = 1
_SYS_PERF_SERVICES = 9      # IADLXSystem::GetPerformanceMonitoringServices
_PERF_CURRENT_FPS = 20      # IADLXPerformanceMonitoringServices::GetCurrentFPS
_FPS_TIMESTAMP, _FPS_VALUE = 3, 4   # IADLXFPS::TimeStamp, ::FPS


def _method(obj, index, *argtypes, res=c_int):
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return ctypes.CFUNCTYPE(res, c_void_p, *argtypes)(vtable[index])


class AmdFps:
    def __init__(self):
        self._perf = None
        self._failed_at = None
        self._last = None           # (horodatage ADLX, moment local où il a changé)
        self._lock = threading.Lock()

    def _start(self):
        if self._failed_at and time.time() - self._failed_at < RETRY:
            return False
        try:
            dll = ctypes.CDLL("amdadlx64.dll")
            ver = c_uint64()
            if dll.ADLXQueryFullVersion(byref(ver)) != 0:
                raise OSError("version ADLX illisible")
            system = c_void_p()
            if dll.ADLXInitialize(ver, byref(system)) != 0 or not system:
                raise OSError("ADLX non initialisé")
            perf = c_void_p()
            if _method(system, _SYS_PERF_SERVICES, POINTER(c_void_p))(system, byref(perf)) != 0 \
                    or not perf:
                raise OSError("suivi des performances indisponible")
            self._perf = perf
            return True
        except (OSError, AttributeError):
            self._failed_at = time.time()       # pas de carte / pilote AMD
            return False

    def fps(self):
        """FPS actuels du jeu suivi par le pilote, ou None (pas de pilote AMD, pas de jeu)."""
        with self._lock:
            if self._perf is None and not self._start():
                return None
            m = c_void_p()
            if _method(self._perf, _PERF_CURRENT_FPS, POINTER(c_void_p))(self._perf, byref(m)) != 0 \
                    or not m:
                return None
            try:
                v, ts = c_int(), c_int64()
                if _method(m, _FPS_VALUE, POINTER(c_int))(m, byref(v)) != 0:
                    return None
                _method(m, _FPS_TIMESTAMP, POINTER(c_int64))(m, byref(ts))
            finally:
                _method(m, _RELEASE, res=c_long)(m)
            now = time.time()
            if not self._last or self._last[0] != ts.value:
                self._last = (ts.value, now)
            elif (now - self._last[1]) * 1000 > STALE_MS:
                return None
            return v.value if v.value > 0 else None


if __name__ == "__main__":
    a = AmdFps()
    for _ in range(5):
        print(a.fps())
        time.sleep(1)
