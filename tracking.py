"""Session state for the live console view: what the game and the patch are doing right now.

State comes from two places only: allowlisted fields of the game's Player.log lines, and the patch's own events.
Account tokens, peer ids and every other log value are never parsed or stored.
"""
import datetime
import json
import re
import threading
import time

ROLES = ('user', 'region_user', 'battle')
TIER_NAMES = {'user': 'Account server', 'region_user': 'Region server', 'battle': 'Battle server'}
MAX_ATTEMPTS = 60
MAX_JOINS = 40
MAX_BACKFILL = 8 * 1024 * 1024

STAMP = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\] \[\d+\]\s*$')
ROLE = re.compile(r'\bid=(user|region_user|battle)\b')
STEP = re.compile(r'NetworkStep - Changed on "(\w+)"')
ADDRESS = re.compile(r'GetAddress completed id=\w+ host=(\S+?)\.? .*?addresses=([\d.]+)')
STARTED = re.compile(r'PeerConnect started id=\w+ address=([\d.]+):(\d+) rtt=(\d+) attempts=(\d+)')
DISCONNECT = re.compile(r'NotifyDisconnected (Success|UserKicked|ShutdownInvoked)')
HOST_OK = re.compile(r'^[a-z0-9.-]{1,80}$')


def epoch(text):
    try:
        return datetime.datetime.strptime(text, '%Y-%m-%d %H:%M:%S.%f').timestamp()
    except ValueError:
        return time.time()


def host_label(host):
    label = host.split('.')[0].lower()
    if not HOST_OK.match(label):
        return ''
    return label[len('prod-game-'):] if label.startswith('prod-game-') else label


def new_role(role):
    return {'role': role, 'name': TIER_NAMES[role], 'status': 'idle', 'host': '', 'ip': '', 'port': 0, 'rtt': 0,
            'since': 0.0, 'attempts': [], 'cycle_start': 0.0}


