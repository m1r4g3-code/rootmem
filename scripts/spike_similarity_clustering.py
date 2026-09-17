"""Phase 2 Prototype-stage spike (build order step 2): proves similarity-
threshold union-find clustering over real Voyage cosine similarities
correctly separates near-duplicate restatements from distinct facts, and
finds a real threshold value, before ADR 0015 locks in `distillation_similarity_threshold`.

Uses tests/fixtures/voyage_embeddings.json's real recorded voyage-4
embeddings (not synthetic/hash-based vectors) so the numbers this spike
reports are genuine cosine-similarity structure, the same discipline
ADR 0009 already established for FixtureReplayEmbeddingProvider.

Run: uv run python scripts/spike_similarity_clustering.py
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "voyage_embeddings.json"
)

# Expected cluster membership, by inspection of sentence content (not by
# running the algorithm) -- the spike's job is to find a threshold that
# reproduces this grouping from cosine similarity alone.
EXPECTED_CLUSTERS: list[set[str]] = [
    {"Alice works at Acme Corp", "Alice is employed at Acme Corp", "Alice's employer is Acme Corp"},
    {"Alice joined Globex as an engineer"},
    {"where is Alice employed now"},
    {"who is employed there currently"},
    {"a completely different sentence involving rainfall totals"},
    {"the weather forecast predicts heavy rain this weekend"},
    {"Bob works at Acme Corp"},
    {"the sky is blue and the grass is green"},
    {"The engineering team relocated to a new office at 500 Market Street."},
]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b

    def clusters(self) -> list[set[str]]:
        groups: dict[str, set[str]] = {}
        for item in self._parent:
            groups.setdefault(self.find(item), set()).add(item)
        return list(groups.values())


def cluster_by_similarity(embeddings: dict[str, list[float]], threshold: float) -> list[set[str]]:
    uf = _UnionFind(list(embeddings))
    for a, b in itertools.combinations(embeddings, 2):
        if cosine_similarity(embeddings[a], embeddings[b]) >= threshold:
            uf.union(a, b)
    return uf.clusters()


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    embeddings: dict[str, list[float]] = fixture["embeddings"]

    print("Pairwise cosine similarities (all pairs, sorted descending):")
    pairs = []
    for a, b in itertools.combinations(embeddings, 2):
        sim = cosine_similarity(embeddings[a], embeddings[b])
        pairs.append((sim, a, b))
    pairs.sort(reverse=True)
    for sim, a, b in pairs:
        print(f"  {sim:.4f}  {a!r:60s} <-> {b!r}")

    print()
    for threshold in (0.70, 0.75, 0.80, 0.85, 0.90):
        clusters = cluster_by_similarity(embeddings, threshold)
        clusters_as_sets = sorted((frozenset(c) for c in clusters), key=len, reverse=True)
        expected_sorted = sorted(frozenset(c) for c in EXPECTED_CLUSTERS)
        matches_expected = expected_sorted == sorted(clusters_as_sets)
        print(
            f"threshold={threshold:.2f}: {len(clusters)} clusters, "
            f"matches_expected={matches_expected}"
        )
        if not matches_expected:
            for c in clusters_as_sets:
                if len(c) > 1:
                    print(f"    cluster: {sorted(c)}")


if __name__ == "__main__":
    main()
