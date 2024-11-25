import requests
from requests.auth import HTTPDigestAuth
from urllib.parse import urlencode, quote as urlquote
from config import config


class DahuaClientException(Exception):
    pass


class DahuaClient:
    @classmethod
    def build_client(cls, packet):
        cam_config = config.get_camera_config(packet)

        if cam_config is None:
            raise DahuaClientException('failed to find any usable config for packet')

        protocol = cam_config.get('admin_protocol', 'http')
        host = cam_config.get('admin_host', packet.host)
        port = cam_config.get('admin_port', packet.https_port if protocol == 'https' else packet.http_port)

        if (protocol, port) in (('http', 80), ('https', 443)):
            base_url = f'{protocol}://{host}'
        else:
            base_url = f'{protocol}://{host}:{port}'

        return cls(
            base_url=base_url,
            username=cam_config['admin_username'],
            password=cam_config['admin_password'])

    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password

        self.auth = HTTPDigestAuth(username=self.username, password=self.password)
        self.session = requests.Session()
        self.session.auth = self.auth

    def read_config(self, key_names):
        response = self.session.get(
            url=f'{self.base_url}/cgi-bin/configManager.cgi?action=getConfig',
            params=urlencode({'name': key_names}, doseq=True, quote_via=urlquote))
        response.raise_for_status()

        res_lines = response.text.splitlines(keepends=False)

        return dict(line.split('=', maxsplit=1) for line in res_lines)

    def write_config(self, config_dict):
        response = self.session.get(
            url=f'{self.base_url}/cgi-bin/configManager.cgi?action=setConfig',
            params=urlencode(config_dict, quote_via=urlquote))
        response.raise_for_status()

        if not response.text.startswith('OK'):
            raise DahuaClientException(response.text)
