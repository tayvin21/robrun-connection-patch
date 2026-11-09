"""Live ANSI status view for the helper's console window (PowerShell, cmd or Windows Terminal).

Pure rendering over tracking.Tracker snapshots: which servers the game is connected to or connecting to, every
attempt, and what the patch did. Nothing here reads tokens or ids.
"""
import ctypes
import os
import re
import shutil
import sys
import threading
import time

RESET = '\x1b[0m'
ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
COLORS = {'accent': '38;5;80', 'ok': '38;5;78', 'warn': '38;5;221', 'bad': '38;5;210', 'muted': '38;5;245',
          'text': '38;5;252', 'bold': '1', 'dim': '2'}
RICH = {'check': '✓', 'cross': '✗', 'packet': '▸', 'solid': '━', 'dash': '╌', 'dots': '┈', 'full': '█', 'empty': '░',
        'relay': '◈', 'bullet': '●', 'rule': '─', 'spin': '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏', 'retry': '↻', 'dot': '·', 'arrow': '→'}
SAFE = {'check': 'v', 'cross': 'x', 'packet': '>', 'solid': '=', 'dash': '-', 'dots': '.', 'full': '#', 'empty': '-',
        'relay': '*', 'bullet': 'o', 'rule': '-', 'spin': '|/-\\', 'retry': '~', 'dot': '.', 'arrow': '>'}
OUTCOME = {'direct': ('ok', 'check', 'connected directly'), 'repaired': ('accent', 'relay', 'repaired by patch'),
           'failed': ('bad', 'cross', 'did not connect'), 'joining': ('warn', 'spin', 'joining')}


def vlen(text):
    return len(ANSI.sub('', text))


def paint(text, *names, on=True):
    if not on:
        return text
    return '\x1b[' + ';'.join(COLORS[n] for n in names) + 'm' + text + RESET


