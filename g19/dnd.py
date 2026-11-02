"""« Ne pas déranger » de Windows, piloté depuis le G19.

Windows 11 n'a pas d'API publique pour la case « Ne pas déranger » elle-même ; elle est en
revanche activée par une session de concentration (horloge → Concentration), qui a une API
officielle : Windows.UI.Shell.FocusSessionManager. Démarrer une session coupe les bannières de
notification ; l'arrêter les rétablit.

La case elle-même se lit dans l'état WNF WNF_SHEL_QUIETHOURS_ACTIVE_PROFILE_CHANGED :
0 = désactivé, 1 / 2 = activé (vérifié sur Windows 11 : change dès le clic)."""
import ctypes
import threading
import time

try:
    from winrt.windows.ui.shell import FocusSessionManager
except ImportError:
    FocusSessionManager = None

POLL = 1        # s entre deux lectures de l'état (il peut changer depuis Windows)
WNF_QUIET_HOURS = 0x0D83063EA3BF1C75


def quiet_hours():
    """Profil « Ne pas déranger » de Windows (0 = désactivé), ou None s'il est illisible."""
    try:
        state, stamp = ctypes.c_uint64(WNF_QUIET_HOURS), ctypes.c_ulong()
        buf, size = (ctypes.c_ubyte * 8)(), ctypes.c_ulong(8)
        status = ctypes.windll.ntdll.NtQueryWnfStateData(
            ctypes.byref(state), None, None, ctypes.byref(stamp), buf, ctypes.byref(size))
        if status != 0 or size.value < 4:
            return None
        return int.from_bytes(bytes(buf[:4]), "little")
    except (AttributeError, OSError):
        return None


class DoNotDisturb:
    def __init__(self):
        self.supported = False
        self.active = False
        self.event = None          # (titre, texte, horodatage) : changé depuis le G19
        self._manager = None
        self._wake = threading.Event()
        self._want = None          # True / False : bascule demandée
        threading.Thread(target=self._run, daemon=True, name="ne pas déranger").start()

    def _read(self):
        """Activé par la case de Windows, ou par une session de concentration."""
        focus = bool(self._manager and self._manager.is_focus_active)
        return focus or bool(quiet_hours())

    def toggle(self):
        """Bascule demandée depuis le G19 (appliquée dans le fil, sans bloquer l'écran)."""
        self._want = not self.active
        self._wake.set()

    def _run(self):
        try:
            if FocusSessionManager is not None and FocusSessionManager.is_supported:
                self._manager = FocusSessionManager.get_default()
        except Exception:
            self._manager = None
        # sans la session de concentration, on lit quand même la case (sans la piloter)
        self.supported = self._manager is not None
        if not self.supported and quiet_hours() is None:
            return
        while True:
            try:
                if self._want is not None and self._manager:
                    want, self._want = self._want, None
                    if want:
                        self._manager.try_start_focus_session()
                    else:
                        self._manager.deactivate_focus()
                    time.sleep(0.3)
                    self.active = self._read()
                    self.event = ("Ne pas déranger " + ("activé" if self.active else "désactivé"),
                                  "notifications en pause" if self.active
                                  else "les notifications reprennent", time.time())
                else:
                    self.active = self._read()
            except Exception:
                pass
            if self._wake.wait(POLL):
                self._wake.clear()
