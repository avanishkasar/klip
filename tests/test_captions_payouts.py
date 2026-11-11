from decimal import Decimal

from clipengine.captions import Word, build_ass, group_words
from clipengine.models import Campaign
from clipengine.payouts.whop import expected_payout_usd
from clipengine.render import CamBox, build_filter


def test_group_words_splits_on_gap_and_count():
    ws = [Word(0, .2, "a"), Word(.2, .4, "b"), Word(.4, .6, "c"), Word(.6, .8, "d"), Word(3, 3.2, "e")]
    g = group_words(ws)
    assert [len(x) for x in g] == [3, 1, 1]


def test_build_ass_has_hook_and_karaoke():
    out = build_ass([Word(0.5, 0.9, "no"), Word(0.9, 1.3, "way")], "HE DID WHAT")
    assert "Style: Hook" in out and "HE DID WHAT" in out and "\\k40" in out


def test_expected_payout():
    c = Campaign(name="x", rate_per_1k_views_usd="1.25", max_payout_per_clip_usd="100", min_views_for_payout=1000)
    assert expected_payout_usd(999, c) == Decimal(0)
    assert expected_payout_usd(10_000, c) == Decimal("12.50")
    assert expected_payout_usd(10_000_000, c) == Decimal(100)


def test_build_filter_layouts():
    assert "[vout]" in build_filter("crop", 1920, 1080, None, None)
    assert "vstack" in build_filter("stack", 1920, 1080, CamBox.parse("0:0:480:270"), None)
    assert "boxblur" in build_filter("blur", 1920, 1080, None, None)


def test_split_filter_and_filler_pick(tmp_path):
    import pytest

    from clipengine.render import pick_filler

    g = build_filter("split", 1920, 1080, None, None)
    assert "[1:v]" in g and "vstack" in g and "crop=1080:1056" in g and "crop=1080:864" in g
    with pytest.raises(FileNotFoundError):
        pick_filler(tmp_path)
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    assert pick_filler(tmp_path).name == "a.mp4"
