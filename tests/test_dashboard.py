from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(not (ROOT / "reports/evaluation.json").exists(), reason="Run pipeline before integration test")
def test_dashboard_renders_and_replay_controls():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(app.tabs) == 5
    app.button(key="start").click().run()
    assert not app.exception
    assert app.session_state["replay_running"]
    app.button(key="pause").click().run()
    assert not app.session_state["replay_running"]
    app.button(key="reset").click().run()
    assert not app.exception
    assert not app.session_state["replay_running"]
