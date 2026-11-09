import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import console
import tracking
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
        t = tracking.Tracker('x')
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
        t = tracking.Tracker('x')
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
        t = tracking.Tracker('x')
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
        t = tracking.Tracker('x')
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


class ConsoleTests(unittest.TestCase):
    def snapshot(self):
        t = tracking.Tracker('x')
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

    def test_update_note_shows_in_header(self):
        t = tracking.Tracker('0.3.0')
        t.set_update('0.4.0')
        shown = '\n'.join(console.ANSI.sub('', line) for line in console.View(rich=False).frame(t.snapshot(), 0, 100, 30))
        self.assertIn('UPDATE v0.4.0 is available', shown)
        quiet = '\n'.join(console.View(rich=False).frame(tracking.Tracker('0.3.0').snapshot(), 0, 100, 30))
        self.assertNotIn('UPDATE', quiet)


if __name__ == '__main__':
    unittest.main()
