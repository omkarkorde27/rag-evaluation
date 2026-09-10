#!/usr/bin/env python3
"""
Generate the Chat AIU Q&A knowledge-source CSV for the IU Graduate School bot.

=====================================================================
KEEP THIS SET SMALL. DO NOT ADD A PAIR FOR EVERY FAILED EVAL ROW.
=====================================================================

What the 2026-08-06 evaluation runs proved:

Run 1 (43 pairs) -> 3 failures, 2 of them real.
Run 2 (50 pairs, added pairs for those 2) -> 4 failures, 3 of which were
NEW REGRESSIONS on questions that had PASSED in run 1:

    Is the application deadline the same as the fee deadline?  Pass -> Fail
    When is the Master's Application for Advanced Degree due?  Pass -> Fail
    I want to take a different course or program               Pass -> Fail

Why: the uploaded Q&A pairs are indexed and retrieved as DOCUMENTS. In run 2
they appear in the Sources column as "content.md (/download?index=...)" blobs
that outranked the real pages. One row even leaked model metadata
("Context length: 256K; Quantization: None...") into the answer.

So each pair is not a free, isolated guarantee. It is another competing
document in the index. Past a small number they crowd out the sitemap, and
adding pairs to fix failures CAUSES failures. Growth is self-defeating.

THE RULE: a pair must fix something that neither retrieval nor the system
prompt can fix. In practice that is only:

  1. HARMFUL RETRIEVAL - the corpus contains text that will be retrieved and
     read the wrong way, with real cost. Only the admissions-deadline case
     qualifies: deadlines/masters.html trains to ~1,300 chars, so the whole
     page lands in one chunk containing "deadline" x8, "Application" x2 and
     "May 3, 2026". A student asking "application deadline" gets near-perfect
     lexical overlap with a GRADUATION form.

  2. NOT IN THE CORPUS - the bot would answer from general knowledge. Only
     English proficiency qualifies: there is no TOEFL/IELTS/Duolingo content
     on either site, so an invented score threshold could cost a student a
     test fee.

Everything else - fellowships, GradGrants, fees, materials, eligibility,
application status, funding predictions, program changes, transfer credit -
retrieval plus the system prompt already handle. Run 2 confirmed this: all of
those rows passed WITHOUT needing their own pair, or passed better before one
was added.

When an eval row fails, fix it in this order:
  1. the system prompt (behaviour), 2. the source config (retrieval),
  3. the evaluation row itself (bad test), 4. and only then a pair.

Usage:  python3 build_qa.py
Output: qa_pairs.csv
"""

import csv
import re

HEADER = ["Question", "Answer"]

FINDER = "https://www.iu.edu/academics/degrees/all-majors-degrees.html"

PAIRS = []


def add(reason, answer, questions):
    for q in questions:
        PAIRS.append((q, answer, reason))


# =========================================================================
# 1. HARMFUL RETRIEVAL - admissions deadline vs graduation deadline
#
# This is the reason the CSV exists at all. Keep the variant list tight:
# every extra variant is another competing document in the index.
# =========================================================================

A_DEADLINE = (
    "The Graduate School does not set a single application deadline. "
    "Departments set their own application deadlines, so check your "
    "prospective program's website to determine when to apply.\n\n"
    "Deadlines vary widely by program, and many doctoral programs close much "
    "earlier than master's programs.\n\n"
    f"Find your program, filtering by campus and program level: {FINDER}\n\n"
    "Please note: the \"Deadlines\" pages on the Graduate School site list "
    "degree-completion deadlines for students who are already enrolled, such "
    "as thesis submission and defense paperwork. Those are not admissions "
    "deadlines."
)

add("harmful-retrieval", A_DEADLINE, [
    "What is the application deadline?",
    "When are applications due?",
    "What is the deadline for fall admission?",
    "What is the deadline for spring admission?",
    "When should I apply?",
    "Is it too late to apply?",
])

# =========================================================================
# 2. NOT IN THE CORPUS - English proficiency tests
#
# No TOEFL / IELTS / Duolingo content exists on either site. Without this the
# model may state a score threshold from general knowledge.
# =========================================================================

A_ENGLISH = (
    "English proficiency requirements, including which tests are accepted "
    "and the minimum scores, are set by the admitting department and by "
    "International Admissions rather than published centrally by the "
    "Graduate School. That includes whether Duolingo, TOEFL, or IELTS is "
    "accepted for your program.\n\n"
    "Please confirm with your program and with International Admissions "
    "before testing, so you do not pay for a test that will not be "
    "accepted.\n\n"
    "International applicants: newtoiu@indiana.edu or 812-855-9086.\n"
    f"Find your program: {FINDER}"
)

add("not-in-corpus", A_ENGLISH, [
    "What English proficiency scores do I need?",
    "Are Duolingo test scores accepted?",
    "What TOEFL score do I need?",
    "What IELTS score do I need?",
])


MAX_PAIRS = 15  # hard ceiling: past this, pairs start crowding out the sitemap


def main():
    seen = set()
    for q, a, reason in PAIRS:
        k = q.strip().lower()
        if k in seen:
            raise SystemExit(f"Duplicate question variant: {q!r}")
        seen.add(k)

    if len(PAIRS) > MAX_PAIRS:
        raise SystemExit(
            f"{len(PAIRS)} pairs exceeds the ceiling of {MAX_PAIRS}.\n"
            "Run 2 showed that growing this set causes regressions: the pairs "
            "are indexed as documents and outrank the real pages.\n"
            "Fix the failure in the system prompt, the source config, or the "
            "evaluation row instead - see the module docstring.")

    month = (r"\b(20\d\d|January|February|March|April|May|June|July|August|"
             r"September|October|November|December)\b")
    for q, a, reason in PAIRS:
        if re.search(month, a) and "degree-completion" not in a:
            raise SystemExit(f"Date leak in answer for {q!r}")

    with open("qa_pairs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HEADER)
        for q, a, reason in PAIRS:
            w.writerow([q, a])

    reasons = {}
    for _, _, r in PAIRS:
        reasons[r] = reasons.get(r, 0) + 1

    print(f"Wrote qa_pairs.csv: {len(PAIRS)} pairs "
          f"(ceiling {MAX_PAIRS}), {len({a for _,a,_ in PAIRS})} answers")
    for r, n in reasons.items():
        print(f"  {r:<18} {n}")
    print("\nEverything else is answered by retrieval + the system prompt.")


if __name__ == "__main__":
    main()
