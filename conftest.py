"""
Root-level pytest conftest.

There's an (empty, likely accidental) __init__.py at the repo root, which
can make pytest's automatic rootdir/import-path detection ambiguous about
whether NOVA/ itself is a package. The app's own code always imports as
`core.xxx`, `ui.xxx`, `config.xxx` (i.e. it expects NOVA/ itself to be on
sys.path, not NOVA's parent) -- so we make that explicit here rather than
relying on pytest to guess it correctly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
