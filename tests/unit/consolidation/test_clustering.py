from __future__ import annotations

from rootmem.consolidation.clustering import cluster_by_similarity


class TestClusterBySimilarity:
    def test_no_pairs_gives_all_singletons(self) -> None:
        clusters = cluster_by_similarity(["a", "b", "c"], [], threshold=0.8)

        assert sorted(sorted(c) for c in clusters) == [["a"], ["b"], ["c"]]

    def test_pair_above_threshold_joins_a_cluster(self) -> None:
        clusters = cluster_by_similarity(
            ["a", "b", "c"], [("a", "b", 0.9), ("b", "c", 0.1)], threshold=0.8
        )

        as_sets = sorted(sorted(c) for c in clusters)
        assert ["a", "b"] in as_sets
        assert ["c"] in as_sets

    def test_pair_below_threshold_does_not_join(self) -> None:
        clusters = cluster_by_similarity(["a", "b"], [("a", "b", 0.5)], threshold=0.8)

        assert sorted(sorted(c) for c in clusters) == [["a"], ["b"]]

    def test_transitive_chain_forms_one_cluster(self) -> None:
        clusters = cluster_by_similarity(
            ["a", "b", "c"], [("a", "b", 0.9), ("b", "c", 0.9)], threshold=0.8
        )

        assert len(clusters) == 1
        assert sorted(clusters[0]) == ["a", "b", "c"]

    def test_exactly_at_threshold_joins(self) -> None:
        clusters = cluster_by_similarity(["a", "b"], [("a", "b", 0.8)], threshold=0.8)

        assert len(clusters) == 1
