#!/usr/bin/env python3
"""Programmatic citation gate for adversarial reviews.

Parses 9-field citation blocks from a review markdown file, verifies each
against Crossref (DOI) and NCBI PubMed (PMID), and:

  - inserts an inline `> CITATION FABRICATED` blockquote before any block
    whose identifier doesn't resolve or resolves to a paper with a very
    different title (common LLM hallucination mode);
  - appends a `## Citation Verification` section listing per-status
    counts and per-citation details;
  - exits non-zero (2) if any fabrication is found, so the parent shell
    can surface a hard-fail signal.

Dependencies: stdlib only (urllib, json, re, xml). No third-party.

Usage:
    verify_citations.py <review_file> [--metadata-out <path>]
                                       [--user-agent <ua>]
                                       [--rate-limit-sec <float>]

Exit codes:
    0  all citations verified, OR no citations found, OR only soft-warn
       statuses (unverifiable, missing-identifier)
    2  one or more citations FABRICATED or FABRICATED-MISMATCH
    3  IO/parse error (review file missing, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


# --- Constants ---

CROSSREF_URL = "https://api.crossref.org/works/"
EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
DEFAULT_USER_AGENT = (
    "beril-adversarial-skill/0.1 (citation-verifier; mailto:aparkin@lbl.gov)"
)
DEFAULT_TIMEOUT = 10.0
DEFAULT_RATE_LIMIT = 0.4  # seconds between calls — NCBI politeness

# Title-overlap threshold below which a verified DOI/PMID is treated as a
# mismatch (DOI exists, but it's for a different paper than the citation
# claims). 0.40 is permissive enough for citation-style title shortening
# (subtitles dropped, etc.) but catches wholesale mismatches.
TITLE_OVERLAP_THRESHOLD = 0.40

# Status enum (string-valued for JSON serialization).
S_VERIFIED = "verified"
S_FABRICATED = "fabricated"
S_FABRICATED_MISMATCH = "fabricated_mismatch"
S_UNVERIFIABLE = "unverifiable"
S_MISSING_IDENTIFIER = "missing_identifier"

HARD_FAIL_STATUSES = {S_FABRICATED, S_FABRICATED_MISMATCH}


# --- Citation parsing ---

# A citation header line has:
#   1. A bold-marked opening: **Authors. (Year). "Title." Venue.**
#   2. A doi: marker OR a PMID:/PMCID:/arXiv:/bioRxiv: identifier
#
# We match on the line containing the bold close (`**`) followed by either
# a doi: marker or one of the recognized ID prefixes. The model's output
# sometimes wraps identifiers in brackets and sometimes not — the regex
# handles both.
CITATION_LINE_RE = re.compile(
    r"^.*?\*\*[^\n]+?\*\*[^\n]*?"
    r"(?:doi:\s*\S+|\[?\s*(?:PMID|PMCID|arXiv|bioRxiv)\s*:\s*\S+)"
    r"[^\n]*$",
    re.MULTILINE,
)

DOI_RE = re.compile(r"doi:\s*(10\.\S+?)(?=[\s\]),]|$)", re.IGNORECASE)
PMID_RE = re.compile(r"PMID\s*:\s*(\d+)", re.IGNORECASE)
TITLE_RE = re.compile(r'"([^"]+)"')


def parse_review(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read review markdown, return (entries, lines).

    Each entry: {
        line_num: int (0-indexed),
        raw_line: str,
        doi: str or None,
        pmid: str or None,
        title: str or None,
    }
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    entries: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if not CITATION_LINE_RE.match(line):
            continue
        doi_m = DOI_RE.search(line)
        pmid_m = PMID_RE.search(line)
        title_m = TITLE_RE.search(line)
        doi = doi_m.group(1).rstrip(".,;:") if doi_m else None
        entries.append(
            {
                "line_num": i,
                "raw_line": line,
                "doi": doi,
                "pmid": pmid_m.group(1) if pmid_m else None,
                "title": title_m.group(1) if title_m else None,
            }
        )
    return entries, lines


# --- Verification ---


def _http_get_json(
    url: str, user_agent: str, timeout: float
) -> tuple[str, dict[str, Any] | None]:
    """GET a URL, parse JSON. Return (status, data_or_none).

    Status is one of: 'found', 'not_found', 'network_error'.
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return ("found", json.load(resp))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ("not_found", None)
        return ("network_error", None)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ("network_error", None)


def verify_doi(
    doi: str, user_agent: str, timeout: float
) -> tuple[str, str | None]:
    """Verify a DOI against Crossref. Return (status, registered_title)."""
    url = CROSSREF_URL + urllib.parse.quote(doi, safe="/")
    status, data = _http_get_json(url, user_agent, timeout)
    if status != "found" or data is None:
        return (status, None)
    msg = data.get("message", {})
    titles = msg.get("title", [])
    return ("found", titles[0] if titles else None)


