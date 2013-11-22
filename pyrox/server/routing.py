from urlparse import urlparse

PROTOCOL_HTTP = 0
PROTOCOL_HTTPS = 1

_PROTOCOLS_BY_NAME = {
    'http': PROTOCOL_HTTP,
    'https': PROTOCOL_HTTPS
}

_PROTOCOL_DEFAULT_PORTS = {
    PROTOCOL_HTTP: 80,
    PROTOCOL_HTTPS: 443
}

_DEFAULT_PROTOCOL = PROTOCOL_HTTP
_DEFAULT_PROTOCOL_PORT = _PROTOCOL_DEFAULT_PORTS[_DEFAULT_PROTOCOL]


def parse_route_url(url):
    parsed_url = urlparse(url)

    protocol = _DEFAULT_PROTOCOL
    host = None
    port = _DEFAULT_PROTOCOL_PORT

    if parsed_url.scheme is not None:
        protocol = _PROTOCOLS_BY_NAME[parsed_url.scheme.lower()]

    if parsed_url.netloc is not None:
        if ':' in parsed_url.netloc:
            split_netloc = parsed_url.netloc.split(':')

            host = split_netloc[0]
            port = int(split_netloc[1])
        else:
            host = parsed_url.netloc
            port = _PROTOCOL_DEFAULT_PORTS.get(protocol)

    if protocol is None:
        raise InvalidRouteError('Unsupported protocol "{}" in URL.'.format(
            parsed_url.scheme))

    if host is None:
        raise InvalidRouteError('Host or address not set in URL.')

    if port is None:
        raise InvalidRouteError(
            'No default port found or set for protocol.')

    return (host, port, protocol)


class InvalidRouteError(Exception):
    pass


class NoRoutesAvailableError(Exception):
    pass


class RoutingHandler(object):

    def __init__(self, routes=None):
        self.routes = list()
        self._next_route = None

        if routes is not None:
            for route in routes:
                if route is not None and isinstance(route, str):
                    self.routes.append(parse_route_url(route))
                else:
                    raise TypeError('A route must be either a valid URL string.')

    def set_next(self, next_route):
        if next_route is not None and isinstance(next_route, str):
            self._next_route = parse_route_url(next_route)
        else:
            raise TypeError('A route must be either a valid URL string.')

    def get_next(self):
        next = None

        if self._next_route is not None:
            next = self._next_route
            self._next_route = None
        else:
            next = self._get_next()

        return next

    def _get_next(self):
        raise NoRoutesAvailableError('No routes available.')


class RoundRobinRouter(RoutingHandler):

    def __init__(self, routes):
        super(RoundRobinRouter, self).__init__(routes)
        self._last_default = 0

    def _get_next(self):
        next_route = None

        if len(self.routes) > 0:
            self._last_default += 1
            idx = self._last_default % len(self.routes)
            next_route = self.routes[idx]

        return next_route
