"""Ensures the repo root is importable as `src.<module>` regardless of
the directory pytest is invoked from.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
