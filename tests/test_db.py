from datetime import UTC, datetime
from decimal import Decimal

from clipengine.db import Ledger
from clipengine.models import (
    Campaign,
    Clip,
    ClipMeta,
    ClipStatus,
    Payout,
    Platform,
    Post,
    PostStatus,
    SourceVideo,
)


def test_roundtrip(tmp_path):
    lg = Ledger(tmp_path / "l.sqlite3")
    c = lg.add_campaign(Campaign(name="kai gta6", rate_per_1k_views_usd="1.25", max_payout_per_clip_usd="500"))
    s = lg.upsert_source(SourceVideo(url="https://x/v", title="t", license_note="brief"))
    clip = lg.add_clip(Clip(source_id=s.id, campaign_id=c.id, start_s=10, end_s=40, score=3.2))
    meta = ClipMeta(hook_text="NO WAY", title="t", caption="c", hashtags=["#GTA6"], why_it_works="w")
    lg.update_clip(clip.model_copy(update={"status": ClipStatus.RENDERED, "meta": meta}))
    got = lg.get_clip(clip.id)
    assert got.status is ClipStatus.RENDERED and got.meta.hook_text == "NO WAY"
    p = lg.upsert_post(Post(clip_id=clip.id, platform=Platform.YOUTUBE, status=PostStatus.PUBLISHED, remote_id="abc", views=100))
    p2 = lg.upsert_post(p.model_copy(update={"views": 50}))
    assert p2.views == 100  # never regress views
    assert lg.add_payout(Payout(provider="paypal", provider_txn_id="T1", amount="12.50",
                                received_at=datetime.now(UTC)))
    assert not lg.add_payout(Payout(provider="paypal", provider_txn_id="T1", amount="12.50",
                                    received_at=datetime.now(UTC)))
    assert lg.summary()["payouts_usd"] == "12.50"
    assert lg.list_campaigns()[0].max_payout_per_clip_usd == Decimal(500)
