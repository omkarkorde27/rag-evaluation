#!/usr/bin/env python3
"""
Component-level RAG evaluation for ChatAIU exports.

WHY THIS EXISTS
ChatAIU reports one number per question: does the answer semantically match my
reference. That single score conflates two failures that need opposite fixes:

    retrieval failure   - the right chunk never surfaced
    generation failure  - the right chunk surfaced and the model ignored it

This decomposes the run into per-layer signals using only the exported CSV
(Question, ExpectedAnswer, ActualAnswer, Verdict, Score, Rationale, Sources).

WHAT IT COMPUTES

  1. SOURCE ATTRIBUTION
     Which source type drove each answer - Q&A pair, sitemap page, or document.
     Q&A pairs export as "content.md (/download?index=...)" blobs; sitemap hits
     export as real URLs. A run where Q&A blobs dominate the top rank is a run
     where the curated set is crowding out the corpus.

  2. RETRIEVAL RECALL  (opt-in, needs an expected_source column)
     Did the page that SHOULD answer this question appear in Sources at all,
     and at what rank? Gives recall@k and MRR - the retrieval-layer metrics
     ChatAIU does not report.

  3. RELEVANCE DISTRIBUTION
     Top-1 and spread per row. Note that scores are NOT bounded to 0-1: the
     reranker emits its own scale (values above 1.0 occur), and chunks have
     been observed entering context at 0.00, which suggests some injection
     path bypasses the minimum-relevance filter. Treat the threshold as an
     empirical knob, not a percentage.

  4. REGRESSION DIFF  (two runs)
     Per-question Pass -> Fail transitions between runs. This is the signal
     that matters most: an aggregate pass rate can hold steady while specific
     questions silently break.

USAGE
    python3 rag_eval.py results.csv
    python3 rag_eval.py results_new.csv --baseline results_old.csv
"""

import argparse
import csv
import html
import re
import statistics
import sys
from collections import Counter

# A Q&A pair exports as a content.md download blob rather than a page URL.
QA_BLOB = re.compile(r"content\.md\s*\(/download\?index=", re.I)
# "Title (https://url) [rel 0.58]" - the trailing score per source.
REL = re.compile(r"\[rel\s+([0-9.]+)\]", re.I)
URL = re.compile(r"\((https?://[^)]+)\)")


# Sources entries end with "[rel N.NN]", so split on that boundary rather
# than a bare ";" - page titles contain HTML entities like "&amp;" whose
# semicolon would otherwise split one source into two.
SPLIT = re.compile(r"\]\s*;\s*")


def parse_sources(cell):
    """Split the Sources cell into ordered entries with type, url, score."""
    if not cell or not cell.strip():
        return []
    cell = html.unescape(cell)
    out = []
    parts = SPLIT.split(cell)
    parts = [p if p.rstrip().endswith("]") else p + "]" for p in parts]
    for part in parts:
        part = part.strip()
        if not part:
            continue
        rel = REL.search(part)
        url = URL.search(part)
        if QA_BLOB.search(part):
            kind = "qa"
        elif url:
            kind = "sitemap"
        else:
            kind = "other"
        out.append({
            "kind": kind,
            "url": url.group(1) if url else None,
            "score": float(rel.group(1)) if rel else None,
            "raw": part,
        })
    return out


