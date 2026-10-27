"""Render Streamlit against a real local API, without fabricated dashboard values."""

import json
import socket
import threading
import time
from datetime import date
from pathlib import Path

import pytest
import uvicorn
from streamlit.testing.v1 import AppTest
from test_research import sample_rows

from clinresearch.api.app import create_app
from clinresearch.research.evaluate import evaluate
from clinresearch.research.run import run_analysis


@pytest.mark.parametrize("research_state", ["not_run", "insufficient_data", "evaluated", "invalid"])
def test_dashboard_with_live_api(loaded, monkeypatch, tmp_path, research_state):
    report_path = tmp_path / "research" / "report.json"
    monkeypatch.setenv("RESEARCH_REPORT_PATH", str(report_path))
    if research_state != "not_run":
        report = run_analysis(loaded, date(2025, 1, 1), date(2024, 1, 1), report_path.parent)
        if research_state == "evaluated":
            report["evaluation"] = evaluate(sample_rows(), date(2020, 7, 1))
            report["cohort_audit"] = {"eligible_patients": 40, "positive_outcomes": 20}
            report["notes"]["count"] = 40
            report.pop("cohort_flow", None)
            report_path.write_text(json.dumps(report))
        if research_state == "invalid":
            report_path.write_text('{"schema_version": 1, "notes": []}')
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(loaded), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        monkeypatch.setenv("API_BASE_URL", f"http://127.0.0.1:{port}")
        app = AppTest.from_file(str(Path("src/clinresearch/dashboard/app.py").resolve())).run(
            timeout=20
        )
        assert not app.exception
        assert not app.error
        assert [metric.value for metric in app.metric][:4] == ["3", "3", "3", "3"]
        assert len(app.get("plotly_chart")) == 3
        assert app.dataframe[0].value["occurrences"].tolist() == [2, 1]
        if research_state == "not_run":
            assert any("No research run yet" in info.value for info in app.info)
        elif research_state == "insufficient_data":
            assert any("Model not trained" in info.value for info in app.info)
        elif research_state == "invalid":
            assert any("could not be loaded" in warning.value for warning in app.warning)
        else:
            assert any("Synthetic holdout scores" in warning.value for warning in app.warning)
        app.selectbox[0].select("race").run()
        assert not app.exception
        assert app.selectbox[0].value == "race"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
