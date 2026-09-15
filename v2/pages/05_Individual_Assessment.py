"""Individual Assessment page entrypoint."""
from importlib import import_module

render_page = import_module("pages.05_Individual_Assessment_Golden").render_page
render_page()