def load(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["_sources"] = parse_sources(r.get("Sources", ""))
        r["_verdict"] = (r.get("Verdict") or "").strip().lower()
        try:
            r["_score"] = float(r.get("Score") or 0)
        except ValueError:
            r["_score"] = 0.0
    return rows


def attribution(rows):
    print("\n" + "=" * 66)
    print("1. SOURCE ATTRIBUTION - what drove each answer")
    print("=" * 66)

    top_kind = Counter()
    no_sources = []
    qa_dominated = []

    for r in rows:
        srcs = r["_sources"]
        q = r.get("Question", "")[:58]
        if not srcs:
            no_sources.append(q)
            top_kind["none"] += 1
            continue
        top_kind[srcs[0]["kind"]] += 1
        qa_n = sum(1 for s in srcs if s["kind"] == "qa")
        if srcs and qa_n / len(srcs) >= 0.5:
            qa_dominated.append((q, qa_n, len(srcs), r["_verdict"]))

    total = len(rows)
    for kind in ("sitemap", "qa", "other", "none"):
        n = top_kind.get(kind, 0)
        if n:
            print(f"  top-ranked source is {kind:<8} {n:>3} / {total}"
                  f"  ({100*n//total}%)")

    if qa_dominated:
        print(f"\n  Q&A-dominated retrievals ({len(qa_dominated)}):")
        print("  These answers came mostly from curated pairs, not the corpus.")
        for q, n, tot, v in qa_dominated[:12]:
            print(f"    [{v:<4}] {n}/{tot} qa   {q}")

    if no_sources:
        print(f"\n  Empty Sources ({len(no_sources)}) - nothing cleared the")
        print("  relevance threshold, so the not-found message likely fired:")
        for q in no_sources[:8]:
            print(f"    {q}")


def recall(rows):
    """Retrieval metrics - only if the dataset carries expected_source."""
    labeled = [r for r in rows if (r.get("expected_source") or "").strip()]
    if not labeled:
        print("\n" + "=" * 66)
        print("2. RETRIEVAL RECALL - skipped")
        print("=" * 66)
        print("  Add an 'expected_source' column (a URL substring that SHOULD")
        print("  answer each question) to compute recall@k and MRR. Without it")
        print("  a retrieval miss is indistinguishable from a generation miss.")
        return

    print("\n" + "=" * 66)
    print("2. RETRIEVAL RECALL")
    print("=" * 66)
    hits, rr, misses = 0, [], []
    for r in labeled:
        want = r["expected_source"].strip()
        rank = None
        for i, s in enumerate(r["_sources"], 1):
            if s["url"] and want in s["url"]:
                rank = i
                break
        if rank:
            hits += 1
            rr.append(1.0 / rank)
        else:
            rr.append(0.0)
            misses.append((r.get("Question", "")[:56], want))

    n = len(labeled)
    print(f"  recall@k : {hits}/{n}  ({100*hits//n}%)")
    print(f"  MRR      : {sum(rr)/n:.3f}")
    if misses:
        print(f"\n  Retrieval misses - the expected page never surfaced:")
        for q, want in misses[:10]:
            print(f"    {q}\n        wanted: {want}")


def relevance(rows):
    print("\n" + "=" * 66)
    print("3. RELEVANCE DISTRIBUTION")
    print("=" * 66)
    tops = [r["_sources"][0]["score"] for r in rows
            if r["_sources"] and r["_sources"][0]["score"] is not None]
    if not tops:
        print("  no scores present")
        return
    print(f"  top-1 score   min {min(tops):.2f}   "
          f"median {statistics.median(tops):.2f}   max {max(tops):.2f}")
    if max(tops) > 1.0:
        print("  NOTE: scores exceed 1.0 - this is reranker output, not cosine")
        print("        similarity. Tune the threshold from observed values.")
    zeros = [r.get("Question", "")[:56] for r in rows
             if any(s["score"] == 0.0 for s in r["_sources"])]
    if zeros:
        print(f"\n  Chunks at relevance 0.00 ({len(zeros)}) - suggests an")
        print("  injection path that bypasses the minimum-relevance filter:")
        for q in zeros[:8]:
            print(f"    {q}")

    low = sorted((r["_sources"][0]["score"], r.get("Question", "")[:52])
                 for r in rows
                 if r["_sources"] and r["_sources"][0]["score"] is not None)[:5]
    print("\n  Weakest top-1 retrievals (most fragile answers):")
    for sc, q in low:
        print(f"    {sc:.2f}  {q}")


def regression(new_rows, base_rows):
    print("\n" + "=" * 66)
    print("4. REGRESSION DIFF vs BASELINE")
    print("=" * 66)
    base = {r.get("Question", "").strip().lower(): r for r in base_rows}
    broke, fixed, drift = [], [], []

    for r in new_rows:
        k = r.get("Question", "").strip().lower()
        b = base.get(k)
        if not b:
            continue
        if b["_verdict"] == "pass" and r["_verdict"] == "fail":
            broke.append((r.get("Question", "")[:56], b["_score"], r["_score"]))
        elif b["_verdict"] == "fail" and r["_verdict"] == "pass":
            fixed.append((r.get("Question", "")[:56], b["_score"], r["_score"]))
        elif abs(b["_score"] - r["_score"]) >= 0.2:
            drift.append((r.get("Question", "")[:56], b["_score"], r["_score"]))

    print(f"  compared {len(base)} baseline rows")
    if broke:
        print(f"\n  *** REGRESSIONS ({len(broke)}) - passed before, fail now ***")
        for q, a, b_ in broke:
            print(f"    {a:.2f} -> {b_:.2f}   {q}")
    else:
        print("\n  no Pass -> Fail regressions")
    if fixed:
        print(f"\n  fixed ({len(fixed)}):")
        for q, a, b_ in fixed:
            print(f"    {a:.2f} -> {b_:.2f}   {q}")
    if drift:
        print(f"\n  score drift >= 0.2 without a verdict flip ({len(drift)}):")
        for q, a, b_ in drift:
            print(f"    {a:.2f} -> {b_:.2f}   {q}")
    return len(broke)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--baseline", help="a previous run, to diff against")
    args = ap.parse_args()

    rows = load(args.results)
    passed = sum(1 for r in rows if r["_verdict"] == "pass")
    print(f"\n{args.results}: {len(rows)} questions, "
          f"{passed} pass ({100*passed//max(len(rows),1)}%)")

    attribution(rows)
    recall(rows)
    relevance(rows)

    broke = 0
    if args.baseline:
        broke = regression(rows, load(args.baseline))

    print("\n" + "=" * 66)
    return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
