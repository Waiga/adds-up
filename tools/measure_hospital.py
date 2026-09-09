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
``--per-document`` writes the findings each file produced, because a total
across documents does not say whether one file made all of them.

    python3 tools/measure_hospital.py corpus/ --samples audit.json \
        --per-document concentration.json

Unlike the tariff corpus, no reshaping happens here at all: the files go into
the tool exactly as the hospitals published them, three header rows and all.
That is the point of having this corpus — it is the only one that exercises
column recognition against hundreds of independently authored headers.
"""

from __future__ import annotations

import argparse
import json
import random
import re
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

#: A CMS standard-charges template version, as printed in the metadata block
#: above the header. Three generations are in circulation at once.
VERSION = re.compile(r"v?[23]\.\d+\.\d+")


def is_json(path: Path) -> bool:
    """True when the file is a JSON document, whatever its name says.

    The CMS schema has a JSON form as well as a tabular one, both contain the
    string ``standard_charge``, and some hospitals publish the JSON one from a
    URL ending ``.csv``. Read as a CSV, one of those is a single row of over a
    million comma-separated fields, which swamps every column total in this
    measurement. Counting them separately is the difference between reporting
    8,519 distinct column names and reporting 661,590 of which 98.7% never
    appear in a CSV at all.
    """
    with path.open("rb") as handle:
        head = handle.read(4096).lstrip(b"\xef\xbb\xbf").lstrip()
    return head[:1] in (b"{", b"[")


#: A check's reason for not running names the column that stopped it, so the
#: raw strings are as various as the corpus's headers and cannot be counted.
#: These buckets are what the README quotes, and they are why it can.
def bucket(reason: str) -> str:
    if "was not used: every one of the" in reason:
        return "the percentage column's writing is not settled by the document"
    if "could not be placed against any of the" in reason:
        return "the percentage could not be paired with a price column"
    if "the column holds no number" in reason:
        return "a column was recognised for the role but holds no number"
    if "holds no number this tool could use" in reason:
        return "the number convention in the column could not be decided"
    if "switched off" in reason:
        return "switched off"
    return reason


def measure(directory: Path, sample_size: int, seed: int):
    # Everything the fetch kept, whatever it is called. Matching `*.csv`
    # case-sensitively measured 162 of 200 files and said so nowhere.
    files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.name != "_index.json"
    )
    totals = {
        "tool_version": __version__,
        "files": len(files),
        "unreadable": 0,
        # A JSON document served from a `.csv` URL is now refused by name,
        # with a message saying it is not a table. It was always exit 2; the
        # difference is that the reader is told why. Counted apart from a file
        # that could not be read, because they are different facts.
        "refused_not_a_table": 0,
        # Rows whose cell count is not the header's. Not read, because their
        # values sit under headings that are not theirs — and counted, because
        # being silent about them was the largest measured source of wrong
        # findings in this tool's history.
        "rows_not_read_wider": 0,
        "rows_not_read_narrower": 0,
        "files_with_ragged_rows": 0,
        "worst_ragged_files": [],
        # Percentage columns refused because nothing in the document settles
        # whether 0.85 in them means 85% or 0.85%.
        "percentage_columns_refused_as_undecidable": 0,
        "files_with_a_refused_percentage_column": [],
        "crashes": 0,
        "crash_examples": [],
        "rows_total": 0,
        "columns_total": 0,
        "columns_with_a_role": 0,
        # The point of this corpus is headers this project did not write, so
        # the count of distinct ones is the figure that says how much of that
        # it delivers. `columns_total` counts instances, which is a different
        # and much larger number.
        "distinct_column_names": 0,
        # The same three figures over the files that really are CSV. The
        # combined ones above are dominated by JSON documents named `.csv`.
        "csv_files": 0,
        "json_files": 0,
        "columns_total_csv_only": 0,
        "columns_with_a_role_csv_only": 0,
        "distinct_column_names_csv_only": 0,
        "cms_template_versions": Counter(),
        "header_row_chosen": Counter(),
        "roles_found": Counter(),
        "checks_ran": {name: 0 for name in CHECK_NAMES},
        "checks_did_not_run": {name: Counter() for name in CHECK_NAMES},
        "why_a_check_did_not_run": {name: Counter() for name in CHECK_NAMES},
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
        "peak_rss_measured_on": "",
        "python": "",
        "bytes_total": 0,
    }
    # Findings per check per file. A total across documents says nothing
    # about whether it came from all of them or from one, and a published
    # figure that is really one pathological file has to say so.
    per_document: dict[str, Counter] = {name: Counter() for name in CHECK_NAMES}
    pool: dict[str, list] = {name: [] for name in CHECK_NAMES}
    pooled: dict[str, set] = {name: set() for name in CHECK_NAMES}
    names: set[str] = set()

    csv_names: set[str] = set()

    for number, path in enumerate(files, start=1):
        size = path.stat().st_size
        tabular = not is_json(path)
        totals["csv_files" if tabular else "json_files"] += 1
        totals["bytes_total"] += size
        started = time.monotonic()
        # Progress on stderr, so a run that dies part way through says where.
        # An earlier run was killed at some point among 200 files with its
        # stderr discarded, and left nothing at all behind to say which.
        print(
            f"[{number}/{len(files)}] {size / 1e6:8.1f} MB  {path.name[:60]}",
            file=sys.stderr, flush=True,
        )
        try:
            result = analyse(path)
        except UnreadableFile as error:
            if "not a table" in str(error):
                totals["refused_not_a_table"] += 1
            else:
                totals["unreadable"] += 1
                if len(totals["crash_examples"]) < 10:
                    totals["crash_examples"].append(
                        {"file": path.name, "error": str(error)}
                    )
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
        # The analysed table is the largest thing in memory by far. Dropping
        # it before the next file is read keeps two of them from overlapping.
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"      {elapsed:6.1f}s  peak so far {peak / (1 << 20 if sys.platform == 'darwin' else 1 << 10):.0f} MB",
              file=sys.stderr, flush=True)
        totals["slowest"].append(
            {"file": path.name, "megabytes": round(size / 1e6, 1),
             "seconds": round(elapsed, 1)}
        )
        any_ran = False
        ragged_here = 0
        for table in result.tables:
            totals["rows_total"] += table.row_count
            totals["rows_not_read_wider"] += table.rows_wider_than_header
            totals["rows_not_read_narrower"] += table.rows_narrower_than_header
            ragged_here += table.rows_set_aside_for_width
            totals["columns_total"] += len(table.columns)
            totals["header_row_chosen"][table.header_row_number] += 1
            if tabular:
                totals["columns_total_csv_only"] += len(table.columns)
            for column in table.columns:
                names.add(column.name.strip())
                if tabular:
                    csv_names.add(column.name.strip())
                if column.role:
                    totals["columns_with_a_role"] += 1
                    totals["roles_found"][column.role] += 1
                    if tabular:
                        totals["columns_with_a_role_csv_only"] += 1
            for row in table.preamble:
                for cell in row:
                    if VERSION.fullmatch(cell.strip()):
                        totals["cms_template_versions"][cell.strip()] += 1
            for index, reason in table.conventions.items():
                if "no other cell" in reason or "mixes both" in reason:
                    totals["number_convention_refusals"][reason[:60]] += 1
            for check in table.checks:
                refused_scale = [
                    line for line in check.set_aside
                    if "lies between 0 " in line
                ] + ([check.reason] if not check.ran and "lies between 0 " in check.reason
                     else [])
                if refused_scale:
                    totals["percentage_columns_refused_as_undecidable"] += len(refused_scale)
                    if path.name not in totals["files_with_a_refused_percentage_column"]:
                        totals["files_with_a_refused_percentage_column"].append(path.name)
                if check.ran:
                    totals["checks_ran"][check.name] += 1
                    any_ran = True
                else:
                    totals["checks_did_not_run"][check.name][check.reason[:110]] += 1
                    totals["why_a_check_did_not_run"][check.name][bucket(check.reason)] += 1
                totals["set_aside"] += len(check.set_aside)
                if check.findings:
                    totals["documents_with_a_finding"][check.name] += 1
                    per_document[check.name][path.name] += len(check.findings)
                for finding in check.findings:
                    totals["findings"][check.name] += 1
                    # Only the first finding per file is kept. The audit draw
                    # deduplicates by file anyway, so this changes nothing
                    # about the sample — and a wide file can produce a hundred
                    # thousand findings, which held in full across 200 files
                    # would need more memory than the analysis itself.
                    if path.name in pooled[check.name]:
                        continue
                    pooled[check.name].add(path.name)
                    pool[check.name].append({
                        "file": path.name,
                        "sheet": finding.places[0].sheet if finding.places else "",
                        "statement": finding.statement,
                        "detail": list(finding.detail),
                        "note": finding.note,
                        "places": [f"row {p.row}, {p.column}" for p in finding.places],
                    })
        if ragged_here:
            totals["files_with_ragged_rows"] += 1
            totals["worst_ragged_files"].append(
                {"file": path.name, "rows_not_read": ragged_here,
                 "rows_read": sum(t.row_count for t in result.tables)}
            )
        if not any_ran:
            totals["files_with_no_check_at_all"] += 1
        del result

    totals["distinct_column_names"] = len(names)
    totals["distinct_column_names_csv_only"] = len(csv_names)
    totals["cms_template_versions"] = dict(
        totals["cms_template_versions"].most_common()
    )
    totals["worst_ragged_files"] = sorted(
        totals["worst_ragged_files"], key=lambda entry: -entry["rows_not_read"]
    )[:10]
    totals["slowest"] = sorted(
        totals["slowest"], key=lambda entry: -entry["seconds"]
    )[:10]
    totals["seconds_total"] = round(totals["seconds_total"], 1)
    # `ru_maxrss` is bytes on macOS and kilobytes on Linux. Dividing by 2**20
    # unconditionally is right on one of them and 1024x wrong on the other,
    # which includes this repository's own CI.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1 << 20 if sys.platform == "darwin" else 1 << 10
    totals["peak_rss_mb"] = round(peak / divisor, 1)
    totals["peak_rss_measured_on"] = sys.platform
    totals["python"] = sys.version.split()[0]
    totals["header_row_chosen"] = dict(sorted(totals["header_row_chosen"].items()))
    totals["roles_found"] = dict(totals["roles_found"].most_common())
    totals["number_convention_refusals"] = dict(
        totals["number_convention_refusals"].most_common(5)
    )
    totals["checks_did_not_run"] = {
        name: dict(counter.most_common(5))
        for name, counter in totals["checks_did_not_run"].items()
    }
    totals["why_a_check_did_not_run"] = {
        name: dict(counter.most_common())
        for name, counter in totals["why_a_check_did_not_run"].items()
    }

    rng = random.Random(seed)
    samples = {}
    for name, entries in pool.items():
        if not entries:
            continue
        # One finding per file, so a single hospital cannot fill the sample.
        unique = sorted(entries, key=lambda e: e["file"])
        samples[name] = rng.sample(unique, min(sample_size, len(unique)))

    concentration = {}
    for name, counter in per_document.items():
        if not counter:
            continue
        ordered = counter.most_common()
        total = sum(counter.values())
        concentration[name] = {
            "findings": total,
            "documents": len(ordered),
            "worst_document": ordered[0][0],
            "worst_document_findings": ordered[0][1],
            "worst_document_share": round(ordered[0][1] / total, 4),
            "top_three_share": round(
                sum(count for _, count in ordered[:3]) / total, 4
            ),
            "median_document_findings": sorted(counter.values())[len(ordered) // 2],
            "per_document": dict(ordered),
        }
    return totals, samples, concentration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument(
        "--per-document",
        type=Path,
        help="write findings per check per file, and the concentration in them",
    )
    args = parser.parse_args()

    totals, samples, concentration = measure(
        args.directory, args.sample_size, args.seed
    )
    print(json.dumps(totals, indent=2, default=str))
    if args.samples:
        args.samples.write_text(
            json.dumps({"seed": args.seed, "size": args.sample_size, "samples": samples},
                       indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nsamples written to {args.samples}", file=sys.stderr)
    if args.per_document:
        args.per_document.write_text(
            json.dumps(concentration, indent=2, default=str), encoding="utf-8"
        )
        print(f"per-document counts written to {args.per_document}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
