"""Tell Chinese reviews from English ones.

RIC reviews written by HKU students are English, written Chinese (traditional
or simplified), or a mix such as "呢個 course 好 hard". A script check is enough
for this: no language-ID model is needed, and it works offline.
"""

from __future__ import annotations

# Unified ideographs (incl. extension A) and compatibility ideographs.
_CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))

# A review is treated as Chinese when at least this share of its letters are
# Chinese characters, so one quoted name in an English review is not translated.
CHINESE_SHARE_THRESHOLD = 0.2


def is_cjk(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _CJK_RANGES)


def chinese_share(text: str) -> float:
    """Share of the letters in ``text`` that are Chinese characters (0.0 if no letters)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(is_cjk(c) for c in letters) / len(letters)


def detect_language(text: str) -> str:
    """``"zh"`` if the text is (mostly) Chinese, otherwise ``"en"``."""
    return "zh" if chinese_share(text) >= CHINESE_SHARE_THRESHOLD else "en"
