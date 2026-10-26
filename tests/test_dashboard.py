"""Render Streamlit against a real local API, without fabricated dashboard values."""

import socket
import threading
import time
from pathlib import Path

import uvicorn
from streamlit.testing.v1 import AppTest

from clinresearch.api.app import create_app


def test_dashboard_with_live_api(loaded, monkeypatch):
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
        app.selectbox[0].select("race").run()
        assert not app.exception
        assert app.selectbox[0].value == "race"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
