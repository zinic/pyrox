from pyrox.http import HttpResponse
from pyrox.filtering import reject


"""
Still playing with this - don't use this.
"""


def start_response(status, headers):
    resp = HttpResponse()
    resp.status = status

    [resp.header(h).values.append(v) for h, v in headers]

    return reject(resp)
