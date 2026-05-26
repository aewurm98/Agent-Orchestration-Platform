"""
Pytest setup for the Arena backend test suite.

Adds `artifacts/backend/` to sys.path so tests can `import agents.ea_integration`,
`import state.db`, etc. — matching the import style already used by main.py.
"""
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
