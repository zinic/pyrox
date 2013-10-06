Pyrox
=====================

Pyrox is a HTTP reverse proxy that can intercept requests ahead of an upstream
HTTP REST service. This allows reuse of common middleware functions like:
message enhancement, dynamic routing, authentication, authorization, resource
request rate limiting, service distribution, content negotiation and content
transformation. These services can then be scaled horizontally separate the
origin REST endpoint.

Built ontop of the `Tornado Async I/O library <http://www.tornadoweb.org/en/stable/>`_
, the HTTP code inside Pyrox can scale to thousands of concurrent
clients and proxy them to a similar number of upstream REST services.


Getting Started
~~~~~~~~~~~~~~~

Below are some helpful documents to help get you started in using Pynsive.

.. toctree::
    :maxdepth: 2

    building

.. toctree::
    :maxdepth: 2

    installing


Pyrox Documentation
~~~~~~~~~~~~~~~~~~~~~

.. toctree::
    :maxdepth: 2

    usage

.. toctree::
    :maxdepth: 2

    pyrox


That Legal Thing...
~~~~~~~~~~~~~~~~~~~

This software library is released to you under the
`MIT Software License <http://opensource.org/licenses/MIT>`_
. See `LICENSE <https://github.com/zinic/pynsive/blob/master/LICENSE>`_ for
more information.

