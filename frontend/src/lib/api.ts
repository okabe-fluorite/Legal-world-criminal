import type {
  AuthResponse,
  AdaptiveRecommendationResponse,
  CaseListResponse,
  CitationFeedback,
  CitationAuditResponse,
  ConfusionAnnotationPayload,
  ConfusionAnnotationResponse,
  EvidenceTimelineResponse,
  KnowledgeCatalogResponse,
  LearningEvent,
  LearningSupportSessionResponse,
  MediaAsset,
  MediaCapabilitiesResponse,
  MediaJob,
  ModelCatalogResponse,
  PlayerAssistResponse,
  PlayerRequest,
  SandboxState,
  SkillCardDetail,
  SkillCardSummary,
  StatusResponse,
  SubjectiveAttempt,
  SubjectiveAttemptResponse,
  SubjectiveAttemptHistoryResponse,
  SubjectiveCatalogResponse,
  TaskAttemptPayload,
  TaskAttemptResponse,
  TeachingReport,
  TeacherAnalyticsResponse,
  TeacherCaseBundleResponse,
  TeacherOverviewResponse,
  TeacherReviewCatalogResponse,
  TeacherSubjectiveQueueResponse,
  TypicalQuestionReport,
  TechnicalEvidenceSnapshot,
} from "./types";

const API_BASE = "/api";

export function getAccessToken(): string | null {
  return localStorage.getItem("lw.token");
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem("lw.token", token);
  else localStorage.removeItem("lw.token");
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.blob();
}

