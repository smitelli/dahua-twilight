import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from .base_client import DahuaClient, DahuaClientException
from clock import clock


def nth_weekday(year, month, weekday, n):
    '''
    year: use current year unless you have a reason not to
    month: 1=jan, 12=dec
    weekday: 0=sunday, 6=saturday
    n: 1=first, 2=second, -1=last, -2=second-last
    '''
    if n < 0:
        month += 1
        if month > 12:
            month = 1
            year += 1

    dt = datetime(year, month, 1)

    while (dt.isoweekday() % 7) != weekday:
        dt += timedelta(days=1)

    while n > 1:
        dt += timedelta(days=7)
        n -= 1

    while n < 0:
        dt -= timedelta(days=7)
        n += 1

    return dt


class CAMERA_PROFILE(Enum):
    UNKNOWN = 0
    GENERAL = 1
    FULL_TIME_DAY = 2
    FULL_TIME_NIGHT = 3
    SCHEDULE = 4
    DAY_NIGHT = 5


class DahuaDayNightClient(DahuaClient):
    TIME_FMT = '%H:%M:%S'
    TZ_OFFSET_DATA = [  # (hour, minute) offset; both positive or both negative
        (0, 0), (1, 0), (2, 0), (3, 0), (3, 30), (4, 0), (4, 30), (5, 0),
        (5, 30), (5, 45), (6, 0), (6, 30), (7, 0), (8, 0), (9, 0), (9, 30),
        (10, 0), (11, 0), (12, 0), (13, 0), (-1, 0), (-2, 0), (-3, 0),
        (-3, -30), (-4, 0), (-5, 0), (-6, 0), (-7, 0), (-8, 0), (-9, 0),
        (-10, 0), (-11, 0), (-12, 0)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.clear_cache()

    def clear_cache(self):
        self.cached_dst = None
        self.cached_timezone = None

    def get_camera_profile(self):
        config = self.read_config(('VideoInMode', 'VideoInOptions[0].NightOptions'))

        profile = None
        consistent = True
        match (config['table.VideoInMode[0].Mode'], config['table.VideoInMode[0].Config[0]']):
            case ('0', '0'):
                profile = CAMERA_PROFILE.FULL_TIME_DAY
                expect_config_1 = None
                expect_time_section_0_1 = '0 00:00:00-23:59:59'
                expect_switch_mode = '0'
            case ('0', '1'):
                profile = CAMERA_PROFILE.FULL_TIME_NIGHT
                expect_config_1 = None
                expect_time_section_0_1 = '0 00:00:00-23:59:59'
                expect_switch_mode = '3'
            case ('0', '2'):
                profile = CAMERA_PROFILE.GENERAL
                expect_config_1 = None
                expect_time_section_0_1 = '0 00:00:00-23:59:59'
                expect_switch_mode = '4'
            case ('1', '0'):
                profile = CAMERA_PROFILE.SCHEDULE
                expect_config_1 = '1'
                expect_time_section_0_1 = '0 00:00:00-00:00:00'
                expect_switch_mode = '2'
            case ('2', '0'):
                profile = CAMERA_PROFILE.DAY_NIGHT
                expect_config_1 = '1'
                expect_time_section_0_1 = '0 00:00:00-23:59:59'
                expect_switch_mode = '1'
            case _:
                return (CAMERA_PROFILE.UNKNOWN, False)

        if (
            config.get('table.VideoInMode[0].Config[1]') != expect_config_1 or
            config['table.VideoInMode[0].TimeSection[0][1]'] != expect_time_section_0_1 or
            config['table.VideoInOptions[0].NightOptions.SwitchMode'] != expect_switch_mode
        ):
            consistent = False

        return (profile, consistent)

    def set_camera_profile(self, profile):
        match profile:
            # The write_config() calls need to be split up as they are below to
            # avoid an unhelpful "Error" response from the camera.
            case CAMERA_PROFILE.GENERAL:
                self.write_config({'VideoInOptions[0].NightOptions.SwitchMode': '4'})
                self.write_config({
                    'VideoInMode[0].Mode': '0',
                    'VideoInMode[0].Config[0]': '2',
                    'VideoInMode[0].TimeSection[0][1]': '0 00:00:00-23:59:59'})
            case CAMERA_PROFILE.FULL_TIME_DAY:
                self.write_config({'VideoInOptions[0].NightOptions.SwitchMode': '0'})
                self.write_config({
                    'VideoInMode[0].Mode': '0',
                    'VideoInMode[0].Config[0]': '0',
                    'VideoInMode[0].TimeSection[0][1]': '0 00:00:00-23:59:59'})
            case CAMERA_PROFILE.FULL_TIME_NIGHT:
                self.write_config({'VideoInOptions[0].NightOptions.SwitchMode': '3'})
                self.write_config({
                    'VideoInMode[0].Mode': '0',
                    'VideoInMode[0].Config[0]': '1',
                    'VideoInMode[0].TimeSection[0][1]': '0 00:00:00-23:59:59'})
            case CAMERA_PROFILE.SCHEDULE:
                self.write_config({'VideoInOptions[0].NightOptions.SwitchMode': '2'})
                self.write_config({
                    'VideoInMode[0].Mode': '1',
                    'VideoInMode[0].Config[0]': '0',
                    'VideoInMode[0].Config[1]': '1',
                    'VideoInMode[0].TimeSection[0][1]': '0 00:00:00-00:00:00'})
            case CAMERA_PROFILE.DAY_NIGHT:
                raise DahuaClientException('refusing day/night; you are on your own')
            case _:
                raise DahuaClientException(f'unknown profile {profile}')

    def get_schedule(self):
        config = self.read_config(('VideoInMode', 'VideoInOptions[0].NightOptions'))
        tz = self.get_timezone()
        camera_now = clock.now().astimezone(tz)
        consistent = True

        sunrise = camera_now.replace(
            hour=int(config['table.VideoInOptions[0].NightOptions.SunriseHour']),
            minute=int(config['table.VideoInOptions[0].NightOptions.SunriseMinute']),
            second=int(config['table.VideoInOptions[0].NightOptions.SunriseSecond']),
            microsecond=0)
        sunset = camera_now.replace(
            hour=int(config['table.VideoInOptions[0].NightOptions.SunsetHour']),
            minute=int(config['table.VideoInOptions[0].NightOptions.SunsetMinute']),
            second=int(config['table.VideoInOptions[0].NightOptions.SunsetSecond']),
            microsecond=0)

        match = re.match(r'(\d+)\s+([^-]+)-([^-]+)', config['table.VideoInMode[0].TimeSection[0][0]'])
        if not match:
            consistent = False
        elif (
            match[1] != '1' or
            match[2] != sunrise.strftime(self.TIME_FMT) or
            match[3] != sunset.strftime(self.TIME_FMT)
        ):
            consistent = False

        return (sunrise, sunset, consistent)

    def set_schedule(self, sunrise, sunset):
        if sunrise.tzinfo is None or sunrise.tzinfo.utcoffset(sunrise) is None:
            raise DahuaClientException('sunrise datetime must be timezone aware')

        if sunset.tzinfo is None or sunset.tzinfo.utcoffset(sunset) is None:
            raise DahuaClientException('sunset datetime must be timezone aware')

        tz = self.get_timezone()
        rise = sunrise.astimezone(tz)
        set_ = sunset.astimezone(tz)
        rise_hms = rise.strftime(self.TIME_FMT)
        set_hms = set_.strftime(self.TIME_FMT)

        self.write_config({
            'VideoInMode[0].TimeSection[0][0]': f'1 {rise_hms}-{set_hms}',
            'VideoInOptions[0].NightOptions.SunriseHour': rise.hour,
            'VideoInOptions[0].NightOptions.SunriseMinute': rise.minute,
            'VideoInOptions[0].NightOptions.SunriseSecond': rise.second,
            'VideoInOptions[0].NightOptions.SunsetHour': set_.hour,
            'VideoInOptions[0].NightOptions.SunsetMinute': set_.minute,
            'VideoInOptions[0].NightOptions.SunsetSecond': set_.second})

    def get_dst_in_effect(self, camera_tz):
        if self.cached_dst is None:
            config = self.read_config('Locales')

            if config['table.Locales.DSTEnable'] != 'true':
                self.cached_dst = False
                return self.cached_dst

            now = clock.now()

            beg_mo = int(config['table.Locales.DSTStart.Month'])
            beg_wk = int(config['table.Locales.DSTStart.Week'])
            beg_dy = int(config['table.Locales.DSTStart.Day'])
            beg_h = int(config['table.Locales.DSTStart.Hour'])
            beg_m = int(config['table.Locales.DSTStart.Minute'])

            end_mo = int(config['table.Locales.DSTEnd.Month'])
            end_wk = int(config['table.Locales.DSTEnd.Week'])
            end_dy = int(config['table.Locales.DSTEnd.Day'])
            end_h = int(config['table.Locales.DSTEnd.Hour'])
            end_m = int(config['table.Locales.DSTEnd.Minute'])

            if config['table.Locales.WeekEnable'] != 'true':
                # Specific date mode
                beg = datetime(now.year, beg_mo, beg_dy)
                end = datetime(now.year, end_mo, end_dy)
            else:
                # Nth week mode
                beg = nth_weekday(now.year, beg_mo, beg_dy, beg_wk)
                end = nth_weekday(now.year, end_mo, end_dy, end_wk)

            # Tricky here: If the camera configured in Eastern (-5:00) this is
            # always the offset encoded in `tz`, even when DST is in effect.
            # DST ends at 2am-4:00, but we have to compute it as though it were
            # 1am-5:00.
            beg = beg.replace(hour=beg_h, minute=beg_m, tzinfo=camera_tz)
            end = end.replace(hour=end_h - 1, minute=end_m, tzinfo=camera_tz)

            self.cached_dst = (beg <= now < end)

        return self.cached_dst

    def get_timezone(self):
        if self.cached_timezone is None:
            config = self.read_config(('NTP', 'OnvifDevice'))

            tz_num = config['table.NTP.TimeZone']
            if tz_num != config['table.OnvifDevice.TimeZone']:
                raise DahuaClientException('NTP/ONVIF timezone mismatch')

            offset_h, offset_m = self.TZ_OFFSET_DATA[int(tz_num)]
            tz = timezone(timedelta(hours=offset_h, minutes=offset_m))

            if self.get_dst_in_effect(camera_tz=tz):
                tz = timezone(timedelta(hours=offset_h + 1, minutes=offset_m))

            self.cached_timezone = tz

        return self.cached_timezone
