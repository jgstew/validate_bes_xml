"""
Pytest configuration shared by the test files.

Pytest loads this before any test file, so the tests import the local src module,
not a pip-installed copy.
"""

import os.path
import sys

SRC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)

# put local src first so we make sure to get the local src module, not pip package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
