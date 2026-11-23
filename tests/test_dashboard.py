"""Smoke tests: every dashboard page renders without an exception.

Needs exported data, so CI runs these after the sample pipeline + publish step.
Skipped when Streamlit or the exports aren't available."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
SAMPLE = DASH / "data_sample"

pytestmark = pytest.mark.skipif(not (SAMPLE / "health.json").exists(),
                                reason="run the sample pipeline first to create dashboard/data_sample")

PAGES = ["two_strike_page", "umpires_page", "arsenal_page", "health_page"]


@pytest.fixture(autouse=True)
def sample_data(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DATA", str(SAMPLE))


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    script = f"import sys; sys.path.insert(0, {str(DASH)!r})\nimport views\nviews.{page}()\n"
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, "page should render a title"


def test_app_shell_shows_sample_banner():
    at = AppTest.from_file(str(DASH / "app.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("sample data" in w.value for w in at.warning)
