import pathlib
import re
import tomllib
from ipaddress import IPv4Address, IPv6Address, IPv6Interface

CONFIG_FILENAME = 'config.toml'
SELF_DIR = pathlib.Path(__file__).parent.resolve()

CONFIG_SCHEMA = {
    'astro': {
        'depression': {'default': None},
        'latitude': {},
        'longitude': {},
        'time_zone': {},
    },
    'clock': {
        'default_sleep_resolution': {'default': 0.25},
        'max_sync_age': {'default': 64},
        'offset_buffer_size': {'default': 10},
        'server_port': {'default': 123},
        'server_timeout': {'default': 2},
    },
    'discover': {
        'max_age': {'default': 128},
        'port': {'default': 5050},
        'timeout': {'default': 10},
    },
    'interval': {
        'repeat': {'default': {'hours': 1}},
        'start_time': {'default': None},
    },
}

CAMERA_CONFIG_SCHEMA = {
    'admin_host': {},
    'admin_password': {},
    'admin_port': {},
    'admin_protocol': {'default': 'http'},
    'admin_username': {},
    'hostname': {'packet_key': 'hostname'},
    'id': {'packet_key': 'Name'},
    'ipv4': {'packet_key': 'ip'},
    'ipv6': {'packet_key': 'IPv6Addr'},
    'mac': {'packet_key': 'mac'},
    'serial': {'packet_key': 'SerialNo'},
}


class ConfigError(Exception):
    pass


class Config:
    def __init__(self):
        self.config_file = SELF_DIR / CONFIG_FILENAME

    def get_config_dict(self):
        with open(self.config_file, 'rb') as f:
            return tomllib.load(f)

    def get_camera_config(self, cam_packet):
        camera_configs = self.get_config_dict()['camera']

        for possible_cfg in camera_configs:
            found = True
            for c_key, schema in CAMERA_CONFIG_SCHEMA.items():
                p_key = schema.get('packet_key')

                if c_key not in possible_cfg or p_key is None:
                    continue

                config_val = possible_cfg[c_key]
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
                    break

            if found:
                return possible_cfg

        return None

    def gimme(self, lookup):
        cfg = self.get_config_dict()
        parts = lookup.split('.')

        if len(parts) == 2:
            section, key = parts

            try:
                schema = CONFIG_SCHEMA[section][key]
            except KeyError:
                raise ConfigError(f'not a valid config lookup: {lookup}')

            try:
                return cfg[section][key]
            except KeyError:
                pass

            try:
                return schema['default']
            except KeyError:
                raise ConfigError(f'config key is required: {lookup}')

        raise ConfigError(f'not a valid config lookup: {lookup}')

    @staticmethod
    def cam_gimme(cam_cfg, key, call_default=None):
        try:
            schema = CAMERA_CONFIG_SCHEMA[key]
        except KeyError:
            raise ConfigError(f'not a valid camera config lookup: {key}')

        try:
            return cam_cfg[key]
        except KeyError:
            if call_default is not None:
                return call_default

        try:
            return schema['default']
        except KeyError:
            raise ConfigError(f'camera config key is required: {key}')


config = Config()
