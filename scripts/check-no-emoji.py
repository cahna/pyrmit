#!/usr/bin/env python3
"""No-emoji checker.

Scans the given files for emoji characters (UTS #51) and exits non-zero on any
match. Permitted Unicode (box-drawing, math operators, normal text characters)
is allowed.

Usage:
    python scripts/check-no-emoji.py PATH [PATH ...]

Output (stderr, on violation):
    <path>:<line>:<col>: U+<hex> <name>
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

# UTS #51 emoji ranges. These are the Unicode blocks containing characters
# carrying the Emoji_Presentation or Extended_Pictographic properties that
# default to or commonly render as emoji. Box-drawing (U+2500-U+257F),
# math operators (U+2200-U+22FF), and arrows (U+2190-U+21FF) are
# deliberately NOT included.
EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x231A, 0x231B),  # WATCH, HOURGLASS
    (0x23E9, 0x23EC),  # BLACK RIGHT-POINTING DOUBLE TRIANGLE etc.
    (0x23F0, 0x23F0),  # ALARM CLOCK
    (0x23F3, 0x23F3),  # HOURGLASS WITH FLOWING SAND
    (0x25FD, 0x25FE),  # SQUARES (presentation emoji)
    (0x2614, 0x2615),  # UMBRELLA WITH RAIN DROPS, HOT BEVERAGE
    (0x2648, 0x2653),  # ZODIAC SIGNS
    (0x267F, 0x267F),  # WHEELCHAIR SYMBOL
    (0x2693, 0x2693),  # ANCHOR
    (0x26A1, 0x26A1),  # HIGH VOLTAGE SIGN
    (0x26AA, 0x26AB),  # MEDIUM WHITE/BLACK CIRCLE
    (0x26BD, 0x26BE),  # SOCCER BALL, BASEBALL
    (0x26C4, 0x26C5),  # SNOWMAN, SUN BEHIND CLOUD
    (0x26CE, 0x26CE),  # OPHIUCHUS
    (0x26D4, 0x26D4),  # NO ENTRY
    (0x26EA, 0x26EA),  # CHURCH
    (0x26F2, 0x26F3),  # FOUNTAIN, FLAG IN HOLE
    (0x26F5, 0x26F5),  # SAILBOAT
    (0x26FA, 0x26FA),  # TENT
    (0x26FD, 0x26FD),  # FUEL PUMP
    (0x2705, 0x2705),  # WHITE HEAVY CHECK MARK (the canonical OK emoji)
    (0x270A, 0x270B),  # RAISED FIST, RAISED HAND
    (0x2728, 0x2728),  # SPARKLES
    (0x274C, 0x274C),  # CROSS MARK
    (0x274E, 0x274E),  # NEGATIVE SQUARED CROSS MARK
    (0x2753, 0x2755),  # QUESTION MARKS, WHITE EXCLAMATION
    (0x2757, 0x2757),  # HEAVY EXCLAMATION
    (0x2795, 0x2797),  # HEAVY PLUS / MINUS / DIVISION
    (0x27B0, 0x27B0),  # CURLY LOOP
    (0x27BF, 0x27BF),  # DOUBLE CURLY LOOP
    # The "presentation by default" set above is a curated subset. The full
    # ranges below catch the rest of the pictographic blocks.
    (0x2300, 0x23FF),  # Miscellaneous Technical (gear U+2699, etc.)
    (0x2600, 0x26FF),  # Miscellaneous Symbols (warning sign U+26A0, etc.)
    (0x2700, 0x27BF),  # Dingbats (heavy check U+2713, etc.)
    (0x1F000, 0x1F02F),  # Mahjong Tiles
    (0x1F0A0, 0x1F0FF),  # Playing Cards
    (0x1F100, 0x1F1FF),  # Enclosed Alphanumeric Supplement + Regional Indicators
    (0x1F200, 0x1F2FF),  # Enclosed Ideographic Supplement
    (0x1F300, 0x1F5FF),  # Miscellaneous Symbols and Pictographs
    (0x1F600, 0x1F64F),  # Emoticons
    (0x1F650, 0x1F67F),  # Ornamental Dingbats
    (0x1F680, 0x1F6FF),  # Transport and Map Symbols
    (0x1F700, 0x1F77F),  # Alchemical Symbols
    (0x1F780, 0x1F7FF),  # Geometric Shapes Extended
    (0x1F800, 0x1F8FF),  # Supplemental Arrows-C
    (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
    (0x1FA00, 0x1FA6F),  # Chess Symbols
    (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
)

# Codepoints inside the broad blocks above that are explicitly permitted
# because they are useful non-emoji symbols.
ALLOWED_CODEPOINTS: frozenset[int] = frozenset({
    # Box-drawing characters are in U+2500-U+257F (not in EMOJI_RANGES)
    # and are permitted. This set covers any exceptions inside the emoji
    # ranges that we want to whitelist.
    # (None currently; placeholder for future carve-outs.)
})

# Codepoints that are emoji modifiers / joiners. Their presence anywhere is
# also a violation since they only have meaning attached to a base emoji.
EMOJI_MODIFIER_CODEPOINTS: frozenset[int] = frozenset({
    0x200D,  # ZERO WIDTH JOINER
    0xFE0E,  # VARIATION SELECTOR-15 (text presentation)
    0xFE0F,  # VARIATION SELECTOR-16 (emoji presentation)
})


def is_emoji(codepoint: int) -> bool:
    """Return True if `codepoint` is forbidden under the No-Emoji rule."""
    if codepoint in ALLOWED_CODEPOINTS:
        return False
    if codepoint in EMOJI_MODIFIER_CODEPOINTS:
        return True
    for start, end in EMOJI_RANGES:
        if start <= codepoint <= end:
            return True
    return False


def codepoint_name(codepoint: int) -> str:
    """Return the Unicode name of `codepoint`, or '<unnamed>'."""
    try:
        return unicodedata.name(chr(codepoint))
    except ValueError:
        return "<unnamed>"


def scan_file(path: Path) -> list[tuple[int, int, int]]:
    """Scan `path` and return a list of (line, column, codepoint) violations.

    Lines and columns are 1-indexed. Binary files (those that fail to decode
    as UTF-8) are skipped silently.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    violations: list[tuple[int, int, int]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for colno, ch in enumerate(line, start=1):
            cp = ord(ch)
            if is_emoji(cp):
                violations.append((lineno, colno, cp))
    return violations


def main(argv: list[str]) -> int:
    """Entry point. Returns the process exit code."""
    if len(argv) < 2:
        print(
            "usage: check-no-emoji.py PATH [PATH ...]",
            file=sys.stderr,
        )
        return 2

    total_violations = 0
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            continue
        for lineno, colno, cp in scan_file(path):
            print(
                f"{path}:{lineno}:{colno}: U+{cp:04X} {codepoint_name(cp)}",
                file=sys.stderr,
            )
            total_violations += 1

    if total_violations:
        print(
            f"\ncheck-no-emoji: {total_violations} violation(s) found. "
            f"Emoji are forbidden in project-authored files; use the ASCII "
            f"status tokens (OK, WIP, PENDING, FAIL, N/A, NOTE, WARN) instead.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
