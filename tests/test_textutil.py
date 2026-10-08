from gamesentenceminer.pipeline.textutil import guess_lang, join_lines, similar


def test_join_lines_uses_spaces_only_for_latin_text():
    assert join_lines(["Where are", "you going?"]) == "Where are you going?"
    assert join_lines(["こんな時間に", "どこへ行くの？"]) == "こんな時間にどこへ行くの？"
    assert join_lines(["  ", "a", ""]) == "a"


def test_guess_lang_by_script():
    assert guess_lang("どこへ行くの？") == "ja"
    assert guess_lang("你要去哪里？") == "zh"
    assert guess_lang("Where?") == "en"
    assert guess_lang("123 !?") is None


def test_similar_tolerates_one_misread_character():
    assert similar("这么晚了你要去哪里？城门午夜就关了。", "这么晚了你要去哪里？城内午夜就关了。")
    assert similar("Hello  world", "hello world")
    assert not similar("Where are you going?", "The gate closes at midnight.")
    assert not similar("", "text")
