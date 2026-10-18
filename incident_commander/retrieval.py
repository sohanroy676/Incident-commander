"""Runbook ranking (PHASE5 7.4): the labelled stub and the hybrid BM25 + char TF-IDF ranker.

A ranker only orders hypotheses (a planner tie-break). It never confirms one.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config
from .types import Candidate, Runbook


class Ranker(Protocol):
    label: str

    def rank(self, query: str) -> list[Candidate]: ...


class StaticRanker:
    """Fixed order, declared as a stub in the output. The query is ignored."""

    label = "STUB"

    def __init__(self, order: list[str] | tuple[str, ...]) -> None:
        if not order:
            raise ValueError("StaticRanker needs a non-empty order")
        if len(set(order)) != len(order):
            raise ValueError("StaticRanker order has duplicate runbook ids")
        self.order = tuple(order)

    def rank(self, query: str) -> list[Candidate]:
        return [
            Candidate(runbook_id, {"static": i}, 0.0, i)
            for i, runbook_id in enumerate(self.order, start=1)
        ]


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def bm25_scores(
    query_tokens: list[str],
    docs_tokens: list[list[str]],
    k1: float = config.BM25_K1,
    b: float = config.BM25_B,
) -> list[float]:
    """Okapi BM25 per document; IDF is ln(1 + (N - df + 0.5) / (df + 0.5)), never negative."""
    n_docs = len(docs_tokens)
    if n_docs == 0:
        return []
    avg_len = sum(len(d) for d in docs_tokens) / n_docs or 1.0
    df = Counter(t for d in docs_tokens for t in set(d))
    scores = []
    for doc in docs_tokens:
        tf = Counter(doc)
        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            norm = tf[term] + k1 * (1 - b + b * len(doc) / avg_len)
            score += idf * tf[term] * (k1 + 1) / norm
        scores.append(score)
    return scores


def rrf(rank_lists: list[list[str]], k: int = config.RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion: each list is ids best-first; score = sum of 1 / (k + rank)."""
    fused: dict[str, float] = {}
    for ids in rank_lists:
        for rank, item in enumerate(ids, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


def _order(ids: list[str], scores: list[float]) -> list[str]:
    """Best score first; equal scores keep corpus order, so output is deterministic."""
    index = {rid: i for i, rid in enumerate(ids)}
    return sorted(ids, key=lambda rid: (-scores[index[rid]], index[rid]))


class HybridRanker:
    """BM25 and char TF-IDF cosine, fused by RRF. Indexes runbook `text` only, never signatures."""

    label = "HYBRID"

    def __init__(self, runbooks: tuple[Runbook, ...], k_rrf: int = config.RRF_K) -> None:
        if not runbooks:
            raise ValueError("HybridRanker needs at least one runbook")
        self._ids = [r.runbook_id for r in runbooks]
        if len(set(self._ids)) != len(self._ids):
            raise ValueError("HybridRanker runbooks have duplicate ids")
        self._k = k_rrf
        self._docs = [tokenize(r.text) for r in runbooks]
        self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=config.CHAR_NGRAM_RANGE)
        self._matrix = self._vectorizer.fit_transform([r.text for r in runbooks])

    def rank(self, query: str) -> list[Candidate]:
        bm25 = bm25_scores(tokenize(query), self._docs)
        char = cosine_similarity(self._vectorizer.transform([query]), self._matrix)[0].tolist()
        bm25_order = _order(self._ids, bm25)
        char_order = _order(self._ids, char)
        fused = rrf([bm25_order, char_order], self._k)
        final = _order(self._ids, [fused[rid] for rid in self._ids])
        return [
            Candidate(
                rid,
                {"bm25": bm25_order.index(rid) + 1, "char": char_order.index(rid) + 1},
                fused[rid],
                i,
            )
            for i, rid in enumerate(final, start=1)
        ]

    @staticmethod
    def margin(candidates: list[Candidate]) -> float:
        """Fused-score gap between rank 1 and rank 2 (0.0 with fewer than two candidates)."""
        if len(candidates) < 2:
            return 0.0
        return candidates[0].fused_score - candidates[1].fused_score
