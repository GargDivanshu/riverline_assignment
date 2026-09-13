"""Deterministic extraction of rupee amounts spoken in plain English.

Exists for exactly one purpose: a pre-mutation sanity check on financial
amounts (see app.finance.amount_matches_utterance). A live call had the person
say "eighteen thousand rupees" and the model's own tool call persisted 10000 —
the transcription was correct, something went wrong purely in the model's own
number-to-JSON step, and nothing caught it. This is not a general NLP parser
(it does not need to be, and should not try to be): it only needs to reliably
read back explicit digit amounts and common Indian-English spoken numbers well
enough to catch an obvious, unrelated mismatch.
"""

from __future__ import annotations

import re

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
           "crore": 10_000_000, "crores": 10_000_000}
_NUMBER_WORDS = set(_ONES) | set(_TENS) | set(_SCALES) | {"and"}


def _words_to_number(tokens: list[str]) -> int | None:
    total = 0
    current = 0
    found = False
    for token in tokens:
        if token == "and":
            continue
        if token in _ONES:
            current += _ONES[token]
            found = True
        elif token in _TENS:
            current += _TENS[token]
            found = True
        elif token == "hundred":
            current = (current or 1) * 100
            found = True
        elif token in _SCALES:
            total += (current or 1) * _SCALES[token]
            current = 0
            found = True
    total += current
    return total if found else None


def extract_rupee_amounts(text: str) -> list[int]:
    """Every clear rupee amount mentioned in `text`, as plain integers.

    Deliberately conservative: a phrase it cannot confidently read (a range
    like "sixty to seventy thousand", vague amounts, anything it doesn't
    recognize) simply contributes nothing rather than a guess — the caller
    treats an empty result as "no evidence either way", not as a mismatch.
    """
    if not text:
        return []
    amounts: list[int] = []

    for match in re.finditer(r"\d[\d,]*", text):
        cleaned = match.group().replace(",", "")
        if cleaned.isdigit():
            amounts.append(int(cleaned))

    words = re.findall(r"[a-zA-Z]+", text.lower())
    run: list[str] = []
    for word in words:
        if word in _NUMBER_WORDS:
            run.append(word)
            continue
        if run:
            value = _words_to_number(run)
            if value:
                amounts.append(value)
            run = []
    if run:
        value = _words_to_number(run)
        if value:
            amounts.append(value)

    return amounts
