import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch as mock
from unittest.mock import Mock
import zlib
import diagnostics
import patch
import transport

def connect_packet(sessions=b'\x02\x02'):
    body = bytearray(53)
    body[:2] = b'\x8f\xff'
    body[8:14] = b'\x82\xff\x00\x01\x00\x00'
    body[14:16] = sessions
    body[24] = 2
    body[45:49] = b'TEST'
    body[4:8] = zlib.crc32(body).to_bytes(4, 'big')
    return bytes(body)

class ProposalTests(unittest.TestCase):
    def test_baseline_rewrite_and_limit(self):
        data = connect_packet(); state = patch.Proposal(0)
        for t in (0, 1, 2):
            self.assertEqual(state.process(data, t, False), (data, 'baseline'))
        changed, phase = state.process(data, 3, False)
        self.assertEqual(phase, 'fresh_proposal')
        self.assertEqual(changed[14:16], b'\xff\xff')
        self.assertEqual(changed[:4], data[:4])
        self.assertEqual(changed[8:14], data[8:14])
        self.assertEqual(changed[16:], data[16:])
        self.assertIsNotNone(patch.inspect_connect(changed))
        for t in range(4, 30): state.process(data, t, False)
        self.assertEqual(state.changed, 12)
        self.assertEqual(state.process(data, 30, False), (data, 'limit_reached'))

    def test_no_change_after_reply_or_to_gameplay(self):
        state = patch.Proposal(0); state.baseline = 3
        for data, replied in [(connect_packet(), True), (b'gameplay', False), (connect_packet(b'\xff\xff'), False)]:
            self.assertEqual(state.process(data, 10, replied)[0], data)

    def test_bad_checksum_and_unknown_layout_pass_unchanged(self):
        for offset in (4, 8, 24):
            data = bytearray(connect_packet()); data[offset] ^= 1; data = bytes(data)
            self.assertIsNone(patch.inspect_connect(data))
            self.assertEqual(patch.Proposal(0).process(data, 100, False)[0], data)

class FakeRelay:
    def __init__(self):
        self.allowed = set(); self.trials = {}; self.lock = threading.Lock(); self.target = None
    def budget_ok(self): return True
    def add_route(self, ip): self.allowed.add(ip); return True
    def remove_route(self, ip): self.allowed.remove(ip)

