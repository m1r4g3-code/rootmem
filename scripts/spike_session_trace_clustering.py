"""Phase 3 Prototype-stage spike (build order step 2): proves session-trace-
level cosine similarity over real Voyage embeddings clusters two
differently-worded successful traces of the same underlying procedure
together, while a failed session on a related-looking task and an unrelated
successful trace both stay separate -- before ADR 0017 locks in
`procedural_session_similarity_threshold`.

This validates docs/research/phase3-research-memo.md's resolution of Phase
2's carried-forward open question: raw episode-level similarity (Phase 2's
signal) doesn't transfer to procedural memory, because the unit of
comparison must be a whole session trace, not an individual step. Each
"sentence" recorded into tests/fixtures/voyage_embeddings.json for this
phase is actually a newline-joined trace summary (ordered session steps),
embedded once per session -- exactly matching how
consolidation/procedural_clustering.py's group_session_traces will build its
embedding input.

Uses tests/fixtures/voyage_embeddings.json's real recorded voyage-4
embeddings (not synthetic/hash-based vectors), same discipline as
scripts/spike_similarity_clustering.py (Phase 2).

Run: uv run python scripts/spike_session_trace_clustering.py
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "voyage_embeddings.json"
)

TRACE_SUCCESS_A = "\n".join(
    [
        "The test suite fails with a KeyError in the payment module.",
        "The root cause is a missing default value in the config loader.",
        "The fix is to add a default value in the config loader, and the tests pass.",
    ]
)
TRACE_SUCCESS_B = "\n".join(
    [
        "A test is failing due to a KeyError inside payment processing.",
        "Root cause: the config loader has no default value set.",
        "Fix applied: added a default value to the config loader; tests now pass.",
    ]
)
TRACE_FAILURE_C = "\n".join(
    [
        "The test suite fails with a TypeError in the billing module.",
        "Attempted fix: changed the input type in the billing handler.",
        "The fix did not work; the TypeError persisted because the root cause "
        "was actually a serialization bug in the API layer, not the input type.",
    ]
)
TRACE_SUCCESS_UNRELATED_D = "\n".join(
    [
        "The deployment pipeline was hanging on the docker build step.",
        "The root cause was a stale layer cache pointing at a deleted base image.",
        "Clearing the build cache and rebuilding fixed the pipeline; it now completes normally.",
    ]
)

TRACE_IDS = {
    TRACE_SUCCESS_A: "success_a",
    TRACE_SUCCESS_B: "success_b",
    TRACE_FAILURE_C: "failure_c",
    TRACE_SUCCESS_UNRELATED_D: "success_unrelated_d",
}

# Expected: the two same-procedure successful traces cluster together;
# the failed trace and the unrelated successful trace each stay singletons.
EXPECTED_CLUSTERS: list[set[str]] = [
    {"success_a", "success_b"},
    {"failure_c"},
    {"success_unrelated_d"},
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
    raw_embeddings: dict[str, list[float]] = fixture["embeddings"]

    embeddings = {TRACE_IDS[text]: vec for text, vec in raw_embeddings.items() if text in TRACE_IDS}
    assert len(embeddings) == 4, "expected all 4 Phase 3 trace sentences in the fixture"

    print("Pairwise session-trace cosine similarities (sorted descending):")
    pairs = []
    for a, b in itertools.combinations(embeddings, 2):
        sim = cosine_similarity(embeddings[a], embeddings[b])
        pairs.append((sim, a, b))
    pairs.sort(reverse=True)
    for sim, a, b in pairs:
        print(f"  {sim:.4f}  {a!r:24s} <-> {b!r}")

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
