"""Individual Assessment page entrypoint.

The legacy-compatible assessment implementation lives in the golden module.
This entrypoint executes that script on every Streamlit page run so navigation
back to the page cannot return a cached, already-rendered Python module.
"""
from pathlib import Path
import runpy


_GOLDEN_PATH = Path(__file__).with_name("05_Individual_Assessment_Golden.py")
runpy.run_path(str(_GOLDEN_PATH), run_name="__main__")
