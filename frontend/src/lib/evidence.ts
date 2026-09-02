import type { EvidenceReference, TypicalQuestionSource } from "./types";

export interface EvidenceLike {
  id?: string;
  evidence_id?: string;
  source_id?: string;
  source_type?: string;
  title?: string;
  source_title?: string;
  article_ref?: string;
  quote?: string;
  authority?: string;
  authority_level?: string;
  effective_from?: string;
  effective_status?: string;
  version?: string;
  source_url?: string;
  source_snapshot_id?: string;
  sha256?: string;
  source_bundle_sha256?: string;
  local_source_sha256?: string;
  risk_flags?: string[];
  allowed_usage?: string[];
  document_number?: string;
  parent_context?: EvidenceReference["parent_context"];
  issuing_authority?: string;
  promulgated_date?: string;
  effective_date?: string;
  expiry_date?: string;
  official_source_url?: string;
  verification_method?: string;
  verification_status?: string;
  source_use?: string;
}

export function toEvidenceReference(value: EvidenceLike, fallbackId = "evidence"): EvidenceReference {
  const title = String(value.title || value.source_title || "受治理Evidence");
  const article = String(value.article_ref || "");
  return {
    id: String(value.id || value.evidence_id || value.source_id || `${fallbackId}:${title}:${article}`),
    source_type: String(value.source_type || (article ? "法律条文" : "教学证据")),
    title,
    article_ref: article,
    quote: String(value.quote || ""),
    authority: String(value.authority || value.authority_level || "待复核"),
    effective_status: String(value.effective_status || ""),
    version: String(value.version || value.effective_from || ""),
    source_url: String(value.source_url || ""),
    source_snapshot_id: String(value.source_snapshot_id || ""),
    sha256: String(value.sha256 || value.source_bundle_sha256 || value.local_source_sha256 || ""),
    risk_flags: Array.isArray(value.risk_flags) ? value.risk_flags.map(String) : [],
    allowed_usage: Array.isArray(value.allowed_usage) ? value.allowed_usage.map(String) : [],
    document_number: String(value.document_number || ""),
    parent_context: value.parent_context ?? null,
    issuing_authority: String(value.issuing_authority || ""),
    promulgated_date: String(value.promulgated_date || ""),
    effective_date: String(value.effective_date || value.effective_from || ""),
    expiry_date: String(value.expiry_date || ""),
    official_source_url: String(value.official_source_url || value.source_url || ""),
    verification_method: String(value.verification_method || ""),
    verification_status: String(value.verification_status || ""),
    source_use: String(value.source_use || ""),
  };
}

export function typicalSourceReference(source: TypicalQuestionSource): EvidenceReference {
  return toEvidenceReference({
    ...source,
    id: source.source_id,
    effective_status: "以冻结版本为准",
  }, source.source_id);
}

export function shortEvidenceText(value: string, limit = 92): string {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  return normalized.length > limit ? `${normalized.slice(0, limit)}…` : normalized;
}
