from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from .indexer import IndexEntry


@dataclass(frozen=True)
class SearchResult:
    name: str
    path: str
    is_dir: bool
    score: float


_WORD_BOUNDARY = re.compile(r"[\s_\-\.\(\)\[\]]")


def _score(name_lower: str, tokens: list[str], mtime: float, now: float) -> float | None:
    score = 0.0
    for tok in tokens:
        idx = name_lower.find(tok)
        if idx < 0:
            return None
        if idx == 0:
            score += 100.0
        elif idx > 0 and _WORD_BOUNDARY.match(name_lower[idx - 1]):
            score += 60.0
        else:
            score += 20.0
        score -= idx * 0.1
    score -= len(name_lower) * 0.05
    age_days = max(0.0, (now - mtime) / 86400.0) if mtime else 365.0
    score += max(0.0, 10.0 - age_days * 0.1)
    return score


class Searcher:
    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []

    def set_index(self, entries: list[IndexEntry]) -> None:
        self._entries = entries

    def search(self, query: str, limit: int = 30) -> list[SearchResult]:
        query = unicodedata.normalize("NFC", query).strip().lower()
        if not query or not self._entries:
            return []
        tokens = [t for t in query.split() if t]
        if not tokens:
            return []
        now = time.time()
        scored: list[tuple[float, IndexEntry]] = []
        for entry in self._entries:
            name_lower, _path, _is_dir, mtime = entry
            s = _score(name_lower, tokens, mtime, now)
            if s is None:
                continue
            scored.append((s, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]
        return [
            SearchResult(
                name=entry[1].rsplit("\\", 1)[-1].rsplit("/", 1)[-1],
                path=entry[1],
                is_dir=entry[2],
                score=score,
            )
            for score, entry in top
        ]
