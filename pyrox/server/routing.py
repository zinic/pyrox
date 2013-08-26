class RoutingHandler(object):

    def __init__(self, default_routes):
        self._default_routes = default_routes
        self._last_default = 0
        self._next_route = None

    def set_next(self, next_route):
        if next_route:
            if isinstance(next_route, str):
                if ':' in next_route:
                    split_route = next_route.split(':')
                    self._next_route = (split_route[0], int(split_route[1]))
                else:
                    self._next_route = (next_route, 80)
            elif isinstance(next_route, tuple) and len(next_route) == 2:
                self._next_route = next_route
            elif isinstance(next_route, list) and len(next_route) == 2:
                self._next_route = (next_route[0], next_route[1])
            else:
                raise TypeError("""A route must be either a string
following the "<host>:<port>" format or a tuple or a list that contains
the host at element 0 and the port at element 1""")

    def get_next(self):
        if self._next_route:
            next = self._next_route
            self._next_route = None
        else:
            self._last_default += 1
            idx = self._last_default % len(self._default_routes)
            next = self._default_routes[idx]
        return next