class Tracker:
    def __init__(self, version=''):
        self.lock = threading.Lock()
        self.revision = 0
        self.last_stamp = time.time()
        self.roles = {r: new_role(r) for r in ROLES}
        self.joins = []
        self.join = None
        self.join_serial = 0
        self.tool = {'version': version, 'status': 'off', 'label': 'Patch not running', 'since': time.time()}
        self.game_running = None
        self.relay = {'routes': 0, 'flows': 0, 'ports_hour': 0, 'port_budget': 60, 'proposals': 0}
        self.last_disconnect = ''
        self.update = ''

    # ---- game log -------------------------------------------------------------------------------------------
    def feed(self, line):
        stamp = STAMP.match(line)
        with self.lock:
            if stamp:
                self.last_stamp = epoch(stamp.group(1))
                return
            changed = self._parse(line)
            if changed:
                self.revision += 1

    def _parse(self, line):
        step = STEP.search(line)
        if step:
            return self._step(step.group(1))
        disconnect = DISCONNECT.search(line)
        if disconnect:
            return self._disconnect(disconnect.group(1))
        if 'RoomConnection.DisconnectedNetworkPeerPacket battle' in line:
            return self._close_role('battle')
        found = ROLE.search(line)
        if not found:
            return False
        role = self.roles[found.group(1)]
        now = self.last_stamp
        address = ADDRESS.search(line)
        if address:
            role['host'] = host_label(address.group(1))
            role['ip'] = address.group(2)
            return True
        started = STARTED.search(line)
        if started:
            role['ip'], role['port'], role['rtt'] = started.group(1), int(started.group(2)), int(started.group(3))
            self._attempt_start(role, now)
            return True
        if 'PeerConnect complete' in line:
            self._attempt_end(role, 'handshake', now)
            role['status'] = 'authorizing'
            return True
        if 'PeerConnect attempt failed' in line or 'PeerConnect failed' in line or 'Connect failed' in line:
            self._attempt_end(role, 'failed', now)
            role['status'] = 'retrying'
            return True
        if 'Connect completed' in line and not line.rstrip().endswith('.'):
            self._attempt_end(role, 'ok', now)
            role['status'] = 'connected'
            role['since'] = now
            if found.group(1) == 'battle' and self.join is not None and not self.join['connected_at']:
                self.join['connected_at'] = now
                self.join['outcome'] = 'repaired' if self.join['repaired'] else 'direct'
            return True
        if 'Connect started' in line:
            if role['status'] not in ('retrying', 'connecting'):
                role['attempts'] = []
                role['cycle_start'] = now
            role['status'] = 'connecting' if role['status'] != 'retrying' else 'retrying'
            return True
        if 'GetPing completed' in line:
            ping = re.search(r'ping=(\d+)', line)
            if ping:
                role['rtt'] = int(ping.group(1))
                return True
        return False

    def _attempt_start(self, role, now):
        role['status'] = 'connecting' if not role['attempts'] else 'retrying'
        if not role['cycle_start']:
            role['cycle_start'] = now
        attempt = {'n': len(role['attempts']) + 1, 't0': now, 't1': None, 'outcome': 'trying'}
        role['attempts'].append(attempt)
        del role['attempts'][:-MAX_ATTEMPTS]
        if role['role'] == 'battle' and self.join is not None:
            self.join['attempts'].append(dict(attempt))
            del self.join['attempts'][:-MAX_ATTEMPTS]
            if not self.join['connect_t0']:
                self.join['connect_t0'] = now
            if not self.join.get('ip'):
                self.join.update(ip=role['ip'], port=role['port'], host=role['host'])

    def _attempt_end(self, role, outcome, now):
        lists = [role['attempts']]
        if role['role'] == 'battle' and self.join is not None:
            lists.append(self.join['attempts'])
        for attempts in lists:
            if attempts and attempts[-1]['outcome'] in ('trying', 'handshake'):
                attempts[-1]['outcome'] = outcome
                if outcome != 'handshake':
                    attempts[-1]['t1'] = now

    def _step(self, name):
        now = self.last_stamp
        if name == 'InBattle':
            self._finish_join(now)
            self.join_serial += 1
            self.join = {'id': self.join_serial, 'started': now, 'host': self.roles['battle']['host'], 'ip': '',
                         'port': 0, 'attempts': [], 'marks': [], 'connected_at': 0.0, 'ended': 0.0, 'connect_t0': 0.0,
                         'outcome': 'joining', 'repaired': False, 'trial': False}
            battle = self.roles['battle']
            battle.update(status='connecting', attempts=[], cycle_start=now, ip='', port=0)
            self.joins.insert(0, self.join)
            del self.joins[MAX_JOINS:]
        elif name == 'InRealmNotInBattle':
            self._finish_join(now)
            self._close_role('battle')
        elif name in ('WaitUserData',):
            self.roles['user'].update(status='connecting', attempts=[], cycle_start=now)
        elif name in ('ConnectToRegion', 'SendingConnectRegionMessage', 'WaitRegionUserData'):
            if self.roles['region_user']['status'] == 'idle':
                self.roles['region_user'].update(status='connecting', cycle_start=now)
        return True

    def _finish_join(self, now):
        join = self.join
        if join is None:
            return
        join['ended'] = now
        if not join['connected_at']:
            join['outcome'] = 'failed'
        for attempt in join['attempts']:
            if attempt['outcome'] in ('trying', 'handshake'):
                attempt['outcome'] = 'abandoned'
                attempt['t1'] = now
        self.join = None

    def _disconnect(self, reason):
        self.last_disconnect = reason
        target = self.joins[0] if self.joins else None
        if target is not None and target['connected_at'] and not target.get('end_reason'):
            target['end_reason'] = {'UserKicked': 'kicked', 'Success': 'left', 'ShutdownInvoked': 'game closed'}[reason]
        return True

    def _close_role(self, role_name):
        role = self.roles[role_name]
        if role['status'] != 'idle':
            role['status'] = 'idle'
            role['since'] = self.last_stamp
        return True

    # ---- patch events ---------------------------------------------------------------------------------------
    def tool_event(self, event, **fields):
        now = time.time()
        with self.lock:
            labels = {'startup': ('starting', 'Starting'), 'armed': ('armed', 'Armed, waiting for a stalled join'),
                      'trial': ('testing', 'Repairing a stalled join'), 'ended': ('armed', 'Armed, waiting for a stalled join'),
                      'stopping': ('stopping', 'Stop requested'), 'cleanup': ('off', 'Stopped'),
                      'error': ('error', 'Error'), 'game_exit': ('stopping', 'Game closed, stopping'),
                      'budget_limit': ('waiting', 'Waiting, hourly port limit reached'),
                      'retry_limit': ('limit', 'Retry limit reached, no further edits'),
                      'route_failed': ('error', 'Could not add temporary route'),
                      'auto_stop': ('stopping', 'Stopping, automatic rearm is off')}
            if event in labels:
                self.tool.update(status=labels[event][0], label=labels[event][1], since=now)
            mark = None
            if event == 'trial':
                mark = 'trial'
            elif event == 'connect':
                phase = fields.get('phase')
                mark = {'baseline': 'baseline', 'fresh_proposal': 'proposal'}.get(phase)
                if mark == 'proposal':
                    self.relay['proposals'] += 1
            elif event in ('reply', 'connected', 'retry_limit'):
                mark = event
            if event == 'connected':
                self.tool.update(status='connected', label='Repaired: connected through the relay', since=now)
            join = self.join or (self.joins[0] if self.joins else None)
            if mark and join is not None:
                join['marks'].append({'t': now, 'kind': mark})
                del join['marks'][:-80]
                if mark in ('trial', 'proposal', 'reply', 'connected'):
                    join['trial'] = True
                if mark == 'connected':
                    join['repaired'] = True
                    if join['outcome'] in ('direct', 'failed'):
                        join['outcome'] = 'repaired'
            self.revision += 1

    def set_update(self, version):
        with self.lock:
            self.update = version

    def set_game(self, running):
        with self.lock:
            if self.game_running != running:
                self.game_running = running
                self.revision += 1

    def set_relay(self, **values):
        with self.lock:
            self.relay.update(values)

    # ---- output ---------------------------------------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            roles = {k: dict(v, attempts=[dict(a) for a in v['attempts']]) for k, v in self.roles.items()}
            joins = [dict(j, attempts=[dict(a) for a in j['attempts']], marks=[dict(m) for m in j['marks']]) for j in self.joins]
            states = [r['status'] for r in roles.values()]
            totals = {'joins': len(joins)}
            for outcome in ('direct', 'repaired', 'failed', 'joining'):
                totals[outcome] = sum(1 for j in joins if j['outcome'] == outcome)
            totals['kicked'] = sum(1 for j in joins if j.get('end_reason') == 'kicked')
            totals['failed_attempts'] = sum(1 for j in joins for a in j['attempts'] if a['outcome'] == 'failed')
            return {
                'now': time.time(), 'revision': self.revision, 'game_running': self.game_running, 'update': self.update,
                'tool': dict(self.tool), 'relay': dict(self.relay), 'roles': roles, 'joins': joins,
                'counts': {'connected': states.count('connected'),
                           'connecting': sum(1 for s in states if s in ('connecting', 'authorizing')),
                           'retrying': states.count('retrying'), 'total': len(states)},
                'totals': totals,
            }

    def backfill_tool(self, path):
        """Attach earlier patch events (from its own diagnostics file) to the joins they happened in."""
        try:
            with open(path, 'rb') as stream:
                rows = stream.read(256 * 1024).decode('utf-8', 'replace').splitlines()
        except OSError:
            return 0
        kinds = {'trial': 'trial', 'reply': 'reply', 'connected': 'connected', 'retry_limit': 'retry_limit'}
        count = 0
        with self.lock:
            for row in rows:
                try:
                    item = json.loads(row)
                    when = datetime.datetime.fromisoformat(item['time']).timestamp()
                    event = item['event']
                except (ValueError, KeyError, TypeError):
                    continue
                kind = kinds.get(event)
                if event == 'connect':
                    kind = {'baseline': 'baseline', 'fresh_proposal': 'proposal'}.get(item.get('phase'))
                if not kind:
                    continue
                for join in self.joins:
                    end = join['ended'] or join['connected_at'] or join['started']
                    if join['started'] - 1 <= when <= max(end, join['connected_at']) + 3:
                        join['marks'].append({'t': when, 'kind': kind})
                        join['marks'].sort(key=lambda m: m['t'])
                        join['trial'] = join['trial'] or kind in ('trial', 'proposal', 'reply', 'connected')
                        if kind == 'connected' and join['connected_at']:
                            join['repaired'] = True
                            join['outcome'] = 'repaired'
                        count += 1
                        break
            self.revision += 1
        return count

    def backfill(self, path, limit=MAX_BACKFILL):
        """Read the current game log once, so the view starts with this session's history."""
        try:
            with open(path, 'rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - limit))
                data = stream.read(limit)
        except OSError:
            return 0
        count = 0
        for raw in data.decode('latin-1').splitlines():
            if 'id=' in raw or 'NetworkStep' in raw or raw.startswith('[20') or 'Disconnect' in raw:
                self.feed(raw.rstrip('\r'))
                count += 1
        return count
