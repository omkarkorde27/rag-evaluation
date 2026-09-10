#!/usr/bin/env python3
"""
Code grader for ChatAIU evaluation results.

ChatAIU ships a MODEL grader (Verdict / Score / Rationale). It judges semantic
equivalence, and it is lenient - it awards credit for "additional correct
detail" and forgives omissions it deems secondary.

That leniency is a problem for the one failure mode that actually hurts a
student: a confident admissions DATE. A model grader may pass an answer that
mentions dates in passing. A code grader cannot be talked into it.

This is the "Code Grader" box from the Anthropic workflow: format and hard
constraints checked programmatically, layered on top of the model grader
rather than replacing it.

Usage:
    python3 grade_results.py <results.csv>

Expects the ChatAIU results columns:
    Question, ExpectedAnswer, ActualAnswer, Verdict, Score, Rationale, Sources
"""

import csv
import re
import sys

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")

# Questions about ADMISSION deadlines must never contain a date.
ADMISSION_RX = re.compile(
    r"\b(apply|application|admission|applicant)\b", re.I)
GRADUATION_RX = re.compile(
    r"\b(thesis|dissertation|graduat|advanced degree|commencement)\b", re.I)
DATE_RX = re.compile(rf"\b(20\d\d|{MONTHS}\s+\d{{1,2}})\b", re.I)

# Things that should never reach a user.
METADATA_RX = re.compile(
    r"context length|quantization|supported modalities|thinking levels",
    re.I)

# A reply that is essentially just a URL.
URL_RX = re.compile(r"https?://\S+")


def check(question, answer):
    """Return a list of hard-constraint violations."""
    problems = []

    if METADATA_RX.search(answer):
        problems.append("LEAKED SYSTEM METADATA into a user-facing answer")

    # Date in an admissions-deadline answer, unless the reply is clearly
    # about graduation instead.
    if ADMISSION_RX.search(question) and not GRADUATION_RX.search(question):
        hit = DATE_RX.search(answer)
        if hit and not GRADUATION_RX.search(answer):
            problems.append(f"DATE '{hit.group(0)}' in an admissions answer")

    prose = URL_RX.sub("", answer).strip()
    if len(prose) < 120 and URL_RX.search(answer):
        problems.append(f"BARE LINK - only {len(prose)} chars of prose")

    if "@" in answer:
        for bad in re.findall(r"grdschl@indiana\.edu", answer):
            problems.append("STALE EMAIL grdschl@indiana.edu (use @iu.edu)")

    return problems


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
    flagged = 0
    model_passed_but_code_failed = 0

    for r in rows:
        q = r.get("Question", "")
        a = r.get("ActualAnswer", "")
        verdict = (r.get("Verdict") or "").strip()
        problems = check(q, a)
        if not problems:
            continue
        flagged += 1
        if verdict.lower() == "pass":
            model_passed_but_code_failed += 1
        print(f"\n[{verdict or '?'}] {q[:70]}")
        for p in problems:
            print(f"    !! {p}")

    print(f"\n{'-'*64}")
    print(f"rows checked                : {len(rows)}")
    print(f"hard-constraint violations  : {flagged}")
    print(f"  of which the model PASSED : {model_passed_but_code_failed}"
          "   <- the leniency gap")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
