"""Individual Assessment page entrypoint.

The golden implementation intentionally owns execution for compatibility with
its original page lifecycle. This entrypoint must therefore import it exactly
once and must not invoke ``render_page`` a second time.
"""
from importlib import import_module

import_module("pages.05_Individual_Assessment_Golden")
