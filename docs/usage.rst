Using Pyrox
===========

Anatomy of HTTP Message Processing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pyrox allows a programmer to hook into the different stages of processing
HTTP messages. There are four stages in total:

* Request Head
* Request Body
* Response Head
* Response Body

Filters that hook into these stages are organized into two pipelines. The
upstream pipeline contains logic that needs to intercept HTTP requests
being sent to an upstream origin service. The downstream pipeline contains
logic that needs to intercept HTTP responses being sent to the downstream
client.


Writing Your First Filter
~~~~~~~~~~~~~~~~~~~~~~~~~

As a programmer, Pyrox allows you to hook into the various processing stages
of a HTTP message via python decorators. There are decorators specified for
each stage.

**Message Head Decorators**

Message head decorators must be applied to class functions that answer to one
argument that represents either the request message head or the response
message head.

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        def on_request_head(self, request_head):
            print('Got request head with verb: {}'.format(request_head.method))

        @filtering.handles_response_head
        def on_request_head(self, response_head):
            print('Got response head with status: {}'.format(response_head.status))

|

**Message Body Decorators**

Message body decorators must be applied to class functions that answer to two
arguments. The first argument represents either the request message body or
the response message body chunk being processed. The second argument is a
writable object to which the processed content can be handed off to for
transmission either upstream or downstream (depending on the stage being
processed).

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_body
        def on_request_body(self, msg_part, output):
            print('Got request content chunk: {}'.format(msg_part))
            output.write(msg_part)

        @filtering.handles_response_body
        def on_response_body(self, msg_part, output):
            print('Got response content chunk: {}'.format(msg_part))
            output.write(msg_part)

|

**Stacking Decorators on Common Functionality**

Pyrox decorators may be stacked onto a class function that adheres to the
expected interface.

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        @filtering.handles_response_head
        def on_head(self, msg_head):
            print('Got msg head: {}'.format(msg_head))

        @filtering.handles_request_body
        @filtering.handles_response_body
        def on_body(self, msg_part, output):
            print('Got message content part: {}'.format(msg_part))
            output.write(msg_part)


Pipeline Processing and Logic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pyrox filters may influence how Pyrox handles further processing of the
HTTP message by returning control actions. These control actions are
available for import in the filtering module.

**Passing a Message Stage**

By default, if a filter returns None, has no return or returns a
FilterAction with the kind class member set to NEXT_FILTER, Pyrox will
continue handing off the HTTP message stage down its associated pipeline to
the next filter.

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        def on_request_head(self, request_head):
            # Do nothing but pass the stage to the next filter in the
            # filter pipeline
            return filtering.next()

        @filtering.handles_response_head
        def on_response_head(self, response_head):
            # No return also defaults to passing the message stage to the
            # next filter in the pipeline
            pass

|

**Consuming a Message Stage**

Consuming a HTTP message stage tells Pyrox to continue proxying the message
but to stop processing it through its associated pipeline.

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        def on_request_head(self, request_head):
            # Do nothing but consume the http message stage
            return filtering.consume()

|

**Rejecting a Message**

Rejecting a HTTP message stage will return to the client with the passed
response message head object. This response object will be serialized and
sent to the client immediately after the function returns.

**Note: rejecting a message may not occur during the response body message
stage.**

::

    import pyrox.http as http
    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        def on_request_head(self, request_head):
            # Reject the request if it is not a GET request
            if request_head.method != 'GET':
                # Create a response object - this should be a static
                # instanace set elsewhere for performance reasons
                response = http.HttpResponse()
                response.version = '1.1'
                response.status = '405 Method Not Allowed'

                return filtering.reject(response)

|

**Routing a Message**

Pyrox allows for a message to be routed to an upstream host target. By
default, messages are proxied to upstream hosts defined in the Pyrox
configuration. When more flexibility is required, a filter action may be
returned that informs Pyrox of the message's intended upstream destination.

**Note: routing a message is only allowed during the request message head
stage.**

::

    import pyrox.filtering as filtering

    class FilterTest(filtering.HttpFilter):

        @filtering.handles_request_head
        def on_request_head(self, request_head):
            # Do nothing but route the request
            return filtering.route('google.com:80')
