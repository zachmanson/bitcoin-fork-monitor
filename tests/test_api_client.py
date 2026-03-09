"""
Unit tests for app/api_client.py.

All tests mock httpx so no real network calls are made.
We patch "app.api_client.httpx.Client" to intercept the context manager
that fetch_blocks_page opens, controlling both status codes and errors.
"""
import pytest
import httpx
from unittest.mock import patch, MagicMock, call
from app.api_client import fetch_blocks_page, BASE_URL, RETRY_DELAYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(status_code: int, body: list | None = None) -> MagicMock:
    """Build a mock httpx response with .status_code and .json()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or []
    # raise_for_status() does nothing on 2xx; we only call it on success path
    resp.raise_for_status.return_value = None
    return resp


SAMPLE_BLOCKS = [
    {
        "id": "00000000000000000001d964abc",
        "height": 820819,
        "timestamp": 1702366992,
        "extras": {"orphans": []},
    }
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchBlocksPageSuccess:

    def test_success_returns_blocks(self):
        """Happy path: first attempt returns 200 with block list."""
        mock_resp = make_response(200, SAMPLE_BLOCKS)

        with patch("app.api_client.httpx.Client") as mock_client_cls:
            # httpx.Client() is used as a context manager (__enter__ returns the client)
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_resp

            result = fetch_blocks_page(820819)

        assert result == SAMPLE_BLOCKS

    def test_correct_url_constructed(self):
        """URL must be BASE_URL + /api/v1/blocks/<height>."""
        mock_resp = make_response(200, SAMPLE_BLOCKS)

        with patch("app.api_client.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_resp

            fetch_blocks_page(820819)

        called_url = mock_client.get.call_args[0][0]
        assert called_url == f"{BASE_URL}/api/v1/blocks/820819"


class TestRetryBehavior:

    def test_retry_on_429(self):
        """429 should trigger retries; eventual 200 returns blocks."""
        responses = [
            make_response(429),
            make_response(429),
            make_response(429),
            make_response(429),
            make_response(200, SAMPLE_BLOCKS),
        ]

        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep"):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = responses

            result = fetch_blocks_page(820819)

        assert result == SAMPLE_BLOCKS
        assert mock_client.get.call_count == 5

    def test_retry_on_5xx(self):
        """503 (and other 5xx codes) should trigger retries."""
        responses = [
            make_response(503),
            make_response(503),
            make_response(503),
            make_response(503),
            make_response(200, SAMPLE_BLOCKS),
        ]

        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep"):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = responses

            result = fetch_blocks_page(820819)

        assert result == SAMPLE_BLOCKS
        assert mock_client.get.call_count == 5

    def test_all_retries_exhausted(self):
        """After 5 consecutive 429s, RuntimeError is raised."""
        responses = [make_response(429)] * 5

        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep"):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = responses

            with pytest.raises(RuntimeError) as exc_info:
                fetch_blocks_page(820819)

        assert "820819" in str(exc_info.value)
        assert mock_client.get.call_count == 5


class TestNetworkErrors:

    def test_network_error_retries(self):
        """A single RequestError is retried; subsequent 200 returns blocks."""
        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep"):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = [
                httpx.RequestError("timeout"),
                make_response(200, SAMPLE_BLOCKS),
            ]

            result = fetch_blocks_page(820819)

        assert result == SAMPLE_BLOCKS
        assert mock_client.get.call_count == 2

    def test_network_error_all_retries(self):
        """Five consecutive RequestErrors raise RuntimeError."""
        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep"):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = httpx.RequestError("timeout")

            with pytest.raises(RuntimeError) as exc_info:
                fetch_blocks_page(820819)

        assert "820819" in str(exc_info.value)


class TestThrottleBehavior:

    def test_500ms_throttle_not_called_on_success(self):
        """
        On a successful first attempt, time.sleep should NOT be called inside
        fetch_blocks_page. The 500ms inter-page throttle lives in the backfill
        worker, not here.
        """
        mock_resp = make_response(200, SAMPLE_BLOCKS)

        with patch("app.api_client.httpx.Client") as mock_client_cls, \
             patch("app.api_client.time.sleep") as mock_sleep:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value = mock_resp

            fetch_blocks_page(820819)

        mock_sleep.assert_not_called()
