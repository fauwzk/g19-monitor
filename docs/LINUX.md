# G19 Monitor sous Linux (en cours)

Testé sur EndeavourOS (Arch), KDE Plasma (Wayland), Python 3.14. L'écran du G19 est piloté en
USB direct : pas besoin de Logitech Gaming Software.

## Installation

Dépendances (Arch / EndeavourOS) :

```bash
sudo pacman -S --needed python-pillow python-psutil python-numpy python-pyusb python-fonttools python-icalendar
pip install --user --break-system-packages recurring-ical-events
```

Accès au clavier sans root (une fois, puis débrancher / rebrancher le G19) :

```bash
sudo cp installer/linux/99-g19.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger
```

Test de l'écran et des touches : `python3 tools/linux_lcd_test.py`.

## Lancer

```bash
python3 g19_monitor.py            # au premier plan (Ctrl+C pour arrêter)
python3 g19_monitor.py --stop     # arrêter l'instance lancée ailleurs
```

Réglages et données : `~/.config/g19-monitor/`. Journal : `g19.log` dans le dossier de l'appli.
L'appli se relance d'elle-même quand son code change (git pull, envoi depuis Windows).

## Ce qui marche, ce qui manque

Marche : écran et touches du G19, toutes les pages et les thèmes (fond d'écran du bureau KDE ou
GNOME compris), CPU / RAM / disques / réseau, températures et ventilateur (capteurs du noyau),
ping, batterie du PC et des périphériques, musique en cours et ses commandes (MPRIS : Spotify,
navigateurs, VLC…), volume / micro / volume par appli / sortie et entrée par défaut (PulseAudio
ou PipeWire via pactl), notifications du bureau (D-Bus), Claude Code, Steam (Web), Home
Assistant, agenda, météo, bilan du jour, bandeaux.

Pas encore : rétroéclairage du clavier, Discord, « Ne pas déranger », écran de repos (PC
inactif ou verrouillé), icône de la barre des tâches, utilitaire de réglage, FPS des jeux,
démarrage avec la session. Les icônes Segoe sont remplacées par des symboles Unicode.

Sous le capot : `g19/linux/compat.py` fournit de fausses versions de `winreg` et des DLL
Windows, pour que le code commun se charge tel quel ; `g19/linux/` contient les équivalents
Linux (écran USB dans `g19/usb_lcd.py`, instance unique, capteurs, polices).
