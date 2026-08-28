from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE_PATH = REPO_ROOT / "dataset" / "case_bundles.jsonl"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "dataset" / "case_bundle_evidence.jsonl"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "dataset" / "case_bundle_manifest.json"
PRIVATE_KEYS = {"reference_private", "teacher_reference_private", "typical_errors_private"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CaseBundleService:
    def __init__(
        self,
        *,
        bundle_path: Path = DEFAULT_BUNDLE_PATH,
        evidence_path: Path = DEFAULT_EVIDENCE_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> None:
        self.bundle_path = Path(bundle_path)
        self.evidence_path = Path(evidence_path)
        self.manifest_path = Path(manifest_path)
        self.bundles = _read_jsonl(self.bundle_path)
        self.evidence = _read_jsonl(self.evidence_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        expected_files = self.manifest.get("files") or {}
        for path in (self.bundle_path, self.evidence_path):
            expected = (expected_files.get(path.name) or {}).get("sha256")
            if not expected or _sha256(path) != expected:
                raise ValueError(f"CaseBundle manifest hash mismatch: {path.name}")
        self.by_runtime_id = {
            str(row["runtime_case_id"]): row for row in self.bundles
        }
        self.by_bundle_id = {str(row["case_bundle_id"]): row for row in self.bundles}
        self.by_original_id = {
            str(row["original_case_id"]): row for row in self.bundles
        }
        self.evidence_by_id = {str(row["evidence_id"]): row for row in self.evidence}

    def resolve(self, case_id: str) -> dict[str, Any] | None:
        value = str(case_id or "").strip()
        if value in self.by_runtime_id:
            return self.by_runtime_id[value]
        if value in self.by_bundle_id:
            return self.by_bundle_id[value]
        if value.startswith("case_"):
            return None
        return self.by_original_id.get(value)

    @staticmethod
    def _catalog_item(bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_bundle_id": bundle["case_bundle_id"],
            "runtime_case_id": bundle["runtime_case_id"],
            "original_case_id": bundle["original_case_id"],
            "title": bundle["title"],
            "case_cause": bundle["case_cause"],
            "charge": bundle["charge"],
            "version": bundle["version"],
            "content_sha256": bundle["content_sha256"],
            "knowledge_links": copy.deepcopy(bundle["knowledge_links"]),
            "evidence_ids": list(bundle["evidence_ids"]),
            "review": copy.deepcopy(bundle["review"]),
            "available_stages": [
                stage
                for stage, packet in bundle["stage_packets"].items()
                if packet.get("availability") == "available"
            ],
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": "criminal-law-case-bundle-catalog-v1",
            "counts": dict(self.manifest.get("counts") or {}),
            "selection_policy": self.manifest.get("selection_policy"),
            "bundles": [self._catalog_item(bundle) for bundle in self.bundles],
            "manifest_sha256": _sha256(self.manifest_path),
            "limits": list(self.manifest.get("limits") or []),
        }

    def public_bundle(
        self,
        case_id: str,
        *,
        stage: str | None = None,
    ) -> dict[str, Any] | None:
        bundle = self.resolve(case_id)
        if bundle is None:
            return None
        payload = {
            "schema_version": "criminal-law-public-case-bundle-v1",
            **self._catalog_item(bundle),
            "student_brief": copy.deepcopy(bundle["student_brief"]),
            "provenance": {
                key: bundle["provenance"].get(key)
                for key in (
                    "source_title",
                    "issuing_authority",
                    "released_at",
                    "source_reference",
                    "source_url",
                    "local_source_sha256",
                )
            },
            "evidences": [
                copy.deepcopy(self.evidence_by_id[evidence_id])
                for evidence_id in bundle["evidence_ids"]
                if evidence_id in self.evidence_by_id
            ],
            "requested_stage": None,
            "stage_packet": None,
            "warnings": [
                "public projection excludes teacher references, expected errors, and outcomes",
                "law evidence does not predetermine the legal conclusion",
            ],
        }
        if stage:
            normalized = str(stage).strip().upper()
            packet = bundle["stage_packets"].get(normalized)
            if packet is None:
                raise ValueError(f"unknown case stage: {stage}")
            payload["requested_stage"] = normalized
            payload["stage_packet"] = {
                "stage": packet["stage"],
                "stage_name": packet["stage_name"],
                "availability": packet["availability"],
                "student_visible": copy.deepcopy(packet["student_visible"]),
                "rubric": copy.deepcopy(packet["rubric"]),
            }
        return payload

    def teacher_bundle(self, case_id: str) -> dict[str, Any] | None:
        bundle = self.resolve(case_id)
        return copy.deepcopy(bundle) if bundle else None

    def teacher_gold(self, case_id: str, stage: str) -> dict[str, Any] | None:
        bundle = self.resolve(case_id)
        if bundle is None:
            return None
        normalized = str(stage or "").strip().upper()
        stage_gold = (
            (bundle.get("reference_private") or {}).get("stage_gold") or {}
        ).get(normalized)
        if not isinstance(stage_gold, dict):
            return None
        gold = copy.deepcopy(stage_gold)
        gold.update(
            {
                "case_cause": bundle["case_cause"],
                "charge": bundle["charge"],
                "knowledge_points": [
                    {
                        "knowledge_id": row["knowledge_id"],
                        "knowledge_name": row["knowledge_name"],
                        "role": row["role"],
                    }
                    for row in bundle["knowledge_links"]
                ],
                "gold_incomplete": False,
                "missing_fields": [],
                "case_bundle_id": bundle["case_bundle_id"],
                "case_bundle_version": bundle["version"],
                "case_bundle_content_sha256": bundle["content_sha256"],
                "law_corpus_manifest_sha256": bundle["law_corpus_manifest_sha256"],
                "rubric_version": bundle["stage_packets"][normalized]["rubric"][
                    "schema_version"
                ],
            }
        )
        return gold

    def versions(self, case_id: str) -> dict[str, str] | None:
        bundle = self.resolve(case_id)
        if bundle is None:
            return None
        return {
            "case_bundle_id": bundle["case_bundle_id"],
            "case_bundle_version": bundle["version"],
            "case_bundle_content_sha256": bundle["content_sha256"],
            "law_corpus_manifest_sha256": bundle["law_corpus_manifest_sha256"],
            "rubric_version": "criminal-law-stage-rubric-v1",
        }


@lru_cache(maxsize=1)
def get_case_bundle_service() -> CaseBundleService:
    return CaseBundleService()


__all__ = ["CaseBundleService", "PRIVATE_KEYS", "get_case_bundle_service"]
