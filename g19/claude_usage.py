"""Usage de Claude Code calculé depuis les transcripts locaux (~/.claude/projects/**/*.jsonl).

Pas de limites du compte (elles ne sont pas écrites en local) : on compte les jetons et les
messages du bloc de 5 h en cours (un bloc démarre à l'heure pile du premier message après
5 h sans bloc ouvert, et se remet à zéro 5 h plus tard), et le total des 7 derniers jours."""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

PROJECTS = Path(os.environ.get("G19_CLAUDE_PROJECTS", Path.home() / ".claude" / "projects"))
BLOCK = 5 * 3600
WEEK = 7 * 86400
INTERVAL = 30


def _ts(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


class ClaudeUsage:
    def __init__(self):
        self.block_tokens = 0      # entrée + création de cache + sortie (la relecture de cache,
        self.block_messages = 0    # quasi gratuite, n'est pas comptée)
        self.block_reset = None    # fin du bloc en cours (epoch), None si aucun bloc ouvert
        self.week_tokens = 0
        self.ready = False
        self._offsets = {}         # fichier → octets déjà lus
        self._entries = {}         # id de réponse → (horodatage, jetons)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self._scan()
                self._compute()
                self.ready = True
            except Exception:
                pass
            time.sleep(INTERVAL)

    def _scan(self):
        if not PROJECTS.is_dir():
            return
        since = time.time() - WEEK
        for path in PROJECTS.rglob("*.jsonl"):
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_mtime < since:
                continue
            start = self._offsets.get(path, 0)
            if st.st_size < start:
                start = 0              # fichier réécrit
            if st.st_size == start:
                continue
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read()
            # on ne garde que les lignes complètes ; la fin sera relue au prochain passage
            end = data.rfind(b"\n") + 1
            self._offsets[path] = start + end
            for line in data[:end].splitlines():
                if b'"usage"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") != "assistant":
                    continue
                msg = e.get("message") or {}
                u = msg.get("usage") or {}
                ts = _ts(e.get("timestamp"))
                if not u or ts is None or ts < since:
                    continue
                key = msg.get("id") or e.get("requestId") or e.get("uuid")
                tokens = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                          + u.get("output_tokens", 0))
                self._entries[key] = (ts, tokens)

    def _compute(self):
        now = time.time()
        entries = sorted(v for v in self._entries.values() if v[0] >= now - WEEK)
        self._entries = {k: v for k, v in self._entries.items() if v[0] >= now - WEEK}
        start, tokens, count = None, 0, 0
        for ts, tok in entries:
            if start is None or ts >= start + BLOCK:
                start, tokens, count = ts - ts % 3600, 0, 0   # nouveau bloc, à l'heure pile
            tokens += tok
            count += 1
        if start is not None and now < start + BLOCK:
            self.block_tokens, self.block_messages, self.block_reset = tokens, count, start + BLOCK
        else:
            self.block_tokens, self.block_messages, self.block_reset = 0, 0, None
        self.week_tokens = sum(tok for _, tok in entries)
