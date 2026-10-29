"""Hook Claude Code : enregistre l'état de chaque session pour le moniteur G19.

Appelé par Claude Code (voir install_hooks.py) avec le JSON de l'événement sur stdin.
Ne doit jamais bloquer ni faire échouer Claude : toute erreur est ignorée.
"""
import json
import os
import sys
import time
from pathlib import Path

STATUS_DIR = Path(os.environ.get("G19_CLAUDE_DIR",
                                 Path.home() / ".claude" / "g19" / "sessions"))


def ancestors(limit=10):
    """PID des processus parents du hook (Claude, puis son terminal ou l'appli desktop) : le
    moniteur s'en sert pour remettre la bonne fenêtre au premier plan."""
    try:
        import psutil
        out, p = [], psutil.Process(os.getppid())
        while p and len(out) < limit:
            out.append(p.pid)
            p = p.parent()
        return out
    except Exception:
        return []


def tool_detail(name, inp):
    inp = inp or {}
    if name == "Bash":
        return inp.get("description") or inp.get("command", "")[:60]
    for key in ("file_path", "notebook_path", "path"):
        if inp.get(key):
            return f"{name} {Path(inp[key]).name}"
    for key in ("description", "pattern", "url", "query", "skill"):
        if inp.get(key):
            return f"{name} {str(inp[key])[:50]}"
    return name


# outils qui attendent une réponse de l'utilisateur
QUESTION_TOOLS = {"AskUserQuestion": "question", "ExitPlanMode": "plan à valider"}
TRANSCRIPT_TAIL = 256 * 1024


def last_assistant_text(transcript_path):
    """Dernier texte écrit par Claude, lu à la fin du transcript (jsonl)."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - TRANSCRIPT_TAIL))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except (OSError, TypeError):
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict)
                 and c.get("type") == "text"]
        if texts:
            return texts[-1]
    return ""


def context_tokens(transcript_path):
    """Taille du contexte de la session : jetons d'entrée du dernier appel du fil principal."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - TRANSCRIPT_TAIL))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        u = (entry.get("message") or {}).get("usage") or {}
        if u:
            return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                    + u.get("cache_read_input_tokens", 0))
    return None


def turn_question(event):
    """Question posée en fin de tour (dernier message terminé par « ? »), ou None."""
    text = event.get("last_assistant_message")
    if not isinstance(text, str):
        text = last_assistant_text(event.get("transcript_path"))
    text = (text or "").strip()
    if not text.endswith("?"):
        return None
    return text.splitlines()[-1].strip("*_ ")[:80]


def main():
    event = json.loads(sys.stdin.buffer.read() or b"{}")
    sid = event.get("session_id")
    if not sid:
        return
    name = event.get("hook_event_name", "")
    path = STATUS_DIR / f"{sid}.json"

    if name == "SessionEnd":
        path.unlink(missing_ok=True)
        return

    try:
        state = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        state = {"session_id": sid, "started": time.time(), "state": "idle"}

    tool = event.get("tool_name", "")
    if name in ("UserPromptSubmit", "PostToolUse"):
        state.update(state="working", message="")
        if name == "UserPromptSubmit":
            state["tool"] = "réfléchit…"
            state.pop("pending_question", None)
    elif name == "PreToolUse" and tool in QUESTION_TOOLS:
        inp = event.get("tool_input") or {}
        qs = inp.get("questions") or []
        q = qs[0].get("question") if qs and isinstance(qs[0], dict) else ""
        state.update(state="waiting", message=(q or QUESTION_TOOLS[tool])[:80])
    elif name == "PreToolUse":
        inp = event.get("tool_input") or {}
        if tool.endswith("__wrap_up") and inp.get("ask"):
            # question posée dans l'encadré de fin de tour de l'appli desktop
            state["pending_question"] = inp["ask"][:80]
        state.update(state="working", message="", tool=tool_detail(tool, inp))
    elif name == "PreCompact":
        state.update(state="working", tool="compacte le contexte")
    elif name == "PermissionRequest":
        state.update(state="waiting",
                     message=f"permission {event.get('tool_name', '')}".strip())
    elif name == "Notification":
        if event.get("notification_type") == "idle_prompt":
            if state.get("state") != "waiting":
                state.update(state="idle", message="")
        else:
            msg = event.get("message", "")
            msg = msg.replace("Claude needs your permission to use", "permission")
            state.update(state="waiting", message=msg[:80])
    elif name == "Stop":
        question = state.pop("pending_question", None) or turn_question(event)
        if question:
            state.update(state="waiting", message=question, tool="")
        else:
            state.update(state="idle", message="", tool="")
    elif name == "SessionStart":
        state.update(state="idle", message="", tool="")
    else:
        return

    ctx = context_tokens(event.get("transcript_path"))
    if ctx:
        state["context"] = ctx
    if not state.get("pids"):
        state["pids"] = ancestors()
    state["cwd"] = event.get("cwd") or state.get("cwd", "")
    state["event"] = name
    state["updated"] = time.time()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
