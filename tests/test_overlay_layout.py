import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from gamesentenceminer.overlay import (  # noqa: E402
    MAX_HEIGHT_RATIO,
    TRANSLATION_SIZES,
    fit_layout,
)

LONG = ("Every shepherd knows the song. It bellows up the river. Urth lives in that sliver "
        "of land. STRENGTH measures your natural bodily prowess alongside a testosterone-"
        "fueled mindset. As a man, it is only proper for you to hone your figure and its "
        "capabilities. But why? The search for meaning is as vital as the struggle towards "
        "competency. Luckily, you already know your cause. To protect the innocent. To lead "
        "the weak. To sacrifice until nothing but your bones hit the pavement. ") * 2


@pytest.fixture(scope="module", autouse=True)
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_short_line_uses_largest_font_and_shows_original():
    layout = fit_layout("どこへ行くの？", "Nereye gidiyorsun?", 1800, 600)
    assert layout.translation_px == TRANSLATION_SIZES[0]
    assert layout.original_h > 0
    assert layout.height < 200


def test_height_grows_with_text_but_stays_capped():
    short = fit_layout("a", "Kısa bir cümle.", 1800, 600)
    medium = fit_layout(LONG[:300], LONG[:300], 1800, 600)
    cap = int(1440 * MAX_HEIGHT_RATIO)
    huge = fit_layout(LONG * 4, LONG * 8, 1800, cap)
    assert short.height < medium.height <= 600
    assert huge.height == cap  # clipped
    assert huge.original_h == 0 and huge.translation_px == TRANSLATION_SIZES[-1]


def test_long_text_shrinks_font_before_dropping_original():
    roomy = fit_layout(LONG, LONG, 1800, 330)
    assert roomy.original_h > 0 and roomy.translation_px < TRANSLATION_SIZES[0]


def test_long_original_is_dropped_to_keep_translation_large():
    layout = fit_layout(LONG * 10, "Kısa çeviri.", 1800, 300)
    assert layout.original_h == 0
    assert layout.translation_px == TRANSLATION_SIZES[0]


def test_original_can_be_turned_off():
    assert fit_layout("orijinal", "çeviri", 1800, 600, show_original=False).original_h == 0
