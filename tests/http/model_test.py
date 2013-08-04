import unittest

from pyrox.http import HttpHeader, HttpMessage, HttpRequest, HttpResponse


class WhenManipulatingHeaders(unittest.TestCase):

    def test_return_false_when_removing_non_existant_header(self):
        http_msg = HttpMessage()
        self.assertFalse(http_msg.remove_header('test'))

    def test_return_true_when_removing_existing_header(self):
        http_msg = HttpMessage()
        http_msg.header('test')
        self.assertTrue(http_msg.remove_header('test'))

    def test_return_empty_header_object_when_header_does_not_exist(self):
        http_msg = HttpMessage()
        header = http_msg.header('test')

        self.assertIsNotNone(header)
        self.assertIsNotNone(http_msg.get_header('test'))

    def test_return_header_when_header_exists(self):
        http_msg = HttpMessage()
        http_msg.header('test')

        header = http_msg.get_header('test')
        self.assertIsNotNone(header)

    def test_return_none_when_header_doesnt_exist(self):
        http_msg = HttpMessage()
        self.assertIsNone(http_msg.get_header('test'))


if __name__ == '__main__':
    unittest.main()