class LifecycleTests(unittest.TestCase):
    def start(self, watcher, ip='5.8.93.226'):
        watcher.read_line('NetworkStep - Changed on "InBattle".')
        watcher.read_line(f'GetAddress completed id=battle host=prod-game-us-0-battle-gcore-35.rob-run.kefir.games. dnsAddresses=1 addresses={ip}')
        watcher.read_line(f'PeerConnect started id=battle address={ip}:36706 rtt=70 attempts=0')
        watcher.move['started'] -= 3

    def test_build_26535791_address_line_still_names_the_server(self):
        watcher = patch.Watcher('does-not-exist', FakeRelay(), lambda *a, **k: None)
        watcher.read_line('NetworkStep - Changed on "InBattle".')
        watcher.read_line('ConnectUpdater.GetAddress completed id=battle host=prod-game-us-0-battle-gcore-17.rob-run.kefir.games. dnsAddresses=1 isProxyPreferred=False addresses=162.216.231.29')
        self.assertEqual(watcher.move.get('server'), 'battle-gcore-17')

    # Reported by a user on GitHub (issue #1, 2026-11-09). Addresses below are documentation-range style stand-ins.
    G1_LINE = ('ConnectUpdater.GetAddress completed id=battle host=prod-game-eu-0-battle-g1-gcore-7.rob-run.kefir.games. '
               'dnsAddresses=1 isProxyPreferred=True addresses=5.188.178.115, 45.82.160.89')

    def test_g1_host_names_are_recognised_and_both_addresses_kept(self):
        watcher = patch.Watcher('does-not-exist', FakeRelay(), lambda *a, **k: None)
        watcher.read_line('NetworkStep - Changed on "InBattle".')
        watcher.read_line(self.G1_LINE)
        self.assertEqual(watcher.move.get('server'), 'battle-g1-gcore-7')
        self.assertEqual(watcher.move.get('addresses'), ['5.188.178.115', '45.82.160.89'])

    def test_stalled_proxy_join_routes_both_addresses_and_removes_both(self):
        relay = FakeRelay(); relay.also = set()
        watcher = patch.Watcher('does-not-exist', relay, lambda *a, **k: None)
        watcher.read_line('NetworkStep - Changed on "InBattle".')
        watcher.read_line(self.G1_LINE)
        watcher.read_line('PeerConnect started id=battle address=5.188.178.115:36650 rtt=60 attempts=0')
        watcher.move['started'] -= 3
        watcher.check_stall()
        self.assertEqual(relay.allowed, {'5.188.178.115', '45.82.160.89'})
        self.assertEqual(relay.target, ('5.188.178.115', 36650))
        self.assertEqual(relay.also, {('45.82.160.89', 36650)})
        watcher.read_line('NetworkStep - Changed on "InRealmNotInBattle".')
        self.assertFalse(relay.allowed); self.assertFalse(relay.also)

    def test_reconnect_steps_inside_a_battle_keep_the_route(self):
        relay = FakeRelay()
        watcher = patch.Watcher('does-not-exist', relay, lambda *a, **k: None)
        self.start(watcher); watcher.check_stall()
        self.assertTrue(relay.allowed)
        for step in ('WaitRegionUserData', 'WaitUserData', 'ConnectToRegion'):
            watcher.read_line(f'NetworkStep - Changed on "{step}".')
            self.assertTrue(relay.allowed, step)
        watcher.read_line('NetworkStep - Changed on "InRealmNotInBattle".')
        self.assertFalse(relay.allowed)

    def test_route_lasts_until_departure_and_rearms_cleanly(self):
        relay = FakeRelay()
        watcher = patch.Watcher('does-not-exist', relay, lambda *a, **k: None)
        self.start(watcher); watcher.check_stall()
        self.assertEqual(relay.target, ('5.8.93.226', 36706))
        relay.trials['old'] = patch.Proposal(0)
        watcher.read_line('PeerConnect complete id=battle address=5.8.93.226:36706')
        watcher.read_line('ConnectUpdater.Connect completed id=battle')
        self.assertTrue(relay.allowed)
        watcher.read_line('NetworkStep - Changed on "InRealmNotInBattle".')
        self.assertFalse(relay.allowed); self.assertFalse(relay.trials)
        self.start(watcher); watcher.check_stall()
        self.assertTrue(relay.allowed)

    def test_healthy_and_private_endpoints_never_routed(self):
        relay = FakeRelay(); watcher = patch.Watcher('does-not-exist', relay, lambda *a, **k: None)
        self.start(watcher)
        watcher.read_line('PeerConnect complete id=battle address=5.8.93.226:36706')
        watcher.check_stall(); self.assertFalse(relay.allowed)
        self.start(watcher, '127.0.0.1'); watcher.check_stall()
        self.assertFalse(relay.allowed)

    def test_failed_route_removal_is_reported(self):
        relay = transport.Relay(None, '127.0.0.1', 1)
        relay.allowed.add('5.8.93.226')
        with mock.object(transport, 'netsh', return_value=(1, 'failure')):
            with self.assertRaises(OSError): relay.remove_route('5.8.93.226')
        self.assertTrue(relay.allowed)

    def test_stop_request_prevents_new_trial(self):
        relay = FakeRelay(); watcher = patch.Watcher('does-not-exist', relay, lambda *a, **k: None)
        self.start(watcher); watcher.allow_trials = False; watcher.check_stall()
        self.assertFalse(relay.allowed)

