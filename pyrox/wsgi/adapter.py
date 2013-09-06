from pyrox.http import HttpResponse
from pyrox.filtering import reject, pass_event


def start_response(status, headers):
    resp = HttpResponse()
    resp.status_code = status

    [resp.header(h).values.append(v) for h, v in headers]

    return reject(resp)

