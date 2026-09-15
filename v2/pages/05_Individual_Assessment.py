"""Individual Assessment page entrypoint.

The implementation lives in the golden-parity module so this registered page
has a small, stable entrypoint while the migration remains modular.
"""
from pages.05_Individual_Assessment_Golden import render_page

render_page()
