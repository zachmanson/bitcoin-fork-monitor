"""
HTTP client for mempool.space API.

This module is the sole outbound HTTP interface for the application.
All block data fetching routes through fetch_blocks_page(). Centralizing
network I/O here means the retry/backoff logic is tested once and trusted
everywhere else in the codebase.
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Base URL for the mempool.space public API
BASE_URL = "https://mempool.space"

# Delay in seconds between each retry attempt (exponential backoff).
# 5 entries = 5 total attempts. If all 5 fail, RuntimeError is raised.
# Professional convention: storing retry delays as a list makes the backoff
# schedule explicit and easy to test — no magic numbers buried in the loop.
RETRY_DELAYS = [1, 2, 4, 8, 16]

# Applied by the backfill worker between pages, not inside this function.
# Defined here so callers can reference the project-wide throttle value.
REQUEST_THROTTLE_SECONDS = 0.5

# HTTP status codes that warrant a retry rather than an immediate failure
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def fetch_tip_height() -> int:
    """
    Fetch the current chain tip height from mempool.space.

    Endpoint: GET /api/blocks/tip/height
    Returns a plain integer — the height of the most recent block.

    Uses the same retry/backoff logic as fetch_blocks_page.

    Returns:
        The current tip height as an integer.

    Raises:
        RuntimeError: If all retry attempts are exhausted.
    """
    url = f"{BASE_URL}/api/blocks/tip/height"
    with httpx.Client(timeout=30.0) as client:
        for attempt, delay in enumerate(RETRY_DELAYS):
            is_last_attempt = attempt == len(RETRY_DELAYS) - 1
            try:
                resp = client.get(url)
                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Retryable HTTP %d fetching tip height (attempt %d/%d). Sleeping %ds.",
                        resp.status_code, attempt + 1, len(RETRY_DELAYS), delay,
                    )
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return int(resp.text.strip())
            except httpx.RequestError as exc:
                logger.warning(
                    "Network error fetching tip height (attempt %d/%d): %s",
                    attempt + 1, len(RETRY_DELAYS), exc,
                )
                if not is_last_attempt:
                    time.sleep(delay)
                continue
    raise RuntimeError("All retries exhausted fetching tip height")


def fetch_blocks_page(start_height: int) -> list[dict]:
    """
    Fetch one page of blocks from mempool.space starting at start_height.

    Endpoint: GET /api/v1/blocks/<start_height>
    Returns the 10 blocks at or below start_height (mempool.space paginates
    backwards — each page ends 10 blocks before the previous one).

    Retry behavior:
        - 429 or 5xx responses: log warning, sleep(delay), retry
        - httpx.RequestError (network failure): log warning, sleep(delay), retry
        - After all 5 attempts fail: raise RuntimeError

    Note: time.sleep is only called between retry attempts. A successful
    first-attempt call sleeps zero times inside this function. The 500ms
    inter-page throttle (REQUEST_THROTTLE_SECONDS) is applied by the
    backfill worker, not here.

    Args:
        start_height: The block height to begin the page at.

    Returns:
        A list of block dicts as returned by the mempool.space API.

    Raises:
        RuntimeError: If all retry attempts are exhausted without success.
    """
    url = f"{BASE_URL}/api/v1/blocks/{start_height}"

    # httpx.Client is used as a context manager so the underlying TCP
    # connection is properly closed even if an exception occurs.
    with httpx.Client(timeout=30.0) as client:
        for attempt, delay in enumerate(RETRY_DELAYS):
            is_last_attempt = attempt == len(RETRY_DELAYS) - 1

            try:
                resp = client.get(url)

                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Retryable HTTP %d for height %d (attempt %d/%d). "
                        "Sleeping %ds.",
                        resp.status_code,
                        start_height,
                        attempt + 1,
                        len(RETRY_DELAYS),
                        delay,
                    )
                    time.sleep(delay)
                    continue

                # Any non-retryable, non-error response is treated as success.
                # raise_for_status() will raise on 4xx/5xx we didn't catch above.
                resp.raise_for_status()
                return resp.json()

            except httpx.RequestError as exc:
                logger.warning(
                    "Network error for height %d (attempt %d/%d): %s",
                    start_height,
                    attempt + 1,
                    len(RETRY_DELAYS),
                    exc,
                )
                if not is_last_attempt:
                    time.sleep(delay)
                continue

    raise RuntimeError(f"All retries exhausted for height {start_height}")


def fetch_block_status(block_hash: str) -> dict:
    """
    Fetch the chain-status of a specific block from mempool.space.

    Endpoint: GET /api/block/<block_hash>/status
    Returns a JSON dict describing where this block sits in the chain.
    The key field callers care about is ``in_best_chain`` (bool): True if the
    block is part of the current best chain, False if it was orphaned/reorged.
    The dict may also contain ``next_best`` (str | None) — the hash of the next
    block in the best chain if this block was orphaned.

    This function is called by the live monitor to confirm which of two
    competing blocks at the same height survived. It uses the same retry/backoff
    logic as the other fetch functions so transient network failures are handled
    uniformly across the codebase.

    Retry behavior:
        - 429 or 5xx responses: log warning, sleep(delay), retry
        - httpx.RequestError (network failure): log warning, sleep(delay), retry
        - After all 5 attempts fail: raise RuntimeError

    Note: time.sleep is only called between retry attempts. A successful
    first-attempt call sleeps zero times inside this function. Inter-call
    throttling (REQUEST_THROTTLE_SECONDS) is applied by the caller if needed.

    Args:
        block_hash: The hex-encoded block hash to look up.

    Returns:
        A dict with at minimum ``in_best_chain`` (bool). Example:
        ``{"in_best_chain": false, "next_best": "000000...abc"}``

    Raises:
        RuntimeError: If all retry attempts are exhausted without success.
    """
    url = f"{BASE_URL}/api/block/{block_hash}/status"

    with httpx.Client(timeout=30.0) as client:
        for attempt, delay in enumerate(RETRY_DELAYS):
            is_last_attempt = attempt == len(RETRY_DELAYS) - 1

            try:
                resp = client.get(url)

                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Retryable HTTP %d fetching block status for %s (attempt %d/%d). "
                        "Sleeping %ds.",
                        resp.status_code,
                        block_hash,
                        attempt + 1,
                        len(RETRY_DELAYS),
                        delay,
                    )
                    time.sleep(delay)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.RequestError as exc:
                logger.warning(
                    "Network error fetching block status for %s (attempt %d/%d): %s",
                    block_hash,
                    attempt + 1,
                    len(RETRY_DELAYS),
                    exc,
                )
                if not is_last_attempt:
                    time.sleep(delay)
                continue

    raise RuntimeError(f"All retries exhausted fetching block status for {block_hash}")
