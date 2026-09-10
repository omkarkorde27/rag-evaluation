#!/usr/bin/env python3
"""
Visual dashboard for ChatAIU evaluation runs.

Reads every results CSV in a directory, computes trend/regression/constraint
metrics, and writes a self-contained HTML report (inline SVG, no CDN, works
offline and in both light and dark themes).

    python3 eval_dashboard.py "Evaluation Sets results" -o dashboard.html
    python3 eval_dashboard.py "Evaluation Sets results" --real real_questions.json

Expected results columns (ChatAIU export):
    Question, ExpectedAnswer, ActualAnswer, Verdict, Score, Rationale, Sources
"""

import argparse, csv, glob, html, json, os, re, statistics, sys
from collections import Counter, OrderedDict

# ---------------------------------------------------------------- constants
MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
ADMISSION_RX = re.compile(r"\b(apply|application|admission|applicant)\b", re.I)
GRADUATION_RX = re.compile(r"\b(thesis|dissertation|graduat|advanced degree|commencement)\b", re.I)
DATE_RX = re.compile(rf"\b(20\d\d|{MONTHS}\s+\d{{1,2}})\b", re.I)
METADATA_RX = re.compile(r"context length|quantization|supported modalities|thinking levels", re.I)
URL_RX = re.compile(r"https?://\S+")
STALE_RX = re.compile(r"grdschl@indiana\.edu", re.I)
QA_BLOB = re.compile(r"content\.md\s*\(/download\?index=", re.I)
REL = re.compile(r"\[rel\s+([0-9.]+)\]", re.I)
SRC_URL = re.compile(r"\((https?://[^)]+)\)")
SPLIT = re.compile(r"\]\s*;\s*")

# ------------------------------------------------------------------ parsing
def parse_sources(cell):
    if not cell or not cell.strip():
        return []
    cell = html.unescape(cell)
    parts = SPLIT.split(cell)
    parts = [p if p.rstrip().endswith("]") else p + "]" for p in parts]
    out = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        rel, url = REL.search(part), SRC_URL.search(part)
        kind = "qa" if QA_BLOB.search(part) else ("sitemap" if url else "other")
        out.append({"kind": kind, "url": url.group(1) if url else None,
                    "score": float(rel.group(1)) if rel else None})
    return out

def violations(question, answer):
    """Reference-blind hard constraints. Mirrors grade_results.py."""
    out = []
    if METADATA_RX.search(answer):
        out.append("leaked metadata")
    if ADMISSION_RX.search(question) and not GRADUATION_RX.search(question):
        hit = DATE_RX.search(answer)
        if hit and not GRADUATION_RX.search(answer):
            out.append("date in admissions answer")
    prose = URL_RX.sub("", answer).strip()
    if len(prose) < 120 and URL_RX.search(answer):
        out.append("bare link")
    if STALE_RX.search(answer):
        out.append("stale email")
    return out