export const api = {
  async status(): Promise<StatusResponse> {
    return request<StatusResponse>("/status");
  },

  async register(email: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async me(): Promise<{ id: string; email: string; role?: string }> {
    return request("/auth/me");
  },

  async getSandbox(): Promise<SandboxState> {
    return request<SandboxState>("/sandbox");
  },

  async ensureSandbox(): Promise<SandboxState> {
    return request<SandboxState>("/sandbox/ensure", { method: "POST" });
  },

  async listCases(): Promise<CaseListResponse> {
    return request<CaseListResponse>("/sandbox/cases");
  },

  async startSandbox(caseId: string): Promise<SandboxState> {
    return request<SandboxState>("/sandbox/start", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    });
  },

  async pauseSandbox(): Promise<SandboxState> {
    return request<SandboxState>("/sandbox/pause", { method: "POST" });
  },

  async restartSandbox(): Promise<SandboxState> {
    return request<SandboxState>("/sandbox/restart", { method: "POST" });
  },

  async playerRuntime(caseId?: string): Promise<{
    player_mode: string;
    enabled: boolean;
    pending: PlayerRequest[];
    count: number;
  }> {
    const qs = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
    return request(`/sandbox/player-lawyer/runtime${qs}`);
  },

  async playerRespond(
    requestId: string,
    message: string,
    extras: {
      original_message?: string;
      polished_message?: string;
      hint_ids?: string[];
      skill_card_ids?: string[];
      assist_mode?: "none" | "polish" | "draft";
      used_ai_polish?: boolean;
    } = {},
  ): Promise<{
    success: boolean;
    request: PlayerRequest;
    citation_feedback?: CitationFeedback | null;
  }> {
    return request("/sandbox/player-lawyer/respond", {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        message,
        ...extras,
      }),
    });
  },

  async playerDraft(
    requestId: string,
    hintIds: string[] = [],
  ): Promise<PlayerAssistResponse> {
    return request("/sandbox/player-lawyer/draft-response", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, hint_ids: hintIds }),
    });
  },

  async playerPolish(
    requestId: string,
    message: string,
  ): Promise<PlayerAssistResponse> {
    return request("/sandbox/player-lawyer/polish-response", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, original_message: message }),
    });
  },

  // ── Teaching ──────────────────────────────────────────────────────

  /** 单阶段批阅结果；404 = 尚未批阅（轮询用，不抛错） */
  async teachingEvent(caseId: string, stage: string): Promise<LearningEvent | null> {
    try {
      return await request<LearningEvent>(
        `/teaching/event/${encodeURIComponent(caseId)}/${encodeURIComponent(stage)}`,
      );
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("404")) return null;
      throw err;
    }
  },

  async teachingReport(studentId: string): Promise<TeachingReport> {
    return request<TeachingReport>(
      `/teaching/report/${encodeURIComponent(studentId)}`,
    );
  },

  async adaptiveRecommendations(
    context: Record<string, unknown> = {},
  ): Promise<AdaptiveRecommendationResponse> {
    return request<AdaptiveRecommendationResponse>("/adaptive/recommend", {
      method: "POST",
      body: JSON.stringify(context),
    });
  },

  async adaptiveEvidenceTimeline(): Promise<EvidenceTimelineResponse> {
    return request<EvidenceTimelineResponse>("/adaptive/evidence-timeline");
  },

  async modelCatalog(): Promise<ModelCatalogResponse> {
    return request<ModelCatalogResponse>("/model/catalog");
  },

  async typicalQuestionReport(): Promise<TypicalQuestionReport> {
    return request<TypicalQuestionReport>("/competition/typical-questions");
  },

  async technicalEvidence(): Promise<TechnicalEvidenceSnapshot> {
    return request<TechnicalEvidenceSnapshot>("/competition/technical-evidence");
  },

  async mediaCapabilities(): Promise<MediaCapabilitiesResponse> {
    return request<MediaCapabilitiesResponse>("/media/capabilities");
  },

  async uploadMediaAsset(
    file: File,
    purpose: "transcription" | "visual_context" | "avatar_source",
  ): Promise<MediaAsset> {
    const body = new FormData();
    body.set("purpose", purpose);
    body.set("file", file);
    return request<MediaAsset>("/multimodal/assets", { method: "POST", body });
  },

  async downloadMediaAsset(assetId: string): Promise<Blob> {
    return requestBlob(`/multimodal/assets/${encodeURIComponent(assetId)}/content`);
  },

  async startTranscription(payload: {
    job_id: string;
    asset_id: string;
    language?: string;
    hotwords?: string[];
    provider?: string;
  }): Promise<MediaJob> {
    return request<MediaJob>("/multimodal/transcriptions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async startVisualAnalysis(payload: {
    job_id: string;
    asset_id: string;
    task: "ocr" | "argument_map_seed" | "case_material_summary";
    provider?: string;
  }): Promise<MediaJob> {
    return request<MediaJob>("/multimodal/visual-analyses", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async synthesizeSpeech(payload: {
    job_id: string;
    text: string;
    voice?: string;
    audio_format?: "mp3" | "wav" | "opus";
    provider?: string;
    ai_generated_disclosure?: boolean;
  }): Promise<MediaJob> {
    return request<MediaJob>("/speech/synthesis", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async renderAvatar(payload: {
    job_id: string;
    script: string;
    avatar_id?: string;
    voice?: string;
    provider?: string;
    ai_generated_disclosure?: boolean;
    likeness_consent_confirmed?: boolean;
  }): Promise<MediaJob> {
    return request<MediaJob>("/avatar/renders", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async mediaJob(jobId: string): Promise<MediaJob> {
    return request<MediaJob>(`/media/jobs/${encodeURIComponent(jobId)}`);
  },

  async auditKnowledgeCitations(citations: Array<{
    title: string;
    article_ref: string;
    quote: string;
    claim: string;
  }>): Promise<CitationAuditResponse> {
    return request<CitationAuditResponse>("/knowledge/audit-citations", {
      method: "POST",
      body: JSON.stringify({ citations }),
    });
  },

  async knowledgeCatalog(): Promise<KnowledgeCatalogResponse> {
    return request<KnowledgeCatalogResponse>("/knowledge/catalog");
  },

  async submitTaskAttempt(payload: TaskAttemptPayload): Promise<TaskAttemptResponse> {
    return request<TaskAttemptResponse>("/adaptive/attempts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async submitConfusion(
    payload: ConfusionAnnotationPayload,
  ): Promise<ConfusionAnnotationResponse> {
    return request<ConfusionAnnotationResponse>("/adaptive/confusions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async createLearningSupportSession(payload: {
    session_id: string;
    knowledge_id: string;
    task_id?: string;
    phase: "prestudy" | "review";
    confusion_type: string;
    confusion_note: string;
  }): Promise<LearningSupportSessionResponse> {
    return request<LearningSupportSessionResponse>("/learning-support/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async respondLearningSupport(
    sessionId: string,
    studentResponse: string,
  ): Promise<LearningSupportSessionResponse> {
    return request<LearningSupportSessionResponse>(
      `/learning-support/sessions/${encodeURIComponent(sessionId)}/respond`,
      {
        method: "POST",
        body: JSON.stringify({ student_response: studentResponse }),
      },
    );
  },

  async subjectiveCatalog(
    phase: "prestudy" | "review",
  ): Promise<SubjectiveCatalogResponse> {
    return request<SubjectiveCatalogResponse>(
      `/subjective-tasks/catalog?phase=${encodeURIComponent(phase)}`,
    );
  },

  async submitSubjectiveAttempt(payload: {
    attempt_id: string;
    task_id: string;
    task_version: string;
    phase: "prestudy" | "review";
    response_text: string;
    confidence: number | null;
  }): Promise<SubjectiveAttemptResponse> {
    return request<SubjectiveAttemptResponse>("/subjective-attempts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async subjectiveAttemptHistory(
    phase?: "prestudy" | "review",
  ): Promise<SubjectiveAttemptHistoryResponse> {
    const query = phase ? `?phase=${encodeURIComponent(phase)}` : "";
    return request<SubjectiveAttemptHistoryResponse>(`/subjective-attempts${query}`);
  },

  async subjectiveAttempt(attemptId: string): Promise<SubjectiveAttempt> {
    return request<SubjectiveAttempt>(
      `/subjective-attempts/${encodeURIComponent(attemptId)}`,
    );
  },

  async teacherSubjectiveQueue(): Promise<TeacherSubjectiveQueueResponse> {
    return request<TeacherSubjectiveQueueResponse>("/teacher/subjective-attempts");
  },

  async reviewSubjectiveAttempt(payload: {
    review_id: string;
    attempt_id: string;
    decision: "approve" | "request_revision" | "reject";
    teacher_score: number | null;
    knowledge_status: "mastered" | "partial" | "missing" | "";
    feedback: string;
    error_tags: string[];
  }): Promise<{
    review_status: string;
    attempt_status: string;
    learning_event?: LearningEvent | null;
  }> {
    return request("/teacher/subjective-reviews", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async teacherOverview(): Promise<TeacherOverviewResponse> {
    return request<TeacherOverviewResponse>("/teacher/overview");
  },

  async createTeacherClass(payload: {
    name: string;
    term: string;
    course_id?: string;
  }): Promise<{ class_status: string; classroom: import("./types").TeacherClassroom }> {
    return request("/teacher/classes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async enrollTeacherStudent(
    classId: string,
    studentEmail: string,
  ): Promise<{ enrollment_status: string; class_id: string; student_ref: string }> {
    return request(`/teacher/classes/${encodeURIComponent(classId)}/enrollments`, {
      method: "POST",
      body: JSON.stringify({ student_email: studentEmail }),
    });
  },

  async teacherClassAnalytics(classId: string): Promise<TeacherAnalyticsResponse> {
    return request<TeacherAnalyticsResponse>(
      `/teacher/classes/${encodeURIComponent(classId)}/analytics`,
    );
  },

  async teacherReviewCatalog(): Promise<TeacherReviewCatalogResponse> {
    return request<TeacherReviewCatalogResponse>("/teacher/reviews/catalog");
  },

  async teacherCaseBundle(caseId: string): Promise<TeacherCaseBundleResponse> {
    return request<TeacherCaseBundleResponse>(
      `/teacher/case-bundles/${encodeURIComponent(caseId)}`,
    );
  },

  async submitTeacherReview(payload: {
    review_id: string;
    object_type: "case_bundle" | "knowledge_card" | "task_item";
    object_id: string;
    object_version: string;
    decision: "approve" | "request_revision" | "reject";
    note: string;
  }): Promise<{ review_status: string }> {
    return request("/teacher/reviews", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async skillCards(studentId: string): Promise<SkillCardSummary[]> {
    const payload = await request<{ student_id: string; cards: SkillCardSummary[] }>(
      `/teaching/skill-cards/${encodeURIComponent(studentId)}`,
    );
    return payload.cards ?? [];
  },

  async skillCardDetail(studentId: string, slug: string): Promise<SkillCardDetail> {
    return request<SkillCardDetail>(
      `/teaching/skill-cards/${encodeURIComponent(studentId)}/${encodeURIComponent(slug)}`,
    );
  },
};
