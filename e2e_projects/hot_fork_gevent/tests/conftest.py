"""Gevent monkey-patching before tests run.

This is the problematic pattern that breaks regular fork mode.
Hot-fork mode should handle this correctly.
"""

from gevent import monkey

monkey.patch_all()
