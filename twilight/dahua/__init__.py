import re
from datetime import timedelta, timezone
from enum import Enum
from .base_client import DahuaClient, DahuaClientException
from clock import clock


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

    def get_timezone(self):
        if self.cached_timezone is None:
            config = self.read_config(('NTP', 'OnvifDevice'))

            tz_num = config['table.NTP.TimeZone']
            if tz_num != config['table.OnvifDevice.TimeZone']:
                raise DahuaClientException('NTP/ONVIF timezone mismatch')

            offset_h, offset_m = self.TZ_OFFSET_DATA[int(tz_num)]

            self.cached_timezone = timezone(timedelta(hours=offset_h, minutes=offset_m))

        return self.cached_timezone
