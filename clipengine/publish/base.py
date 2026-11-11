from __future__ import annotations

from dataclasses import dataclass


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishResult:
    remote_id: str
    url: str
