import unittest

import pyrox.util.cbuf as cbuf


class WhenUsingCBuffers(unittest.TestCase):

    def test_should_init(self):
        cbuffer = cbuf.CyclicBuffer()

    def test_should_put(self):
        cbuffer = cbuf.CyclicBuffer()
        input_test = b'12345'

        cbuffer.put(input_test)
        self.assertEqual(len(input_test), cbuffer.available())

#    def test_should_get(self):
#        cbuffer = cbuf.CyclicBuffer()
#        input_test = b'12345'

#        cbuffer.put(input_test)
#        actual = cbuffer.get(len(input_test))
#        self.assertEqual(input_test, actual)

if __name__ == '__main__':
    unittest.main()
