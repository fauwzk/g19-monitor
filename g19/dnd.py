"""« Ne pas déranger » de Windows, piloté depuis le G19.

Windows 11 n'a pas d'API publique pour la case « Ne pas déranger » elle-même ; elle est en
revanche activée par une session de concentration (horloge → Concentration), qui a une API
officielle : Windows.UI.Shell.FocusSessionManager. Démarrer une session coupe les bannières de
notification ; l'arrêter les rétablit."""
import threading
import time

try:
    from winrt.windows.ui.shell import FocusSessionManager
except ImportError:
    FocusSessionManager = None

POLL = 3        # s entre deux lectures de l'état (il peut changer depuis Windows)


class DoNotDisturb:
    def __init__(self):
        self.supported = False
        self.active = False
        self.event = None          # (titre, texte, horodatage) : changé depuis le G19
        self._manager = None
        self._wake = threading.Event()
        self._want = None          # True / False : bascule demandée
        if FocusSessionManager is not None:
            threading.Thread(target=self._run, daemon=True, name="ne pas déranger").start()

    def toggle(self):
        """Bascule demandée depuis le G19 (appliquée dans le fil, sans bloquer l'écran)."""
        self._want = not self.active
        self._wake.set()

    def _run(self):
        try:
            self.supported = bool(FocusSessionManager.is_supported)
            if not self.supported:
                return
            self._manager = FocusSessionManager.get_default()
        except Exception:
            return
        while True:
            try:
                if self._want is not None:
                    want, self._want = self._want, None
                    if want:
                        self._manager.try_start_focus_session()
                    else:
                        self._manager.deactivate_focus()
                    time.sleep(0.3)
                    self.active = bool(self._manager.is_focus_active)
                    self.event = ("Ne pas déranger " + ("activé" if self.active else "désactivé"),
                                  "notifications Windows en pause" if self.active
                                  else "les notifications reprennent", time.time())
                else:
                    self.active = bool(self._manager.is_focus_active)
            except Exception:
                pass
            if self._wake.wait(POLL):
                self._wake.clear()
