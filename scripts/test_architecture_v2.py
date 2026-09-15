from __future__ import annotations

import unittest

from filter_graph_asof import filter_graph
from nkg.core.runtime import GraphRuntime
from nkg.extraction.packet import build_extraction_packet, choose_retrieval_level
from nkg.temporal.checkpoints import checkpoint_chapters, graph_fingerprint
from nkg.validation.accuracy import compare_outputs
from nkg.validation.invariants import validate_invariants
from nkg.views.quality import build_quality_summary
from nkg.views.snapshot_diff import diff_snapshots
from test_final_delivery import fixture_graph


class RuntimeTests(unittest.TestCase):
    def test_runtime_indexes_state_and_neighbors(self):
        graph = fixture_graph()
        runtime = GraphRuntime(graph)
        self.assertEqual(runtime.entity("hero")["id"], "hero")
        self.assertEqual(runtime.state_at("hero", 5)["inventory_quantity"]["value"], 1)
        self.assertIn("skill", runtime.connected_entities({"hero"}, 8, hops=1))
        self.assertTrue(runtime.events_for("hero", 1, 3))


class ExtractionPacketTests(unittest.TestCase):
    def test_packet_escalates_and_never_truncates_accuracy_inputs(self):
        graph = fixture_graph()
        candidates = [{"id": "cand1", "kind": "commitment", "entity_id": "hero", "mandatory": True}]
        packet = build_extraction_packet(
            graph,
            [{"chapter": 2, "text": "早期名终于再次承诺一定会回来。"}],
            chapter_start=2,
            chapter_end=2,
            candidates=candidates,
            max_context_chars=1,
        )
        self.assertEqual(packet["retrieval_level"], "R3")
        self.assertEqual(packet["candidate_records"], candidates)
        self.assertIn("commitments", packet["schema_slice"])
        self.assertIn("hero", packet["entity_ids"])
        self.assertTrue(packet["token_telemetry"]["budget_exceeded"])
        self.assertFalse(packet["token_telemetry"]["truncated_for_budget"])
        self.assertTrue(packet["accuracy_contract"]["candidate_recall_must_not_drop"])

    def test_universal_claim_forces_r4_and_cannot_be_downgraded(self):
        self.assertEqual(choose_retrieval_level("他从未使用过这门技能。"), "R4")
        packet = build_extraction_packet(
            fixture_graph(),
            [{"chapter": 2, "text": "早期名从未使用过这门技能。"}],
            chapter_start=2,
            chapter_end=2,
            requested_level="R1",
        )
        self.assertEqual(packet["retrieval_level"], "R4")
        self.assertTrue(packet["accuracy_contract"]["global_search_required"])


class AccuracyAndInvariantTests(unittest.TestCase):
    def test_accuracy_gate_fails_when_confirmed_fact_or_evidence_is_dropped(self):
        baseline = {"entities": [{"id": "a", "evidence_ids": ["e1"]}], "evidence": [{"id": "e1"}], "candidates": [{"id": "c1", "high_risk": True}]}
        optimized = {"entities": [{"id": "a", "evidence_ids": []}], "evidence": [{"id": "e1"}], "candidates": []}
        report = compare_outputs(baseline, optimized)
        self.assertFalse(report["valid"])
        self.assertEqual(report["high_risk_candidate_recall"], 0.0)
        self.assertTrue(report["evidence_regressions"])

    def test_invariant_engine_detects_explicit_state_chain_break(self):
        graph = fixture_graph()
        graph["state_changes"].append({
            "id": "bad_chain", "entity_id": "hero", "facet": "inventory_quantity", "action": "gained",
            "chapter": 9, "before": 2, "after": 3, "reason": "fixture", "evidence_ids": ["e9"], "confidence": "explicit",
        })
        report = validate_invariants(graph)
        self.assertIn("state_chain_discontinuity", report["counts"])

    def test_quality_metrics_are_derived_not_story_facts(self):
        report = build_quality_summary(fixture_graph())
        self.assertTrue(report["derived_only"])
        self.assertIn("evidence", report)
        self.assertIn("invariants", report)


class TemporalUtilityTests(unittest.TestCase):
    def test_checkpoint_plan_and_snapshot_diff(self):
        self.assertEqual(checkpoint_chapters(1, 120, 50), [1, 50, 100, 120])
        graph = fixture_graph()
        self.assertEqual(graph_fingerprint(graph), graph_fingerprint(graph))
        before = filter_graph(graph, 5, strict=True)
        after = filter_graph(graph, 8, strict=True)
        diff = diff_snapshots(before, after)
        self.assertGreaterEqual(diff["summary"]["new_events"], 1)
        self.assertGreaterEqual(diff["summary"]["changed_state_facets"], 1)


if __name__ == "__main__":
    unittest.main()
