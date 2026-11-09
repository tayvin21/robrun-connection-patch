"""Windows adapter and UDP forwarding for the ROB RUN connection workaround."""
import collections
import ctypes
import ctypes.wintypes as w
import os
import re
import socket
import struct
import subprocess
import threading
import time

NAME = 'RobRunCommunityPatch'
TUN_IP = '198.18.77.4'
IP_UNICAST_IF = 31
CREATE_NO_WINDOW = 0x08000000
DEFAULT_LOG = os.path.join(os.environ.get('USERPROFILE', ''), r'AppData\LocalLow\Kefir\ROB RUN\Player.log')

def log(text):
    # Replaced by the application's bounded diagnostic sink.
    pass

def netsh(*args):
    result = subprocess.run(['netsh', *args], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=15)
    return result.returncode, (result.stdout + result.stderr).strip()

def checksum(data):
    if len(data) % 2:
        data += b'\0'
    total = sum(struct.unpack(f'!{len(data) // 2}H', data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def build_udp_packet(src, dst, sport, dport, payload):
    udp_length = 8 + len(payload)
    pseudo = src + dst + struct.pack('!BBH', 0, 17, udp_length)
    header = struct.pack('!HHHH', sport, dport, udp_length, 0)
    udp_sum = checksum(pseudo + header + payload) or 0xFFFF
    udp = struct.pack('!HHHH', sport, dport, udp_length, udp_sum) + payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + udp_length, 0, 0x4000, 64, 17, 0, src, dst)
    ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
    return ip + udp


class Tun:
    def __init__(self, dll_path):
        d = ctypes.WinDLL(dll_path, use_last_error=True)
        d.WintunCreateAdapter.restype = ctypes.c_void_p
        d.WintunCreateAdapter.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p]
        d.WintunCloseAdapter.argtypes = [ctypes.c_void_p]
        d.WintunStartSession.restype = ctypes.c_void_p
        d.WintunStartSession.argtypes = [ctypes.c_void_p, w.DWORD]
        d.WintunEndSession.argtypes = [ctypes.c_void_p]
        d.WintunGetReadWaitEvent.restype = w.HANDLE
        d.WintunGetReadWaitEvent.argtypes = [ctypes.c_void_p]
        d.WintunReceivePacket.restype = ctypes.c_void_p
        d.WintunReceivePacket.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.DWORD)]
        d.WintunReleaseReceivePacket.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        d.WintunAllocateSendPacket.restype = ctypes.c_void_p
        d.WintunAllocateSendPacket.argtypes = [ctypes.c_void_p, w.DWORD]
        d.WintunSendPacket.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.d = d
        self.lock = threading.Lock()
        self.closed = False
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.adapter = d.WintunCreateAdapter(NAME, NAME, None)
        if not self.adapter:
            raise OSError(ctypes.get_last_error(), 'WintunCreateAdapter failed')
        self.session = d.WintunStartSession(self.adapter, 0x400000)
        if not self.session:
            d.WintunCloseAdapter(self.adapter)
            raise OSError(ctypes.get_last_error(), 'WintunStartSession failed')
        self.event = d.WintunGetReadWaitEvent(self.session)

    def send(self, packet):
        with self.lock:
            if self.closed:
                return
            target = self.d.WintunAllocateSendPacket(self.session, len(packet))
            if target:
                ctypes.memmove(target, packet, len(packet))
                self.d.WintunSendPacket(self.session, target)

    def receive(self):
        size = w.DWORD()
        pointer = self.d.WintunReceivePacket(self.session, ctypes.byref(size))
        if not pointer:
            return None
        data = ctypes.string_at(pointer, size.value)
        self.d.WintunReleaseReceivePacket(self.session, pointer)
        return data

    def wait(self, milliseconds):
        self.kernel.WaitForSingleObject(self.event, milliseconds)

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.d.WintunEndSession(self.session)
                self.d.WintunCloseAdapter(self.adapter)


class Flow:
    def __init__(self, client_ip, client_port, server_ip, server_port):
        self.client_ip = client_ip
        self.client_port = client_port
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.created = 0.0
        self.replied = False
        self.ports = []


