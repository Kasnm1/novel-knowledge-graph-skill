#!/usr/bin/env python3
"""Compatibility merge entry point for commitments and safe relation intervals."""
from __future__ import annotations

import merge_graph
from schema_expansion import install_required_fields


def safe_coalesce_relations(records):
    """Merge restatements without reopening a known closed interval.

    The historical coalescer popped ``valid_to`` whenever a later overlapping
    restatement was active/open, which could make a relation appear active for
    every later chapter. A known close is stronger than an open restatement;
    true resumed episodes do not overlap and therefore become a new episode.
    """
    result = []
    buckets = {}
    canonicalization = {}
    ordered = sorted(records, key=lambda r: (r.get("valid_from") if isinstance(r.get("valid_from"), int) else 0))
    for record in ordered:
        key = merge_graph.relation_key(record)
        match_index = next(
            (i for i in buckets.get(key, []) if merge_graph.relation_intervals_overlap(result[i], record)),
            None,
        )
        if match_index is None:
            buckets.setdefault(key, []).append(len(result))
            result.append(merge_graph.prepare_relation(record))
            continue
        prior = result[match_index]
        prior_id = prior["id"]
        duplicate_id = record["id"]
        result[match_index] = merge_graph.merge_relation_records(prior, merge_graph.prepare_relation(record))
        if duplicate_id != prior_id:
            canonicalization[duplicate_id] = prior_id
    return result, canonicalization


def main() -> int:
    install_required_fields()
    if "commitments" not in merge_graph.ARRAYS:
        merge_graph.ARRAYS = tuple(merge_graph.ARRAYS) + ("commitments",)
    old_merge_value = merge_graph.merge_value

    def merge_value(left, right, field):
        if field == "created_chapter" and isinstance(left, int) and isinstance(right, int):
            return min(left, right)
        if field == "resolved_chapter" and isinstance(left, int) and isinstance(right, int):
            return max(left, right)
        return old_merge_value(left, right, field)

    merge_graph.merge_value = merge_value
    merge_graph.coalesce_relations = safe_coalesce_relations
    return merge_graph.main()


if __name__ == "__main__":
    raise SystemExit(main())
