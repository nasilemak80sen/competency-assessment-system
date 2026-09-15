"""V2 dashboard entry point.

The dashboard is rendered from the original app.py branch without changing
its UI, session initialization, or business rules.
"""

from core.legacy_runtime import render_legacy_page

render_legacy_page("🏠 Dashboard Home")
