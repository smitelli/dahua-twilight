import re
import socket
import struct
from io import BytesIO
from clock import clock


class Inventory:
    def __init__(self):
        self.reset()

    def reset(self):
        self.table = {}

    def register(self, packet):
        self.table[packet.host] = (clock.now(), packet)

    def do_expirations(self, max_age):
        now = clock.now()
        self.table = {
            k: v for k, v in self.table.items()
            if (now - v[0]).total_seconds() <= max_age}

    def all_packets(self):
        yield from (v[1] for v in self.table.values())

    def all_nvrs(self):
        yield from (p for p in self.all_packets() if isinstance(p, NVRPacket))

    def all_cameras(self):
        yield from (p for p in self.all_packets() if isinstance(p, CameraPacket))


class Packet:
    @staticmethod
    def discern(**kwargs):
        payload = kwargs['payload']

        if payload.startswith(b'\xa3'):
            p = NVRPacket(**kwargs)
        elif payload.startswith(b'\xb3'):
            p = CameraPacket(**kwargs)
        else:
            raise Exception('weird payload magic number')

        return p

    def __init__(self, payload, host, port):
        self.payload = payload
        self.host = host
        self.port = port
        self.data = {}
        self.trailer = {}

        f = BytesIO(self.payload)

        for field, fmt, *options in self._fields:
            read_size = struct.calcsize(fmt)
            value = struct.unpack(f'<{fmt}', f.read(read_size))

            unmarshal_fn = self._unmarshal_default
            if options:
                unmarshal_fn = getattr(self, options[0])

            self.data[field] = unmarshal_fn(value)

        trailer_data = f.read().decode()
        for line in trailer_data.splitlines(keepends=False):
            if match := re.match(r'([^:]+):\s*(.*)', line):
                self.trailer[match[1]] = match[2]

    def __getattr__(self, attr):
        return self.to_dict()[attr]

    def to_dict(self):
        return {
            **self.data,
            **self.trailer}

    def _unmarshal_default(self, value):
        return value[0]

    def _unmarshal_unknown(self, value):
        return value[0].hex(' ', 1)


class NVRPacket(Packet):
    _fields = [
        ('message_type', '4s', '_unmarshal_unknown'),  # a3 01 00 01
        ('payload_length', 'I'),
        ('seq_or_id', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('unknown_0c', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('length_or_sid', '4s', '_unmarshal_unknown'),  # 02 00 00 00
        ('trailer_length', 'I'),
        ('sid', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('unknown_1c', '4s', '_unmarshal_unknown')]  # 00 00 00 00

    @property
    def hostname(self):
        host_last_octet = self.host.split('.')[-1]
        return f'NVR{host_last_octet}'


class CameraPacket(Packet):
    _fields = [
        ('message_type', '4s', '_unmarshal_unknown'),  # b3 00 1c 01 ## 0x1c may be length of mac+model not counted by payload_length
        ('payload_length', 'I'),  # not counting 32 byte header, mac+model, or trailer
        ('seq_or_id', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('unknown_0c', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('length_or_sid', '4s', '_unmarshal_unknown'),  # 02 00 00 00
        ('trailer_length', 'I'),
        ('sid', '4s', '_unmarshal_unknown'),  # 00 00 01 00
        ('unknown_1c', '4s', '_unmarshal_unknown'),  # 00 00 00 00
        ('version', '4H', '_unmarshal_version'),  # @0x20
        ('hostname', '16s', '_unmarshal_string'),
        ('ip', '4s', '_unmarshal_ip'),
        ('subnet_mask', '4s', '_unmarshal_ip'),
        ('default_gateway', '4s', '_unmarshal_ip'),
        ('dns_ip', '4s', '_unmarshal_ip'),
        ('alarm_ip', '4s', '_unmarshal_ip'),
        ('alarm_port', 'H'),
        ('unknown_4e', '2s', '_unmarshal_unknown'),  # 2f 01 (303, 12033, 47/1)
        ('email_ip', '4s', '_unmarshal_ip'),
        ('email_port', 'H'),
        ('unknown_56', '8s', '_unmarshal_unknown'),  # 00 02 00 00 00 00 00 00
        ('http_port', 'H'),
        ('https_port', 'H'),
        ('tcp_port', 'H'),
        ('max_connections', 'H'),
        ('ssl_port', 'H'),
        ('udp_port', 'H'),
        ('unknown_6a', '2s', '_unmarshal_unknown'),  # 00 00
        ('multicast_ip', '4s', '_unmarshal_ip'),
        ('multicast_port', 'H'),
        ('unknown_72', '6s', '_unmarshal_unknown'),  # 00 00 00 00 00 00
        ('mac', '17s', '_unmarshal_string'),  # @0x78
        ('model', '11s', '_unmarshal_string')]  # @0x89

    def _unmarshal_ip(self, value):
        return socket.inet_ntoa(value[0])

    def _unmarshal_string(self, value):
        return value[0].rstrip(b'\0').decode()

    def _unmarshal_version(self, value):
        return f'{value[0]}.{value[1]}.{value[2]}.{value[3]}'


inventory = Inventory()
