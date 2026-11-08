"""Automatic capture stays off, and session injection keeps only durable types."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_session_summary_capture_does_not_call_the_api():
    import capture_session_summary

    with patch("urllib.request.urlopen") as urlopen:
        capture_session_summary.main()

    urlopen.assert_not_called()


def test_auto_capture_does_not_call_the_api():
    import auto_capture

    with patch("urllib.request.urlopen") as urlopen:
        auto_capture.main()

    urlopen.assert_not_called()


def test_timeline_drops_session_summaries():
    from session_timeline import format_timeline

    text = format_timeline(
        [
            {
                "id": "aaaaaaaa-1111",
                "memory": "User concluded the best path is a local 9B model",
                "metadata": {"type": "session_summary"},
            },
            {
                "id": "bbbbbbbb-2222",
                "memory": "ragflow 下载不再硬编码 Bearer 前缀",
                "metadata": {"type": "decision"},
            },
        ]
    )

    assert "ragflow" in text
    assert "9B" not in text
    assert "可沿用的决定" in text


def test_search_default_threshold_rejects_weak_matches():
    from _search import search_memories

    captured = {}

    def mock_urlopen(req, timeout=None):
        captured.update(json.loads(req.data.decode()))
        response = MagicMock()
        response.read.return_value = json.dumps({"results": []}).encode()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    with patch.dict("os.environ", {"MEM0_API_HOST": "http://gateway.local"}, clear=False):
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            search_memories("key", "user", "proj", "query")

    assert captured["threshold"] == 0.45
