#!/usr/bin/env python3
"""Reproduces the GTFS figures in docs/corpus-manifest.md.

Published transit fares looked like the one available source that could
exercise `unit-mismatch` on a currency rather than on a unit: real price data,
free, machine-readable, and spread across dozens of currencies. This is the
script that established that it cannot, and it exists so that the four numbers
the manifest publishes about that decision are re-runnable rather than
asserted.

    python3 tools/probe_gtfs.py --feeds 140

It downloads the Mobility Database catalogue, samples feeds at a fixed seed,
and reports how many carry a fare table, how many fare rows those hold, how
many repeat a `fare_id`, and how many carry more than one currency. The last
two are the ones that matter: `fare_id` is a primary key in the GTFS
specification, so the same fare can never appear twice, and a feed is
published by one agency in one currency.

This is the second file in the repository that uses the network. Like
`fetch_hospital.py` it is not part of the installed package, and
`tests/test_offline.py` fails if `adds_up` itself ever gains the ability.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

CATALOGUE = "https://bit.ly/catalogs-csv"
FARE_FILES = (
    "fare_attributes.txt", "fare_products.txt", "rider_categories.txt",
    "fare_leg_rules.txt", "fare_media.txt",
)


def catalogue() -> list[dict]:
    with urllib.request.urlopen(CATALOGUE, timeout=120) as response:
        text = response.read().decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [
        row for row in rows
        if row.get("data_type") == "gtfs"
        and not row.get("redirect.id")
        and row.get("urls.latest")
    ]


def probe(feeds: int, seed: int) -> dict:
    rows = catalogue()
    totals = {
        "catalogue_url": CATALOGUE,
        "gtfs_static_feeds_listed": len(rows),
        "countries_listed": len({row["location.country_code"] for row in rows}),
        "feeds_tried": 0,
        "feeds_unreachable": 0,
        "feeds_with_a_fare_table": 0,
        "fare_rows": 0,
        "feeds_with_a_repeated_fare_id": 0,
        "feeds_with_more_than_one_currency": 0,
        "feeds_with_fares_v2_products": 0,
        "currencies_seen": Counter(),
    }
    random.Random(seed).shuffle(rows)
    for row in rows:
        if totals["feeds_with_a_fare_table"] >= feeds:
            break
        totals["feeds_tried"] += 1
        try:
            with urllib.request.urlopen(row["urls.latest"], timeout=90) as response:
                payload = response.read()
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except Exception:  # noqa: BLE001
            totals["feeds_unreachable"] += 1
            continue
        names = set(archive.namelist())
        if "fare_products.txt" in names:
            totals["feeds_with_fares_v2_products"] += 1
        if not any(name in names for name in FARE_FILES):
            continue
        if "fare_attributes.txt" not in names:
            continue
        totals["feeds_with_a_fare_table"] += 1
        text = archive.read("fare_attributes.txt").decode("utf-8-sig", "replace")
        fares = list(csv.DictReader(io.StringIO(text)))
        totals["fare_rows"] += len(fares)
        identifiers = [fare.get("fare_id") for fare in fares]
        if len(identifiers) != len(set(identifiers)):
            totals["feeds_with_a_repeated_fare_id"] += 1
        currencies = {
            fare.get("currency_type") for fare in fares if fare.get("currency_type")
        }
        for currency in currencies:
            totals["currencies_seen"][currency] += 1
        if len(currencies) > 1:
            totals["feeds_with_more_than_one_currency"] += 1
    totals["currencies_seen"] = dict(totals["currencies_seen"].most_common())
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feeds", type=int, default=140)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    print(json.dumps(probe(args.feeds, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
