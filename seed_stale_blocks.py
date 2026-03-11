"""
One-time script to seed historical orphaned block data from the
bitcoin-data/stale-blocks community dataset.

Source: https://github.com/bitcoin-data/stale-blocks
License: CC0 (public domain)

Coverage: ~2,014 stale blocks from height 74,638 onward (2011–present).
This dataset is crowd-sourced: contributors run Bitcoin Core nodes and
submit orphans they observe via `getchaintips`. It's not exhaustive, but
it's the best free historical source available.

What this script does:
  1. Downloads the CSV from GitHub.
  2. Decodes the miner timestamp from each block's 80-byte header.
  3. Looks up the canonical block hash at each height (DB first, then API).
  4. Inserts orphan Block rows and ForkEvent rows that don't already exist.

Run once after backfill has made reasonable progress:
  python seed_stale_blocks.py

It's safe to re-run — all inserts are guarded by existence checks.
"""

import csv
import io
import struct
import time
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.database import engine
from app.models import Block, ForkEvent

CSV_URL = "https://raw.githubusercontent.com/bitcoin-data/stale-blocks/master/stale-blocks.csv"

# Seconds between mempool.space API calls when we need to look up a canonical hash.
# The canonical block is usually already in our DB, so this is only hit for heights
# the backfill hasn't reached yet.
API_THROTTLE = 0.3


def decode_header_timestamp(header_hex: str) -> datetime:
    """
    Extract the miner-reported timestamp from a raw Bitcoin block header.

    A Bitcoin block header is exactly 80 bytes with this layout:
        bytes  0– 3: version (little-endian int32)
        bytes  4–35: previous block hash (32 bytes, reversed)
        bytes 36–67: merkle root (32 bytes)
        bytes 68–71: timestamp (little-endian uint32, Unix seconds)  ← we want this
        bytes 72–75: difficulty bits
        bytes 76–79: nonce

    The CSV stores the header as a hex string (160 characters = 80 bytes).
    """
    ts_bytes = bytes.fromhex(header_hex[136:144])  # bytes 68–71 = chars 136–143
    unix_ts = struct.unpack("<I", ts_bytes)[0]      # little-endian uint32
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).replace(tzinfo=None)


def get_canonical_hash(height: int, session: Session, client: httpx.Client) -> str | None:
    """
    Find the canonical block hash at a given height.

    Checks the local DB first (fast, no network). Falls back to the
    mempool.space API for heights the backfill hasn't reached yet.

    Returns None if the API call fails after retries.
    """
    # Fast path: canonical block already in DB
    result = session.exec(
        select(Block.hash)
        .where(Block.height == height)
        .where(Block.is_canonical == True)
    ).first()
    if result:
        return result

    # Slow path: ask mempool.space for the canonical hash at this height
    url = f"https://mempool.space/api/block-height/{height}"
    for attempt in range(3):
        try:
            resp = client.get(url, timeout=15.0)
            if resp.status_code == 200:
                return resp.text.strip()
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            return None
        except httpx.RequestError:
            time.sleep(2 ** attempt)
    return None


def main() -> None:
    print("Downloading stale-blocks CSV...")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(CSV_URL)
        resp.raise_for_status()

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    print(f"Found {len(rows)} stale block entries")

    inserted_blocks = 0
    inserted_forks = 0
    skipped = 0

    with Session(engine) as session:
        with httpx.Client(timeout=15.0) as client:
            for i, row in enumerate(rows):
                height = int(row["height"])
                orphan_hash = row["hash"]
                header_hex = row["header"]

                # Skip if we already have this orphan
                if session.get(Block, orphan_hash) is not None:
                    skipped += 1
                    continue

                # Decode timestamp from the block header
                try:
                    ts = decode_header_timestamp(header_hex)
                except Exception as e:
                    print(f"  [WARN] height {height}: couldn't decode header — {e}")
                    continue

                # Get canonical block hash at this height
                canonical_hash = get_canonical_hash(height, session, client)
                if canonical_hash is None:
                    print(f"  [WARN] height {height}: couldn't find canonical hash, skipping")
                    continue

                # Data quality guard: CSV occasionally lists a block as orphaned
                # that is actually the canonical block at that height (e.g. after a reorg
                # flipped which chain won). Skip these — they're not real orphans.
                if canonical_hash == orphan_hash:
                    print(f"  [SKIP] height {height}: orphan hash matches canonical — stale CSV entry")
                    skipped += 1
                    continue

                # Insert canonical Block if not already in DB (can happen for heights
                # the backfill hasn't reached yet — we store a placeholder so the
                # ForkEvent foreign reference is consistent)
                if session.get(Block, canonical_hash) is None:
                    session.add(Block(
                        hash=canonical_hash,
                        height=height,
                        timestamp=ts,  # approximate — miner ts from orphan header
                        is_canonical=True,
                    ))

                # Insert the orphaned Block
                session.add(Block(
                    hash=orphan_hash,
                    height=height,
                    timestamp=ts,
                    is_canonical=False,
                ))
                inserted_blocks += 1

                # Insert a ForkEvent linking the two
                session.add(ForkEvent(
                    height=height,
                    canonical_hash=canonical_hash,
                    orphaned_hash=orphan_hash,
                    detected_at=ts,
                    # resolution_seconds: not available from this dataset
                ))
                inserted_forks += 1

                session.commit()

                # Progress every 100 rows
                if (i + 1) % 100 == 0:
                    print(f"  {i + 1}/{len(rows)} processed — {inserted_blocks} inserted, {skipped} skipped")

                # Throttle only when we had to hit the API
                # (If canonical was in DB, no sleep needed)
                time.sleep(0.05)  # small pause to avoid hammering the DB

    print(f"\nDone.")
    print(f"  Orphan blocks inserted : {inserted_blocks}")
    print(f"  Fork events inserted   : {inserted_forks}")
    print(f"  Already existed        : {skipped}")


if __name__ == "__main__":
    main()
