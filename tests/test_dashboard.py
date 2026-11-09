import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import console
import dashboard
import demo

SECRET = 'FAKE-TOKEN-FOR-TESTS'


def stamp(tracker, text):
    tracker.feed('[2026-11-09 05:31:20.000] [1]')
    tracker.feed(text)


def clean_join(tracker, host='us-0-battle-gcore-27', ip='162.216.231.231'):
    stamp(tracker, '[Network] NetworkStep - Changed on "InBattle".')
    stamp(tracker, '[Network] ConnectUpdater.Connect started id=battle isHostExist=True isNetworkHostStarted=False isAuthorized=False needConnectSpecial=True')
    stamp(tracker, f'[Network] ConnectUpdater.GetAddress completed id=battle host=prod-game-{host}.rob-run.kefir.games. dnsAddresses=1 isProxyPreferred=False addresses={ip}')
    stamp(tracker, f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:36606 rtt=42 attempts=0')
    stamp(tracker, f'[Network] ConnectUpdater.PeerConnect complete id=battle address={ip}:36606')
    stamp(tracker, f'[Network] ConnectUpdater.PeerAuthorize started id=battle destination=11111111-1111-4111-8111-111111111111 peer=22222222-2222-4222-8222-222222222222 token={SECRET} attempts=1')
    stamp(tracker, '[Network] ConnectUpdater.Connect completed id=battle')
    stamp(tracker, '[Network] ConnectUpdater.Connect completed id=battle.')


class TrackerTests(unittest.TestCase):
    def test_clean_join_counts_one_connected_server_and_hides_secrets(self):
        t = dashboard.Tracker('x')
        clean_join(t)
        snap = t.snapshot()
        self.assertEqual(snap['roles']['battle']['status'], 'connected')
        self.assertEqual(snap['counts']['connected'], 1)
        self.assertEqual(snap['joins'][0]['outcome'], 'direct')
        self.assertEqual(snap['joins'][0]['host'], 'us-0-battle-gcore-27')
        blob = json.dumps(snap)
        for forbidden in (SECRET, '11111111', '22222222', 'token'):
            self.assertNotIn(forbidden, blob)

    def test_stall_retries_are_counted_and_patch_repair_is_attributed(self):
        t = dashboard.Tracker('x')
        ip = '91.199.82.145'
        stamp(t, '[Network] NetworkStep - Changed on "InBattle".')
        stamp(t, '[Network] ConnectUpdater.Connect started id=battle isHostExist=True isNetworkHostStarted=True isAuthorized=False needConnectSpecial=True')
        stamp(t, f'[Network] ConnectUpdater.GetAddress completed id=battle host=prod-game-us-0-battle-gcore-42.rob-run.kefir.games. dnsAddresses=1 isProxyPreferred=False addresses={ip}')
        stamp(t, f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:36602 rtt=52 attempts=0')
        self.assertEqual(t.snapshot()['counts']['connecting'], 1)
        t.tool_event('trial')
        t.tool_event('connect', phase='fresh_proposal')
        t.tool_event('reply')
        stamp(t, f'[Network] ConnectUpdater.PeerConnect attempt failed id=battle address={ip}:36602 error=0')
        stamp(t, '[Network] ConnectUpdater.Connect failed id=battle reason=connect_failed')
        self.assertEqual(t.snapshot()['counts']['retrying'], 1)
        stamp(t, f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:36602 rtt=100 attempts=0')
        stamp(t, f'[Network] ConnectUpdater.PeerConnect complete id=battle address={ip}:36602')
        stamp(t, '[Network] ConnectUpdater.Connect completed id=battle')
        t.tool_event('connected')
        join = t.snapshot()['joins'][0]
        self.assertEqual(join['outcome'], 'repaired')
        self.assertEqual([a['outcome'] for a in join['attempts']], ['failed', 'ok'])
        self.assertIn('proposal', [m['kind'] for m in join['marks']])
        self.assertEqual(t.snapshot()['totals']['repaired'], 1)

    def test_unrecovered_stall_is_failed_and_kick_is_recorded(self):
        t = dashboard.Tracker('x')
        stamp(t, '[Network] NetworkStep - Changed on "InBattle".')
        stamp(t, '[Network] ConnectUpdater.PeerConnect started id=battle address=1.2.3.4:36602 rtt=40 attempts=0')
        stamp(t, '[Network] NetworkStep - Changed on "InRealmNotInBattle".')
        join = t.snapshot()['joins'][0]
        self.assertEqual(join['outcome'], 'failed')
        self.assertEqual(join['attempts'][0]['outcome'], 'abandoned')
        clean_join(t)
        stamp(t, '[Network] NetworkStep - Changed on "InRealmNotInBattle".')
        stamp(t, '[EOS] battle-1 - NotifyDisconnected UserKicked.')
        self.assertEqual(t.snapshot()['joins'][0]['end_reason'], 'kicked')
        self.assertEqual(t.snapshot()['totals']['kicked'], 1)

    def test_demo_script_runs_and_ends(self):
        t = dashboard.Tracker('x')
        stop = threading.Event()
        script = demo.Script(t, stop, speed=400.0)
        runner = threading.Thread(target=script.run, daemon=True)
        runner.start()
        runner.join(timeout=0.5)
        stop.set()
        runner.join(timeout=3)
        snap = t.snapshot()
        self.assertGreaterEqual(snap['totals']['joins'], 3)
        self.assertGreaterEqual(snap['totals']['repaired'], 1)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        (Path(self.dir.name) / 'index.html').write_text('<!doctype html><title>t</title>', encoding='utf-8')
        (Path(self.dir.name) / 'secret.txt').write_text('no', encoding='utf-8')
        outside = Path(self.dir.name).parent / 'outside.css'
        outside.write_text('x{}', encoding='utf-8')
        self.outside = outside
        self.tracker = dashboard.Tracker('x')
        self.server, self.url = dashboard.serve(self.tracker, self.dir.name, preferred_port=0)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.outside.unlink(missing_ok=True)
        self.dir.cleanup()

    def get(self, path, host=None, method='GET'):
        request = Request(f'http://127.0.0.1:{self.port}{path}', method=method, headers={'Host': host} if host else {})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except HTTPError as error:
            return error.code, dict(error.headers), b''

    def test_serves_state_and_page_with_strict_headers(self):
        code, headers, body = self.get('/api/state')
        self.assertEqual(code, 200)
        self.assertIn('roles', json.loads(body))
        code, headers, _ = self.get('/')
        self.assertEqual(code, 200)
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_rejects_foreign_host_writes_odd_types_and_traversal(self):
        self.assertEqual(self.get('/api/state', host='evil.example')[0], 403)
        self.assertEqual(self.get('/api/state', method='POST')[0], 405)
        self.assertEqual(self.get('/secret.txt')[0], 404)
        self.assertEqual(self.get('/..%2foutside.css')[0], 404)
        self.assertEqual(self.get('/../outside.css')[0], 404)


class ConsoleTests(unittest.TestCase):
    def snapshot(self):
        t = dashboard.Tracker('x')
        clean_join(t)
        stamp(t, '[Network] ConnectUpdater.Connect started id=user isHostExist=True isNetworkHostStarted=False isAuthorized=False needConnectSpecial=True')
        t.tool_event('trial')
        t.set_relay(routes=1)
        return t.snapshot()

    def test_frames_fit_every_size_in_both_glyph_sets(self):
        snap = self.snapshot()
        for rich in (True, False):
            for width, height in ((110, 40), (100, 30), (80, 24), (60, 20), (50, 12)):
                view = console.View(rich=rich, color=True)
                view.log('hello')
                for tick in (0, 3, 9):
                    frame = view.frame(snap, tick, width, height)
                    self.assertLessEqual(len(frame), height)
                    for line in frame:
                        self.assertLessEqual(console.vlen(line), width, line)

    def test_plain_mode_has_no_escape_codes_and_safe_ascii_set_is_ascii(self):
        snap = self.snapshot()
        frame = console.View(rich=False, color=False).frame(snap, 1, 100, 30)
        text = '\n'.join(frame)
        self.assertNotIn('\x1b', text)
        self.assertTrue(text.isascii())

    def test_states_use_words_not_only_colour(self):
        snap = self.snapshot()
        text = '\n'.join(console.ANSI.sub('', line) for line in console.View(rich=True).frame(snap, 1, 100, 30))
        self.assertIn('Connected', text)
        self.assertIn('Connecting', text)
        self.assertIn('PATCH RELAY', text)


if __name__ == '__main__':
    unittest.main()
