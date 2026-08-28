"""Governed CaseBundle contracts for criminal-law case learning."""

from .selection import select_diverse_cases
from .service import CaseBundleService, get_case_bundle_service

__all__ = ["CaseBundleService", "get_case_bundle_service", "select_diverse_cases"]
