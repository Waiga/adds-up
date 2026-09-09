#!/usr/bin/env python3
"""Every number published about adds-up comes out of this script.

It reshapes the OpenEI U.S. Utility Rate Database into one price list per
published tariff, runs the tool over every one of them, and prints the totals
as JSON. ``--samples`` draws the hand-audit samples at a fixed seed so the
same export gives the same rows to anyone who runs it.

    python3 tools/measure_corpus.py usurdb.csv.gz
    python3 tools/measure_corpus.py usurdb.csv.gz --samples audit.json

The reshape is the only thing done to the data. A URDB row stores a tariff's
tier table across up to 6 periods x 24 tiers of wide columns; this writes each
period's tiers out as rows, keeping URDB's own field names — ``tier``, ``max``,
``rate``, ``adj``, ``unit``. Nothing is filtered, corrected or rounded.

That reshape is also the measurement's largest limitation and it is stated in
the manifest: every document in this corpus arrives with the same five column
names, so the column-recognition step is exercised once rather than 29,521
times.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adds_up import __version__  # noqa: E402
from adds_up.analyse import analyse  # noqa: E402
from adds_up.checks import CHECK_NAMES  # noqa: E402

csv.field_size_limit(10 ** 9)

STRUCTURES = ("energyratestructure", "demandratestructure", "flatdemandstructure")
FIELDS = ("tier", "max", "rate", "adj", "unit")


def opener(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="")
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tier_rows(row: dict, structure: str, period: int) -> list[dict]:
    out = []
    for index in range(24):
        prefix = f"{structure}/period{period}/tier{index}"
        rate = row.get(prefix + "rate")
        if rate in (None, ""):
            break
        out.append({
            "tier": index + 1,
            "max": row.get(prefix + "max", ""),
            "rate": rate,
            "adj": row.get(prefix + "adj", ""),
            "unit": row.get(prefix + "unit", ""),
        })
    return out


def ladder_shape(rows: list[dict]) -> str:
    """Which way a tier ladder moves, before the tool is asked anything.

    ``rising`` is how a deliberately inclining block tariff is built.
    ``falling`` is an ordinary volume discount. ``mixed`` falls and then rises,
    or the reverse, and is the shape no pricing policy sets out to produce.
    """
    values = []
    for row in rows:
        try:
            values.append(float(row["rate"] or 0) + float(row["adj"] or 0))
        except ValueError:
            return "unreadable"
    ups = sum(1 for a, b in zip(values, values[1:]) if b > a)
    downs = sum(1 for a, b in zip(values, values[1:]) if b < a)
    if ups and downs:
        return "mixed"
    if ups:
        return "rising"
    if downs:
        return "falling"
    return "flat"


def price_lists(source: Path):
    """Yield (identity, rows) for every multi-tier price list in the export."""
    with opener(source) as handle:
        for row in csv.DictReader(handle):
            for structure in STRUCTURES:
                for period in range(6):
                    rows = tier_rows(row, structure, period)
                    if len(rows) < 2:
                        continue
                    yield {
                        "label": row.get("label", ""),
                        "utility": row.get("utility", ""),
                        "name": row.get("name", ""),
                        "sector": row.get("sector", ""),
                        "structure": structure,
                        "period": period,
                        "enddate": row.get("enddate", ""),
                        "source": row.get("source", ""),
                        "tiers": len(rows),
                    }, rows


def export_shape(source: Path) -> dict:
    """The export's own dimensions, so the manifest's figures have a producer.

    Counted from the file rather than from the price lists derived from it —
    the two are different numbers and one of them used to be printed under the
    other's name.
    """
    utilities = set()
    with_a_source = 0
    columns = 0
    records = 0
    with opener(source) as handle:
        reader = csv.DictReader(handle)
        columns = len(reader.fieldnames or [])
        for row in reader:
            records += 1
            utilities.add(row.get("utility", ""))
            if row.get("source"):
                with_a_source += 1
    return {
        "records": records,
        "columns": columns,
        "utilities": len(utilities),
        "records_naming_a_source_document": with_a_source,
    }


def measure(source: Path, sample_size: int, seed: int):
    totals = {
        "tool_version": __version__,
        "python": sys.version.split()[0],
        "corpus": {
            "file": source.name,
            "sha256": sha256(source),
            "bytes": source.stat().st_size,
            "export": export_shape(source),
        },
        "records_with_a_multi_tier_list": 0,
        "price_lists": 0,
        "distinct_tariffs": 0,
        "distinct_utilities": 0,
        "still_active": 0,
        "rows_total": 0,
        # The design doc explains why an adjuster is added to the rate; this
        # is how many rows carry one, so that explanation has a producer.
        "rows_with_an_adjustment": 0,
        "crashes": 0,
        "crash_examples": [],
        "checks_ran": {name: 0 for name in CHECK_NAMES},
        "checks_did_not_run": {name: Counter() for name in CHECK_NAMES},
        "findings": {name: 0 for name in CHECK_NAMES},
        "documents_with_a_finding": {name: 0 for name in CHECK_NAMES},
        "set_aside": 0,
        "volume_tier_zero_lower_band": 0,
        # A tier ladder that only ever rises is how inclining block pricing is
        # deliberately built. One that falls and then rises is not, and the
        # two are worth counting apart before any claim is made about either.
        "ladder_shape": Counter(),
        "findings_by_ladder_shape": Counter(),
        "by_structure": defaultdict(lambda: {"lists": 0, "volume_tier": 0}),
        "by_sector": defaultdict(lambda: {"lists": 0, "volume_tier": 0}),
        "tier_count": Counter(),
        "units_seen": Counter(),
        "number_convention_refusals": 0,
    }
    tariffs = set()
    utilities = set()
    pool: dict[str, list] = {name: [] for name in CHECK_NAMES}

    with tempfile.TemporaryDirectory() as workspace:
        scratch = Path(workspace) / "list.csv"
        seen_records = set()
        for identity, rows in price_lists(source):
            totals["price_lists"] += 1
            totals["rows_total"] += len(rows)
            totals["rows_with_an_adjustment"] += sum(
                1 for row in rows if row["adj"] not in ("", None)
            )
            totals["tier_count"][len(rows)] += 1
            tariffs.add(identity["label"])
            utilities.add(identity["utility"])
            seen_records.add(identity["label"])
            if not identity["enddate"]:
                totals["still_active"] += 1
            sector = identity["sector"] or "(none)"
            totals["by_sector"][sector]["lists"] += 1
            totals["by_structure"][identity["structure"]]["lists"] += 1
            shape = ladder_shape(rows)
            totals["ladder_shape"][shape] += 1
            for row in rows:
                totals["units_seen"][row["unit"]] += 1

            with scratch.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            try:
                result = analyse(scratch)
            except Exception as error:  # noqa: BLE001 — a crash is a measurement
                totals["crashes"] += 1
                if len(totals["crash_examples"]) < 10:
                    totals["crash_examples"].append(
                        {"label": identity["label"], "error": f"{type(error).__name__}: {error}"}
                    )
                continue

            for table in result.tables:
                for value in table.conventions.values():
                    if "no other cell" in value or "mixes both" in value:
                        totals["number_convention_refusals"] += 1
                for check in table.checks:
                    if check.ran:
                        totals["checks_ran"][check.name] += 1
                    else:
                        totals["checks_did_not_run"][check.name][check.reason] += 1
                    totals["set_aside"] += len(check.set_aside)
                    if check.findings:
                        totals["documents_with_a_finding"][check.name] += 1
                        if check.name == "volume-tier":
                            totals["by_sector"][sector]["volume_tier"] += 1
                            totals["by_structure"][identity["structure"]]["volume_tier"] += 1
                            totals["findings_by_ladder_shape"][shape] += 1
                    for finding in check.findings:
                        totals["findings"][check.name] += 1
                        if finding.note:
                            totals["volume_tier_zero_lower_band"] += 1
                        pool[check.name].append({
                            "label": identity["label"],
                            "utility": identity["utility"],
                            "tariff": identity["name"],
                            "sector": identity["sector"],
                            "structure": identity["structure"],
                            "period": identity["period"],
                            "source": identity["source"],
                            "statement": finding.statement,
                            "detail": list(finding.detail),
                            "note": finding.note,
                            "ladder_shape": shape,
                            "rows": rows,
                        })

    # Not the records in the export: `seen_records` only ever receives labels
    # of records that already passed the two-tier filter. The field is named
    # for what it is.
    totals["records_with_a_multi_tier_list"] = len(seen_records)
    totals["distinct_tariffs"] = len(tariffs)
    totals["distinct_utilities"] = len(utilities)
    totals["by_sector"] = dict(totals["by_sector"])
    totals["by_structure"] = dict(totals["by_structure"])
    totals["ladder_shape"] = dict(totals["ladder_shape"].most_common())
    totals["findings_by_ladder_shape"] = dict(totals["findings_by_ladder_shape"].most_common())
    totals["tier_count"] = dict(sorted(totals["tier_count"].items()))
    totals["units_seen"] = dict(totals["units_seen"].most_common())
    totals["checks_did_not_run"] = {
        name: dict(counter.most_common(5))
        for name, counter in totals["checks_did_not_run"].items()
    }

    samples = {}
    rng = random.Random(seed)
    for name, entries in pool.items():
        if not entries:
            continue
        # One row per tariff, so a single utility with a thousand tiers cannot
        # fill the sample with the same mistake.
        by_tariff = {}
        for entry in entries:
            by_tariff.setdefault(entry["label"], entry)
        unique = sorted(by_tariff.values(), key=lambda e: e["label"])
        samples[name] = rng.sample(unique, min(sample_size, len(unique)))
    return totals, samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="usurdb.csv or usurdb.csv.gz")
    parser.add_argument("--samples", type=Path, help="write the audit draw here")
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    totals, samples = measure(args.export, args.sample_size, args.seed)
    print(json.dumps(totals, indent=2, default=str))
    if args.samples:
        args.samples.write_text(
            json.dumps({"seed": args.seed, "size": args.sample_size, "samples": samples},
                       indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nsamples written to {args.samples}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
