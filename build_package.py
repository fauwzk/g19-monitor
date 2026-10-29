"""Construit le paquet d'installation pour un autre PC : dist/G19Monitor-AAAAMMJJ.zip.

Contenu : Installer.cmd / Desinstaller.cmd / LISEZMOI.txt à la racine, l'appli dans app/.
Ni réglages, ni accès (Discord, Steam), ni historiques : ils vivent dans %LOCALAPPDATA%\\G19Monitor
et se reprennent avec l'export / import des réglages."""
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_FILES = ["g19_monitor.py", "config_g19.pyw", "start_g19.pyw", "claude_hook.py",
             "install_hooks.py", "install_startup.py", "setup_discord.py", "requirements.txt",
             "update.cmd", "README.md", "g19.ico"]
INSTALLER = ["Installer.cmd", "Desinstaller.cmd", "LISEZMOI.txt", "install.ps1", "uninstall.ps1",
             "extras.ps1"]


def repo_info():
    """(URL du dépôt GitHub, branche) d'après git, ou ("", "main") hors dépôt."""
    def git(*args):
        try:
            out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
        except OSError:
            return ""
        return out.stdout.strip() if out.returncode == 0 else ""
    return git("remote", "get-url", "origin"), git("rev-parse", "--abbrev-ref", "HEAD") or "main"


def build():
    out = ROOT / "dist" / "G19Monitor"
    if out.exists():
        shutil.rmtree(out)
    app = out / "app"
    (app / "g19").mkdir(parents=True)
    for name in APP_FILES:
        shutil.copy2(ROOT / name, app / name)
    for py in sorted((ROOT / "g19").glob("*.py")):
        shutil.copy2(py, app / "g19" / py.name)
    for name in INSTALLER:
        src = ROOT / "installer" / name
        if name.endswith(".ps1"):
            url, branch = repo_info()
            text = src.read_text("utf-8").replace('"__REPO__"', f'"{url}"') \
                .replace('"__BRANCH__"', f'"{branch}"')
            # Windows PowerShell 5 lit un script sans BOM en ANSI : les accents seraient abîmés
            (out / name).write_text(text, "utf-8-sig")
        else:
            shutil.copy2(src, out / name)
    zip_path = ROOT / "dist" / f"G19Monitor-{time.strftime('%Y%m%d')}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path("G19Monitor") / f.relative_to(out))
    return zip_path, out


if __name__ == "__main__":
    path, folder = build()
    files = sum(1 for f in folder.rglob("*") if f.is_file())
    print(f"{path}  ({files} fichiers, {path.stat().st_size / 1024:.0f} Ko)")
