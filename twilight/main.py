import datetime
import socket
import threading
from enum import Enum
from zoneinfo import ZoneInfo

from astro import TinyAstro
from clock import clock, UnsynchronizedException
from config import config
from dahua import CAMERA_PROFILE, DahuaDayNightClient, DahuaClientException
from discover import Packet, NVRPacket, inventory
from log import log

tlock = threading.Lock()


class STATE(Enum):
    UNINITIALIZED = 0
    RUNNING = 1
    CLOCK_LOST = 2


def receive_loop():
    global state

    state = STATE.UNINITIALIZED
    last_offset = None  # DEBUG

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(config.gimme('discover.timeout'))
    sock.bind(('', config.gimme('discover.port')))

    while True:
        if clock.offset_buffer[0] != last_offset:  # DEBUG
            ofs = clock.offset_buffer[0]
            valid = sum(x is not None for x in clock.offset_buffer)
            log.print(f'new SNTP offset: {ofs}; {valid} offset(s) in buffer; server={clock.server}')
            last_offset = ofs

        try:
            payload, (host, port) = sock.recvfrom(1024)
            packet = Packet.discern(payload=payload, host=host, port=port)
        except TimeoutError:
            packet = None

        match state:
            case STATE.UNINITIALIZED:
                if packet is not None and isinstance(packet, NVRPacket):
                    clock.use_ntp_server(packet.host)
                    state = STATE.RUNNING
                    log.print('clock is initialized!')

            case STATE.RUNNING:
                if not clock.is_valid():
                    state = STATE.CLOCK_LOST
                    continue

                tlock.acquire()

                if packet is not None:
                    inventory.register(packet)
                    log.print_gossip(packet.hostname)

                inventory.do_expirations(max_age=config.gimme('discover.max_age'))

                tlock.release()

            case STATE.CLOCK_LOST:
                tlock.acquire()
                inventory.reset()
                tlock.release()

                state = STATE.UNINITIALIZED
                log.print('CLOCK LOST')


def different_enough(d1, d2):
    return abs(clock.intraday_delta(d1, d2).total_seconds()) >= 1


def thread_crash_hook(args):
    import os
    import traceback

    exc_type, exc_value, exc_traceback, thread = args

    log.print(traceback.format_exc())
    log.print(f'Exiting due to unhandled exception in {thread.name}')
    os._exit(1)


threading.excepthook = thread_crash_hook

if __name__ == '__main__':
    log.print('starting receive thread')

    receive_thread = threading.Thread(target=receive_loop, daemon=True)
    receive_thread.start()

    log.print('waiting for any NVR to provide initial clock offset...')

    next_run = None
    while True:
        try:
            now = clock.now()
        except UnsynchronizedException:
            # hot-as-hell loop here
            continue

        if next_run is None:
            start_time = config.gimme('interval.start_time') or datetime.time()

            next_run = now.replace(
                hour=start_time.hour, minute=start_time.minute,
                second=start_time.second, microsecond=start_time.microsecond)
            while next_run < now:
                next_run += datetime.timedelta(**config.gimme('interval.repeat'))

            log.print(f'next run: {next_run.astimezone().isoformat()}')

        if next_run > now:
            clock.sleep(1)
            continue

        next_run = None

        log.print('--- main loop running ---')

        tz = ZoneInfo(config.gimme('astro.time_zone'))
        latitude = config.gimme('astro.latitude')
        longitude = config.gimme('astro.longitude')
        depression = config.gimme('astro.depression')
        local_today = now.astimezone(tz).replace(tzinfo=None)
        ast = TinyAstro()
        new_start = ast.dawn_utc(local_today, latitude, longitude, depression)
        new_end = ast.dusk_utc(local_today, latitude, longitude, depression)

        tlock.acquire()

        for p in inventory.all_cameras():
            log.print(p.host, end=': ')

            try:
                dc = DahuaDayNightClient.build_client(p)
                print('proceeding')
            except DahuaClientException:
                print('not configurable')
                continue

            profile, consistent = dc.get_camera_profile()
            log.print(f'  {profile=} {consistent=}')

            if not consistent or profile != CAMERA_PROFILE.SCHEDULE:
                log.print('  setting profile...')
                dc.set_camera_profile(CAMERA_PROFILE.SCHEDULE)
                profile, consistent = dc.get_camera_profile()
                log.print(f'  => profile set to {profile=} {consistent=}')
            else:
                log.print('  => no profile configuration changes')

            old_start, old_end, consistent = dc.get_schedule()
            log.print(f'  sunrise={old_start.isoformat()} sunset={old_end.isoformat()} {consistent=}')

            if (
                not consistent or
                different_enough(old_start, new_start) or
                different_enough(old_end, new_end)
            ):
                log.print('  setting schedule')
                dc.set_schedule(new_start, new_end)
                start, end, consistent = dc.get_schedule()
                log.print(f'  => schedule set to sunrise={start.isoformat()} sunset={end.isoformat()} {consistent=}')
            else:
                log.print('  => no schedule configuration changes')

        log.print('--- main loop sleeping ---')
        tlock.release()