def fit(text, width):
    """Pad or clip to a visible width, keeping colour codes intact."""
    visible = vlen(text)
    if visible <= width:
        return text + ' ' * (width - visible)
    out, seen, i = [], 0, 0
    while i < len(text) and seen < width:
        m = ANSI.match(text, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        out.append(text[i])
        seen += 1
        i += 1
    return ''.join(out) + (RESET if '' in text else '')


def duration(seconds):
    if seconds is None:
        return '-'
    return f'{seconds:.1f} s' if seconds < 100 else f'{int(seconds // 60)} min {int(seconds % 60):02d} s'


def clock(epoch_seconds):
    return time.strftime('%H:%M:%S', time.localtime(epoch_seconds))


class View:
    """Holds what the viewer chose (selected lane, history) and turns a snapshot into lines."""

    def __init__(self, rich=False, color=True):
        self.g = RICH if rich else SAFE
        self.color = color
        self.selected = 'battle'
        self.events = []

    def p(self, text, *names):
        return paint(text, *names, on=self.color)

    def log(self, text):
        self.events.append((time.time(), text))
        del self.events[:-8]

    def link(self, status, width, tick, relay=''):
        g = self.g
        width = max(width, 8)
        if status == 'connected':
            body = g['solid'] * (width - 1) + g['packet']
            tone = 'ok'
        elif status in ('connecting', 'authorizing'):
            cells = [g['dots']] * width
            for start in range(tick % 8, width, 8):
                cells[start] = g['packet']
            body = ''.join(cells)
            tone = 'accent'
        elif status == 'retrying':
            body = (g['dash'] * width)
            mid = width // 2
            mark = g['cross'] if (tick // 4) % 2 == 0 else ' '
            body = body[:mid] + mark + body[mid + 1:]
            tone = 'warn'
        else:
            body = g['dots'] * width
            tone = 'muted'
        if relay:
            chip = f' {relay} '
            start = max((width - len(chip)) // 2, 1)
            return self.p(body[:start], tone) + self.p(chip, 'accent', 'bold') + self.p(body[start + len(chip):], tone)
        return self.p(body, tone)

    def state_text(self, role, snap, tick):
        g = self.g
        status = role['status']
        now = snap['now']
        if status == 'connected':
            return self.p(f"{g['check']} Connected", 'ok', 'bold')
        if status in ('connecting', 'authorizing'):
            spin = g['spin'][tick % len(g['spin'])]
            tries = len(role['attempts'])
            elapsed = f" {duration(now - role['attempts'][-1]['t0'])}" if role['attempts'] else ''
            word = 'Authorizing' if status == 'authorizing' else 'Connecting'
            return self.p(f"{spin} {word}", 'accent', 'bold') + self.p(f"  try {max(tries, 1)}{elapsed}", 'muted')
        if status == 'retrying':
            failed = sum(1 for a in role['attempts'] if a['outcome'] == 'failed')
            return self.p(f"{g['retry']} Retrying", 'warn', 'bold') + self.p(f"  {failed} failed, try {len(role['attempts'])}", 'muted')
        return self.p('Not connected', 'muted')

    def lanes(self, snap, width, tick):
        lines = []
        relay_on = snap['relay']['routes'] > 0
        for key, number in (('user', '1'), ('region_user', '2'), ('battle', '3')):
            role = snap['roles'][key]
            mark = self.p('>', 'accent', 'bold') if self.selected == key else ' '
            name = role['name']
            relay = ''
            if key == 'battle':
                relay = f"{self.g['relay']} PATCH RELAY: forwarding" if relay_on else 'patch relay: standby'
            left = f' {mark}{self.p(number, "muted")} THIS PC '
            right = f' {self.p(name, "bold")}'
            room = width - vlen(left) - vlen(right) - 1
            if relay and not relay_on:
                relay = ''
            lines.append(left + self.link(role['status'], room, tick, relay) + right)
            where = f"{role['host']} {role['ip']}:{role['port']}" if role['ip'] else 'waiting for the game'
            rtt = f"  {role['rtt']} ms" if role['rtt'] and role['status'] != 'idle' else ''
            detail = '      ' + self.state_text(role, snap, tick) + self.p(f'   {where}{rtt}', 'muted')
            if key == 'battle' and not relay_on:
                detail += self.p('   patch relay: standby', 'muted')
            lines.append(fit(detail, width))
        return lines

    def counts(self, snap):
        c, t = snap['counts'], snap['totals']
        parts = [(f"{c['connected']}/{c['total']}", 'connected', 'ok'), (str(c['connecting']), 'connecting', 'accent'),
                 (str(c['retrying']), 'retrying', 'warn'), (str(t['repaired']), 'repaired', 'accent'),
                 (str(t['failed_attempts']), 'failed tries', 'bad')]
        return '  '.join(self.p(v, tone, 'bold') + ' ' + self.p(label, 'muted') for v, label, tone in parts)

    def attempts(self, snap, width):
        g = self.g
        sel = self.selected
        role = snap['roles'][sel]
        join = snap['joins'][0] if sel == 'battle' and snap['joins'] else None
        attempts = join['attempts'] if join else role['attempts']
        title = f"{role['name']}: attempts"
        out = [self.p(title, 'bold')]
        if not attempts:
            return out + [self.p('  none yet', 'muted')]
        now = snap['now']
        start = attempts[0]['t0']
        end = max((a['t1'] or now) for a in attempts)
        span = max(end - start, 5.0)
        bar = max(min(width - 40, 40), 12)
        for a in attempts[-6:]:
            t1 = a['t1'] or now
            left = int((a['t0'] - start) / span * bar)
            size = max(int((t1 - a['t0']) / span * bar), 1)
            size = min(size, bar - left)
            tone, icon, word = {'failed': ('bad', 'cross', 'failed'), 'ok': ('ok', 'check', 'connected'),
                                'handshake': ('accent', 'dot', 'handshake'), 'trying': ('accent', 'dot', 'trying'),
                                'abandoned': ('muted', 'dot', 'cancelled')}.get(a['outcome'], ('muted', 'dot', a['outcome']))
            cells = g['empty'] * left + g['full'] * size + g['empty'] * (bar - left - size)
            out.append(f"  try {a['n']:<2} " + self.p(cells, tone) + f' {self.p(icon_text(g, icon) + " " + word, tone)} {self.p(duration(t1 - a["t0"]), "muted")}')
        if len(attempts) > 6:
            out.insert(1, self.p(f'  ... {len(attempts) - 6} earlier tries not shown', 'muted'))
        if join:
            out.extend(self.patch_line(join))
        return out

    def patch_line(self, join):
        marks = [m for m in join['marks'] if m['kind'] != 'baseline']
        if not marks:
            return [self.p('  patch: not needed' if join['outcome'] == 'direct' else '  patch: watching', 'muted')]
        base = join['connect_t0'] or join['started']
        names = {'trial': 'started repair', 'proposal': 'edited proposal', 'reply': 'server replied',
                 'connected': 'connected', 'retry_limit': 'retry limit'}
        text = '  patch: ' + '  '.join(f"{names.get(m['kind'], m['kind'])} +{m['t'] - base:.1f}s" for m in marks)
        return [self.p(text, 'accent')]

    def history(self, snap, width, rows):
        out = [self.p('Recent joins', 'bold')]
        if not snap['joins']:
            return out + [self.p('  none yet', 'muted')]
        for join in snap['joins'][:rows]:
            tone, icon, word = OUTCOME.get(join['outcome'], ('muted', 'dot', join['outcome']))
            origin = join['connect_t0'] or join['started']
            took = (join['connected_at'] - origin) if join['connected_at'] else ((join['ended'] or snap['now']) - origin)
            end = f"  {join['end_reason']}" if join.get('end_reason') else ''
            out.append(fit(f"  #{join['id']:<3}{join['host'][-22:]:<22} " + self.p(f"{icon_text(self.g, icon)} {word}", tone)
                           + self.p(f"   {plural(len(join['attempts']), 'try', 'tries')}   {duration(took)}{end}", 'muted'), width))
        return out

    def frame(self, snap, tick, width, height):
        tool = snap['tool']
        tone = {'connected': 'accent', 'testing': 'accent', 'armed': 'ok', 'error': 'bad', 'limit': 'warn', 'waiting': 'warn'}.get(tool['status'], 'muted')
        game = {True: 'game running', False: 'game not running', None: 'game: checking'}[snap['game_running']]
        head = ' ' + self.p('ROB RUN connection patch', 'bold') + self.p(f" {tool['version']}", 'muted')
        status = self.p(tool['label'].upper(), tone, 'bold') + self.p(f'  |  {game}', 'muted')
        gap = max(width - vlen(head) - vlen(status) - 1, 1)
        rule = self.p(self.g['rule'] * (width - 2), 'muted')
        lines = [head + ' ' * gap + status, ' ' + rule]
        if snap.get('update'):
            lines.append(' ' + self.p(f"UPDATE v{snap['update']} is available.", 'warn', 'bold') + self.p(' Stop this window, run START.cmd and press V.', 'muted'))
        lines += [' ' + self.counts(snap), '']
        lines += self.lanes(snap, width, tick) + ['']
        lines += [' ' + x for x in self.attempts(snap, width)] + ['']
        spare = height - len(lines) - 6
        if spare >= 3:
            lines += [' ' + x for x in self.history(snap, width, min(5, spare - 1))] + ['']
        recent = self.events[-3:]
        if recent and height - len(lines) >= 5:
            lines += [fit(f' {self.p(clock(t), "muted")} {text}', width) for t, text in recent] + ['']
        keys = ' 1 2 3 pick a server   ENTER or S safe stop' + ('' if self.g is RICH else '   (ASCII mode)')
        lines.append(self.p(keys, 'muted'))
        return [fit(line, width) for line in lines[:height]]


def plural(n, one, many):
    return f'{n} {one if n == 1 else many}'


def icon_text(g, icon):
    return g['spin'][0] if icon == 'spin' else g[icon]


def enable_vt():
    """Turn on ANSI colour handling and UTF-8 output; False if the console cannot do it."""
    if os.name != 'nt' or not sys.stdout.isatty():
        return False
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if not kernel.SetConsoleMode(handle, mode.value | 0x0004 | 0x0001):
            return False
        kernel.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        return True
    except (OSError, AttributeError, ValueError):
        return False


class Live:
    """Redraws the view in place on the alternate screen about eight times a second."""

    def __init__(self, tracker, rich=None):
        self.tracker = tracker
        self.rich = bool(os.environ.get('WT_SESSION') or os.environ.get('ROBRUN_UNICODE')) if rich is None else rich
        self.view = View(rich=self.rich, color=not os.environ.get('NO_COLOR'))
        self.stop = threading.Event()
        self.thread = None

    def log(self, text):
        self.view.log(text)

    def start(self):
        sys.stdout.write('\x1b[?1049h\x1b[?25l')
        sys.stdout.flush()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        tick = 0
        while not self.stop.is_set():
            size = shutil.get_terminal_size((100, 30))
            width = max(min(size.columns, 110), 50)
            try:
                lines = self.view.frame(self.tracker.snapshot(), tick, width, max(size.lines, 12))
                sys.stdout.write('\x1b[H' + '\x1b[K\n'.join(lines) + '\x1b[K\x1b[J')
                sys.stdout.flush()
            except OSError:
                return
            tick += 1
            self.stop.wait(0.125)

    def select(self, key):
        if key in ('user', 'region_user', 'battle'):
            self.view.selected = key

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
        sys.stdout.write('\x1b[?25h\x1b[?1049l')
        sys.stdout.flush()


def key_loop(live, on_stop):
    """Keys for the live view: 1 2 3 pick a server, ENTER or S or Q stop."""
    import msvcrt
    while not live.stop.is_set():
        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue
        key = msvcrt.getwch()
        if key in ('\x00', '\xe0'):
            msvcrt.getwch()
        elif key in '123':
            live.select(('user', 'region_user', 'battle')[int(key) - 1])
        elif key in ('\r', '\n', 's', 'S', 'q', 'Q', '\x03'):
            on_stop()
            return
