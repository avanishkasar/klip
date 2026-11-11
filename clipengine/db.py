from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import (
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

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  rate_per_1k_views_usd TEXT NOT NULL,
  max_payout_per_clip_usd TEXT,
  min_views_for_payout INTEGER NOT NULL DEFAULT 0,
  platforms TEXT NOT NULL,
  requirements TEXT NOT NULL DEFAULT '',
  url TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT '',
  local_path TEXT,
  duration_s REAL,
  creator TEXT NOT NULL DEFAULT '',
  license_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  campaign_id INTEGER REFERENCES campaigns(id),
  start_s REAL NOT NULL,
  end_s REAL NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  render_path TEXT,
  meta_json TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clip_id INTEGER NOT NULL REFERENCES clips(id),
  platform TEXT NOT NULL,
  status TEXT NOT NULL,
  remote_id TEXT,
  url TEXT,
  views INTEGER NOT NULL DEFAULT 0,
  last_synced_at TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(clip_id, platform)
);
CREATE TABLE IF NOT EXISTS payouts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id INTEGER REFERENCES campaigns(id),
  provider TEXT NOT NULL,
  provider_txn_id TEXT NOT NULL,
  amount TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount_inr TEXT,
  received_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  UNIQUE(provider, provider_txn_id)
);
CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class Ledger:
    """SQLite-backed ledger. One connection per Ledger; guarded by a lock for thread use."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    # ---- campaigns ----
    def add_campaign(self, c: Campaign) -> Campaign:
        with self._tx() as cx:
            cur = cx.execute(
                "INSERT INTO campaigns(name,source,rate_per_1k_views_usd,max_payout_per_clip_usd,"
                "min_views_for_payout,platforms,requirements,url,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    c.name, c.source, str(c.rate_per_1k_views_usd),
                    str(c.max_payout_per_clip_usd) if c.max_payout_per_clip_usd is not None else None,
                    c.min_views_for_payout, json.dumps([p.value for p in c.platforms]), c.requirements,
                    str(c.url) if c.url else None, int(c.active), _iso(c.created_at),
                ),
            )
            return c.model_copy(update={"id": cur.lastrowid})

    def list_campaigns(self, active_only: bool = True) -> list[Campaign]:
        q = "SELECT * FROM campaigns" + (" WHERE active=1" if active_only else "") + " ORDER BY id"
        return [self._row_campaign(r) for r in self._conn.execute(q)]

    def get_campaign(self, cid: int) -> Campaign | None:
        r = self._conn.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
        return self._row_campaign(r) if r else None

    @staticmethod
    def _row_campaign(r: sqlite3.Row) -> Campaign:
        return Campaign(
            id=r["id"], name=r["name"], source=r["source"],
            rate_per_1k_views_usd=Decimal(r["rate_per_1k_views_usd"]),
            max_payout_per_clip_usd=Decimal(r["max_payout_per_clip_usd"]) if r["max_payout_per_clip_usd"] else None,
            min_views_for_payout=r["min_views_for_payout"],
            platforms=[Platform(p) for p in json.loads(r["platforms"])],
            requirements=r["requirements"], url=r["url"], active=bool(r["active"]),
            created_at=_dt(r["created_at"]) or datetime.now(),
        )

    # ---- sources ----
    def upsert_source(self, s: SourceVideo) -> SourceVideo:
        with self._tx() as cx:
            cx.execute(
                "INSERT INTO sources(url,title,local_path,duration_s,creator,license_note,created_at)"
                " VALUES(?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,"
                " local_path=COALESCE(excluded.local_path, sources.local_path),"
                " duration_s=COALESCE(excluded.duration_s, sources.duration_s),"
                " creator=excluded.creator, license_note=excluded.license_note",
                (s.url, s.title, str(s.local_path) if s.local_path else None, s.duration_s,
                 s.creator, s.license_note, _iso(s.created_at)),
            )
            r = cx.execute("SELECT * FROM sources WHERE url=?", (s.url,)).fetchone()
            return self._row_source(r)

    def get_source(self, sid: int) -> SourceVideo | None:
        r = self._conn.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        return self._row_source(r) if r else None

    @staticmethod
    def _row_source(r: sqlite3.Row) -> SourceVideo:
        return SourceVideo(
            id=r["id"], url=r["url"], title=r["title"],
            local_path=Path(r["local_path"]) if r["local_path"] else None,
            duration_s=r["duration_s"], creator=r["creator"], license_note=r["license_note"],
            created_at=_dt(r["created_at"]) or datetime.now(),
        )

    # ---- clips ----
    def add_clip(self, c: Clip) -> Clip:
        with self._tx() as cx:
            cur = cx.execute(
                "INSERT INTO clips(source_id,campaign_id,start_s,end_s,score,status,render_path,meta_json,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (c.source_id, c.campaign_id, c.start_s, c.end_s, c.score, c.status.value,
                 str(c.render_path) if c.render_path else None,
                 c.meta.model_dump_json() if c.meta else None, _iso(c.created_at)),
            )
            return c.model_copy(update={"id": cur.lastrowid})

    def update_clip(self, c: Clip) -> None:
        if c.id is None:
            raise ValueError("clip has no id")
        with self._tx() as cx:
            cx.execute(
                "UPDATE clips SET status=?, render_path=?, meta_json=?, score=? WHERE id=?",
                (c.status.value, str(c.render_path) if c.render_path else None,
                 c.meta.model_dump_json() if c.meta else None, c.score, c.id),
            )

    def get_clip(self, cid: int) -> Clip | None:
        r = self._conn.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()
        return self._row_clip(r) if r else None

    def list_clips(self, status: ClipStatus | None = None, source_id: int | None = None) -> list[Clip]:
        q, args = "SELECT * FROM clips WHERE 1=1", []
        if status:
            q, args = q + " AND status=?", args + [status.value]
        if source_id:
            q, args = q + " AND source_id=?", args + [source_id]
        return [self._row_clip(r) for r in self._conn.execute(q + " ORDER BY score DESC, id", args)]

    @staticmethod
    def _row_clip(r: sqlite3.Row) -> Clip:
        return Clip(
            id=r["id"], source_id=r["source_id"], campaign_id=r["campaign_id"],
            start_s=r["start_s"], end_s=r["end_s"], score=r["score"], status=ClipStatus(r["status"]),
            render_path=Path(r["render_path"]) if r["render_path"] else None,
            meta=ClipMeta.model_validate_json(r["meta_json"]) if r["meta_json"] else None,
            created_at=_dt(r["created_at"]) or datetime.now(),
        )

    # ---- posts ----
    def upsert_post(self, p: Post) -> Post:
        with self._tx() as cx:
            cx.execute(
                "INSERT INTO posts(clip_id,platform,status,remote_id,url,views,last_synced_at,error,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(clip_id,platform) DO UPDATE SET status=excluded.status,"
                " remote_id=COALESCE(excluded.remote_id, posts.remote_id), url=COALESCE(excluded.url, posts.url),"
                " views=MAX(excluded.views, posts.views), last_synced_at=excluded.last_synced_at, error=excluded.error",
                (p.clip_id, p.platform.value, p.status.value, p.remote_id, p.url, p.views,
                 _iso(p.last_synced_at), p.error, _iso(p.created_at)),
            )
            r = cx.execute("SELECT * FROM posts WHERE clip_id=? AND platform=?",
                           (p.clip_id, p.platform.value)).fetchone()
            return self._row_post(r)

    def list_posts(self, status: PostStatus | None = None) -> list[Post]:
        q, args = "SELECT * FROM posts", []
        if status:
            q, args = q + " WHERE status=?", [status.value]
        return [self._row_post(r) for r in self._conn.execute(q + " ORDER BY id", args)]

    @staticmethod
    def _row_post(r: sqlite3.Row) -> Post:
        return Post(
            id=r["id"], clip_id=r["clip_id"], platform=Platform(r["platform"]), status=PostStatus(r["status"]),
            remote_id=r["remote_id"], url=r["url"], views=r["views"], last_synced_at=_dt(r["last_synced_at"]),
            error=r["error"], created_at=_dt(r["created_at"]) or datetime.now(),
        )

    # ---- payouts ----
    def add_payout(self, p: Payout) -> bool:
        """Idempotent on (provider, provider_txn_id). Returns True if inserted."""
        with self._tx() as cx:
            cur = cx.execute(
                "INSERT OR IGNORE INTO payouts(campaign_id,provider,provider_txn_id,amount,currency,amount_inr,"
                "received_at,note) VALUES(?,?,?,?,?,?,?,?)",
                (p.campaign_id, p.provider, p.provider_txn_id, str(p.amount), p.currency,
                 str(p.amount_inr) if p.amount_inr is not None else None, _iso(p.received_at), p.note),
            )
            return cur.rowcount == 1

    def list_payouts(self) -> list[Payout]:
        rows = self._conn.execute("SELECT * FROM payouts ORDER BY received_at").fetchall()
        return [
            Payout(
                id=r["id"], campaign_id=r["campaign_id"], provider=r["provider"],
                provider_txn_id=r["provider_txn_id"], amount=Decimal(r["amount"]), currency=r["currency"],
                amount_inr=Decimal(r["amount_inr"]) if r["amount_inr"] else None,
                received_at=_dt(r["received_at"]) or datetime.now(), note=r["note"],
            )
            for r in rows
        ]

    # ---- reporting ----
    def summary(self) -> dict[str, Any]:
        cx = self._conn
        n = lambda q, *a: cx.execute(q, a).fetchone()[0]
        total_usd = sum((p.amount for p in self.list_payouts() if p.currency == "USD"), Decimal(0))
        return {
            "campaigns_active": n("SELECT COUNT(*) FROM campaigns WHERE active=1"),
            "sources": n("SELECT COUNT(*) FROM sources"),
            "clips_candidate": n("SELECT COUNT(*) FROM clips WHERE status='candidate'"),
            "clips_rendered": n("SELECT COUNT(*) FROM clips WHERE status='rendered'"),
            "clips_published": n("SELECT COUNT(*) FROM clips WHERE status='published'"),
            "posts_published": n("SELECT COUNT(*) FROM posts WHERE status='published'"),
            "posts_manual_pending": n("SELECT COUNT(*) FROM posts WHERE status='manual'"),
            "total_views": n("SELECT COALESCE(SUM(views),0) FROM posts"),
            "payouts_count": n("SELECT COUNT(*) FROM payouts"),
            "payouts_usd": str(total_usd),
        }
