import numpy as np

from gamesentenceminer.pipeline.watcher import ChangeWatcher


def box(text_value: int = 0, size=(60, 200)) -> np.ndarray:
    """Dark dialog box; `text_value` > 0 draws a bright 'text' stripe of that width."""
    img = np.full((*size, 4), 20, np.uint8)
    if text_value:
        img[20:40, 10:10 + text_value, :3] = 230
    return img


def test_reads_once_after_content_settles():
    w = ChangeWatcher(settle_s=0.4)
    w.feed(box(150), 0.0)
    assert not w.ready(0.2)  # still inside the settle window
    assert w.ready(0.5)
    assert not w.ready(0.6)  # only once


def test_typewriter_animation_is_read_at_the_end():
    w = ChangeWatcher(settle_s=0.4)
    t = 0.0
    for width in range(20, 181, 20):  # text grows every 0.2 s
        w.feed(box(width), t)
        assert not w.ready(t)
        t += 0.2
    assert not w.ready(t - 0.1)
    assert w.ready(t + 0.3)


def test_same_content_is_not_read_again():
    w = ChangeWatcher(settle_s=0.2)
    w.feed(box(150), 0.0)
    assert w.ready(0.3)
    for t in (0.4, 0.6, 0.8):
        w.feed(box(150), t)
        assert not w.ready(t + 0.5)


def test_new_line_after_previous_is_read():
    w = ChangeWatcher(settle_s=0.2)
    w.feed(box(150), 0.0)
    assert w.ready(0.3)
    w.feed(box(60), 1.0)
    assert w.ready(1.3)


def test_blank_box_is_never_read():
    w = ChangeWatcher(settle_s=0.2)
    w.feed(box(150), 0.0)
    assert w.ready(0.3)
    w.feed(box(0), 1.0)  # dialog closed: plain box
    assert not w.ready(1.5)


def test_change_settles_without_new_frames():
    # Static screens stop producing frames; time alone must settle the change.
    w = ChangeWatcher(settle_s=0.4)
    w.feed(box(150), 0.0)
    assert w.ready(1.0)


def test_forget_rereads_current_content():
    w = ChangeWatcher(settle_s=0.2)
    w.feed(box(150), 0.0)
    assert w.ready(0.3)
    w.forget()
    assert w.ready(0.4)