def verify_pmid(
    pmid: str, user_agent: str, timeout: float
) -> tuple[str, str | None]:
    """Verify a PMID against NCBI eutils esummary. Return (status, title)."""
    url = f"{EUTILS_URL}?db=pubmed&id={pmid}&retmode=json"
    status, data = _http_get_json(url, user_agent, timeout)
    if status != "found" or data is None:
        return (status, None)
    result = data.get("result", {})
    uid_data = result.get(pmid)
    if not uid_data:
        return ("not_found", None)
    if isinstance(uid_data, dict) and "error" in uid_data:
        return ("not_found", None)
    return ("found", uid_data.get("title"))


def title_overlap(claimed: str | None, actual: str | None) -> float:
    """Word-level Jaccard overlap, lowercased and stripped of stopwords.

    Returns 0.0 if either is None or empty.
    """
    if not claimed or not actual:
        return 0.0
    # Tokenize: lowercase, alphanum runs only.
    stopwords = {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "is",
        "of", "on", "or", "the", "to", "with",
    }
    def toks(t: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in stopwords}
    c, a = toks(claimed), toks(actual)
    if not c or not a:
        return 0.0
    return len(c & a) / len(c | a)


def classify(
    entry: dict[str, Any],
    user_agent: str,
    timeout: float,
    rate_limit_sec: float,
) -> tuple[str, str]:
    """Classify a citation entry. Return (status, reason)."""
    has_doi = entry["doi"] is not None
    has_pmid = entry["pmid"] is not None

    if not has_doi and not has_pmid:
        return (S_MISSING_IDENTIFIER, "no DOI or PMID present")

    # DOI path
    if has_doi:
        doi_status, registered_title = verify_doi(
            entry["doi"], user_agent, timeout
        )
        time.sleep(rate_limit_sec)
        if doi_status == "not_found":
            return (
                S_FABRICATED,
                f"DOI {entry['doi']} not found in Crossref",
            )
        if doi_status == "found":
            ov = title_overlap(entry["title"], registered_title)
            if registered_title and entry["title"] and ov < TITLE_OVERLAP_THRESHOLD:
                return (
                    S_FABRICATED_MISMATCH,
                    f"DOI {entry['doi']} resolves to "
                    f"\"{registered_title}\", but citation claims "
                    f"\"{entry['title']}\" (title overlap {ov:.0%})",
                )
            return (S_VERIFIED, f"DOI {entry['doi']} resolved")
        # network_error — fall through to PMID if available

    # PMID path
    if has_pmid:
        pmid_status, registered_title = verify_pmid(
            entry["pmid"], user_agent, timeout
        )
        time.sleep(rate_limit_sec)
        if pmid_status == "not_found":
            return (
                S_FABRICATED,
                f"PMID {entry['pmid']} not found in PubMed",
            )
        if pmid_status == "found":
            ov = title_overlap(entry["title"], registered_title)
            if registered_title and entry["title"] and ov < TITLE_OVERLAP_THRESHOLD:
                return (
                    S_FABRICATED_MISMATCH,
                    f"PMID {entry['pmid']} resolves to "
                    f"\"{registered_title}\", but citation claims "
                    f"\"{entry['title']}\" (title overlap {ov:.0%})",
                )
            return (S_VERIFIED, f"PMID {entry['pmid']} resolved")

    # Both registries unreachable.
    return (
        S_UNVERIFIABLE,
        "could not reach Crossref or PubMed registry (network error)",
    )


# --- Mutation ---


def insert_inline_warnings(
    lines: list[str], entries: list[dict[str, Any]]
) -> list[str]:
    """Insert blockquote warnings before fabricated citations.

    Mutates a copy from end to start so line numbers don't shift.
    """
    new_lines = list(lines)
    fabs = [e for e in entries if e["status"] in HARD_FAIL_STATUSES]
    fabs.sort(key=lambda e: -e["line_num"])
    for entry in fabs:
        warning = f"> ⚠️ **CITATION FABRICATED**: {entry['reason']}"
        new_lines.insert(entry["line_num"], warning)
    return new_lines


def build_report_section(entries: list[dict[str, Any]]) -> list[str]:
    """Produce the `## Citation Verification` section as a list of lines."""
    by_status: dict[str, list[dict[str, Any]]] = {
        S_VERIFIED: [],
        S_FABRICATED: [],
        S_FABRICATED_MISMATCH: [],
        S_UNVERIFIABLE: [],
        S_MISSING_IDENTIFIER: [],
    }
    for e in entries:
        by_status.setdefault(e["status"], []).append(e)

    n_total = len(entries)
    n_fab = len(by_status[S_FABRICATED]) + len(by_status[S_FABRICATED_MISMATCH])
    n_verified = len(by_status[S_VERIFIED])
    n_unverifiable = len(by_status[S_UNVERIFIABLE])
    n_missing = len(by_status[S_MISSING_IDENTIFIER])

    out: list[str] = [
        "",
        "## Citation Verification",
        "",
        (
            f"Programmatically verified {n_total} citation block(s) "
            "against Crossref (DOI) and NCBI PubMed (PMID)."
        ),
        "",
        f"- Verified: {n_verified}",
        f"- Fabricated: {n_fab}",
        f"- Unverifiable (network failure): {n_unverifiable}",
        f"- Missing identifier (no DOI/PMID): {n_missing}",
        "",
    ]

    if by_status[S_FABRICATED] or by_status[S_FABRICATED_MISMATCH]:
        out.append("### Fabricated")
        out.append("")
        for e in by_status[S_FABRICATED] + by_status[S_FABRICATED_MISMATCH]:
            out.append(f"- Line {e['line_num'] + 1}: {e['reason']}")
        out.append("")

    if by_status[S_UNVERIFIABLE]:
        out.append("### Unverifiable")
        out.append("")
        out.append(
            "Could not reach the relevant registry. Re-run with network "
            "access to verify; manually confirm before relying on these."
        )
        out.append("")
        for e in by_status[S_UNVERIFIABLE]:
            out.append(f"- Line {e['line_num'] + 1}: {e['reason']}")
        out.append("")

    if by_status[S_MISSING_IDENTIFIER]:
        out.append("### Missing identifier")
        out.append("")
        out.append(
            "These citations lack both DOI and PMID — cannot be verified "
            "programmatically. The reviewer should add an identifier or "
            "remove the citation."
        )
        out.append("")
        for e in by_status[S_MISSING_IDENTIFIER]:
            out.append(f"- Line {e['line_num'] + 1}: missing identifier")
        out.append("")

    return out


