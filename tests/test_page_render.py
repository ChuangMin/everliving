"""Run the page's JavaScript for real.

Everything else in this suite stops at the server boundary: it can prove `/api/say`
returns the right JSON and still miss a typo that leaves the browser showing an empty
page. "The tests pass but the thing doesn't run" has already cost this project a
playtest, so the drawing code gets executed too.

Skips when node isn't installed rather than failing — the Python side must stay
runnable on a machine that has no JavaScript toolchain at all.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

CHECK = Path(__file__).parent / "page_check.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_javascript_runs():
    result = subprocess.run(
        ["node", str(CHECK)], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    assert result.returncode == 0, (
        f"page checks failed\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
