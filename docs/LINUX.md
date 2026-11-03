# G19 Monitor sous Linux (en cours)

Testé sur EndeavourOS (Arch), KDE Plasma (Wayland), Python 3.14. L'écran du G19 est piloté en
USB direct : pas besoin de Logitech Gaming Software.

## Installation

Dépendances (Arch / EndeavourOS) :

```bash
sudo pacman -S --needed python-pillow python-psutil python-numpy python-pyusb python-fonttools python-icalendar pyside6
pip install --user --break-system-packages recurring-ical-events pystray
```

`pyside6` : l'utilitaire de réglage ; `pystray` : l'icône dans la barre des tâches.

Accès au clavier sans root, écran et rétroéclairage (une fois, puis débrancher / rebrancher) :

```bash
sudo cp installer/linux/99-g19.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
```

Test de l'écran et des touches : `python3 tools/linux_lcd_test.py`.

## Lancer

```bash
python3 g19_monitor.py            # au premier plan
python3 g19_monitor.py --stop     # arrêter l'instance en cours
python3 config_g19.pyw            # utilitaire de réglage
```

Démarrage avec la session et gardien (relance si l'appli plante) : un service utilisateur
systemd, à activer depuis l'icône (« Démarrage auto et gardien ») ou à la main :

```bash
python3 -c "from g19.linux import compat; compat.install(); from g19.linux import service; service.set_enabled(True)"
systemctl --user start g19-monitor
```

Réglages et données : `~/.config/g19-monitor/`. Journal : `g19.log` dans le dossier de l'appli.
L'appli se relance d'elle-même quand son code change (git pull, envoi depuis Windows).

## Ce qui marche, ce qui manque

Marche : écran et touches du G19, toutes les pages et les thèmes (fond d'écran du bureau KDE ou
GNOME compris), CPU / RAM / disques / réseau, températures, ventilateur, GPU (AMD, et Intel par
son temps de veille), ping, batteries, musique en cours et ses commandes (MPRIS), volume / micro
/ volume par appli / sortie et entrée par défaut (PulseAudio ou PipeWire), notifications du
bureau (D-Bus), recopie d'écran (portail de capture + PipeWire : le bureau demande une fois
quel écran partager), « Ne pas déranger » (KDE et serveurs compatibles), écran de repos (PC verrouillé
ou session inactive), Discord (socket IPC, client normal / Flatpak / Snap, Vesktop), rétroéclairage
du clavier (hidraw), jeux Steam (natifs et Proton) : sessions, page GPU au lancement, succès,
Claude Code, Steam (Web), Home Assistant, agenda, météo, bilan du jour, bandeaux, icône de la
barre des tâches, utilitaire, démarrage automatique et gardien (systemd).

Limites : pas de FPS des jeux (pas d'équivalent de RTSS sous Linux) ; sous Wayland, l'écran de
repos ne voit pas « aucune touche depuis 5 min » sans verrouillage ; icônes Segoe remplacées par des symboles Unicode. Accès Discord, Home Assistant,
Steam, agenda : copier les fichiers de `%LOCALAPPDATA%\G19Monitor` (Windows) dans
`~/.config/g19-monitor/`.

Sous le capot : `g19/linux/compat.py` fournit de fausses versions de `winreg` et des DLL
Windows, pour que le code commun se charge tel quel ; `g19/linux/` contient les équivalents
Linux (écran USB dans `g19/usb_lcd.py`, instance unique, capteurs, polices).
