import pyrox.filtering as filtering


class StaticWebServer(filtering.HttpFilter):

    @filtering.handles_request_head
    def on_request_head(self, request_message):
        user_agent_header = request_message.get_header('user-agent')

        if user_agent_header and len(user_agent_header.values) > 0:
            # If there is a user-agent value then print it out and pass
            # the request upstream
            print(user_agent_header.values[0])
            return filtering.next()
        else:
            # If there is no user-agent, then reject the request
            return filtering.reject()
