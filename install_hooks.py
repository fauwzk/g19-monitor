"""Ajoute (ou retire avec --uninstall) les hooks du voyant G19 dans ~/.claude/settings.json."""
import json
import sys
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK = Path(__file__).resolve().with_name("claude_hook.py")
MARKER = "claude_hook.py"
EVENTS = ["SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "PermissionRequest", "Notification", "Stop", "PreCompact"]
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PermissionRequest"}


def _load():
    return json.loads(SETTINGS.read_text("utf-8")) if SETTINGS.exists() else {}


def _ours(group):
    return any(MARKER in h.get("command", "") for h in group.get("hooks", []))


def is_installed():
    return any(_ours(g) for groups in _load().get("hooks", {}).values() for g in groups)


def set_installed(install):
    settings = _load()
    hooks = settings.setdefault("hooks", {})
    # retire nos anciennes entrées pour rester idempotent
    for event in list(hooks):
        groups = [g for g in hooks[event] if not _ours(g)]
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]

    if install:
        python = Path(sys.executable).with_name("python.exe").as_posix()
        cmd = f'"{python}" "{HOOK.as_posix()}"'
        for event in EVENTS:
            group = {"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}
            if event in TOOL_EVENTS:
                group = {"matcher": "*", **group}
            hooks.setdefault(event, []).append(group)

    if not hooks:
        settings.pop("hooks")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", "utf-8")


def main():
    install = "--uninstall" not in sys.argv
    set_installed(install)
    print(("Hooks installés dans " if install else "Hooks retirés de ") + str(SETTINGS))


if __name__ == "__main__":
    main()