class Relay:
    def __init__(self, tun, egress_ip, interface_index, rotate_seconds, max_ports, port_budget=60, label=None):
        self.port_budget = port_budget
        self.opened = collections.deque()
        self.budget_warned = False
        self.tun = tun
        self.egress_ip = egress_ip
        self.interface_index = interface_index
        self.rotate_seconds = rotate_seconds
        self.max_ports = max_ports
        self.label = label or (lambda ip: ip)
        self.allowed = set()
        self.flows = {}
        self.lock = threading.Lock()
        self.stop = False
        self.readers = []

    def budget_ok(self):
        now = time.monotonic()
        while self.opened and now - self.opened[0] > 3600:
            self.opened.popleft()
        if len(self.opened) < self.port_budget:
            self.budget_warned = False
            return True
        if not self.budget_warned:
            self.budget_warned = True
            log(f'Hourly limit of {self.port_budget} new source ports reached. Not trying more for now.')
        return False

    def add_route(self, ip):
        if ip in self.allowed:
            return True
        code, text = netsh('interface', 'ipv4', 'add', 'route', f'prefix={ip}/32', f'interface={NAME}', 'metric=1', 'store=active')
        if code != 0:
            log(f'Could not add route: {text}')
            return False
        self.allowed.add(ip)
        return True

    def remove_route(self, ip):
        if ip not in self.allowed:
            return
        code, _ = netsh('interface', 'ipv4', 'delete', 'route', f'prefix={ip}/32', f'interface={NAME}', 'store=active')
        if code:
            raise OSError('Temporary route cleanup failed')
        self.allowed.discard(ip)
        with self.lock:
            for key in [k for k, f in self.flows.items() if f.server_ip == ip]:
                flow = self.flows.pop(key)
                if flow.sock:
                    flow.sock.close()
                    flow.sock = None

    def remove_all(self):
        for ip in list(self.allowed):
            self.remove_route(ip)

    def open_socket(self, flow):
        if flow.sock:
            flow.sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, IP_UNICAST_IF, struct.pack('!I', self.interface_index))
        sock.bind((self.egress_ip, 0))
        flow.sock = sock
        flow.created = time.monotonic()
        self.opened.append(flow.created)
        flow.ports.append(sock.getsockname()[1])
        index = len(flow.ports)
        log(f'{self.label(flow.server_ip)}:{flow.server_port}: sending from new source port #{index}')
        reader = threading.Thread(target=self.read_replies, args=(flow, sock, index), daemon=True)
        self.readers = [thread for thread in self.readers if thread.is_alive()]
        self.readers.append(reader)
        reader.start()

    def read_replies(self, flow, sock, index):
        sock.settimeout(1.0)
        server = (flow.server_ip, flow.server_port)
        while not self.stop:
            try:
                data, address = sock.recvfrom(65535)
            except socket.timeout:
                if flow.sock is not sock:
                    return
                continue
            except ConnectionResetError:
                log(f'{self.label(flow.server_ip)}:{flow.server_port}: server reports port closed (ICMP) on source port #{index}')
                continue
            except OSError:
                return
            if address != server:
                continue
            if not flow.replied:
                flow.replied = True
                log(f'{self.label(flow.server_ip)}:{flow.server_port}: SERVER ANSWERED on source port #{index}')
            self.tun.send(build_udp_packet(socket.inet_aton(flow.server_ip), flow.client_ip, flow.server_port, flow.client_port, data))

    def pump(self):
        while not self.stop:
            packet = self.tun.receive()
            if packet is None:
                self.tun.wait(100)
                continue
            self.handle_packet(packet)


