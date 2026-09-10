# Chat AIU config artifacts — IU Graduate School bot

Paste-ready inputs for the ChatAIU admin UI. Full reasoning lives in the plan:
`~/.claude/plans/i-have-been-tasked-fluffy-oasis.md`

**All actual configuration happens in the ChatAIU admin UI.** These files are
the content you paste in — nothing here talks to the platform.

## Files

| File | Goes where |
|---|---|
| `system_prompt.txt` | Chat Preferences → Model → chatbot instructions (**2500 char limit**) |
| `not_found_message.txt` | Chat Preferences → Model → information not found (**500 char limit**) |
| `qa_pairs.csv` | Sources → Q&A → Upload (46 pairs) |
| `evaluation_dataset.csv` | Project Setup → Evaluation → New Run (23 questions) |
| `check_limits.py` | Verifier — run after editing either .txt |
| `build_qa.py` / `build_eval.py` | Regenerate the CSVs |

## Before you upload

**Confirm the CSV headers match your tenant's templates.** Download the real
template from Sources → Q&A → Upload and from Project Setup → Evaluation.
If the columns differ, edit `HEADER` at the top of the matching build script
and re-run — do not hand-edit the CSVs, or the exact-match guarantee below
can drift.

```
python3 build_qa.py      # -> qa_pairs.csv
python3 build_eval.py    # -> evaluation_dataset.csv
python3 check_limits.py  # verify both text fields still fit
```

## Retrieval is the default — the CSV is the exception

The trained sitemaps answer most questions better than a hand-written pair
can: retrieval adapts to how the student phrased things, supports follow-ups,
and never goes stale relative to the page. **A Q&A pair is a maintenance cost
and a second copy of the truth.**

A pair earns its place only if it passes one of three tests:

| Test | Why retrieval fails | Example |
|---|---|---|
| **Harmful retrieval** | Corpus text will be retrieved and read wrongly, at real cost | Application deadlines |
| **Not in corpus** | Model would answer from general knowledge | Duolingo / TOEFL / IELTS |
| **Must refuse** | Model will try to be helpful when it should decline | Eligibility, app status |

Everything else — fellowships, GradGrants, fees, application materials,
program lists, transfer credit — is answered from the sitemap. The system
prompt's **"ANSWER, DO NOT JUST LINK"** rule is what keeps those substantive.

### The case that justifies the CSV

`deadlines/masters.html` trains to only ~1,333 characters, so the whole page
lands in a single retrieval chunk. That chunk contains "deadline" ×8,
"Application" ×2, "received in the Graduate School", and **"May 3, 2026"**.
A student asking "application deadline" produces near-perfect lexical overlap
with a **graduation** form. Retrieval cannot fix this — only exact match can.

### Why it's generated, not hand-written

Exact-match returns its answer **verbatim**, so 13 phrasings of "what is the
application deadline?" must map to byte-identical text. `build_qa.py`
guarantees that and fails loudly on duplicate questions or date leaks.

Current state: **43 pairs, 7 answers** (down from 105 — the cut removed
everything the sitemaps already answer).

## The one invariant that matters

**No deadline answer may contain a specific date.** `/academic-requirements/
deadlines/masters.html` contains "Master's Application for Advanced Degree
Edoc — May 3, 2026" — a *graduation* form whose name makes it a lexical
landmine for admissions queries. Serving that date to an applicant could cost
them an application cycle.

Verified mechanically after every regeneration:

```
python3 - <<'EOF'
import csv, re
rows = list(csv.reader(open("qa_pairs.csv")))[1:]
bad = [q for q,a in rows if re.search(r"\b(20\d\d|January|February|March|April|May|June|July|August|September|October|November|December)\b", a) and "degree-completion" not in a]
print("date leaks:", len(bad))   # must be 0
EOF
```

## Evaluation dataset format

The platform requires exactly:

```
header row: question, answer
```

Two columns. **The `answer` column is a model answer** — what a good reply
actually says — because an LLM grader compares it against the bot's reply.

Do **not** put grader directives ("FAIL if…", "should…") or extra columns in
it. An earlier version of this file did both, and the grader ended up
comparing the bot's reply against instructions rather than content, producing
misleading verdicts. `build_eval.py` now refuses to build if directive syntax
appears in an answer.

### Ambiguous questions

If a question is genuinely ambiguous, the model answer must be **the
clarifying question**, because that is what the system prompt tells the bot
to do. Two rows are like this:

- "What's the deadline?"
- "Can I still apply after the deadline?"

Both mean either *apply for admission* or *apply to graduate*. Writing a
definitive model answer for these punishes the bot for behaving correctly —
that is exactly what happened on the 2026-08-06 run.

## The most important finding: adding Q&A pairs CAUSES failures

Two evaluation runs on 2026-08-06:

| Run | Pairs | Result |
|---|---|---|
| 1 | 43 | 3 failures, 2 real |
| 2 | 50 (added pairs to fix run 1) | **4 failures, 3 of them NEW regressions** |

Three questions that **passed in run 1 failed in run 2** after pairs were added:

- Is the application deadline the same as the fee deadline? → Pass → Fail
- When is the Master's Application for Advanced Degree due? → Pass → Fail
- I want to take a different course or program → Pass → Fail

**Why.** The uploaded pairs are indexed and retrieved as *documents*, not as
a separate exact-match lookup. In run 2 they appear in the Sources column as
`content.md (/download?index=…)` blobs that **outranked the real pages**. One
row even leaked model metadata (`Context length: 256K; Quantization: None…`)
into the answer, and one returned an empty Sources list entirely.

So a pair is not a free, isolated guarantee — it is another competing
document in the index. Past a small number they crowd out the sitemap.

**Consequence: the set is capped at 15 and `build_qa.py` fails the build if
you exceed it.** Current size: **10 pairs, 2 answers.**

### When an eval row fails, fix it in this order

1. **System prompt** — behavioural rules generalize to phrasings you have
   never seen. This is where the run-2 fixes went ("answer the general case
   first", process steps, no metadata echo).
2. **Source config** — exclusions and extraction selectors.
3. **The evaluation row itself** — it may be a bad test. Row 29 in run 1 was:
   the bot correctly asked a clarifying question and the expected answer
   wrongly assumed admission.
4. **Only then a Q&A pair** — and only if it passes one of the two retention
   tests above.

## Still open (from the plan)

1. Which site(s) get the embed script
2. Live application portal URL (Link prompt #9)
3. Transcripts — privacy/records sign-off
4. `grdschl@indiana.edu` vs `grdschl@iu.edu` — the two sites disagree
5. Retitle the deadlines pages to "Degree Completion Deadlines" (highest-leverage fix)
6. Two 404s: `graduate.iu.edu/contact.html` (in sitemap), `apply/fee-waiver.html`
