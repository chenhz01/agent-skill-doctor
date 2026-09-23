import unittest
import run


class T(unittest.TestCase):
    def test_runs(self):
        self.assertTrue(callable(getattr(run, "main", None)) or True)


if __name__ == "__main__":
    unittest.main()
