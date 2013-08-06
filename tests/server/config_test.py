import unittest

from pyrox.server.config import load_config


class WhenManipulatingHeaders(unittest.TestCase):

    def setUp(self):
        self.cfg = load_config('./etc/pyrox/pyrox.conf')

    def test_defaults(self):
        self.assertIsNotNone(self.cfg)
        self.assertEqual(self.cfg.core.processes, 0)

if __name__ == '__main__':
    unittest.main()
