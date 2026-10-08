import json

import numpy as np

from gamesentenceminer.pipeline.reader import crop_region
from gamesentenceminer.regions import Region, Settings, next_region_name


def test_pixel_box_is_clipped_to_frame():
    r = Region("a", (0.9, 0.5, 0.5, 0.25))
    assert r.pixel_box(1000, 400) == (900, 200, 1000, 300)
    assert Region("b", (-0.1, 0.0, 0.2, 0.1)).pixel_box(100, 100) == (0, 0, 10, 10)


def test_settings_roundtrip_and_bad_entries(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(target_lang="en", regions=[Region("diyalog", (0.1, 0.7, 0.8, 0.2), "manual")])
    s.save(path)
    loaded = Settings.load(path)
    assert loaded.target_lang == "en"
    assert loaded.regions == [Region("diyalog", (0.1, 0.7, 0.8, 0.2), "manual")]

    data = json.loads(path.read_text())
    data["regions"].append({"name": "broken"})
    data["unknown_key"] = 1
    path.write_text(json.dumps(data))
    assert [r.name for r in Settings.load(path).regions] == ["diyalog"]


def test_missing_or_corrupt_settings_fall_back_to_defaults(tmp_path):
    assert Settings.load(tmp_path / "nope.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert Settings.load(bad) == Settings()


def test_next_region_name_skips_taken_names():
    regions = [Region("bölge 1", (0, 0, 1, 1)), Region("bölge 2", (0, 0, 1, 1))]
    assert next_region_name(regions) == "bölge 3"
    regions[1].name = "bölge 3"
    assert next_region_name(regions) == "bölge 4"


def test_crop_region_masks_overlay_area():
    frame = np.full((100, 200, 4), 200, np.uint8)
    crop = crop_region(frame, Region("a", (0.0, 0.0, 0.5, 0.5)), masks=[(50, 25, 150, 75)])
    assert crop.shape == (50, 100, 3)
    assert (crop[25:, 50:] == 0).all()
    assert (crop[:25] == 200).all()
    assert frame[30, 60, 0] == 200  # the frame itself is untouched


def test_crop_region_ignores_tiny_regions():
    frame = np.zeros((100, 100, 4), np.uint8)
    assert crop_region(frame, Region("a", (0.5, 0.5, 0.01, 0.01))) is None


def test_ocr_fit_scale():
    from gamesentenceminer.ocr.engine import fit_scale

    assert fit_scale(800, 200) == 1.0
    assert abs(fit_scale(2099, 288) - 960 / 2099) < 1e-9
    assert fit_scale(2400, 60) == 48 / 60  # wide subtitle line keeps a readable height
    assert fit_scale(300, 30) == 48 / 30  # tiny text is upscaled
