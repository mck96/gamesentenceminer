"""Small text helpers shared by OCR and translation."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_HANGUL = re.compile(r"[가-힯]")
_SPACE = re.compile(r"\s+")


def has_cjk(text: str) -> bool:
    return bool(_KANA.search(text) or _HAN.search(text) or _HANGUL.search(text))


def guess_lang(text: str) -> str | None:
    """Script-based guess: kana -> ja, Han only -> zh, hangul -> ko, Latin -> en."""
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _HAN.search(text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


def join_lines(lines: list[str]) -> str:
    """CJK lines join without spaces, everything else with one space."""
    parts = [ln.strip() for ln in lines if ln and ln.strip()]
    sep = "" if any(has_cjk(p) for p in parts) else " "
    return sep.join(parts)


def _normalize(text: str) -> str:
    return _SPACE.sub("", text).casefold()


def similar(a: str, b: str, threshold: float = 0.9) -> bool:
    """Treat OCR results as the same line despite a misread character or two."""
    na, nb = _normalize(a), _normalize(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    return SequenceMatcher(None, na, nb).ratio() >= threshold
