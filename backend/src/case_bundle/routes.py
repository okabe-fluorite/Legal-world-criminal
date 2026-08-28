from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from .service import get_case_bundle_service


Stage = Literal["LC", "INV", "PR", "DS", "CR", "CRA"]
router = APIRouter(prefix="/api/case-bundles", tags=["case-bundles"])


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    return get_case_bundle_service().catalog()


@router.get("/{case_id}")
def public_bundle(case_id: str, stage: Stage | None = None) -> dict[str, Any]:
    try:
        result = get_case_bundle_service().public_bundle(case_id, stage=stage)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="case bundle not found")
    return result


__all__ = ["router"]
