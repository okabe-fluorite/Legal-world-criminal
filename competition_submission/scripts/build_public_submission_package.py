"""Build a privacy-gated public XH-202620 submission DRAFT package.

The package contains sanitized source code, PPT, narrated video, effect report,
public ethics materials, and public audits. Private signatures, consents,
password hashes, databases, local runtime backups, and original secret values
are excluded and scanned before the package is emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader


REPO = Path(__file__).resolve().parents[2]
SUBMISSION = REPO / "competition_submission"
DEFAULT_OUTPUT = SUBMISSION / "07-公开提交包_DRAFT"
ENV_EXAMPLE = REPO / ".env.example"
VIDEO = SUBMISSION / "offline_backup" / "narrated-video-proposed-final" / "星火智学_真实交互演示_AI配音_DRAFT.mp4"

SENSITIVE_ENV_NAME = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN|DATABASE_URL|TEACHER_EMAILS|ADMIN_EMAILS)", re.I)
PRIVATE_PATH_PATTERNS = ("D:\\Code\\", "E:\\guabangjieshuai\\", "C:\\Users\\26967\\")
SECRET_TOKEN_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOWED_EMAIL_DOMAINS = {"example.com", "localhost", "court.edu", "school.edu"}
REQUIRED_SOURCE_ENTRIES = {
    ".env.example",
    "README.md",
    "requirements.lock.txt",
    "backend/ws_server.py",
    "backend/legal_corpus/processed/law_corpus_manifest.json",
    "frontend/package-lock.json",
    "frontend/src/components/CognitiveDashboard.vue",
    "adaptive_service/requirements.txt",
    "adaptive_service/src/edubrain_adaptive/api.py",
    "schemas/evidence-pack-v1.schema.json",
    "competition_submission/scripts/build_narrated_demo.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO)
    return [Path(value.decode("utf-8")) for value in raw.split(b"\0") if value]


def source_allowed(path: Path) -> bool:
    value = path.as_posix()
    if value in {"AGENTS.md", "CLAUDE.md"}:
        return False
    if value.startswith("competition_submission/"):
        return value.startswith("competition_submission/scripts/")
    if value.startswith((".git/", ".claude/", ".codex-artifacts/", "tmp/")):
        return False
    return True


def parse_env() -> tuple[str, dict[str, str]]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    sanitized: list[str] = []
    sensitive_values: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            sanitized.append(line)
            continue
        name, value = match.group(1), match.group(2).strip()
        if SENSITIVE_ENV_NAME.search(name):
            if value and len(value) >= 8:
                sensitive_values[name] = value
            sanitized.append(f"{name}=")
        else:
            sanitized.append(line)
    sanitized.insert(0, "# PUBLIC SANITIZED TEMPLATE: all keys, passwords, JWT secrets, emails and database URLs are blank")
    return "\n".join(sanitized) + "\n", sensitive_values


def safe_text(data: bytes) -> str | None:
    if b"\0" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None


def sanitize_private_paths(data: bytes) -> bytes:
    text = safe_text(data)
    if text is None:
        return data
    for pattern in PRIVATE_PATH_PATTERNS:
        text = re.sub(
            re.escape(pattern),
            lambda _match: "<LOCAL_WORKSPACE>\\",
            text,
            flags=re.I,
        )
    return text.encode("utf-8")


def build_source_zip(path: Path) -> tuple[int, dict[str, str]]:
    sanitized_env, sensitive_values = parse_env()
    entries = 0
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(tracked_files(), key=lambda value: value.as_posix()):
            if not source_allowed(relative):
                continue
            if relative.as_posix() == ".env.example":
                data = sanitized_env.encode("utf-8")
            else:
                source = REPO / relative
                if not source.is_file():
                    continue
                data = sanitize_private_paths(source.read_bytes())
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            entries += 1
    return entries, sensitive_values


def public_materials() -> dict[str, Path]:
    return {
        "01-作品方案/星火智学_作品方案_Guizang_DRAFT.pptx": SUBMISSION / "04-作品方案" / "星火智学_作品方案_Guizang_DRAFT.pptx",
        "02-演示视频/星火智学_真实交互演示_AI配音_DRAFT.mp4": VIDEO,
        "03-效果验证/星火智学效果验证报告_DRAFT.pdf": SUBMISSION / "06-效果验证" / "效果验证报告包_DRAFT" / "public" / "星火智学效果验证报告_DRAFT.pdf",
        "03-效果验证/EVIDENCE_INDEX.json": SUBMISSION / "06-效果验证" / "效果验证报告包_DRAFT" / "public" / "EVIDENCE_INDEX.json",
        "04-伦理与安全/伦理与安全合规声明正文.pdf": SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT" / "public" / "伦理与安全合规声明正文.pdf",
        "04-伦理与安全/签署前核对清单.pdf": SUBMISSION / "02-伦理与安全" / "伦理签署包_DRAFT" / "public" / "签署前核对清单.pdf",
        "06-公开审计/FINAL_SUBMISSION_AUDIT_DRAFT.json": SUBMISSION / "00-提交清单" / "FINAL_SUBMISSION_AUDIT_DRAFT.json",
        "06-公开审计/FINAL_SUBMISSION_AUDIT_DRAFT.md": SUBMISSION / "00-提交清单" / "FINAL_SUBMISSION_AUDIT_DRAFT.md",
        "06-公开审计/NARRATED_VIDEO_DRAFT_AUDIT.json": SUBMISSION / "03-Demo" / "NARRATED_VIDEO_DRAFT_AUDIT.json",
        "06-公开审计/LEGAL_SOURCE_CURRENCY_AUDIT.json": SUBMISSION / "03-Demo" / "LEGAL_SOURCE_CURRENCY_AUDIT.json",
        "06-公开审计/LEGAL_SOURCE_CURRENCY_AUDIT.md": SUBMISSION / "03-Demo" / "LEGAL_SOURCE_CURRENCY_AUDIT.md",
        "06-公开审计/FROZEN_DEMO_AUDIT.json": SUBMISSION / "03-Demo" / "FROZEN_DEMO_AUDIT.json",
        "06-公开审计/25帧视觉接触表.png": SUBMISSION / "06-效果验证" / "视频审片包_DRAFT" / "25帧视觉接触表.png",
        "06-公开审计/视频技术审计与时间轴.pdf": SUBMISSION / "06-效果验证" / "视频审片包_DRAFT" / "public" / "视频技术审计与时间轴.pdf",
        "06-公开审计/专家审核包_MANIFEST_DRAFT.md": SUBMISSION / "06-效果验证" / "专家审核包_MANIFEST_DRAFT.md",
        "06-公开审计/目标用户试用包_MANIFEST_DRAFT.md": SUBMISSION / "06-效果验证" / "目标用户试用包_MANIFEST_DRAFT.md",
        "06-公开审计/伦理签署包_MANIFEST_DRAFT.md": SUBMISSION / "02-伦理与安全" / "伦理签署包_MANIFEST_DRAFT.md",
        "06-公开审计/视频审片包_MANIFEST_DRAFT.md": SUBMISSION / "06-效果验证" / "视频审片包_MANIFEST_DRAFT.md",
        "06-公开审计/效果验证报告包_MANIFEST_DRAFT.md": SUBMISSION / "06-效果验证" / "效果验证报告包_MANIFEST_DRAFT.md",
    }


def scan_source_zip(path: Path, sensitive_values: dict[str, str]) -> dict[str, Any]:
    forbidden_entries: list[str] = []
    private_path_hits: list[str] = []
    token_hits: list[str] = []
    original_value_hits: list[str] = []
    email_domains: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Source ZIP CRC test failed")
        names = archive.namelist()
        for name in names:
            lower = name.lower()
            if any(value in lower for value in ("offline_backup", "/private/", "_私密", ".db", ".sqlite", ".env.local")):
                forbidden_entries.append(name)
            data = archive.read(name)
            text = safe_text(data)
            if text is None:
                continue
            for pattern in PRIVATE_PATH_PATTERNS:
                if pattern.lower() in text.lower():
                    private_path_hits.append(f"{name}:{pattern}")
            for pattern in SECRET_TOKEN_PATTERNS:
                if pattern.search(text):
                    token_hits.append(name)
            for variable, value in sensitive_values.items():
                if value and value in text:
                    original_value_hits.append(f"{name}:{variable}")
            email_domains.update(match.group(1).lower() for match in EMAIL_PATTERN.finditer(text))
        env = archive.read(".env.example").decode("utf-8")
        for line in env.splitlines():
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if match and SENSITIVE_ENV_NAME.search(match.group(1)) and match.group(2).strip():
                original_value_hits.append(f".env.example:{match.group(1)}")
    required_missing = sorted(REQUIRED_SOURCE_ENTRIES - set(names))
    disallowed_email_domains = sorted(email_domains - ALLOWED_EMAIL_DOMAINS)
    return {
        "entry_count": len(names),
        "forbidden_entries": sorted(set(forbidden_entries)),
        "private_path_hits": sorted(set(private_path_hits)),
        "secret_token_hits": sorted(set(token_hits)),
        "original_sensitive_value_hits": sorted(set(original_value_hits)),
        "email_domains": sorted(email_domains),
        "disallowed_email_domains": disallowed_email_domains,
        "required_entry_count": len(REQUIRED_SOURCE_ENTRIES),
        "required_entries_missing": required_missing,
        "sanitized_env_present": True,
        "passed": not any((forbidden_entries, private_path_hits, token_hits, original_value_hits, disallowed_email_domains, required_missing)),
    }


def scan_public_files(files: dict[str, Path]) -> dict[str, Any]:
    forbidden_names: list[str] = []
    private_path_hits: list[str] = []
    secret_hits: list[str] = []
    identity_hits: list[str] = []
    for target, source in files.items():
        lower = target.lower()
        if any(value in lower for value in ("private", "私密", "consent", "签署页", ".db", ".sqlite", "offline_backup")):
            forbidden_names.append(target)
        text = ""
        if source.suffix.lower() == ".pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(source)).pages)
        elif source.suffix.lower() in {".md", ".json", ".txt", ".html"}:
            text = source.read_text(encoding="utf-8")
        if text:
            for pattern in PRIVATE_PATH_PATTERNS:
                if pattern.lower() in text.lower():
                    private_path_hits.append(f"{target}:{pattern}")
            for pattern in SECRET_TOKEN_PATTERNS:
                if pattern.search(text):
                    secret_hits.append(target)
            if any(value in text for value in ("[本人签字]", "参与者姓名", "团队负责人姓名")):
                identity_hits.append(target)
    return {
        "file_count": len(files),
        "forbidden_name_hits": forbidden_names,
        "private_path_hits": private_path_hits,
        "secret_token_hits": secret_hits,
        "identity_field_hits": identity_hits,
        "passed": not any((forbidden_names, private_path_hits, secret_hits, identity_hits)),
    }


def zip_write(path: Path, root: Path, files: dict[str, Path], extra: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for target, source in sorted(files.items()):
            info = zipfile.ZipInfo(target, date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())
        for target, data in sorted(extra.items()):
            info = zipfile.ZipInfo(target, date_time=(2026, 8, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    materials = public_materials()
    missing = [target for target, source in materials.items() if not source.is_file()]
    if missing:
        raise SystemExit(f"Missing public materials: {missing}")
    source_zip = output / "LegalWorld-星火智学-源码_DRAFT.zip"
    source_entries, sensitive_values = build_source_zip(source_zip)
    source_scan = scan_source_zip(source_zip, sensitive_values)
    public_scan = scan_public_files(materials)
    if not source_scan["passed"] or not public_scan["passed"]:
        raise SystemExit(f"Public package scan failed: {source_scan} / {public_scan}")
    deliverables = {**materials, "05-代码/LegalWorld-星火智学-源码_DRAFT.zip": source_zip}
    manifest = {
        "schema": "xh-202620-public-submission-draft-manifest-v1",
        "source_git_commit": git_output("rev-parse", "HEAD"),
        "package_build_date": date(2026, 8, 30).isoformat(),
        "files": [{"path": target, "bytes": source.stat().st_size, "sha256": sha256(source)} for target, source in sorted(deliverables.items())],
        "source_code": {"entry_count": source_entries, "sha256": sha256(source_zip), "sanitized_env": True},
        "pending": {
            "expert_review": True,
            "real_target_users": 2,
            "ethics_signatures": 3,
            "video_approvals": 3,
            "effect_report_approvals": 3,
        },
        "ready_for_final_submission": False,
        "evidence_boundary": "Public DRAFT package only; human review, users, signatures and approvals remain pending",
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    readme = f"""# 星火智学 XH-202620 公开提交包（DRAFT）