class Watcher:
    def __init__(self, path, relay, stall_seconds):
        self.path = path
        self.relay = relay
        self.stall_seconds = stall_seconds
        self.position = os.path.getsize(path) if os.path.exists(path) else 0
        self.partial = b''
        self.move = None

    def end_move(self):
        if self.move and self.move.get('routed'):
            self.relay.remove_route(self.move['ip'])
            if not self.move.get('connected'):
                log(f"{self.move.get('server')}: not repaired before the server cancelled the join.")
        self.move = None

    def read_line(self, line):
        if 'id=battle' not in line and 'NetworkStep' not in line:
            return
        step = re.search(r'NetworkStep - Changed on "(\w+)"', line)
        if step:
            self.end_move()
            if step.group(1) == 'InBattle':
                self.move = {}
            return
        move = self.move
        if move is None:
            return
        found = re.search(r'GetAddress completed id=battle host=\S*?(battle-gcore-\d+)\S* dnsAddresses=\d+ addresses=([\d.]+)', line)
        if found:
            move.setdefault('server', found.group(1))
            return
        started = re.search(r'PeerConnect started id=battle address=([\d.]+):(\d+) rtt=(\d+)', line)
        if started and 'started' not in move:
            move.update(ip=started.group(1), port=started.group(2), rtt=int(started.group(3)), started=time.monotonic())
            return
        if 'PeerConnect complete id=battle' in line:
            move['handshake'] = True
            if move.get('routed'):
                log(f"{move.get('server')}: handshake completed through the relay.")
        elif re.search(r'ConnectUpdater\.Connect completed id=battle', line) and not move.get('connected'):
            move['connected'] = True
            if move.get('routed'):
                log(f"REPAIRED: {move.get('server')} connected {time.monotonic() - move['started']:.1f}s after the join began.")

    def check_stall(self):
        move = self.move
        if not move or 'started' not in move or move.get('handshake') or move.get('routed'):
            return
        limit = max(self.stall_seconds, move['rtt'] * 10 / 1000)
        if time.monotonic() - move['started'] >= limit and self.relay.budget_ok() and self.relay.add_route(move['ip']):
            move['routed'] = True
            log(f"{move.get('server')}: no answer after {limit:.1f}s. Rerouting this server through the relay.")

    def poll(self):
        try:
            with open(self.path, 'rb') as source:
                source.seek(0, os.SEEK_END)
                size = source.tell()
                if size < self.position:
                    log('Game restarted, following the new log.')
                    self.end_move()
                    self.position = 0
                    self.partial = b''
                if size > self.position:
                    source.seek(self.position)
                    data = source.read(1048576)
                    self.position += len(data)
                    lines = (self.partial + data).split(b'\n')
                    self.partial = lines.pop()[-16384:]
                    for raw in lines:
                        self.read_line(raw.decode('latin-1').rstrip('\r'))
        except OSError:
            pass
        self.check_stall()


def find_egress():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.connect(('8.8.8.8', 53))
    address = probe.getsockname()[0]
    probe.close()
    index = w.DWORD()
    target = struct.unpack('<I', socket.inet_aton('8.8.8.8'))[0]
    if ctypes.WinDLL('iphlpapi').GetBestInterface(target, ctypes.byref(index)) != 0:
        raise OSError('GetBestInterface failed')
    return address, index.value


def configure_adapter():
    for _ in range(40):
        code, text = netsh('interface', 'ipv4', 'set', 'interface', f'interface={NAME}', 'dadtransmits=0', 'routerdiscovery=disabled', 'store=active')
        if code == 0:
            break
        time.sleep(0.25)
    else:
        raise OSError(f'Could not find the adapter: {text}')
    code, text = netsh('interface', 'ipv4', 'set', 'address', f'name={NAME}', 'source=static', f'address={TUN_IP}', 'mask=255.255.255.255', 'gateway=none')
    if code != 0:
        raise OSError(f'Could not configure the adapter: {text}')
    query = f"(Get-NetIPAddress -InterfaceAlias '{NAME}' -IPAddress '{TUN_IP}' -ErrorAction SilentlyContinue).AddressState"
    state = ''
    for _ in range(40):
        state = subprocess.run(['powershell', '-NoProfile', '-Command', query], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW).stdout.strip()
        if state == 'Preferred':
            return
        time.sleep(0.25)
    raise OSError(f'The adapter address never became ready (state: {state})')