class LongSessionTests(unittest.TestCase):
    start = LifecycleTests.start
    def test_still_repairs_after_two_hours_of_healthy_play(self):
        relay = FakeRelay(); relay.error = None
        events = []
        watcher = patch.Watcher('does-not-exist', relay, lambda event, **kw: events.append(event))
        clock = [0]
        polls = []

        def advance(_): clock[0] += 1800
        def poll():
            polls.append(clock[0])
            if clock[0] in (0, 1800, 3600):
                self.start(watcher)
                watcher.read_line('PeerConnect complete id=battle address=5.8.93.226:36706')
                watcher.read_line('NetworkStep - Changed on "InRealmNotInBattle".')
            elif clock[0] == 5400:
                self.start(watcher)
                watcher.check_stall()
                self.assertTrue(relay.allowed)
            elif clock[0] == 7200:
                watcher.read_line('NetworkStep - Changed on "InRealmNotInBattle".')

        with tempfile.TemporaryDirectory() as folder, mock.object(patch, 'ROOT', Path(folder)), \
             mock.object(patch.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.object(patch.time, 'sleep', side_effect=advance), \
             mock.object(patch.subprocess, 'run', side_effect=[Mock(returncode=0) for _ in range(5)] + [Mock(returncode=1)]), \
             mock.object(watcher, 'poll', side_effect=poll):
            patch.watch_session(watcher, relay, Mock(poll=Mock(return_value=None)), threading.Event(), lambda event, **kw: events.append(event))
        self.assertEqual(polls, [0, 1800, 3600, 5400, 7200])
        self.assertIn('trial', events)
        self.assertEqual(events[-1], 'game_exit')
        self.assertFalse(relay.allowed)

    def test_stop_still_waits_for_active_route(self):
        relay = FakeRelay(); relay.error = None; relay.allowed.add('5.8.93.226')
        watcher = patch.Watcher('does-not-exist', relay, lambda *a, **kw: None)
        stopping = threading.Event(); stopping.set()
        events = []
        def leave(_): relay.allowed.clear()
        with tempfile.TemporaryDirectory() as folder, mock.object(patch, 'ROOT', Path(folder)), \
             mock.object(patch.subprocess, 'run', return_value=Mock(returncode=0)), \
             mock.object(patch.time, 'sleep', side_effect=leave), mock.object(watcher, 'poll') as poll:
            patch.watch_session(watcher, relay, Mock(poll=Mock(return_value=None)), stopping, lambda event, **kw: events.append(event))
        self.assertEqual(poll.call_count, 2)
        self.assertFalse(watcher.allow_trials)
        self.assertEqual(events, ['stopping'])

    def test_hourly_limit_is_reported_and_recovers_when_budget_expires(self):
        events = []
        relay = patch.Relay(None, '127.0.0.1', 1, lambda *a, **kw: None)
        relay.opened.extend([0] * 60)
        watcher = patch.Watcher('does-not-exist', relay, lambda event, **kw: events.append(event))
        with mock.object(transport, 'log', side_effect=lambda text: patch.report_transport(text, lambda event: events.append(event))), \
             mock.object(transport, 'netsh', return_value=(0, '')), \
             mock.object(patch.time, 'monotonic', return_value=10):
            self.start(watcher)
            watcher.check_stall(); watcher.check_stall()
            self.assertFalse(relay.allowed)
            self.assertEqual(events, ['budget_limit'])
            with mock.object(patch.time, 'monotonic', return_value=3601):
                watcher.check_stall()
            self.assertTrue(relay.allowed)
            self.assertEqual(events, ['budget_limit', 'trial'])

    def test_retry_limit_reports_once_and_keeps_forwarding(self):
        events = []
        relay = patch.Relay(None, '127.0.0.1', 1, lambda event, **kw: events.append(event))
        relay.allowed.add('5.8.93.226'); relay.target = ('5.8.93.226', 36706)
        sock = Mock()
        packet = transport.build_udp_packet(socket.inet_aton('127.0.0.1'), socket.inet_aton('5.8.93.226'), 50000, 36706, connect_packet())
        with mock.object(relay, 'open_socket', side_effect=lambda flow: setattr(flow, 'sock', sock)):
            for second in range(30):
                with mock.object(patch.time, 'monotonic', return_value=second):
                    relay.handle_packet(packet)
        self.assertEqual(events.count('retry_limit'), 1)
        self.assertEqual(sock.sendto.call_count, 30)
        self.assertEqual(sum(p.changed for p in relay.trials.values()), 12)


class DiagnosticTests(unittest.TestCase):
    def test_auto_rearm_setting_defaults_and_opt_out(self):
        with tempfile.TemporaryDirectory() as folder, mock.object(patch, 'ROOT', Path(folder)):
            self.assertTrue(patch.auto_rearm_enabled())
            settings = Path(folder) / 'settings.json'
            settings.write_text('{"auto_rearm":false}')
            self.assertFalse(patch.auto_rearm_enabled())
            settings.write_text('x' * 5000)
            self.assertFalse(patch.auto_rearm_enabled())

    def test_size_rotation_privacy_and_export_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            diag = diagnostics.Diagnostics(folder)
            for _ in range(5000):
                diag.emit('connect', phase='baseline', seconds=1.2, token='SECRET', ip='1.2.3.4')
            files = list(Path(folder).glob('*.jsonl'))
            self.assertEqual(len(files), 2)
            self.assertLessEqual(sum(p.stat().st_size for p in files), 2 * diagnostics.LIMIT)
            self.assertNotIn('SECRET', ''.join(p.read_text() for p in files))
            output = Path(folder) / 'share.txt'; diagnostics.export(folder, output)
            self.assertLessEqual(output.stat().st_size, diagnostics.LIMIT)

    def test_opt_out_creates_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            diagnostics.Diagnostics(folder, False).emit('armed')
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_export_rejects_raw_logs_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'diagnostics.jsonl'
            path.write_text('SECRET' * 50000 + '\n' + json.dumps({'event':'armed','token':'SECRET'}) + '\n')
            output = Path(folder) / 'share.txt'; diagnostics.export(folder, output)
            self.assertNotIn('SECRET', output.read_text())
            path.write_text(json.dumps({'event':'armed','token':'SECRET'}) + '\n')
            diagnostics.export(folder, output)
            self.assertNotIn('SECRET', output.read_text())

class PacketTests(unittest.TestCase):
    def test_rebuilt_ipv4_udp_checksums(self):
        src = socket.inet_aton('127.0.0.1'); dst = socket.inet_aton('127.0.0.2')
        packet = transport.build_udp_packet(src, dst, 1000, 2000, b'payload')
        self.assertEqual(transport.checksum(packet[:20]), 0)
        pseudo = src + dst + struct.pack('!BBH', 0, 17, len(packet) - 20)
        self.assertEqual(transport.checksum(pseudo + packet[20:]), 0)
        self.assertEqual(packet[28:], b'payload')

if __name__ == '__main__': unittest.main()
