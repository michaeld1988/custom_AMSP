"""Run every test module. Usage: python3 tests/run_all.py"""

import sys
import unittest
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
sys.path.insert(0, str(here.parent))

if __name__ == '__main__':
    suite = unittest.TestLoader().discover(str(here), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
