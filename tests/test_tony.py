from unittest import TestCase

from tony.functions import process


class MyTestCase(TestCase):
    def setUp(self):
        pass

    def test_process(self):
        result = process(filepath="test.txt", output_directory="output/")
        self.assertTrue(result)
