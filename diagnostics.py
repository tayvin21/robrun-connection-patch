"""Small local records. Never saves raw game logs, packets, IDs or credentials."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

LIMIT = 128 * 1024
FIELDS = {'phase', 'seconds', 'changed', 'baseline', 'result', 'version'}
EVENTS = {'armed', 'trial', 'connect', 'reply', 'connected', 'ended', 'cleanup',
          'error', 'stopping', 'startup', 'idle_stop', 'unsupported', 'route_failed'}


class Diagnostics:
    def __init__(self, directory, enabled=True):
        self.directory = Path(directory)
        self.enabled = enabled
        self.lock = threading.Lock()

    def emit(self, event, **fields):
        if not self.enabled or event not in EVENTS:
            return
        record = {'time': datetime.now(timezone.utc).isoformat(timespec='milliseconds'), 'event': event}
        for key, value in fields.items():
            if key not in FIELDS:
                continue
            if isinstance(value, (bool, int, float)):
                record[key] = value
            elif isinstance(value, str) and value.isascii() and len(value) <= 48 and all(c.isalnum() or c in '_-.' for c in value):
                record[key] = value
        raw = (json.dumps(record, separators=(',', ':')) + '\n').encode('utf-8')
        try:
            with self.lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / 'diagnostics.jsonl'
                if path.exists() and path.stat().st_size + len(raw) > LIMIT:
                    path.replace(self.directory / 'diagnostics.previous.jsonl')
                with path.open('ab') as stream:
                    stream.write(raw)
        except OSError:
            # Diagnostics must never break a recovered connection.
            pass


def export(directory, destination):
    """Allowlisted records only; bounded reads and output, no archive handling."""
    clean = []
    remaining = LIMIT
    for name in ('diagnostics.jsonl', 'diagnostics.previous.jsonl'):
        path = Path(directory) / name
        if not path.exists():
            continue
        with path.open('rb') as stream:
            raw = stream.read(LIMIT)
        for line in raw.splitlines():
            if len(line) > 1024:
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get('event') not in EVENTS:
                    continue
                # Treat local files as untrusted. Re-export only controlled values.
                safe = {'event': row['event']}
                stamp = row.get('time', '')
                if isinstance(stamp, str) and len(stamp) < 40:
                    datetime.fromisoformat(stamp)
                    safe['time'] = stamp
                for key in FIELDS:
                    value = row.get(key)
                    if isinstance(value, (int, float, bool)):
                        safe[key] = value
                    elif isinstance(value, str) and len(value) <= 48 and value.isascii() and all(c.isalnum() or c in '_-.' for c in value):
                        safe[key] = value
                text = json.dumps(safe, separators=(',', ':')) + '\n'
                size = len(text.encode('utf-8'))
                if size > remaining:
                    break
                clean.append(text)
                remaining -= size
            except (ValueError, TypeError, RecursionError):
                continue
    Path(destination).write_bytes(''.join(clean).encode('utf-8'))
    return len(clean)
