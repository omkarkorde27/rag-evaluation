#!/usr/bin/env python3
"""
Verify the character-limited Chat AIU fields still fit before you paste them.

Chat AIU limits:
  chatbot instructions (system prompt) : 2500
  "information not found" message      : 500

Run this after ANY edit to system_prompt.txt or not_found_message.txt.
The margins are deliberately thin, so eyeballing is not safe.

Also warns about characters that commonly break in admin textareas:
smart quotes, em/en dashes, and other non-ASCII that may re-encode on paste
and silently change the count.

Usage:  python3 check_limits.py
Exit:   0 = all fit, 1 = something is over the limit
"""

import sys
import unicodedata

CHECKS = [
    ("system_prompt.txt", 2500, "Chat Preferences > Model > chatbot instructions"),
    ("not_found_message.txt", 500, "Chat Preferences > Model > information not found"),
]


def describe(ch):
    try:
        return unicodedata.name(ch)
    except ValueError:
        return f"U+{ord(ch):04X}"


def main():
    failed = False
    for path, limit, where in CHECKS:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            print(f"MISSING  {path}")
            failed = True
            continue

        # Trailing newline from the editor is not part of the pasted value.
        text = text.rstrip("\n")
        n = len(text)
        left = limit - n
        status = "OK " if n <= limit else "OVER"
        if n > limit:
            failed = True

        print(f"[{status}] {path}: {n} / {limit} chars ({left:+d})")
        print(f"        field: {where}")

        if 0 <= left <= 50:
            print(f"        NOTE: only {left} chars of headroom - re-run after any edit.")

        non_ascii = {c for c in text if ord(c) > 127}
        if non_ascii:
            listed = ", ".join(f"{c!r} ({describe(c)})" for c in sorted(non_ascii))
            print(f"        WARNING: non-ASCII present: {listed}")
            print("        These can re-encode on paste and change the count.")
        print()

    if failed:
        print("FAIL: fix the files above before pasting into Chat AIU.")
        return 1
    print("PASS: both fields fit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
