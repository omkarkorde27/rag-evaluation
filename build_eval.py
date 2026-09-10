#!/usr/bin/env python3
"""
Generate the Chat AIU evaluation dataset for the IU Graduate School bot.

FORMAT (per the platform's upload instructions):
    header row: question, answer
    standard CSV quoting for values containing commas, newlines, or quotes.

The "answer" column must be a MODEL ANSWER - what a good reply actually says.
It is compared against the bot's reply by an LLM grader.

Do NOT write grader directives here ("FAIL if...", "should...", "PASS if..."),
and do not add extra columns. An earlier version of this file did both. The
grader then compared the bot's reply against instructions rather than against
content, which produced misleading verdicts.

AMBIGUOUS QUESTIONS: if a question is genuinely ambiguous, the model answer
must be the clarifying question, because that is the behaviour the system
prompt requires. Writing a definitive model answer for an ambiguous question
punishes the bot for following its instructions.

Usage:  python3 build_eval.py
Output: evaluation_dataset.csv
"""

import csv
import re

HEADER = ["question", "answer"]

FINDER = "https://www.iu.edu/academics/degrees/all-majors-degrees.html"

# (question, model answer, internal note - note is NOT written to the CSV)
ROWS = [
    # --- central content: must answer with substance ----------------------
    ("How much is the application fee?",
     "For most programs, the application fee is $70 for domestic and "
     "international students, paid by credit card. Applications are not "
     "reviewed until the fee is paid. Some programs differ, so confirm the "
     "amount with your specific program.",
     "fee-hedge"),

    ("What materials do I need to apply?",
     "Most departments require a personal statement, transcripts from all "
     "institutions you have attended, and letters of reference. Many also "
     "require GRE scores or another test. Each department sets its own "
     "specific requirements, so check with your program for the exact list.",
     "materials"),

    ("Where is the Graduate School office?",
     "The Bloomington office is in Wells Library, Room E546, 1320 E. 10th "
     "Street, Bloomington, IN 47405. Other IU campuses have their own "
     "graduate offices.",
     "campus-qualified"),

    ("How do I contact the Graduate School?",
     "For Bloomington, email grdschl@iu.edu or call 812-855-8853. "
     "International applicants can contact newtoiu@indiana.edu or "
     "812-855-9086. Other IU campuses have their own graduate offices.",
     "contacts"),

    ("What fellowships does the Graduate School offer?",
     "The Graduate School administers fellowships and awards including "
     "recruitment fellowships such as Graduate Fellows and Graduate Scholars, "
     "dissertation completion fellowships, and other internal awards, "
     "alongside a searchable index of external opportunities. For most of "
     "these, departments nominate students rather than students applying "
     "directly.",
     "fellowships-substance"),

    ("What is an Accelerated Master's Program?",
     "An Accelerated Master's Program lets students earn a bachelor's and a "
     "master's degree in less time, typically about five years, by taking "
     "approved master's-level courses while still an undergraduate. Students "
     "usually apply in their second or third year, and individual programs "
     "set the details.",
     "amp"),

    ("What support services are available to graduate students?",
     "The Graduate School and IU offer career coaching and professional "
     "development, the Graduate Mentoring Center and GradGrants Center, "
     "health and wellness services including counseling, accessibility and "
     "disability services, housing and family support, and help for "
     "international students.",
     "support"),

    ("Are there fellowships?",
     "Yes. The Graduate School offers internal fellowships and awards, "
     "recruitment fellowships, and a searchable index of external funding, "
     "plus the GradGrants Center which helps students find and apply for "
     "grants. For most internal fellowships the department or school "
     "nominates students rather than students applying directly. "
     "Assistantships and departmental funding packages are decided by "
     "individual departments.",
     "fellowships-substance"),

    ("What is the GradGrants Center?",
     "The GradGrants Center is a free service for IU graduate students that "
     "helps them find and apply for grants and fellowships, including "
     "one-on-one consultations, proposal review, and access to a grants "
     "database.",
     "gradgrants"),

    ("How many letters of recommendation do I need?",
     "Each department sets its own recommendation requirements, so check the "
     "graduate eApp and your specific program for how many letters are needed "
     "and from whom. The Graduate School does not set a university-wide "
     "number.",
     "letters"),

    # --- deadline confusion: the core risk --------------------------------
    ("What is the application deadline?",
     "The Graduate School does not set a single application deadline. "
     "Departments set their own application deadlines, so check your "
     f"prospective program's website. You can find your program here: {FINDER}",
     "deadline-core"),

    ("When are applications due for fall admission?",
     "Departments set their own application deadlines, so there is no single "
     "date for fall admission. Check your specific program's website for its "
     "deadline.",
     "deadline-core"),

    ("I'm applying for a PhD - when is the deadline?",
     "Admission deadlines are set by the individual department, not the "
     "Graduate School. Find your program and check its website or contact it "
     "directly for the deadline.",
     "deadline-core"),

    ("I heard the application deadline is December 1 - is that right?",
     "Departments set their own application deadlines, so there is no "
     "single university-wide date. Check your specific program's website to "
     "confirm the correct deadline for you.",
     "deadline-false-premise"),

    ("Is the application deadline the same as the fee deadline?",
     "They are different things. Departments set their own application "
     "deadlines, so check your program's website. Separately, an application "
     "is not reviewed until the application fee is paid.",
     "deadline-vs-fee"),

    ("When is the Master's Application for Advanced Degree due?",
     "The Master's Application for Advanced Degree is a graduation form, not "
     "an admissions application. It must be received by the Graduate School "
     "by the posted date for the month you intend to graduate, with specific "
     "dates for May, August, and December graduation listed on the Master's "
     "deadlines page.",
     "graduation-form"),

    ("When do I need to submit my thesis?",
     "Master's students submit the thesis to ProQuest by the deadline for the "
     "month they intend to graduate, and Ph.D. students submit the "
     "dissertation on the same basis, with specific dates for May, August, "
     "and December graduation on the Graduate School's deadlines pages.",
     "inverse-test"),

    # --- genuinely ambiguous: the clarifying question IS the right answer --
    ("What's the deadline?",
     "Could you clarify whether you are asking about applying for admission "
     "to a program, or about deadlines for graduating as a current student? "
     "The answer is different for each.",
     "ambiguous-clarify"),

    ("Can I still apply after the deadline?",
     "Could you clarify whether you mean applying for admission to a program, "
     "or applying to graduate as a current student? For admission, "
     "departments decide whether a late application can be considered, so "
     "you would need to contact the program directly.",
     "ambiguous-clarify"),

    # --- must refuse ------------------------------------------------------
    ("What GPA do I need for the Computer Science PhD?",
     "I don't have the minimum GPA for that program. Requirements such as "
     "GPA, test scores, and prerequisites are set by the department rather "
     "than the Graduate School, so contact the program directly.",
     "refuse-program-specific"),

    ("What's the acceptance rate for the History MA?",
     "I don't have acceptance rate figures for individual programs. That "
     "information would come from the department, so contact the program "
     "directly.",
     "refuse-program-specific"),

    ("Can you tell me if I'll get in?",
     "I can't predict admission decisions. Those are made by the individual "
     "graduate program, which reviews your full application. Contact the "
     "program directly to ask how your background compares to what they look "
     "for.",
     "refuse-chances"),

    ("I have a 320 GRE and 3.5 GPA, am I eligible for the program?",
     "I can't assess your eligibility. No single score or GPA guarantees "
     "admission, and requirements are set by the individual program. Contact "
     "the department directly to discuss your background.",
     "refuse-eligibility"),

    ("What is the status of my application?",
     "I can't look up individual application status. Your application is "
     "reviewed by the program you applied to, and that program will notify "
     "you of its decision. Contact the department directly for status or "
     "missing materials.",
     "refuse-status"),

    ("Will I get funding based on my scores?",
     "I can't predict funding decisions. For most Graduate School "
     "fellowships, departments nominate students, and each award has its own "
     "criteria. Assistantships and departmental funding are decided by the "
     "department, often alongside the admission decision.",
     "refuse-funding"),

    ("Can I get a GRE waiver?",
     "Test requirements and waivers are set by the individual department, not "
     "the Graduate School. Contact your program to ask whether it requires a "
     "test and whether it grants waivers.",
     "refuse-waiver"),

    ("Are Duolingo test scores accepted?",
     "I don't have that in the Graduate School's published content. Accepted "
     "English proficiency tests and minimum scores are set by the admitting "
     "department and by International Admissions. Confirm with your program "
     "and with International Admissions at newtoiu@indiana.edu or "
     "812-855-9086 before testing.",
     "not-in-corpus"),

    # --- multi-campus -----------------------------------------------------
    ("What graduate programs does IU Indianapolis offer?",
     "IU has nine campuses and programs differ at each. Use the IU degree "
     f"finder to filter programs by campus and program level: {FINDER}",
     "campus"),

    ("How do I apply to IU?",
     "IU graduate programs use a common online application, and you can apply "
     "to programs across IU campuses. Individual departments set their own "
     "deadlines and admission requirements, and admission decisions are made "
     "by the program. Find your program to check its specific requirements.",
     "campus-neutral"),

    ("Does IU have online graduate programs?",
     "Yes. IU offers online graduate programs across its campuses and through "
     "IU Online. Use the IU degree finder to filter by campus and learning "
     "format.",
     "campus-online"),

    # --- department-owned -------------------------------------------------
    ("How do I send my test scores to IU?",
     "Test scores and supporting documents generally go to the admitting "
     "program or to International Admissions rather than to the Graduate "
     "School office. International applicants should in most cases mail "
     "supporting documentation such as transcripts to the Office of "
     "International Admissions, Indiana University, Ferguson International "
     "Center, 330 N Eagleson Ave, Bloomington, IN 47405. Confirm the correct "
     "destination with your program before sending anything.",
     "send-scores"),

    ("Will my undergraduate courses count toward a graduate degree?",
     "Generally undergraduate coursework does not count toward a graduate "
     "degree, though Accelerated Master's Programs are a specific exception "
     "where approved master's-level courses can count toward both. Your "
     "department determines transfer credit, so contact the program directly.",
     "transfer-credit"),

    ("I want to take a different course or program",
     "Changing programs or transferring between schools is handled by the "
     "departments involved rather than centrally. If you have not applied "
     "yet, apply directly to the program you want. If you are already "
     "enrolled, speak with your academic advisor and the program you want to "
     "move into.",
     "change-program"),

    ("How long does a master's degree take?",
     "It varies by program. Most master's degrees take about two years of "
     "full-time study, but the length depends on the specific program, and "
     "Accelerated Master's Programs can be faster. Check your program's page "
     "for its expected length.",
     "duration"),

    # --- school contact routing (front-desk request, Aug 2026) -----------
    ("Who do I contact about the Kelley MBA?",
     "For the Full-Time or Flex MBA, contact Kelley MBA admissions at "
     "iumba@iu.edu or 812-855-8006. The Kelley Direct online MBA is a "
     "separate office at kdirect@iu.edu or 877-785-4713.",
     "school-routing"),

    ("I have a question about a music graduate program.",
     "Contact the Jacobs School of Music Graduate Office at musgrad@iu.edu "
     "or 812-855-1738 for graduate programs in music.",
     "school-routing"),

    ("Who handles admissions for the Luddy data science masters?",
     "For on-campus Luddy graduate programs including data science, contact "
     "GoLuddy@iu.edu or 812-856-3960. Luddy online graduate programs are "
     "handled separately at luddyonl@iu.edu or 812-856-5953.",
     "school-routing"),

    ("Who do I contact about the School of Education graduate programs?",
     "Contact the School of Education Office of Graduate Studies at "
     "educate@iu.edu or 812-856-8504.",
     "school-routing"),

    ("Who do I contact about the School of Optometry graduate program?",
     "I don't have a specific graduate contact for that school. For general "
     "graduate questions contact the IU Graduate School Bloomington at "
     "grdschl@iu.edu or 812-855-8853, and check the program's own website "
     "for its admissions contact.",
     "school-routing-fallback"),

    # --- out of scope -----------------------------------------------------
    ("What's the weather in Bloomington?",
     "I don't have that in the Graduate School's published content. I can "
     "help with graduate admissions, academic requirements, funding, and "
     "student support at IU.",
     "out-of-scope"),
]


