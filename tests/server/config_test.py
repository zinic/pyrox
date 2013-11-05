import unittest

from pyrox.server.config import load_pyrox_config
from pyrox.server.config import _split_and_strip as split_and_strip
from pyrox.server.config import _host_tuple as host_tuple
from pyrox.util.config import ConfigurationError


class WhenManipulatingHeaders(unittest.TestCase):

    def setUp(self):
        self.cfg = load_pyrox_config('./examples/config/pyrox.conf')

    def test_defaults(self):
        self.assertIsNotNone(self.cfg)
        self.assertEqual(self.cfg.core.processes, 0)

    def test_split_and_strip_multiple_paths(self):
        values_str = '/usr/share/project/python,/usr/share/other/python'
        split_on = ','
        path_list = [path for path in split_and_strip(values_str, split_on)]
        self.assertEqual(path_list[0], '/usr/share/project/python')
        self.assertEqual(path_list[1], '/usr/share/other/python')

    def test_split_and_strip_single_path(self):
        values_str = '/usr/share/project/python'
        split_on = ','
        path_list = split_and_strip(values_str, split_on)
        self.assertEqual(path_list[0], '/usr/share/project/python')

    def test_host_tuple(self):
        upstream_hosts_single = 'localhost:8080'
        result = [host_tuple(host) for host in
                  split_and_strip(upstream_hosts_single, ',')]
        self.assertEqual(result, [('localhost', 8080)])

        upstream_hosts_multiple = '127.0.0.1:1,127.0.0.2:2,127.0.0.3:3'
        result = [host_tuple(host) for host in
                  split_and_strip(upstream_hosts_multiple, ',')]
        self.assertEqual(result, [('127.0.0.1', 1),
                                  ('127.0.0.2', 2),
                                  ('127.0.0.3', 3)])

        upstream_hosts_multiple_with_spaces = \
            '127.0.0.1:1, 127.0.0.2:2, 127.0.0.3:3'
        result = [host_tuple(host) for host in
                  split_and_strip(upstream_hosts_multiple_with_spaces, ',')]
        self.assertEqual(result, [('127.0.0.1', 1),
                                  ('127.0.0.2', 2),
                                  ('127.0.0.3', 3)])

    def test_host_tuple_no_port(self):
        upstream_host = 'localhost'
        result = [host_tuple(host) for host in
                  split_and_strip(upstream_host, ',')]
        self.assertEqual(result, [('localhost', 80)])

    def test_host_tuple_should_raise_configuration_error(self):
        self.assertRaises(ConfigurationError, host_tuple, 'a.b.c:1:2:3')

if __name__ == '__main__':
    unittest.main()
