"""Whop Content Rewards has no public clipper-side payout API; import the CSV you export from the
Whop dashboard (Payouts -> Export) and compute what each campaign *owes* you from tracked views."""
from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from ..db import Ledger
from ..models import Campaign, Payout


def expected_payout_usd(views: int, c: Campaign) -> Decimal:
    """Rate * (views/1000), floored at campaign min, capped at per-clip max. Pure."""
    if views < c.min_views_for_payout:
        return Decimal(0)
    amt = (Decimal(views) / Decimal(1000)) * c.rate_per_1k_views_usd
    if c.max_payout_per_clip_usd is not None:
        amt = min(amt, c.max_payout_per_clip_usd)
    return amt.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def import_csv(ledger: Ledger, path: Path, campaign_id: int | None = None) -> int:
    """Flexible import: needs columns containing 'id', 'amount', 'date' (case-insensitive)."""
    inserted = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            return 0
        cols = {c.lower(): c for c in rd.fieldnames}
        id_c = next((cols[k] for k in cols if "id" in k), None)
        amt_c = next((cols[k] for k in cols if "amount" in k or "total" in k), None)
        date_c = next((cols[k] for k in cols if "date" in k or "time" in k), None)
        if not (id_c and amt_c and date_c):
            raise ValueError(f"CSV needs id/amount/date columns; got {rd.fieldnames}")
        for row in rd:
            raw = row[amt_c].replace("$", "").replace(",", "").strip()
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(row[date_c].strip().replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.now(UTC)
            p = Payout(campaign_id=campaign_id, provider="whop", provider_txn_id=row[id_c].strip(),
                       amount=Decimal(raw), currency="USD", received_at=dt, note="whop csv import")
            if ledger.add_payout(p):
                inserted += 1
    return inserted
