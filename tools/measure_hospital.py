#!/usr/bin/env python3
"""The second corpus: US hospital price transparency files.

Every hospital in the United States is required by 45 CFR 180.50 to publish a
machine-readable file of its standard charges, free of charge and reachable by
automated download. Those files are price lists in the CMS template's own CSV
shape — a gross charge, a cash price, a negotiated dollar amount, a negotiated
percentage of the gross charge, and a declared minimum and maximum — which is
four of the seven things this tool checks, and none of them is anything the
utility-tariff corpus can exercise.

This runs the tool over a directory of them and prints the totals as JSON.
``--samples`` draws the hand-audit sample at a fixed seed.

    python3 tools/measure_hospital.py corpus/ --samples audit.json

Unlike the tariff corpus, no reshaping happens here at all: the files go into
the tool exactly as the hospitals published them, three header rows and all.
That is the point of having this corpus — it is the only one that exercises
column recognition against hundreds of independently authored headers.
"""

from __future__ import annotations

import argparse
import json
import random
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adds_up import __version__  # noqa: E402
from adds_up.analyse import analyse  # noqa: E402
from adds_up.checks import CHECK_NAMES  # noqa: E402
from adds_up.tables import UnreadableFile  # noqa: E402


def measure(directory: Path, sample_size: int, seed: int):
    files = sorted(p for p in directory.glob("*.csv") if p.name != "_index.json")
    totals = {
        "tool_version": __version__,
        "files": len(files),
        "unreadable": 0,
        "crashes": 0,
        "crash_examples": [],
        "rows_total": 0,
        "columns_total": 0,
        "columns_with_a_role": 0,
        "header_row_chosen": Counter(),
        "roles_found": Counter(),
        "checks_ran": {name: 0 for name in CHECK_NAMES},
        "checks_did_not_run": {name: Counter() for name in CHECK_NAMES},
        "findings": {name: 0 for name in CHECK_NAMES},
        "documents_with_a_finding": {name: 0 for name in CHECK_NAMES},
        "files_with_no_check_at_all": 0,
        "set_aside": 0,
        "number_convention_refusals": Counter(),
        # Published, because holding a whole table in memory is this tool's
        # hardest limit and a reader deserves the number rather than a warning.
        "seconds_total": 0.0,
        "slowest": [],
        "peak_rss_mb": 0,
        "bytes_total": 0,
    }
    pool: dict[str, list] = {name: [] for name in CHECK_NAMES}

    for path in files:
        size = path.stat().st_size
        totals["bytes_total"] += size
        started = time.monotonic()
        try:
            result = analyse(path)
        except UnreadableFile as error:
            totals["unreadable"] += 1
            if len(totals["crash_examples"]) < 10:
                totals["crash_examples"].append({"file": path.name, "error": str(error)})
            continue
        except Exception as error:  # noqa: BLE001 — a crash is a measurement
            totals["crashes"] += 1
            if len(totals["crash_examples"]) < 10:
                totals["crash_examples"].append(
                    {"file": path.name, "error": f"{type(error).__name__}: {error}"}
                )
            continue

        elapsed = time.monotonic() - started
        totals["seconds_total"] += elapsed
        totals["slowest"].append(
            {"file": path.name, "megabytes": round(size / 1e6, 1),
             "seconds": round(elapsed, 1)}
        )
        any_ran = False
        for table in result.tables:
            totals["rows_total"] += table.row_count
            totals["columns_total"] += len(table.columns)
            totals["header_row_chosen"][table.header_row_number] += 1
            for column in table.columns:
                if column.role:
                    totals["columns_with_a_role"] += 1
                    totals["roles_found"][column.role] += 1
            for index, reason in table.conventions.items():
                if "no other cell" in reason or "mixes both" in reason:
                    totals["number_convention_refusals"][reason[:60]] += 1
            for check in table.checks:
                if check.ran:
                    totals["checks_ran"][check.name] += 1
                    any_ran = True
                else:
                    totals["checks_did_not_run"][check.name][check.reason[:110]] += 1
                totals["set_aside"] += len(check.set_aside)
                if check.findings:
                    totals["documents_with_a_finding"][check.name] += 1
                for finding in check.findings:
                    totals["findings"][check.name] += 1
                    pool[check.name].append({
                        "file": path.name,
                        "sheet": finding.places[0].sheet if finding.places else "",
                        "statement": finding.statement,
                        "detail": list(finding.detail),
                        "note": finding.note,
                        "places": [f"row {p.row}, {p.column}" for p in finding.places],
                    })
        if not any_ran:
            totals["files_with_no_check_at_all"] += 1

    totals["slowest"] = sorted(
        totals["slowest"], key=lambda entry: -entry["seconds"]
    )[:10]
    totals["seconds_total"] = round(totals["seconds_total"], 1)
    totals["peak_rss_mb"] = round(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20), 1
    )
    totals["header_row_chosen"] = dict(sorted(totals["header_row_chosen"].items()))
    totals["roles_found"] = dict(totals["roles_found"].most_common())
    totals["number_convention_refusals"] = dict(
        totals["number_convention_refusals"].most_common(5)
    )
    totals["checks_did_not_run"] = {
        name: dict(counter.most_common(5))
        for name, counter in totals["checks_did_not_run"].items()
    }

    rng = random.Random(seed)
    samples = {}
    for name, entries in pool.items():
        if not entries:
            continue
        # One finding per file, so a single hospital cannot fill the sample.
        by_file: dict[str, dict] = {}
        for entry in entries:
            by_file.setdefault(entry["file"], entry)
        unique = sorted(by_file.values(), key=lambda e: e["file"])
        samples[name] = rng.sample(unique, min(sample_size, len(unique)))
    return totals, samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    totals, samples = measure(args.directory, args.sample_size, args.seed)
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
