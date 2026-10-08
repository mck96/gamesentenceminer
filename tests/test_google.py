import io
import json

import pytest

from gamesentenceminer.translate import google
from gamesentenceminer.translate.google import GoogleTranslator, TranslateError, parse_response


def test_parse_response_joins_segments_and_reads_source_lang():
    data = [[["Nereye ", "Where ", None], ["gidiyorsun?", "are you going?", None]], None, "en"]
    result = parse_response(data)
    assert result.text == "Nereye gidiyorsun?"
    assert result.source_lang == "en"


def test_parse_response_rejects_garbage():
    with pytest.raises(TranslateError):
        parse_response(None)


def test_translate_caches_results(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(json.dumps([[["Merhaba", "Hello", None]], None, "en"]).encode())

    monkeypatch.setattr(google.urllib.request, "urlopen", fake_urlopen)
    t = GoogleTranslator()
    assert t.translate("Hello", "tr").text == "Merhaba"
    assert t.translate("Hello", "tr").text == "Merhaba"
    assert len(calls) == 1
    assert "tl=tr" in calls[0] and "q=Hello" in calls[0]
    assert t.translate("   ", "tr").text == ""


def test_network_errors_become_translate_error(monkeypatch):
    def broken(request, timeout):
        raise OSError("offline")

    monkeypatch.setattr(google.urllib.request, "urlopen", broken)
    with pytest.raises(TranslateError):
        GoogleTranslator().translate("Hello", "tr")
