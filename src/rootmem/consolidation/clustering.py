"""Similarity-threshold union-find clustering (ADR 0015) — not k-means/HDBSCAN,
no new ML dependency. Pure function, zero I/O: the pairwise similarities it
clusters over are fetched once per batch by
`MemoryRepository.find_similar_pairs` and handed in by
`consolidation.distill`'s orchestration.

Threshold validated empirically against real voyage-4 embeddings by
scripts/spike_similarity_clustering.py before being locked into
`distillation_similarity_threshold` (ADR 0015).
"""

from __future__ import annotations


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

    def clusters(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self._parent:
            groups.setdefault(self.find(item), []).append(item)
        return list(groups.values())


def cluster_by_similarity(
    memory_ids: list[str], pairs: list[tuple[str, str, float]], threshold: float
) -> list[list[str]]:
    """Group `memory_ids` into clusters via union-find over `pairs`
    (`(id_a, id_b, cosine_similarity)`), joining any pair at or above
    `threshold`. Every id in `memory_ids` appears in exactly one cluster,
    including singleton clusters for ids with no qualifying pair."""
    uf = _UnionFind(memory_ids)
    for id_a, id_b, similarity in pairs:
        if similarity >= threshold:
            uf.union(id_a, id_b)
    return uf.clusters()
