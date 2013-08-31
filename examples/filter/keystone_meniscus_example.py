from ConfigParser import ConfigParser
from keystoneclient.v2_0 import client

import pyrox.http.filtering as filtering

"""
This is a very rough example of what an authentication function might look like

Configuration Example
---------------------

[keystone_meniscus]
MENISCUS_SERVICE = user
MENISCUS_PASSWORD = password
MENISCUS_AUTH_URL = http://127.0.0.1:35357/v2.0
MENISCUS_TENANT = tenant

[keystone_meniscus_ftest]
username = user
password = password
tenant_name = tenant
auth_url = http://127.0.0.1:35357/v2.0
host = http://127.0.0.1
tenant_id = 1234567
"""

_MENISCUS_CONFIG_KEY = 'keystone_meniscus'
config = ConfigParser()
config.read("examples/config/pyrox.conf")

X_AUTH_TOKEN = 'x-auth-token'
MENISCUS_SERVICE = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_SERVICE')
MENISCUS_PASSWORD = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_PASSWORD')
MENISCUS_AUTH_URL = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_AUTH_URL')
MENISCUS_TENANT = config.get(_MENISCUS_CONFIG_KEY, 'MENISCUS_TENANT')


def try_authentication(tenant_id, token):
    keystone = client.Client(
        username=MENISCUS_SERVICE,
        password=MENISCUS_PASSWORD,
        tenant_name=MENISCUS_TENANT,
        auth_url=MENISCUS_AUTH_URL)
    keystone.auth_token_from_user = token

    try:
        if keystone.authenticate(token=token, tenant_id=tenant_id):
            return filtering.pass_event()
    except Exception as ex:
        # Safer default is to reject in case of error
        return filtering.reject()


class MeniscusKeystoneFilter(filtering.HttpFilter):

    def on_request(self, request_message):
        tenant_id = request_message.url.split("/")[-1]
        auth_header = request_message.get_header(X_AUTH_TOKEN)

        if auth_header:
            return try_authentication(tenant_id, auth_header.values[0])
        return filtering.reject()
