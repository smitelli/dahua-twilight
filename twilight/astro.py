'''
Adapted from the Astral project
Copyright 2009-2016, Simon Kennedy, sffjunkie+code@gmail.com
Published under the Apache License 2.0
https://astral.readthedocs.io/en/latest/
https://github.com/sffjunkie/astral/blob/535a84b7cf83fbb7b40be32f621c5d9ab4b7472b/LICENSE
https://github.com/sffjunkie/astral/blob/535a84b7cf83fbb7b40be32f621c5d9ab4b7472b/src/astral.py

Stripped down and streamlined to support only the following usage:

    from datetime import datetime
    from astro import TinyAstro
    a = TinyAstro()

    a.dawn_utc(datetime.now(), 35.7796, -78.6382)
    # datetime.datetime(2024, 6, 9, 9, 57, 56, 458536, tzinfo=....utc)

    a.dusk_utc(datetime.now(), 35.7796, -78.6382)
    # datetime.datetime(2024, 6, 10, 0, 30, 11, 476830, tzinfo=....utc)
'''

from datetime import datetime, timedelta, timezone
from math import degrees, radians, sin, cos, tan, asin, acos


class TinyAstro:
    '''
    Calculates any date's sunrise and sunset times for a location on Earth.

    This adaptation tries extremely hard to avoid raising exceptions under any
    circumstances. In particular, when presented with arguments that refer to a
    location/date that has constant day or constant night, the (dusk - dawn)
    time difference is 24 hours or zero seconds, respectively.

    NOTE: When passing dates to this class, it is a wise idea to ignore all
    prevailing date-handling wisdom and explicitly use naive datetimes in the
    *local* time zone. The reason for this is to avoid any possibility of the
    date being converted into UTC and (possibly) spilling over to an adjacent
    day. As an example:

        You are in the UTC-5 timezone and the sun sets at around 9pm. It is
        8:30pm on July 1 and you want to know precisely when the sunset will
        occur. From a timezone-aware datetime's perspective, the current UTC
        time is 1:30am on July 2, which would produce *tomorrow's* sunset time
        instead of what you actually wanted.

    The returned datetime is always timezone aware in UTC -- this will *not*
    have the same date spillover problem as the input date, but you will need to
    remember to localize the times when you use them.

    The depression angle is expressed in positive degrees below the horizon. The
    default depression represents the instant the top edge of the sun's disk
    enters (dawn) or leaves (dusk) view over an ideal horizon (= 0.833 degrees).
    For civil twilight use 6; nautical is 12; astronomical is 18.
    '''

    DEFAULT_DEPRESSION = 5 / 6  # degrees below horizon
    DIR_RISING = 1
    DIR_SETTING = -1

    def dawn_utc(self, date, latitude, longitude, depression=None):
        '''
        Calculate the dawn/sunrise time for a date at the given location.

        Params:
            date: Instance of datetime.datetime; the calendar day to calculate.
            latitude: -90 to 90; negatives are on the southern hemisphere.
            longitude: -180 to 180; negatives are on the western hemisphere.
            depression: Positive degrees below the horizon. This is the position
                of the center of the sun at the calculated time. Defaults to
                the position where the top of the sun crosses the horizon.

        Returns:
            datetime.datetime of the provided `date` with the time adjusted to
            the dawn/sunrise time at this location.
        '''
        if depression is None:
            depression = self.DEFAULT_DEPRESSION

        return self._calc_time(90 + depression, self.DIR_RISING, date, latitude, longitude)

    def dusk_utc(self, date, latitude, longitude, depression=None):
        '''
        Calculate the dusk/sunset time for a date at the given location.

        Params:
            date: Instance of datetime.datetime; the calendar day to calculate.
            latitude: -90 to 90; negatives are on the southern hemisphere.
            longitude: -180 to 180; negatives are on the western hemisphere.
            depression: Positive degrees below the horizon. This is the position
                of the center of the sun at the calculated time. Defaults to
                the position where the top of the sun crosses the horizon.

        Returns:
            datetime.datetime of the provided `date` with the time adjusted to
            the dusk/sunset time at this location.
        '''
        if depression is None:
            depression = self.DEFAULT_DEPRESSION

        return self._calc_time(90 + depression, self.DIR_SETTING, date, latitude, longitude)

    @staticmethod
    def _julianday(date):
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return 2440587.5 + (date.timestamp() / 86400)

    @staticmethod
    def _jday_to_jcentury(julianday):
        return (julianday - 2451545) / 36525

    @staticmethod
    def _mean_obliquity_of_ecliptic(juliancentury):
        seconds = 21.448 - juliancentury * (46.815 + juliancentury * (0.00059 - juliancentury * 0.001813))
        return 23 + (26 + (seconds / 60)) / 60

    def _obliquity_correction(self, juliancentury):
        e0 = self._mean_obliquity_of_ecliptic(juliancentury)
        omega = 125.04 - 1934.136 * juliancentury
        return e0 + 0.00256 * cos(radians(omega))

    @staticmethod
    def _geom_mean_long_sun(juliancentury):
        l0 = 280.46646 + juliancentury * (36000.76983 + 0.0003032 * juliancentury)
        return l0 % 360

    @staticmethod
    def _eccentrilocation_earth_orbit(juliancentury):
        return 0.016708634 - juliancentury * (0.000042037 + 0.0000001267 * juliancentury)

    @staticmethod
    def _geom_mean_anomaly_sun(juliancentury):
        return 357.52911 + juliancentury * (35999.05029 - 0.0001537 * juliancentury)

    def _eq_of_time(self, juliancentury):
        m = self._geom_mean_anomaly_sun(juliancentury)
        l0 = self._geom_mean_long_sun(juliancentury)
        e = self._eccentrilocation_earth_orbit(juliancentury)
        epsilon = self._obliquity_correction(juliancentury)

        m_rad = radians(m)
        sinm = sin(m_rad)
        sin2m = sin(2 * m_rad)
        l0_rad = radians(l0)
        sin2l0 = sin(2 * l0_rad)
        cos2l0 = cos(2 * l0_rad)
        sin4l0 = sin(4 * l0_rad)
        y = tan(radians(epsilon) / 2) ** 2

        etime = y * sin2l0 - 2 * e * sinm + 4 * e * y * sinm * cos2l0 - 0.5 * y * y * sin4l0 - 1.25 * e * e * sin2m

        return degrees(etime) * 4

    def _sun_eq_of_center(self, juliancentury):
        m = self._geom_mean_anomaly_sun(juliancentury)

        m_rad = radians(m)
        sinm = sin(m_rad)
        sin2m = sin(2 * m_rad)
        sin3m = sin(3 * m_rad)

        c = sinm * (1.914602 - juliancentury * (0.004817 + 0.000014 * juliancentury)) + \
            sin2m * (0.019993 - 0.000101 * juliancentury) + \
            sin3m * 0.000289

        return c

    def _sun_true_long(self, juliancentury):
        l0 = self._geom_mean_long_sun(juliancentury)
        c = self._sun_eq_of_center(juliancentury)
        return l0 + c

    def _sun_apparent_long(self, juliancentury):
        o = self._sun_true_long(juliancentury)
        omega = 125.04 - 1934.136 * juliancentury
        return o - 0.00569 - 0.00478 * sin(radians(omega))

    def _sun_declination(self, juliancentury):
        e = self._obliquity_correction(juliancentury)
        lambd = self._sun_apparent_long(juliancentury)
        sint = sin(radians(e)) * sin(radians(lambd))
        return degrees(asin(sint))

    @staticmethod
    def _hour_angle(latitude, declination, depression):
        latitude_rad = radians(latitude)
        declination_rad = radians(declination)
        depression_rad = radians(depression)

        n = cos(depression_rad)
        d = cos(latitude_rad) * cos(declination_rad)
        t = tan(latitude_rad) * tan(declination_rad)
        h = (n / d) - t
        h = max(-1, min(1, h))

        return degrees(acos(h))

    def _calc_time(self, depression, direction, date, latitude, longitude):
        julianday = self._julianday(date)

        latitude = max(-90, min(90, latitude))

        t = self._jday_to_jcentury(julianday)

        eqtime = self._eq_of_time(t)
        solar_dec = self._sun_declination(t)

        hourangle = -self._hour_angle(latitude, solar_dec, 90 + (5 / 6))

        delta = -longitude - hourangle
        time_diff = 4 * delta
        time_utc = 720 + time_diff - eqtime

        newt = self._jday_to_jcentury(julianday + time_utc / 1440)
        eqtime = self._eq_of_time(newt)
        solar_dec = self._sun_declination(newt)

        hourangle = self._hour_angle(latitude, solar_dec, depression) * direction

        delta = -longitude - hourangle
        time_diff = 4 * delta
        time_utc = 720 + time_diff - eqtime

        while time_utc < 0:
            time_utc += 1440
            date -= timedelta(days=1)
        while time_utc >= 1440:
            time_utc -= 1440
            date += timedelta(days=1)

        hour = time_utc / 60
        minute = time_utc % 60
        second = (time_utc % 1) * 60
        usec = (second % 1) * 1_000_000

        return datetime(
            date.year, date.month, date.day, int(hour), int(minute), int(second), int(usec), tzinfo=timezone.utc)
