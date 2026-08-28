from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from src.case_bundle.routes import router
from src.case_bundle.selection import select_diverse_cases
from src.case_bundle.service import PRIVATE_KEYS, CaseBundleService
from src.data.data_loader import DataLoader
from src.teaching import transcript
from src.teaching.scorer import TeachingScorer


REPO_ROOT = Path(__file__).resolve().parents[2]


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


class CaseBundleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CaseBundleService()

    def test_manifest_schema_and_runtime_mapping_match_seed_selection(self) -> None:
        released = json.loads(
            (REPO_ROOT / "dataset" / "released_case_dataset.json").read_text(
                encoding="utf-8"
            )
        )
        selected = select_diverse_cases(list(released), len(released))
        expected = {
            f"case_{index}": int(record["original_id"])
            for index, record in enumerate(selected, start=1)
        }
        actual = {
            runtime_id: int(row["original_case_id"])
            for runtime_id, row in self.service.manifest["runtime_mapping"].items()
        }
        self.assertEqual(actual, expected)
        self.assertEqual(actual, {"case_1": 1, "case_2": 3, "case_3": 2})
        schema = json.loads(
            (REPO_ROOT / "schemas" / "case-bundle-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for bundle in self.service.bundles:
            Draft202012Validator(schema).validate(bundle)
            self.assertEqual(set(bundle["stage_packets"]), {"LC", "INV", "PR", "DS", "CR", "CRA"})
            self.assertTrue(bundle["evidence_ids"])
            for role in ("plaintiff", "defendant"):
                config_path = (
                    REPO_ROOT
                    / "backend"
                    / "sandbox_seed_data"
                    / "cases"
                    / bundle["runtime_case_id"]
                    / role
                    / "config.yaml"
                )
                config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                self.assertEqual(config["original_case_id"], bundle["original_case_id"])
                self.assertEqual(config["case_bundle_id"], bundle["case_bundle_id"])
                self.assertEqual(
                    config["case_bundle_content_sha256"], bundle["content_sha256"]
                )

    def test_public_projection_excludes_teacher_reference_and_outcome_leakage(self) -> None:
        for bundle in self.service.bundles:
            public = self.service.public_bundle(bundle["runtime_case_id"])
            self.assertTrue(PRIVATE_KEYS.isdisjoint(set(nested_keys(public))))
            self.assertNotIn("guiding_points", set(nested_keys(public)))
            self.assertNotIn("reference_judgment", set(nested_keys(public)))
            self.assertNotIn("court_opinion", set(nested_keys(public)))
            self.assertNotIn("main_sentence", set(nested_keys(public)))
            self.assertEqual(
                len(public["evidences"]), len(bundle["evidence_ids"])
            )
            for stage in ("LC", "INV", "PR", "DS", "CR", "CRA"):
                staged = self.service.public_bundle(bundle["runtime_case_id"], stage=stage)
                self.assertEqual(staged["requested_stage"], stage)
                self.assertTrue(PRIVATE_KEYS.isdisjoint(set(nested_keys(staged))))

        # runtime case_2 maps to original case 3, which did not enter appeal.
        no_appeal = self.service.public_bundle("case_2", stage="CRA")
        self.assertEqual(no_appeal["stage_packet"]["availability"], "not_applicable")

    def test_teaching_gold_uses_runtime_bundle_mapping_not_raw_numeric_id(self) -> None:
        case_2_record = transcript.find_dataset_case("case_2")
        case_3_record = transcript.find_dataset_case("case_3")
        self.assertEqual(case_2_record["original_id"], 3)
        self.assertEqual(case_3_record["original_id"], 2)
        case_2_gold = transcript.load_gold("case_2", "DS")
        case_3_gold = transcript.load_gold("case_3", "DS")
        self.assertEqual(case_2_gold["charge"], "抢劫罪")
        self.assertIn("故意伤害", case_3_gold["charge"])
        self.assertEqual(
            case_2_gold["case_bundle_id"],
            self.service.resolve("case_2")["case_bundle_id"],
        )
        seed_root = REPO_ROOT / "backend" / "sandbox_seed_data"
        loader = DataLoader(str(seed_root / "case_data_extracted.json"))
        case_2_config = yaml.safe_load(
            (seed_root / "cases" / "case_2" / "defendant" / "config.yaml").read_text(
                encoding="utf-8"
            )
        )
        resolved = loader.resolve_case_for_config(case_2_config)
        self.assertEqual(resolved["original_id"], 3)

    def test_learning_event_identity_and_payload_bind_case_versions(self) -> None:
        versions = self.service.versions("case_2")
        kwargs = {
            "case_id": "case_2",
            "stage": "DS",
            "charge": "抢劫罪",
            "student_id": "student",
            "payload": {"capability_scores": {}},
            "law_citations": [],
            "gold_incomplete": False,
            "utterance_texts": ["独立学生回答"],
            "utterances": [
                {
                    "request_id": "req-versioned",
                    "text": "独立学生回答",
                    "final_text": "独立学生回答",
                    "assist_mode": "none",
                    "timestamp": "2026-08-28T00:00:00+08:00",
                }
            ],
            "source_versions": versions,
        }
        first = TeachingScorer()._build_learning_event(**kwargs)
        changed_versions = {**versions, "case_bundle_content_sha256": "f" * 64}
        second = TeachingScorer()._build_learning_event(
            **{**kwargs, "source_versions": changed_versions}
        )
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["case_bundle_id"], versions["case_bundle_id"])
        self.assertEqual(
            first["case_bundle_content_sha256"],
            versions["case_bundle_content_sha256"],
        )
        self.assertEqual(first["rubric_version"], "criminal-law-stage-rubric-v1")

    def test_public_api_is_callable_and_runtime_mapping_is_visible(self) -> None:
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            catalog = client.get("/api/case-bundles/catalog")
            staged = client.get("/api/case-bundles/case_2?stage=DS")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()["counts"]["case_bundles"], 3)
        self.assertEqual(staged.status_code, 200)
        self.assertEqual(staged.json()["original_case_id"], 3)
        self.assertEqual(staged.json()["requested_stage"], "DS")


if __name__ == "__main__":
    unittest.main()
