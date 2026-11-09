"""Scripted demo session for the status views. Needs no game, no admin rights and touches no network.

It replays the shape of a real session (recorded 2026-11-09): sign-in, a clean join, a server-side kick, a stall the
patch could not see, then two stalls it repaired. Hosts and addresses are public game servers; no tokens exist here.
"""
import datetime
import threading


def _stamp():
    return '[' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + '] [1]'


class Script:
    def __init__(self, tracker, stop, speed=1.0):
        self.tracker = tracker
        self.stop = stop
        self.speed = speed

    def wait(self, seconds):
        self.stop.wait(seconds / self.speed)
        return not self.stop.is_set()

    def line(self, text):
        self.tracker.feed(_stamp())
        self.tracker.feed(text)

    def tool(self, event, **fields):
        self.tracker.tool_event(event, **fields)

    def step(self, name):
        self.line(f'[Network] NetworkStep - Changed on "{name}".')

    def connect_clean(self, role, host, ip, port, rtt):
        self.line(f'[Network] ConnectUpdater.Connect started id={role} isHostExist=True isNetworkHostStarted=False isAuthorized=False needConnectSpecial=True')
        self.wait(0.3)
        self.line(f'[Network] ConnectUpdater.GetAddress completed id={role} host=prod-game-{host}.rob-run.kefir.games. dnsAddresses=1 isProxyPreferred=False addresses={ip}')
        self.line(f'[Network] ConnectUpdater.PeerConnect started id={role} address={ip}:{port} rtt={rtt} attempts=0')
        self.wait(0.5)
        self.line(f'[Network] ConnectUpdater.PeerConnect complete id={role} address={ip}:{port}')
        self.wait(0.2)
        self.line(f'[Network] ConnectUpdater.Connect completed id={role}')

    def stalled_join(self, host, ip, port, failures, repaired):
        self.step('InBattle')
        self.line('[Network] ConnectUpdater.Connect started id=battle isHostExist=True isNetworkHostStarted=True isAuthorized=False needConnectSpecial=True')
        self.line(f'[Network] ConnectUpdater.GetAddress completed id=battle host=prod-game-{host}.rob-run.kefir.games. dnsAddresses=1 isProxyPreferred=False addresses={ip}')
        self.line(f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:{port} rtt=48 attempts=0')
        if repaired:
            self.wait(0.6)
            self.tool('trial')
            self.tracker.set_relay(routes=1, flows=1, ports_hour=3)
            self.tool('connect', phase='baseline')
            self.wait(3.2)
            self.tool('connect', phase='baseline')
            self.tool('connect', phase='baseline')
            self.wait(0.3)
            self.tool('connect', phase='fresh_proposal')
            self.tool('reply')
            self.wait(0.4)
        else:
            for i in range(failures):
                self.wait(5.0 if i == 0 else 4.0)
                if self.stop.is_set():
                    return
                self.line(f'[Network] ConnectUpdater.PeerConnect attempt failed id=battle address={ip}:{port} error=0')
                self.line(f'[Network] ConnectUpdater.PeerConnect failed id=battle address={ip}:{port}')
                self.line('[Network] ConnectUpdater.Connect failed id=battle reason=connect_failed')
                self.line('[Network] ConnectUpdater.Connect started id=battle isHostExist=True isNetworkHostStarted=True isAuthorized=False needConnectSpecial=True')
                self.line(f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:{port} rtt=45 attempts=0')
            self.wait(3.0)
            self.step('InRealmNotInBattle')
            return
        self.line(f'[Network] ConnectUpdater.PeerConnect attempt failed id=battle address={ip}:{port} error=0')
        self.line(f'[Network] ConnectUpdater.PeerConnect failed id=battle address={ip}:{port}')
        self.line('[Network] ConnectUpdater.Connect failed id=battle reason=connect_failed')
        self.line(f'[Network] ConnectUpdater.PeerConnect started id=battle address={ip}:{port} rtt=100 attempts=0')
        self.wait(0.2)
        self.line(f'[Network] ConnectUpdater.PeerConnect complete id=battle address={ip}:{port}')
        self.line('[Network] ConnectUpdater.Connect completed id=battle')
        self.tool('connected')
        self.wait(6.0)
        self.line('[Network] RoomConnection.DisconnectedNetworkPeerPacket battle')
        self.step('InRealmNotInBattle')
        self.line('[EOS] battle-demo - NotifyDisconnected Success.')
        self.tool('ended', result='connected')
        self.tracker.set_relay(routes=0, flows=0)

    def run(self):
        t = self.tracker
        t.set_game(True)
        self.tool('startup')
        self.tool('armed')
        self.step('WaitUserData')
        self.connect_clean('user', 'center-7', '34.38.12.1', 36002, 120)
        self.step('ConnectToRegion')
        self.connect_clean('region_user', 'us-0-meta-gcore-14', '162.216.231.213', 36502, 40)
        self.step('WaitStartMainMenuInput')
        if not self.wait(1.5):
            return
        while not self.stop.is_set():
            self.step('InBattle')
            self.connect_clean('battle', 'us-0-battle-gcore-27', '162.216.231.231', 36606, 42)
            self.wait(5.0)
            self.line('[Network] RoomConnection.DisconnectedNetworkPeerPacket battle')
            self.step('InRealmNotInBattle')
            self.line('[EOS] battle-demo - NotifyDisconnected UserKicked.')
            if not self.wait(2.0):
                return
            self.stalled_join('us-0-battle-gcore-42', '91.199.82.145', 36602, failures=3, repaired=False)
            if not self.wait(2.0):
                return
            self.stalled_join('us-0-battle-gcore-42', '91.199.82.145', 36602, failures=0, repaired=True)
            if not self.wait(2.0):
                return
            self.stalled_join('us-0-battle-gcore-43', '95.85.93.104', 36706, failures=0, repaired=True)
            if not self.wait(6.0):
                return


def start(tracker, stop, speed=1.0):
    thread = threading.Thread(target=Script(tracker, stop, speed).run, daemon=True)
    thread.start()
    return thread

