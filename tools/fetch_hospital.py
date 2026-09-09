#!/usr/bin/env python3
"""Collect the hospital corpus described in docs/corpus-manifest.md.

This is the only file in the repository that uses the network, and it is not
part of the installed package — `adds_up` itself cannot open a connection, and
`tests/test_offline.py` fails if it ever gains the ability. Nothing here is
imported by the tool.

    python3 tools/fetch_hospital.py corpus/ --count 200 --cap-mb 40

Selection rule, repeated from the manifest so it is beside the code that
implements it: the state index files are shuffled at a fixed seed and worked
through in that order; a row is kept when a HEAD gives a non-zero
Content-Length under the cap, the body downloads, and the CSV (unzipped if
necessary) declares the CMS standard-charges schema in its first 16 kB.
Everything rejected is counted by reason, and the counts are written out
beside the files.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import sys
import threading
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

INDEX = (
    "https://raw.githubusercontent.com/nathansutton/"
    "hospital-price-transparency/main/dim/urls/{state}.json"
)
STATES = (
    "ak al ar az ca co ct dc de fl ga hi ia id il in ks ky la ma md me mi mn "
    "mo ms mt nc nd ne nh nj nm nv ny oh ok or pa ri sc sd tn tx ut va vt wa "
    "wi wv wy"
).split()

# Several hospital sites serve a 403 to a default urllib user-agent and a 200
# to a browser one. This is not a way round any access control: 45 CFR
# 180.50 requires these files to be downloadable by automated request.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}


def fetch(url: str, timeout: int, head: bool = False):
    request = urllib.request.Request(
        url, headers=HEADERS, method="HEAD" if head else "GET"
    )
    return urllib.request.urlopen(request, timeout=timeout)


def load_index() -> list[dict]:
    rows: list[dict] = []
    for state in STATES:
        try:
            with fetch(INDEX.format(state=state), 60) as response:
                entries = json.loads(response.read().decode("utf-8", "replace"))
        except Exception as error:  # noqa: BLE001
            print(f"index {state}: {type(error).__name__}", file=sys.stderr)
            continue
        for entry in entries:
            entry["state"] = state.upper()
            rows.append(entry)
    return rows


def collect(out: Path, want: int, cap: int, seed: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = load_index()
    candidates = [row for row in rows if row.get("file_url")]
    random.Random(seed).shuffle(candidates)
    print(f"index rows {len(rows)}, with a file_url {len(candidates)}", flush=True)

    lock = threading.Lock()
    stop = threading.Event()
    stats = {
        "index_rows": len(rows),
        "with_a_file_url": len(candidates),
        "probed": 0,
        "unreachable": 0,
        "no_content_length": 0,
        "over_the_cap": 0,
        "download_failed": 0,
        "not_a_cms_template": 0,
        "kept": 0,
    }
    index: list[dict] = []

    def one(entry: dict) -> None:
        if stop.is_set():
            return
        url = entry["file_url"]
        try:
            with fetch(url, 25, head=True) as response:
                length = int(response.headers.get("Content-Length") or 0)
                content_type = response.headers.get("Content-Type", "")
        except Exception:  # noqa: BLE001
            with lock:
                stats["unreachable"] += 1
            return
        with lock:
            stats["probed"] += 1
        if length == 0:
            with lock:
                stats["no_content_length"] += 1
            return
        if length > cap:
            with lock:
                stats["over_the_cap"] += 1
            return
        try:
            with fetch(url, 240) as response:
                payload = response.read()
        except Exception:  # noqa: BLE001
            with lock:
                stats["download_failed"] += 1
            return

        name = url.rsplit("/", 1)[-1].split("?")[0] or "file.csv"
        body = payload
        if payload[:2] == b"PK":
            try:
                archive = zipfile.ZipFile(io.BytesIO(payload))
                inner = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                if not inner:
                    with lock:
                        stats["not_a_cms_template"] += 1
                    return
                name = inner[0].rsplit("/", 1)[-1]
                body = archive.read(inner[0])
            except Exception:  # noqa: BLE001
                with lock:
                    stats["download_failed"] += 1
                return

        head_text = body[:16000].decode("utf-8", "replace")
        if "standard_charge" not in head_text:
            with lock:
                stats["not_a_cms_template"] += 1
            return
        lines = head_text.splitlines()
        ccn = str(entry.get("ccn") or "")
        # The content has been verified to be a CMS-template CSV, so it is
        # named as one. A URL basename is not: 38 of the first 200 files
        # collected were called `.aspx`, `.php`, `.json`, `.CSV` or nothing at
        # all, and `measure_hospital.py` glob'd `*.csv` and silently measured
        # 162 of them.
        stem = name.rsplit(".", 1)[0] if "." in name else name
        name = f"{stem}.csv"
        with lock:
            if stats["kept"] >= want:
                stop.set()
                return
            stats["kept"] += 1
            count = stats["kept"]
            # Numbered, because a CCN can appear more than once in the index
            # with different locations, and truncating `{ccn}-{basename}` to a
            # sane length collided on 41 of 200 files in the first collection.
            filename = f"{count:04d}-{ccn}-{name}".replace("/", "_")[:120]
        (out / filename).write_bytes(body)
        with lock:
            index.append({
                "ccn": ccn,
                "state": entry.get("state", ""),
                "hospital": entry.get("hospital_name", ""),
                "url": url,
                "saved_as": filename,
                "bytes": len(body),
                "downloaded_bytes": len(payload),
                "content_type": content_type,
                "sha256": hashlib.sha256(body).hexdigest(),
                "metadata_row": lines[1][:300] if len(lines) > 1 else "",
            })
        if count % 10 == 0:
            print(f"kept {count}", flush=True)

    # `shutdown(cancel_futures=True)` rather than leaving the `with` block:
    # 5,023 futures are submitted and the target is reached after a few
    # hundred, and an executor that waits for the rest takes an hour to write
    # its manifest.
    pool = ThreadPoolExecutor(max_workers=20)
    try:
        futures = [pool.submit(one, entry) for entry in candidates]
        for _ in as_completed(futures):
            if stop.is_set():
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    manifest = {
        "retrieved_by": "tools/fetch_hospital.py",
        "index": INDEX,
        "seed": seed,
        "cap_bytes": cap,
        "stats": stats,
        "files": sorted(index, key=lambda entry: entry["saved_as"]),
    }
    (out / "_index.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--cap-mb", type=int, default=40)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    manifest = collect(args.directory, args.count, args.cap_mb * 1024 * 1024, args.seed)
    print(json.dumps(manifest["stats"], indent=1))
    print(f"{len(manifest['files'])} file(s) in {args.directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
