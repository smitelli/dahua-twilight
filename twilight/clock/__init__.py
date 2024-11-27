import statistics
import time
from datetime import datetime, timedelta, timezone
from . import sntp
from config import config

OWN_EPOCH = datetime(2024, 11, 1, tzinfo=timezone.utc)
CLOCK_CONFIG = config.get_clock_config()


class UnsynchronizedException(Exception):
    pass


class Clock:
    DEFAULT_SLEEP_RESOLUTION = CLOCK_CONFIG.get('default_sleep_resolution', 0.25)
    MAX_SYNC_AGE = CLOCK_CONFIG.get('max_sync_age', 64)
    OFFSET_BUFFER_SIZE = CLOCK_CONFIG.get('offset_buffer_size', 10)
    SERVER_PORT = CLOCK_CONFIG.get('server_port', 123)
    SERVER_TIMEOUT = CLOCK_CONFIG.get('server_timeout', 2)

    @staticmethod
    def intraday_delta(d1, d2):
        d2 = d2.astimezone(d1.tzinfo).replace(year=d1.year, month=d1.month, day=d1.day)

        return d1 - d2

    def __init__(self):
        self.reset()

    def reset(self, server=None):
        self.server = server

        self.last_refresh = sntp.NTP_EPOCH
        self.offset_buffer = [None] * self.OFFSET_BUFFER_SIZE

    def use_ntp_server(self, server):
        if self.server != server:
            self.reset(server=server)
            self.sync()

            if not self.is_valid():
                self.reset()
                return False

        return True

    def sync(self):
        if self.server is None:
            return

        lnow = sntp.local_now()
        if (lnow - self.last_refresh).total_seconds() <= self.MAX_SYNC_AGE:
            return
        self.last_refresh = lnow

        try:
            offset, delay = sntp.server_offset(
                host=self.server, port=self.SERVER_PORT, timeout=self.SERVER_TIMEOUT)
        except Exception:
            offset = None

        self.offset_buffer.pop()
        self.offset_buffer.insert(0, offset)

    def is_valid(self):
        self.sync()

        return any(self.offset_buffer)

    def now(self):
        self.sync()

        if not self.is_valid():
            raise UnsynchronizedException(f'not synchronized to server: {self.server}')

        offset = statistics.mean(o for o in self.offset_buffer if o is not None)

        dt = sntp.local_now() + timedelta(seconds=offset)

        while dt < OWN_EPOCH:
            dt += timedelta(seconds=sntp.MAX32)

        return dt

    def sleep(self, delay, resolution=None):
        if resolution is None:
            resolution = self.DEFAULT_SLEEP_RESOLUTION

        if not self.is_valid()
            time.sleep(delay)
            return

        soon = self.now() + timedelta(seconds=delay)

        try:
            while soon > self.now():
                time.sleep(resolution)
                delay -= resolution
        except UnsynchronizedException:
            time.sleep(delay)


clock = Clock()
