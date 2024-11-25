import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

MAX32 = 2 ** 32
NTP_EPOCH = datetime(1900, 1, 1, tzinfo=timezone.utc)
NTP_VERSION = 4


class LEAP(Enum):
    NONE = 0
    ADD = 1
    REMOVE = 2
    UNSYNCHRONIZED = 3


class MODE(Enum):
    UNSPECIFIED = 0
    SYMMETRIC_ACTIVE = 1
    SYMMETRIC_PASSIVE = 2
    CLIENT = 3
    SERVER = 4
    BROADCAST_MULTICAST = 5
    CONTROL_MESSAGE = 6
    RESERVED = 7


@dataclass
class LeapVerMode:
    leap: LEAP
    mode: MODE
    version: int = NTP_VERSION

    @classmethod
    def from_packed(cls, value):
        return cls(
            leap=LEAP((value & 0b11000000) >> 6),
            version=(value & 0b00111000) >> 3,
            mode=MODE(value & 0b00000111))

    def to_packed(self):
        return (self.leap.value << 6) \
            | (self.version << 3) \
            | self.mode.value


def _to_ts(dt):
    return int((dt - NTP_EPOCH).total_seconds() * MAX32)


def local_now():
    return datetime.now(tz=timezone.utc)


def server_offset(host, port=123, timeout=5):
    client = socket.socket(type=socket.SOCK_DGRAM)
    client.settimeout(timeout)

    request = struct.pack(
        '!B39xQ',
        LeapVerMode(leap=LEAP.NONE, mode=MODE.CLIENT).to_packed(),
        _to_ts(local_now()))
    client.sendto(request, (host, port))
    response, _ = client.recvfrom(1024)
    finish_ts = _to_ts(local_now())

    lvm, stratum, start_ts, rx_ts, tx_ts = struct.unpack('!2B22x3Q', response)
    lvm = LeapVerMode.from_packed(lvm)

    ok = lvm.leap != LEAP.UNSYNCHRONIZED \
        and lvm.mode == MODE.SERVER \
        and 0 < stratum < 16 \
        and tx_ts != 0

    if not ok:
        return None

    offset = ((rx_ts - start_ts) - (finish_ts - tx_ts)) / 2
    delay = (finish_ts - start_ts) - (tx_ts - rx_ts)

    return offset / MAX32, delay / MAX32
