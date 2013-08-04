from pyrox.http.filtering import HttpFilter, reject, pass_event


class SimpleFilter(HttpFilter):

    def on_request(self, request_message):
        user_agent_header = request_message.get_header('user-agent')
        if user_agent_header and len(user_agent_header.values) > 0:
            print(user_agent_header.values[0])
        return pass_event()
