import datetime
import pathlib
import re
import tomllib
from ipaddress import IPv4Address, IPv6Address, IPv6Interface
from zoneinfo import ZoneInfo

CONFIG_FILENAME = 'config.toml'
SELF_DIR = pathlib.Path(__file__).parent.resolve()


class ConfigError(Exception):
    pass


class Config:
    def __init__(self):
        self.config_file = SELF_DIR / CONFIG_FILENAME

    def get_config_dict(self):
        with open(self.config_file, 'rb') as f:
            return tomllib.load(f)

    def get_astro_config(self):
        config = self.get_config_dict()

        tz = config['astro']['time_zone']
        lat = config['astro']['latitude']
        lon = config['astro']['longitude']
        dep = config['astro'].get('depression')

        return (ZoneInfo(tz), lat, lon, dep)

    def get_clock_config(self):
        config = self.get_config_dict()

        return config.get('clock')

    def get_discover_config(self):
        config = self.get_config_dict()

        port = config.get('discover', {}).get('port', 5050)
        timeout = config.get('discover', {}).get('timeout', 10)
        max_age = config.get('discover', {}).get('max_age', 128)

        return (port, timeout, max_age)

    def get_interval_config(self):
        config = self.get_config_dict()

        start_time = config.get('interval', {}).get('start_time', datetime.time())
        if not isinstance(start_time, datetime.time):
            raise ConfigError('interval.start_time should be a "local time" object')

        interval = config.get('interval', {}).get('repeat', {'hours': 1})

        return (start_time, datetime.timedelta(**interval))

    def get_camera_config(self, cam_packet):
        config = self.get_config_dict()

        cfg_map = [  # dict key in config file, attr on CameraPacket instance
            ('hostname', 'hostname'),
            ('id', 'Name'),
            ('serial', 'SerialNo'),
            ('ipv4', 'ip'),
            ('ipv6', 'IPv6Addr'),
            ('mac', 'mac')]

        for config_candidate in config['camera']:
            found = True
            for c_key, p_key in cfg_map:
                if c_key not in config_candidate:
                    continue

                config_val = config_candidate.get(c_key)
                packet_val = getattr(cam_packet, p_key)

                match c_key:
                    case 'ipv4':
                        config_val = IPv4Address(config_val)
                        packet_val = IPv4Address(packet_val)
                    case 'ipv6':
                        config_val = IPv6Address(config_val)
                        packet_val = IPv6Interface(packet_val.split(';')[0]).ip
                    case 'mac':
                        config_val = re.sub(r'[^0-9a-f]', '', config_val.lower())
                        packet_val = re.sub(r'[^0-9a-f]', '', packet_val.lower())

                if config_val != packet_val:
                    found = False

            if found:
                return config_candidate

        return None


config = Config()
