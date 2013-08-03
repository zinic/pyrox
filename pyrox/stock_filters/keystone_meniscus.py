from ConfigParser import ConfigParser
from keystoneclient.v2_0 import client

from pyrox.http.filtering import HttpFilter, reject, pass_event

_MENISCUS_CONFIG_KEY = 'keystone_meniscus'
config = ConfigParser()
config.read("/etc/pyrox/pyrox.conf")

X_AUTH_TOKEN = 'x-auth-token'
MENISCUS_SERVICE = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_SERVICE')
MENISCUS_PASSWORD = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_PASSWORD')
MENISCUS_AUTH_URL = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_AUTH_URL')
MENISCUS_TENANT = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_TENANT')


class MeniscusKeystoneFilter(HttpFilter):

    def on_request(self, request_message):
        tenant_id = request_message.url.split("/")[-1]
        auth_header = request_message.headers[X_AUTH_TOKEN]
        token = auth_header.values[0]

        keystone = client.Client(
            username=MENISCUS_SERVICE,
            password=MENISCUS_PASSWORD,
            tenant_name=MENISCUS_TENANT,
            auth_url=MENISCUS_AUTH_URL)
        keystone.auth_token_from_user = token

        try:
            if keystone.authenticate(token=token, tenant_id=tenant_id):
                return pass_event()
        except Exception as ex:
            pass
        return reject()
