"""Experimental ROB RUN connection helper."""
import argparse
import ctypes
import ctypes.wintypes as w
import ipaddress
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib

sys.dont_write_bytecode = True
import diagnostics
import transport

VERSION = '0.2.2'
ROOT = Path(__file__).resolve().parent
WARNING = '''UNOFFICIAL EXPERIMENTAL PATCH - NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.
THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN. USE AT YOUR OWN RISK.
May fail or disconnect you. Requires administrator access and changes network routing.
No game-file or memory edits. No automatic uploads. No restart of your game.'''


def inspect_connect(payload):
    if len(payload) != 53 or payload[:2] != b'\x8f\xff' or payload[8:14] != b'\x82\xff\x00\x01\x00\x00':
        return None
    if payload[24] != 2 or payload[49:53] != bytes(4):
        return None
    if any(s not in (0, 1, 2, 3, 255) for s in payload[14:16]):
        return None
    check = bytearray(payload)
    check[4:8] = bytes(4)
    if payload[4:8] != zlib.crc32(check).to_bytes(4, 'big'):
        return None
    return payload[14:16]


class Proposal:
    def __init__(self, now):
        self.started = now
        self.baseline = 0
        self.changed = 0

    def process(self, payload, now, replied):
        sessions = inspect_connect(payload)
        if sessions is None:
            return payload, None
        if replied:
            return payload, 'reply_seen'
        if self.baseline < 3 or now - self.started < 3:
            self.baseline += 1
            return payload, 'baseline'
        if self.changed >= 12:
            return payload, 'limit_reached'
        if sessions == b'\xff\xff':
            return payload, 'already_fresh'
        updated = bytearray(payload)
        updated[14:16] = b'\xff\xff'
        updated[4:8] = bytes(4)
        updated[4:8] = zlib.crc32(updated).to_bytes(4, 'big')
        self.changed += 1
        return bytes(updated), 'fresh_proposal'


class Relay(transport.Relay):
    def __init__(self, tun, egress, index, report):
        super().__init__(tun, egress, index, 1e9, 1, port_budget=60)
        self.target = None
        self.trials = {}
        self.error = None
        self.report = report

    def handle_packet(self, packet):
        if len(packet) < 28 or packet[0] >> 4 != 4 or packet[9] != 17:
            return
        header = (packet[0] & 15) * 4
        if header < 20 or len(packet) < header + 8 or struct.unpack_from('!H', packet, 6)[0] & 0x3fff:
            return
        ip = socket.inet_ntoa(packet[16:20])
        if ip not in self.allowed:
            return
        cp, sp, length = struct.unpack_from('!HHH', packet, header)
        if length < 8 or header + length > len(packet):
            return
        payload = packet[header + 8:header + length]
        key = (cp, ip, sp)
        with self.lock:
            flow = self.flows.get(key)
            if flow is None:
                if len(self.flows) >= 16:
                    return
                flow = transport.Flow(packet[12:16], cp, ip, sp)
                self.flows[key] = flow
                self.open_socket(flow)
            sock = flow.sock
            if (ip, sp) == self.target:
                state = self.trials.setdefault(key, Proposal(time.monotonic()))
                payload, phase = state.process(payload, time.monotonic(), flow.replied)
                if phase:
                    self.report('connect', phase=phase, seconds=round(time.monotonic() - state.started, 3), baseline=state.baseline, changed=state.changed)
        try:
            sock.sendto(payload, (ip, sp))
        except OSError:
            self.report('error', result='udp_send')

    def pump(self):
        try:
            super().pump()
        except Exception as error:
            self.error = type(error).__name__
            self.stop = True


class Watcher(transport.Watcher):
    def __init__(self, path, relay, report):
        super().__init__(path, relay, 2)
        self.report = report
        self.ended = False
        self.allow_trials = True

    def check_stall(self):
        move = self.move
        if not self.allow_trials or not move or 'started' not in move or move.get('handshake') or move.get('routed'):
            return
        port = int(move['port'])
        if not move.get('server') or not 36600 <= port <= 36711 or not ipaddress.ip_address(move['ip']).is_global:
            return
        if time.monotonic() - move['started'] < max(2, move['rtt'] / 100):
            return
        if not self.relay.budget_ok():
            return
        self.relay.target = (move['ip'], port)
        if self.relay.add_route(move['ip']):
            move['routed'] = True
            self.report('trial')
        else:
            self.report('route_failed')

    def end_move(self):
        routed = bool(self.move and self.move.get('routed'))
        connected = bool(self.move and self.move.get('connected'))
        super().end_move()
        if routed:
            with self.relay.lock:
                self.relay.trials.clear()
                self.relay.target = None
            self.ended = True
            self.report('ended', result='connected' if connected else 'not_connected')