源码commit：`{manifest['source_git_commit']}`

本包包含源码、PPT、121.6秒AI配音视频DRAFT、效果验证报告、伦理正文和公开审计。源码ZIP中的`.env.example`已自动脱敏，所有Key、密码、JWT、数据库URL和角色邮箱字段为空。

## 尚未完成

- 独立法学专家A/B审核；
- U01/U02两名真实目标用户试用；
- 三名伦理责任人签署；
- 内容/技术/隐私三人完整审片批准；
- 内容/数据/教学三人批准效果报告。

在上述事项完成前，本包必须保留`DRAFT/PENDING`，不得作为最终提交或学习效果证明。
""".encode("utf-8")
    package_zip = output / "星火智学_XH-202620_公开提交包_DRAFT.zip"
    zip_write(package_zip, output, deliverables, {"MANIFEST.json": manifest_bytes, "README_DRAFT.md": readme})
    with zipfile.ZipFile(package_zip) as archive:
        corrupt = archive.testzip()
        package_names = archive.namelist()
    if corrupt is not None:
        raise SystemExit(f"Public package CRC failed: {corrupt}")
    total_uncompressed = sum(row["bytes"] for row in manifest["files"])
    audit = {
        "schema": "xh-202620-public-submission-draft-build-audit-v1",
        "source_git_commit": manifest["source_git_commit"],
        "package_file": package_zip.name,
        "package_bytes": package_zip.stat().st_size,
        "package_sha256": sha256(package_zip),
        "package_entry_count": len(package_names),
        "total_uncompressed_bytes": total_uncompressed,
        "under_100_mb": package_zip.stat().st_size < 100 * 1024 * 1024,
        "source_code_scan": source_scan,
        "public_material_scan": public_scan,
        "crc_passed": True,
        "private_material_included": False,
        "ready_for_final_submission": False,
        "evidence_boundary": manifest["evidence_boundary"],
    }
    audit_path = output / "BUILD_AUDIT.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / f"{package_zip.name}.sha256.txt").write_text(f"{sha256(package_zip)}  {package_zip.name}\n", encoding="utf-8")
    (output / "MANIFEST.json").write_bytes(manifest_bytes)
    (output / "README_DRAFT.md").write_bytes(readme)
    print(json.dumps({"output": str(output), "package": str(package_zip), "package_bytes": package_zip.stat().st_size, "package_sha256": sha256(package_zip), "package_entries": len(package_names), "source_entries": source_entries, "under_100_mb": audit["under_100_mb"], "ready": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
