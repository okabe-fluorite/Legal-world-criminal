from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


NPC_DETAIL_ENDPOINT = "https://flk.npc.gov.cn/law-search/search/flfgDetails"
NPC_STATUS = {
    1: ("repealed", "已废止"),
    2: ("superseded", "已修改"),
    3: ("verified_current", "有效"),
    4: ("unresolved", "尚未生效"),
}


def normalize_title(value: Any) -> str:
    return re.sub(r"[\s　《》〈〉（）()\[\]【】·,，。]", "", str(value or "")).lower()


def npc_document_id(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.lower() != "flk.npc.gov.cn":
        return ""
    return str((parse_qs(parsed.query).get("id") or [""])[0]).strip()


def fetch_npc_detail(document_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    url = f"{NPC_DETAIL_ENDPOINT}?{urlencode({'bbbs': document_id})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "LegalWorld-Verification/1.0"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed official host
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or int(payload.get("code") or 0) != 200:
        raise RuntimeError(str(payload.get("msg") or "official NPC detail API failed"))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("official NPC detail API returned no data")
    return data


def project_npc_status(
    source: dict[str, Any],
    detail: dict[str, Any],
    *,
    checked_at: str | None = None,
) -> dict[str, Any]:
    official_code = int(detail.get("sxx") or 0)
    status, status_label = NPC_STATUS.get(official_code, ("unresolved", "未知状态"))
    source_title = str(source.get("title") or "").strip()
    official_title = str(detail.get("title") or "").strip()
    title_matches = bool(
        source_title
        and official_title
        and (
            normalize_title(source_title) == normalize_title(official_title)
            or normalize_title(source_title) in normalize_title(official_title)
            or normalize_title(official_title) in normalize_title(source_title)
        )
    )
    if not title_matches:
        status = "unresolved"
    document_id = npc_document_id(str(source.get("official_source_url") or ""))
    return {
        "document_id": str(source.get("document_id") or ""),
        "source_type": str(source.get("source_type") or "law"),
        "title": source_title,
        "document_number": str(source.get("document_number") or ""),
        "issuing_authority": str(detail.get("zdjgName") or source.get("issuing_authority") or ""),
        "promulgated_date": str(detail.get("gbrq") or source.get("promulgated_date") or ""),
        "effective_date": str(detail.get("sxrq") or source.get("effective_date") or ""),
        "revision_date": str(source.get("revision_date") or ""),
        "expiry_date": str(source.get("expiry_date") or ""),
        "effective_status": status,
        "official_source_url": f"https://flk.npc.gov.cn/detail.html?id={document_id}" if document_id else "",
        "official_status_code": official_code,
        "official_status_label": status_label,
        "official_category": str(detail.get("flxz") or ""),
        "official_title": official_title,
        "official_title_matches": title_matches,
        "verification_method": "official_npc_status_api",
        "verification_status": "verified" if title_matches and official_code in NPC_STATUS else "unresolved",
        "notes": (
            f"国家法律法规数据库详情API：sxx={official_code}（{status_label}）；"
            f"官方标题{'匹配' if title_matches else '不匹配'}。"
        ),
        "checked_at": checked_at or date.today().isoformat(),
    }


def recheck_one(
    source: dict[str, Any],
    *,
    fetcher: Callable[[str], dict[str, Any]] = fetch_npc_detail,
    attempts: int = 3,
) -> dict[str, Any]:
    document_id = npc_document_id(str(source.get("official_source_url") or ""))
    if not document_id:
        return {
            **source,
            "effective_status": "unresolved",
            "verification_status": "unresolved",
            "verification_method": "official_npc_status_api",
            "notes": "缺少可解析的国家法律法规数据库详情ID。",
            "checked_at": date.today().isoformat(),
        }
    last_error = ""
    for attempt in range(max(1, attempts)):
        try:
            return project_npc_status(source, fetcher(document_id))
        except Exception as exc:  # noqa: BLE001 - retry and sanitize below
            last_error = f"{type(exc).__name__}: {exc}"[:240]
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2**attempt))
    return {
        **source,
        "effective_status": "unresolved",
        "verification_status": "unresolved",
        "verification_method": "official_npc_status_api",
        "notes": f"国家法律法规数据库详情API暂不可用：{last_error}",
        "checked_at": date.today().isoformat(),
    }


def recheck_laws(
    sources: Iterable[dict[str, Any]],
    *,
    workers: int = 24,
    fetcher: Callable[[str], dict[str, Any]] = fetch_npc_detail,
) -> list[dict[str, Any]]:
    return sorted(
        iter_rechecked_laws(sources, workers=workers, fetcher=fetcher),
        key=lambda row: str(row.get("document_id") or ""),
    )


def iter_rechecked_laws(
    sources: Iterable[dict[str, Any]],
    *,
    workers: int = 24,
    fetcher: Callable[[str], dict[str, Any]] = fetch_npc_detail,
) -> Iterable[dict[str, Any]]:
    rows = [dict(row) for row in sources if str(row.get("source_type") or "") == "law"]
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 64))) as executor:
        futures = {executor.submit(recheck_one, row, fetcher=fetcher): row for row in rows}
        for future in as_completed(futures):
            yield future.result()


__all__ = [
    "NPC_DETAIL_ENDPOINT",
    "NPC_STATUS",
    "fetch_npc_detail",
    "npc_document_id",
    "project_npc_status",
    "iter_rechecked_laws",
    "recheck_laws",
    "recheck_one",
]