def adapters_present():
    command = "Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @('RobRunRepair','RobRunFreshHandshake','RobRunCommunityPatch') } | Select-Object -ExpandProperty Name"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True, creationflags=transport.CREATE_NO_WINDOW, timeout=20)
    if result.returncode:
        raise OSError('Cannot check existing adapters')
    return bool(result.stdout.strip())


def auto_rearm_enabled():
    try:
        with (ROOT / 'settings.json').open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return False
        settings = json.loads(raw)
        return isinstance(settings, dict) and settings.get('auto_rearm', True) is True
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False


def guard(parent):
    """Remove the helper's remaining routes after its process exits."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.OpenMutexW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
    kernel.OpenMutexW.restype = w.HANDLE
    mutex = kernel.OpenMutexW(0x100000, False, 'Local\\RobRunCommunityPatch')
    kernel.OpenEventW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
    kernel.OpenEventW.restype = w.HANDLE
    kernel.SetEvent.argtypes = [w.HANDLE]
    ready = kernel.OpenEventW(2, False, f'Local\\RobRunPatchGuardReady_{parent}')
    if not mutex or not ready:
        raise RuntimeError('Guardian handshake failed')
    handle = kernel.OpenProcess(0x100000, False, parent)
    kernel.SetEvent(ready)
    kernel.CloseHandle(ready)
    if handle:
        kernel.WaitForSingleObject(handle, 0xffffffff)
        kernel.CloseHandle(handle)
    command = "Get-NetRoute -InterfaceAlias 'RobRunCommunityPatch' -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.DestinationPrefix -ne '198.18.77.4/32' } | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue"
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, creationflags=transport.CREATE_NO_WINDOW, timeout=20)
    kernel.CloseHandle(mutex)


def run(opt):
    print(WARNING, flush=True)
    if not opt.accept_risk:
        print('\nStart with START.cmd and accept the warning before enabling the patch.')
        return 1
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print('Administrator access is required. Run START.cmd.')
        return 1
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
    kernel.CreateMutexW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\RobRunCommunityPatch')
    if not mutex or ctypes.get_last_error() == 183:
        if mutex:
            kernel.CloseHandle(mutex)
        print('Another copy is running. Use its window.')
        return 1
    diag = diagnostics.Diagnostics(ROOT / 'logs', enabled=not opt.no_logs)
    tun = relay = pump = None
    stopping = threading.Event()

    def report(event, **fields):
        diag.emit(event, **fields)
        try:
            (ROOT / 'status.json').write_text(json.dumps({'pid': os.getpid(), 'status': event, 'version': VERSION}), encoding='utf-8')
        except OSError:
            pass
        labels = {'startup': 'STARTING', 'armed': 'ARMED - waiting for a stalled join',
                  'trial': 'TESTING - forwarding unchanged connection requests',
                  'reply': 'Server replied', 'ended': 'Location ended; route removed',
                  'stopping': 'STOP REQUESTED - waiting for you to leave this location normally',
                  'cleanup': 'STOPPED - temporary adapter released', 'error': 'ERROR - see local diagnostic code',
                  'route_failed': 'Could not add temporary route', 'idle_stop': 'Stopped after 60 idle minutes'}
        if event == 'connect' and fields.get('phase') == 'fresh_proposal' and fields.get('changed') == 1:
            print('TESTING - fresh handshake proposed; waiting for reply', flush=True)
        elif event == 'connected':
            changed = any(p.changed for p in relay.trials.values()) if relay else False
            print('CONNECTED - after handshake change (cause not proven)' if changed else 'CONNECTED - before handshake change', flush=True)
        elif event in labels:
            print(labels[event], flush=True)

    def transport_log(text):
        if 'SERVER ANSWERED' in text:
            report('reply')
        elif text.startswith('REPAIRED:'):
            report('connected')
        elif text.startswith('Could not add route:'):
            report('route_failed')

    transport.log = transport_log
    try:
        if adapters_present():
            print('Another ROB RUN relay adapter exists. Leave its location and stop that helper first.')
            return 1
        if not Path(transport.DEFAULT_LOG).exists():
            print('Game log not found. Start ROB RUN through Steam first, then run START.cmd.')
            return 1
        dll = ROOT / 'wintun.dll'
        if not dll.exists():
            print('Missing bundled wintun.dll. Download the release ZIP and extract all files.')
            return 1
        # Guardian starts before any temporary route exists. It cannot overlap another instance.
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
        kernel.CreateEventW.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        ready = kernel.CreateEventW(None, True, False, f'Local\\RobRunPatchGuardReady_{os.getpid()}')
        if not ready:
            raise OSError('Cannot create cleanup handshake')
        guardian = subprocess.Popen([sys.executable, str(ROOT / 'patch.py'), '--guard', str(os.getpid())], creationflags=transport.CREATE_NO_WINDOW)
        try:
            if kernel.WaitForSingleObject(ready, 10000) != 0:
                raise OSError('Cleanup guardian did not become ready')
        finally:
            kernel.CloseHandle(ready)
        report('startup', version=VERSION)
        egress, index = transport.find_egress()
        tun = transport.Tun(str(dll))
        transport.configure_adapter()
        relay = Relay(tun, egress, index, report)
        pump = threading.Thread(target=relay.pump, daemon=True)
        pump.start()
        watcher = Watcher(transport.DEFAULT_LOG, relay, report)
        # Ignore completed assignments when attaching to an existing game log.
        with open(transport.DEFAULT_LOG, 'rb') as stream:
            stream.seek(max(0, watcher.position - 2_000_000))
            lines = stream.read(watcher.position - stream.tell()).decode('latin-1').splitlines()
        starts = [i for i, line in enumerate(lines) if 'NetworkStep - Changed on ' in line]
        if starts:
            for line in lines[starts[-1]:]:
                watcher.read_line(line)
        report('armed')
        print('Press ENTER to stop safely. If connected through the relay, leave the location first.\nLocal diagnostics: ' + ('OFF' if opt.no_logs else 'ON (256 KiB maximum; never uploaded)'), flush=True)
        def request_stop():
            try:
                input()
            except EOFError:
                pass
            stopping.set()
        threading.Thread(target=request_stop, daemon=True).start()
        deadline = time.monotonic() + 3600
        next_game_check = 0
        notified = False
        while True:
            try:
                if (ROOT / 'stop.request').exists():
                    stopping.set()
                watcher.allow_trials = not stopping.is_set()
                if time.monotonic() >= next_game_check:
                    game = subprocess.run(['powershell.exe', '-NoProfile', '-Command', "if (Get-Process -Name 'ROB RUN' -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"], capture_output=True, creationflags=transport.CREATE_NO_WINDOW, timeout=15)
                    next_game_check = time.monotonic() + 5
                    if game.returncode == 1:
                        watcher.end_move()
                        break
                    if game.returncode != 0:
                        raise OSError('Could not check game process')
                watcher.poll()
                if relay.error:
                    raise RuntimeError(relay.error)
                if guardian.poll() is not None:
                    raise RuntimeError('Cleanup guardian stopped unexpectedly')
                if watcher.ended:
                    watcher.ended = False
                    deadline = time.monotonic() + 3600
                    if not auto_rearm_enabled():
                        stopping.set()
                    elif not stopping.is_set():
                        report('armed')
                if stopping.is_set():
                    if not relay.allowed:
                        break
                    if not notified:
                        report('stopping')
                        notified = True
                    # Stop is deferred while forwarding an active assignment.
                if not relay.allowed and time.monotonic() > deadline:
                    report('idle_stop')
                    break
                time.sleep(0.1)
            except KeyboardInterrupt:
                stopping.set()
    except Exception as error:
        report('error', result=type(error).__name__)
        print('Patch stopped because of an error. Do not disable EAC or antivirus to run it.', flush=True)
        return 2
    finally:
        try:
            if relay:
                relay.stop = True
                if pump:
                    pump.join(timeout=2)
                relay.remove_all()
        finally:
            if tun:
                tun.close()
            kernel.CloseHandle(mutex)
            report('cleanup')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accept-risk', action='store_true')
    parser.add_argument('--no-logs', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--guard', type=int)
    opt = parser.parse_args()
    if opt.export:
        count = diagnostics.export(ROOT / 'logs', ROOT / 'diagnostics-share.txt')
        print(f'Exported {count} events to {ROOT / "diagnostics-share.txt"} (maximum 128 KiB). Review before sharing. Nothing uploaded.')
        return 0
    if opt.guard:
        guard(opt.guard)
        return 0
    return run(opt)


if __name__ == '__main__':
    raise SystemExit(main())
