"""
Root-level conftest.py.

Ensures the project root is on sys.path so `app.*` and `tests.*` imports
work when pytest is invoked from any directory without installing the package.
"""

import os
import sys

# Add the project root (one level above this file) to the import path
sys.path.insert(0, os.path.dirname(__file__))
