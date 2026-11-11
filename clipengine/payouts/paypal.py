"""PayPal: pull incoming transactions into the ledger (Transaction Search API).

Setup: developer.paypal.com -> My Apps -> Live app -> enable "Transaction Search" feature -> client id/secret.
India note: PayPal India business accounts auto-withdraw USD to your linked bank in INR (no balance holding);
the FIRC/remittance details show in PayPal Activity. Keep them for ITR.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from ..db import Ledger
from ..models import Payout

log = logging.getLogger(__name__)


class PayPalError(RuntimeError):
    pass


def _base() -> str:
    return "https://api-m.paypal.com" if get_settings().clip_paypal_env == "live" else "https://api-m.sandbox.paypal.com"


@retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=15),
       retry=retry_if_exception_type((httpx.TransportError, PayPalError)))
def _token(c: httpx.Client) -> str:
    s = get_settings()
    if not (s.clip_paypal_client_id and s.clip_paypal_client_secret):
        raise RuntimeError("CLIP_PAYPAL_CLIENT_ID / SECRET not set")
    r = c.post(f"{_base()}/v1/oauth2/token", data={"grant_type": "client_credentials"},
               auth=(s.clip_paypal_client_id, s.clip_paypal_client_secret))
    if r.status_code >= 500:
        raise PayPalError(f"token {r.status_code}")
    if r.status_code >= 400:
        raise RuntimeError(f"PayPal auth failed {r.status_code}: {r.text[:200]}")
    return str(r.json()["access_token"])


def sync_incoming(ledger: Ledger, days: int = 31) -> int:
    """Insert new incoming (credit) transactions. Returns count inserted. Max window per call: 31 days."""
    days = min(max(days, 1), 31)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    inserted = 0
    with httpx.Client(timeout=60.0) as c:
        tok = _token(c)
        page = 1
        while True:
            r = c.get(f"{_base()}/v1/reporting/transactions", headers={"Authorization": f"Bearer {tok}"}, params={
                "start_date": start.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "end_date": end.strftime("%Y-%m-%dT%H:%M:%S-0000"),
                "fields": "transaction_info,payer_info", "page_size": 100, "page": page,
                "transaction_status": "S",
            })
            if r.status_code == 403:
                raise RuntimeError("PayPal app lacks 'Transaction Search' permission (enable it in the app settings; "
                                   "takes up to 9h to activate)")
            if r.status_code >= 400:
                raise RuntimeError(f"PayPal transactions {r.status_code}: {r.text[:300]}")
            data = r.json()
            for t in data.get("transaction_details", []):
                ti = t["transaction_info"]
                amt = Decimal(ti["transaction_amount"]["value"])
                if amt <= 0:
                    continue  # outgoing / fees
                payer = (t.get("payer_info") or {}).get("payer_name", {}).get("alternate_full_name", "")
                p = Payout(provider="paypal", provider_txn_id=ti["transaction_id"], amount=amt,
                           currency=ti["transaction_amount"]["currency_code"],
                           received_at=datetime.fromisoformat(ti["transaction_initiation_date"].replace("Z", "+00:00")),
                           note=f"{payer} {ti.get('transaction_subject', '')}".strip())
                if ledger.add_payout(p):
                    inserted += 1
            if page >= int(data.get("total_pages", 1)):
                break
            page += 1
    log.info("paypal: %d new incoming transactions", inserted)
    return inserted