def insert_report_section(
    lines: list[str], report_lines: list[str]
) -> list[str]:
    """Insert report before any `## Run Metadata` heading; else append."""
    for i, line in enumerate(lines):
        if line.strip() == "## Run Metadata":
            return lines[:i] + report_lines + lines[i:]
    return lines + report_lines


# --- Orchestration ---


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify citations in an adversarial review markdown file."
    )
    parser.add_argument("review_file", help="Path to the review markdown file.")
    parser.add_argument(
        "--metadata-out",
        help="Optional path to write a JSON status summary.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="HTTP User-Agent header for registry calls.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--rate-limit-sec",
        type=float,
        default=DEFAULT_RATE_LIMIT,
        help="Seconds to sleep between registry calls (default: %(default)s).",
    )
    args = parser.parse_args()

    review_path = Path(args.review_file)
    if not review_path.exists():
        print(f"ERROR: review file not found: {review_path}", file=sys.stderr)
        return 3
    if not review_path.is_file():
        print(f"ERROR: not a regular file: {review_path}", file=sys.stderr)
        return 3

    try:
        entries, lines = parse_review(review_path)
    except OSError as e:
        print(f"ERROR: cannot read review file: {e}", file=sys.stderr)
        return 3

    if not entries:
        print(
            "Citation verification: no 9-field citation blocks found.",
            file=sys.stderr,
        )
        if args.metadata_out:
            Path(args.metadata_out).write_text(
                json.dumps(
                    {
                        "total": 0,
                        "verified": 0,
                        "fabricated": 0,
                        "unverifiable": 0,
                        "missing_identifier": 0,
                    }
                ),
                encoding="utf-8",
            )
        return 0

    print(
        f"Citation verification: checking {len(entries)} block(s)...",
        file=sys.stderr,
    )

    for entry in entries:
        status, reason = classify(
            entry,
            user_agent=args.user_agent,
            timeout=args.timeout,
            rate_limit_sec=args.rate_limit_sec,
        )
        entry["status"] = status
        entry["reason"] = reason
        marker = {
            S_VERIFIED: "✓",
            S_FABRICATED: "✗",
            S_FABRICATED_MISMATCH: "✗",
            S_UNVERIFIABLE: "?",
            S_MISSING_IDENTIFIER: "?",
        }[status]
        print(
            f"  {marker} Line {entry['line_num'] + 1}: {status} — {reason}",
            file=sys.stderr,
        )

    # Mutate review file in place.
    new_lines = insert_inline_warnings(lines, entries)
    report = build_report_section(entries)
    final = insert_report_section(new_lines, report)
    review_path.write_text("\n".join(final), encoding="utf-8")

    n_total = len(entries)
    n_fab = sum(1 for e in entries if e["status"] in HARD_FAIL_STATUSES)
    n_verified = sum(1 for e in entries if e["status"] == S_VERIFIED)
    n_unverifiable = sum(1 for e in entries if e["status"] == S_UNVERIFIABLE)
    n_missing = sum(
        1 for e in entries if e["status"] == S_MISSING_IDENTIFIER
    )

    if args.metadata_out:
        Path(args.metadata_out).write_text(
            json.dumps(
                {
                    "total": n_total,
                    "verified": n_verified,
                    "fabricated": n_fab,
                    "unverifiable": n_unverifiable,
                    "missing_identifier": n_missing,
                }
            ),
            encoding="utf-8",
        )

    if n_fab > 0:
        print(
            f"Citation verification: FAIL — {n_fab} fabrication(s) marked "
            "in review and listed in the Citation Verification section.",
            file=sys.stderr,
        )
        return 2

    if n_unverifiable > 0 or n_missing > 0:
        print(
            f"Citation verification: PASS with caveats — "
            f"{n_verified} verified, {n_unverifiable} unverifiable, "
            f"{n_missing} missing-identifier.",
            file=sys.stderr,
        )
    else:
        print(
            f"Citation verification: PASS — all {n_verified} verified.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