def main():
    # Catch grader syntax, not ordinary prose. "should" appears naturally in
    # real answers ("applicants should mail..."), so only flag the directive
    # forms: FAIL/PASS as verdicts, and test-harness vocabulary.
    banned = re.compile(
        r"\b(FAIL|PASS)\b|\bFAIL if\b|\bPASS if\b|INVERSE TEST|BLOCKER"
        r"|\bthe (bot|answer|reply) (should|must)\b",
        re.IGNORECASE)
    seen = set()
    for q, a, note in ROWS:
        if banned.search(a):
            raise SystemExit(
                f"Grader directive leaked into the answer for {q!r}. "
                "The answer column must be a model answer, not an instruction.")
        k = q.strip().lower()
        if k in seen:
            raise SystemExit(f"Duplicate question: {q!r}")
        seen.add(k)

    with open("evaluation_dataset.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(HEADER)
        for q, a, note in ROWS:
            w.writerow([q, a])

    print(f"Wrote evaluation_dataset.csv: {len(ROWS)} questions")
    print(f"Columns: {', '.join(HEADER)}")
    print("Model answers only - no grader directives, no extra columns.")
    amb = [q for q, a, n in ROWS if n == "ambiguous-clarify"]
    print(f"\nAmbiguous questions where the clarifying question is correct: {len(amb)}")
    for q in amb:
        print(f"  - {q}")


if __name__ == "__main__":
    main()
