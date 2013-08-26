import pyrox.http.filtering as filtering


class SimpleFilter(filtering.HttpFilter):
    """
    This is an example of a simple filter that simply prints out the
    user-agent value from the header
    """
    def on_request(self, request_message):
        user_agent_header = request_message.get_header('user-agent')
        if user_agent_header and len(user_agent_header.values) > 0:
            # If there is a user-agent value then print it out and pass
            # the request upstream
            print(user_agent_header.values[0])
            return filtering.pass_event()
        else:
            # If there is no user-agent, then reject the request
            return filtering.reject()
