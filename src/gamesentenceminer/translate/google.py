"""Keyless Google Translate (the unofficial endpoint the web widget uses).

Good enough for the MVP; it can change or rate-limit without notice, so the
translator stays swappable (DeepL once there is an API key).
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MAX_CHARS = 1500


@dataclass(frozen=True)
class Translation:
    text: str
    source_lang: str | None


class TranslateError(RuntimeError):
    pass


def parse_response(data) -> Translation:
    try:
        segments = data[0] or []
        text = "".join(seg[0] for seg in segments if seg and isinstance(seg[0], str))
    except (TypeError, IndexError) as e:
        raise TranslateError(f"unexpected response shape: {e}") from e
    source = data[2] if len(data) > 2 and isinstance(data[2], str) else None
    return Translation(text.strip(), source)


class GoogleTranslator:
    def __init__(self, timeout: float = 8.0, cache_size: int = 512) -> None:
        self.timeout = timeout
        self._cache: OrderedDict[tuple[str, str, str], Translation] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def translate(self, text: str, target: str, source: str = "auto") -> Translation:
        text = text.strip()[:MAX_CHARS]
        if not text:
            return Translation("", None)
        key = (text, target, source)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]

        query = urllib.parse.urlencode(
            {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text})
        request = urllib.request.Request(f"{ENDPOINT}?{query}",
                                         headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except (OSError, ValueError) as e:
            raise TranslateError(str(e)) from e
        result = parse_response(data)

        with self._lock:
            self._cache[key] = result
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result