def load_run(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["_q"] = (r.get("Question") or "").strip()
        r["_a"] = r.get("ActualAnswer") or ""
        r["_v"] = (r.get("Verdict") or "").strip().lower()
        try:
            r["_s"] = float(r.get("Score") or 0)
        except ValueError:
            r["_s"] = 0.0
        r["_src"] = parse_sources(r.get("Sources", ""))
        r["_viol"] = violations(r["_q"], r["_a"])
    return rows

# -------------------------------------------------------------------- charts
PAL = {"good": "#0ca30c", "critical": "#d03b3b",
       "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a"}

def bar_chart(items, width=560, row_h=30, maxval=None, fmt=lambda v: str(v)):
    """items: [(label, value, color)]. Horizontal bars w/ direct labels."""
    if not items:
        return '<p class="muted">No data.</p>'
    maxval = maxval or max((v for _, v, _ in items), default=1) or 1
    lab_w, pad, bar_w = 190, 8, width - 190 - 70
    h = row_h * len(items) + 8
    svg = [f'<svg viewBox="0 0 {width} {h}" width="100%" height="{h}" role="img">']
    for i, (label, val, color) in enumerate(items):
        y = i * row_h + 4
        bw = max(2, int(bar_w * (val / maxval))) if maxval else 2
        svg.append(
            f'<text x="{lab_w-pad}" y="{y+15}" text-anchor="end" '
            f'font-size="12" fill="var(--text-secondary)">{html.escape(str(label))[:34]}</text>')
        svg.append(f'<rect x="{lab_w}" y="{y+3}" width="{bw}" height="16" rx="4" fill="{color}"><title>{html.escape(str(label))}: {fmt(val)}</title></rect>')
        svg.append(f'<text x="{lab_w+bw+8}" y="{y+15}" font-size="12" '
                   f'fill="var(--text-primary)">{fmt(val)}</text>')
    svg.append('</svg>')
    return "".join(svg)

def trend_chart(labels, values, width=560, height=190):
    """Single-series pass-rate trend. One series -> no legend, title names it."""
    if len(values) < 2:
        return '<p class="muted">Need 2+ runs to show a trend.</p>'
    ml, mr, mt, mb = 44, 16, 14, 40
    pw, ph = width - ml - mr, height - mt - mb
    n = len(values)
    xs = [ml + (pw * i / (n - 1)) for i in range(n)]
    ys = [mt + ph - (ph * (v / 100.0)) for v in values]
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">']
    for gv in (0, 25, 50, 75, 100):
        gy = mt + ph - (ph * gv / 100.0)
        svg.append(f'<line x1="{ml}" y1="{gy:.1f}" x2="{width-mr}" y2="{gy:.1f}" '
                   f'stroke="var(--grid)" stroke-width="1"/>')
        svg.append(f'<text x="{ml-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" '
                   f'fill="var(--text-muted)">{gv}%</text>')
    d = " ".join(f'{"M" if i==0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(zip(xs, ys)))
    svg.append(f'<path d="{d}" fill="none" stroke="{PAL["s1"]}" stroke-width="2" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')
    for x, y, v, lb in zip(xs, ys, values, labels):
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{PAL["s1"]}" '
                   f'stroke="var(--surface-1)" stroke-width="2"><title>{html.escape(lb)}: {v:.0f}%</title></circle>')
        svg.append(f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11" '
                   f'fill="var(--text-primary)">{v:.0f}%</text>')
        svg.append(f'<text x="{x:.1f}" y="{height-14}" text-anchor="middle" font-size="10" '
                   f'fill="var(--text-muted)">{html.escape(lb)[:14]}</text>')
    svg.append('</svg>')
    return "".join(svg)

# --------------------------------------------------------------------- html
CSS = """
:root{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#f4f3f0;--border:#dedcd6;
--grid:#e7e5df;--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#7a7873;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--surface-1:#1a1a19;--surface-2:#232322;--border:#38383a;--grid:#2e2e2d;
--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#8f8e86;}}
:root[data-theme="dark"]{--surface-1:#1a1a19;--surface-2:#232322;--border:#38383a;
--grid:#2e2e2d;--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#8f8e86;}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-1);color:var(--text-primary);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:28px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:0 0 12px;font-weight:600}
.sub{color:var(--text-secondary);margin:0 0 24px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.card{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.tile{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:14px}
.tile .n{font-size:26px;font-weight:650;letter-spacing:-.02em}
.tile .l{font-size:12px;color:var(--text-secondary);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--text-secondary);font-weight:600;font-size:12px}
.muted{color:var(--text-muted);font-size:13px}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;font-weight:600}
.scroll{overflow-x:auto}
code{background:var(--surface-1);padding:1px 4px;border-radius:3px;font-size:12px}
"""

def tile(n, label, color=None):
    c = f' style="color:{color}"' if color else ""
    return f'<div class="tile"><div class="n"{c}>{n}</div><div class="l">{html.escape(label)}</div></div>'

def build(runs, real_qs, out):
    names = list(runs.keys())
    latest = names[-1]
    lrows = runs[latest]

    pass_rates, labels = [], []
    for n in names:
        rs = runs[n]
        p = sum(1 for r in rs if r["_v"] == "pass")
        pass_rates.append(100.0 * p / max(len(rs), 1))
        labels.append(n)

    npass = sum(1 for r in lrows if r["_v"] == "pass")
    viol_rows = [r for r in lrows if r["_viol"]]
    viol_passed = sum(1 for r in viol_rows if r["_v"] == "pass")

    # regressions vs previous run
    regressions = []
    if len(names) >= 2:
        prev = {r["_q"].lower(): r for r in runs[names[-2]]}
        for r in lrows:
            p = prev.get(r["_q"].lower())
            if p and p["_v"] == "pass" and r["_v"] == "fail":
                regressions.append((r["_q"], p["_s"], r["_s"]))

    vc = Counter(v for r in lrows for v in r["_viol"])
    kinds = Counter()
    for r in lrows:
        kinds[r["_src"][0]["kind"] if r["_src"] else "none"] += 1

    scores = [s["score"] for r in lrows for s in r["_src"] if s["score"] is not None]

    # real-user coverage
    cov_html = ""
    if real_qs:
        evalqs = {r["_q"].lower() for rs in runs.values() for r in rs}
        covered = [q for q in real_qs if q.lower() in evalqs]
        missing = [q for q in real_qs if q.lower() not in evalqs]
        cov_html = f"""
        <div class="card"><h2>Real-user coverage</h2>
        <p class="muted">{len(covered)} of {len(real_qs)} real questions appear in the eval set.
        The rest are untested behaviour in production.</p>
        <div class="scroll"><table><tr><th>Untested real question</th></tr>
        {"".join(f"<tr><td>{html.escape(q)}</td></tr>" for q in missing[:20])}
        </table></div></div>"""

    reg_html = ("".join(
        f'<tr><td>{html.escape(q)[:70]}</td><td>{a:.2f} &rarr; {b:.2f}</td></tr>'
        for q, a, b in regressions)
        if regressions else '<tr><td colspan="2" class="muted">None &mdash; no Pass&rarr;Fail since previous run.</td></tr>')

    viol_html = ("".join(
        f'<tr><td>{html.escape(r["_q"])[:58]}</td>'
        f'<td><span class="pill" style="background:{PAL["good"] if r["_v"]=="pass" else PAL["critical"]};color:#fff">{r["_v"] or "?"}</span></td>'
        f'<td>{html.escape(", ".join(r["_viol"]))}</td></tr>'
        for r in viol_rows)
        if viol_rows else '<tr><td colspan="3" class="muted">None &mdash; all hard constraints clean.</td></tr>')

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChatAIU Eval Dashboard</title><style>{CSS}</style></head><body><div class="wrap">
<h1>ChatAIU evaluation dashboard</h1>
<p class="sub">Latest run: <code>{html.escape(latest)}</code> &middot; {len(names)} run(s) compared</p>

<div class="tiles">
  {tile(f"{100*npass//max(len(lrows),1)}%", "pass rate (model grader)")}
  {tile(len(lrows), "questions in run")}
  {tile(len(regressions), "regressions vs prev run", PAL["critical"] if regressions else None)}
  {tile(len(viol_rows), "hard-constraint violations", PAL["critical"] if viol_rows else None)}
  {tile(viol_passed, "of those the model PASSED", PAL["critical"] if viol_passed else None)}
</div>

<div class="grid">
  <div class="card"><h2>Pass rate across runs</h2>{trend_chart(labels, pass_rates)}</div>
  <div class="card"><h2>Verdicts in latest run</h2>
    {bar_chart([("Pass", npass, PAL["good"]), ("Fail", len(lrows)-npass, PAL["critical"])])}</div>
  <div class="card"><h2>Hard-constraint violations by type</h2>
    {bar_chart([(k, v, PAL["critical"]) for k, v in vc.most_common()] or [("none", 0, PAL["good"])])}
    <p class="muted">Reference-blind checks &mdash; unaffected by ground-truth quality.</p></div>
  <div class="card"><h2>Top-ranked source type</h2>
    {bar_chart([(k, v, {"sitemap":PAL["s1"],"qa":PAL["s2"],"none":PAL["s3"],"other":PAL["s3"]}.get(k,PAL["s3"])) for k, v in kinds.most_common()])}
    <p class="muted">High <code>qa</code> share means curated pairs are outranking the corpus.
    <code>none</code> means nothing was retrieved.</p></div>
</div>

<div class="grid" style="margin-top:16px">
  <div class="card"><h2>Regressions (Pass &rarr; Fail)</h2>
    <div class="scroll"><table><tr><th>Question</th><th>Score</th></tr>{reg_html}</table></div></div>
  <div class="card"><h2>Hard-constraint violations</h2>
    <div class="scroll"><table><tr><th>Question</th><th>Model</th><th>Violation</th></tr>{viol_html}</table></div></div>
  {cov_html}
</div>

<p class="sub" style="margin-top:22px">Relevance scores in latest run:
{"min %.2f / median %.2f / max %.2f" % (min(scores), statistics.median(scores), max(scores)) if scores else "none reported"}.
</p></div></body></html>"""

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return {"runs": len(names), "latest": latest, "rows": len(lrows),
            "pass": npass, "regressions": len(regressions),
            "violations": len(viol_rows), "viol_passed": viol_passed}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("-o", "--out", default="dashboard.html")
    ap.add_argument("--real", help="JSON list of real user questions")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.results_dir, "*.csv")))
    if not files:
        sys.exit(f"No CSVs in {a.results_dir}")
    runs = OrderedDict((os.path.basename(f).replace("_results", "").replace(".csv", ""),
                        load_run(f)) for f in files)

    real = []
    if a.real and os.path.exists(a.real):
        raw = json.load(open(a.real))
        real = [x["q"] if isinstance(x, dict) else x for x in raw]

    s = build(runs, real, a.out)
    print(f"Wrote {a.out}")
    print(f"  runs compared      : {s['runs']}")
    print(f"  latest             : {s['latest']} ({s['rows']} questions, {s['pass']} pass)")
    print(f"  regressions        : {s['regressions']}")
    print(f"  hard violations    : {s['violations']}  (model passed {s['viol_passed']})")

if __name__ == "__main__":
    main()
