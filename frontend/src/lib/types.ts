// WebSocket protocol message types — mirrors backend/src/simulation/ws_protocol.py

export type WSMessageType =
  | "agent_spawn"
  | "agent_move"
  | "agent_sit"
  | "agent_stand"
  | "agent_bubble"
  | "agent_despawn"
  | "dialogue_update"
  | "dialogue_gate_waiting"
  | "dialogue_gate_accepted"
  | "dialogue_gate_error"
  | "runtime_progress"
  | "step_gate_waiting"
  | "step_gate_accepted"
  | "step_gate_error"
  | "case_state_change"
  | "scenario_start"
  | "scenario_end"
  | "case_runtime_issue"
  | "agent_goto_front_desk"
  | "agent_update_dialogue"
  | "agent_end_interaction"
  | "client_logout_ack"
  | "player_lawyer_error"
  | "player_lawyer_input_submitted"
  | string;

export interface WSMessage {
  type: WSMessageType;
  [key: string]: unknown;
}

export interface AgentSpawnPayload {
  agent_id: string;
  name: string;
  character_name?: string;
  x?: number;
  y?: number;
  role?: string;
}

export interface DialogueUpdatePayload {
  case_id: string;
  speaker_id: string;
  speaker_name: string;
  content: string;
  turn: number;
  scenario_type?: string;
  generation_duration_seconds?: number;
  generation_total_tokens?: number;
  player_responsibility?: boolean;
  evaluation_marker_label?: string;
  evaluation_marker_reason?: string;
}

export interface CaseStateChangePayload {
  case_id: string;
  event: string;
  from_state?: string;
  to_state?: string;
  party_role?: string;
  overall_state?: string;
}

export interface ScenarioStartPayload {
  case_id: string;
  scenario_type: string;
  participants: string[];
}

export interface RuntimeProgressPayload {
  case_id: string;
  phase: string;
  message: string;
  detail?: string;
  blocking?: boolean;
  occurred_at?: string;
}

export interface CaseRuntimeIssuePayload {
  case_id: string;
  scenario_type: string;
  stage_label: string;
  code: string;
  message: string;
  retryable: boolean;
  occurred_at: string;
}

// REST types

export interface AuthResponse {
  access_token: string;
  token_type?: string;
  user?: {
    id: string | number;
    email: string;
    role?: "student" | "teacher" | "admin" | string;
  };
}

export interface TeacherClassroom {
  class_id: string;
  course_id: string;
  name: string;
  term: string;
  status: string;
  student_count: number;
  created_at?: string | null;
}

export interface TeacherOverviewResponse {
  schema_version: string;
  role: "teacher" | "admin" | string;
  classes: TeacherClassroom[];
}

export interface TeacherAnalyticsResponse {
  schema_version: string;
  classroom: TeacherClassroom;
  summary: {
    student_count: number;
    active_student_count: number;
    learning_event_count: number;
    task_attempt_count: number;
    case_stage_event_count: number;
    confusion_event_count: number;
    provisional_knowledge_states: number;
  };
  event_type_counts: Record<string, number>;
  knowledge: Array<{
    knowledge_id: string;
    knowledge_name: string;
    mastered_students: number;
    partial_students: number;
    missing_students: number;
    provisional_students: number;
    confusion_count: number;
  }>;
  capabilities: Array<{ code: string; mean: number; student_count: number }>;
  top_error_tags: Array<{ tag: string; count: number }>;
  privacy: {
    aggregation: string;
    student_emails_included: false;
    raw_confusion_notes_included: false;
    small_group_detail_suppressed: boolean;
    minimum_aggregate_size: number;
  };
  warnings: string[];
  generated_at: string;
}

export interface TeacherReviewObject {
  object_type: "case_bundle" | "knowledge_card" | "task_item";
  object_id: string;
  object_version: string;
  title: string;
  subtitle: string;
  review_status: string;
  difficulty?: number;
  cognitive_dimension?: string;
  standard_evidence_ids: string[];
  unresolved_legal_basis_fragments?: string[];
  latest_teacher_review?: {
    review_id: string;
    decision: "approve" | "request_revision" | "reject";
    note: string;
    created_at?: string | null;
  } | null;
}

export interface TeacherReviewCatalogResponse {
  schema_version: string;
  counts: {
    case_bundles: number;
    knowledge_cards: number;
    task_items: number;
    teacher_review_events: number;
  };
  objects: TeacherReviewObject[];
  boundary: string;
}

export interface TeacherCaseBundleResponse {
  schema_version: string;
  boundary: string;
  case_bundle: {
    case_bundle_id: string;
    runtime_case_id: string;
    original_case_id: number;
    title: string;
    charge: string;
    version: string;
    content_sha256: string;
    knowledge_links: Array<{
      knowledge_id: string;
      knowledge_name: string;
      role: string;
    }>;
    evidence_ids: string[];
    unresolved_legal_basis_fragments: string[];
    stage_packets: Record<
      string,
      { stage_name: string; availability: string; rubric: { capabilities: unknown[] } }
    >;
    reference_private: {
      guiding_points?: string;
      defense_hint?: string;
    };
    review: { risk_flags?: string[] };
  };
}

export interface SandboxState {
  sandbox?: {
    id?: string;
    status?: string;
    selected_case_id?: string | null;
  } | null;
  runtime_status?: {
    status?: string;
    running?: boolean;
  };
}

export interface CasePickerEntry {
  case_id: string;
  title: string;
  plaintiff_name: string;
  defendant_name: string;
  case_category?: "criminal";
  raw_case_cause: string;
  training_category?: string;
  difficulty?: string;
  status?: string;
  case_bundle_id?: string;
  case_bundle_version?: string;
  case_bundle_content_sha256?: string;
  evidence_count?: number;
  knowledge_count?: number;
  teacher_recheck_required?: boolean;
}

export interface CaseListResponse {
  cases: CasePickerEntry[];
  selected_case_id?: string | null;
}

export type PlayerMode = "auto" | "player";

export interface PlayerRequest {
  request_id: string;
  sandbox_id?: string | number;
  case_id?: string;
  stage?: string;
  role?: string;
  speaker_label?: string;
  prompt?: string;
  context_summary?: string;
  status?: string;
  created_at?: string;
  expires_at?: string | null;
}

export interface PlayerAssist {
  request_id: string;
  case_id?: string;
  stage?: string;
  user_original_message?: string;
  ai_polished_message?: string;
  final_submitted_message?: string;
  used_ai_polish?: boolean;
  assist_mode?: "none" | "polish" | "draft";
  hint_ids?: string[];
  skill_card_ids?: string[];
}

export interface PlayerAssistResponse {
  success: boolean;
  assist?: PlayerAssist;
}

export interface StatusResponse {
  status: string;
  backend_version?: string;
  backend_version_label?: string;
  backend_version_time?: string;
  clients_connected?: number;
  simulation_running?: boolean;
}

// ── Teaching subsystem ──────────────────────────────────────────────

export interface CitationFeedbackDetail {
  citation?: string;
  status?: string;
  message?: string;
  content?: string;
  suggestion?: string;
  [key: string]: unknown;
}

export interface CitationFeedback {
  status: string;
  messages: string[];
  details?: CitationFeedbackDetail[] | null;
}

/** 即时法条校验：从 submit 响应透传（PlayerInputPanel → DialogueFeed） */
export interface CitationNotice {
  id: string;
  status?: string;
  messages: string[];
  details: CitationFeedbackDetail[];
}

export interface CapabilityScore {
  score: number | null;
  raw?: number;
  weight?: number;
  rationale?: string;
  evidence_quote?: string;
}

export interface SubsumptionRow {
  element: string;
  fact_found: string;
  conclusion: string;
  comment?: string;
}

export interface KnowledgeVerdict {
  kp: string;
  status: string;
  reason?: string;
}

export interface LawCitation {
  citation: string;
  status: string;
  content?: string;
  issue?: string;
}

export interface CitationAlignmentItem {
  sentence: string;
  citation: string;
  title?: string;
  article_ref?: string;
  verdict: "supports" | "contradicts" | "neutral";
  reason?: string;
  layers?: string[];
  layer_conflict?: boolean;
  model_score?: number;
  model_verdict?: string;
}

export interface AlignmentSummary {
  supports?: number;
  contradicts?: number;
  neutral?: number;
  total?: number;
  model_layer?: boolean;
  model_name?: string;
}

export interface LearningEvent {
  event_id: string;
  schema_version?: string;
  student_id: string;
  case_id: string;
  charge?: string;
  stage: string;
  task_id?: string;
  case_bundle_id?: string;
  case_bundle_version?: string;
  case_bundle_content_sha256?: string;
  law_corpus_manifest_sha256?: string;
  rubric_version?: string;
  source_response_sha256?: string;
  assist?: {
    modes?: string[];
    ai_drafted?: boolean;
    ai_polished?: boolean;
    hint_count?: number;
    skill_card_ids?: string[];
  };
  evidence_eligibility?: {
    formative_feedback?: boolean;
    long_term_profile?: boolean;
    reason?: string;
  };
  gold_incomplete?: boolean;
  capability_scores: Record<string, CapabilityScore>;
  subsumption_table?: SubsumptionRow[];
  knowledge_verdicts?: KnowledgeVerdict[];
  error_tags?: string[];
  law_citations?: LawCitation[];
  citation_alignment?: CitationAlignmentItem[];
  alignment_summary?: AlignmentSummary;
  knowledge_gaps?: string[];
  overall_feedback?: string;
  scored_at?: string;
}

export interface GrowthPoint {
  at: string;
  stage: string;
  case_id: string;
  mean: number;
}

export interface KnowledgeGapEntry {
  kp: string;
  exposed: number;
  latest: string;
}

export interface RecommendationItem {
  chapter?: string;
  question_no?: number | string;
  question: string;
  knowledge_points: string[];
  question_type?: string;
  source?: string;
}

export interface AdaptiveKnowledgeEvidence {
  knowledge_name?: string;
  latest?: string;
  event_count?: number;
  task_count?: number;
  evidence_status?: "observed" | "provisional" | "insufficient_evidence" | string;
  history?: Array<{
    status?: string;
    event_id?: string;
    task_id?: string;
    evidence_weight?: number;
  }>;
}

export interface AdaptiveConfusionEvidence {
  knowledge_name?: string;
  count?: number;
  latest?: {
    event_id?: string;
    task_id?: string;
    phase?: string;
    confusion_type?: string;
    note?: string;
    submitted_at?: string;
  };
}

export interface AdaptiveRecommendationItem {
  rank?: number;
  task_id?: string;
  item_id?: string;
  task_type?: string;
  knowledge_id?: string;
  knowledge_name?: string;
  stem?: string;
  options?: Record<string, string>;
  difficulty?: number;
  cognitive_dimension?: string;
  reason_code?: string;
  score?: number;
  answer_included?: false;
  content_version?: string;
  standard_evidence_ids?: string[];
  // The explicitly labelled local fallback uses TeachingReport rows.
  chapter?: string;
  question?: string;
  knowledge_points?: string[];
  question_type?: string;
}

export interface AdaptiveRecommendationResponse {
  status: "ok" | "fallback" | string;
  source: "edubrain_adaptive_service" | "local_evidence_heuristic" | string;
  schema_version?: string;
  policy_version?: string;
  warning?: string;
  profile?: {
    schema_version?: string;
    event_count?: number;
    eligible_event_count?: number;
    excluded_event_count?: number;
    self_report_event_count?: number;
    knowledge?: Record<string, AdaptiveKnowledgeEvidence>;
    confusions?: Record<string, AdaptiveConfusionEvidence>;
    warnings?: string[];
  };
  recommendations: AdaptiveRecommendationItem[];
}

export interface EvidenceTimelineEvent {
  event_id: string;
  event_type: string;
  stage: string;
  task_id: string;
  created_at?: string | null;
  long_term_profile_eligible: boolean;
  knowledge_verdicts: Array<{
    knowledge_id?: string;
    knowledge_name?: string;
    kp?: string;
    status?: string;
    reason?: string;
  }>;
  error_tags: string[];
  standard_evidence_ids: string[];
}

export interface EvidenceTimelineResponse {
  schema_version: string;
  events: EvidenceTimelineEvent[];
  boundary: string;
}

export interface ModelRouteStatus {
  task: string;
  provider: string;
  model_name: string;
  api_base: string;
  api_key_configured: boolean;
  timeout_seconds: number;
  configured: boolean;
  circuit_open?: boolean;
}

export interface ModelCatalogResponse {
  schema_version: string;
  small_model_enabled: boolean;
  small_model_tasks: string[];
  routes: ModelRouteStatus[];
  failover: {
    mode: string;
    circuit_seconds: number;
    routes: ModelRouteStatus[];
  };
}

export interface TypicalQuestionSource {
  source_id: string;
  source_type: string;
  title: string;
  article_ref: string;
  quote: string;
  authority: string;
  version: string;
  source_url: string;
  source_bundle_sha256?: string;
  local_source_sha256?: string;
}

export interface TypicalQuestionCase {
  case_id: string;
  title: string;
  question: string;
  standard_answer: string;
  required_source_ids: string[];
  sources: TypicalQuestionSource[];
  run_status: string;
  model_output: {
    answer: string;
    rule_steps: string[];
    conclusion: string;
    citations: Array<{
      source_id: string;
      title: string;
      article_ref: string;
      quote: string;
    }>;
    uncertainty: string;
    confidence: number;
    ai_generated: true;
  };
  model_route?: { task?: string; provider?: string; model_name?: string; api_base?: string };
  point_audit: Array<{
    point_id: string;
    label: string;
    passed: boolean;
    matched_keywords: string[];
  }>;
  point_coverage: number;
  citation_audit: {
    passed: boolean;
    valid_source_ids: string[];
    missing_required_source_ids: string[];
  };
  automated_gate_pass: boolean;
  expert_review_status: "pending" | "approved" | "rejected" | string;
  verified_accurate: boolean;
}

export interface TypicalQuestionReport {
  schema_version: string;
  generated_at: string;
  mode: string;
  suite_sha256: string;
  law_manifest_sha256: string;
  case_bundle_manifest_sha256: string;
  case_count: number;
  automated_gate_pass_count: number;
  all_expert_reviews_complete: boolean;
  cases: TypicalQuestionCase[];
  boundary: { proves: string; does_not_prove: string };
}

export interface CitationAuditResponse {
  schema_version: string;
  items: Array<{
    index: number;
    status: string;
    title: string;
    article_ref: string;
    quote_status: string;
    claim_support_status: string;
    risk_flags: string[];
  }>;
  summary: Record<string, number> & { total: number };
  semantic_boundary: string;
}

export interface KnowledgeCard {
  schema_version: "criminal-law-knowledge-card-v1" | string;
  knowledge_id: string;
  canonical_name: string;
  domain: string;
  chapter: string;
  knowledge_type: string;
  learning_objective: string;
  summary: string;
  law_article_refs: string[];
  standard_evidence_ids: string[];
  prerequisite_ids: string[];
  common_errors: string[];
  theory_scope: string;
  review_status: string;
  reviewer_role: string;
  version: string;
  law_corpus_snapshot: string;
  content_sha256: string;
}

export interface KnowledgeCatalogResponse {
  schema_version: string;
  domain: string;
  review_status: string;
  knowledge_cards: KnowledgeCard[];
  counts: {
    knowledge_cards: number;
    task_items: number;
    evidence_items: number;
  };
  content_manifest_sha256: string;
  law_corpus_manifest_sha256: string;
  limits: string[];
}

export interface TaskAttemptPayload {
  schema_version: "criminal-law-task-attempt-v1";
  attempt_id: string;
  task_id: string;
  content_version: string;
  phase: "prestudy" | "review";
  selected_options: string[];
  submitted_at: string;
  response_time_ms: number;
  confidence: number | null;
  hint_count: number;
  answer_revealed_before_submit: boolean;
}

export interface TaskAttemptFeedback {
  correct: boolean;
  score: number;
  max_score: number;
  correct_options: string[];
  rationale: string;
  triggered_misconceptions: string[];
  knowledge_status: "mastered" | "partial" | "missing" | string;
  standard_evidence_ids: string[];
}

export interface TaskAttemptResponse extends AdaptiveRecommendationResponse {
  schema_version: "edubrain-task-attempt-response-v1" | string;
  attempt_status: "inserted" | "duplicate" | string;
  attempt_id: string;
  persistence: {
    status: "inserted" | "duplicate" | string;
    payload_sha256?: string;
    snapshot_status?: string;
  };
  learning_event: {
    event_id: string;
    event_type: "task_attempt_assessment" | string;
    task_id: string;
    phase: "prestudy" | "review";
    task_version: string;
    grading: {
      score: number;
      max_score: number;
      correct: boolean;
      knowledge_status: string;
    };
  };
  feedback: TaskAttemptFeedback;
}

export interface ConfusionAnnotationPayload {
  schema_version: "criminal-law-confusion-annotation-v1";
  annotation_id: string;
  phase: "prestudy" | "review";
  task_id?: string;
  knowledge_id?: string;
  confusion_type:
    | "concept_boundary"
    | "rule_understanding"
    | "fact_application"
    | "evidence_use"
    | "other";
  note: string;
  request_help: boolean;
  submitted_at: string;
}

export interface ConfusionAnnotationResponse extends AdaptiveRecommendationResponse {
  schema_version: "edubrain-confusion-response-v1" | string;
  annotation_status: "inserted" | "duplicate" | string;
  annotation_id: string;
  persistence: {
    status: "inserted" | "duplicate" | string;
    payload_sha256?: string;
    snapshot_status?: string;
  };
  learning_event: {
    event_id: string;
    event_type: "confusion_annotation" | string;
  };
}

export interface LearningSupportResult {
  diagnosis: { category: string; summary: string };
  layers: {
    norm: {
      content: string;
      citations: Array<{ title: string; article_ref: string; quote: string }>;
    };
    plain: { content: string };
    application: { content: string };
    dispute: { content: string };
  };
  next_action: {
    type: "retry_task" | "review_knowledge" | "ask_teacher" | string;
    instruction: string;
  };
  confidence: number;
  teacher_review_required: boolean;
  warnings?: string[];
  fallback_reason?: string;
}

export interface LearningSupportSession {
  session_id: string;
  knowledge_id: string;
  task_id: string;
  phase: "prestudy" | "review";
  confusion_type: string;
  confusion_note: string;
  diagnostic_question: string;
  knowledge_version: string;
  task_version: string;
  student_response: string;
  status: "awaiting_response" | "completed" | "needs_teacher_review" | string;
  result_source: "llm_governed_evidence" | "deterministic_fallback" | string;
  result: LearningSupportResult | null;
  model_route?: { task?: string; provider?: string; model_name?: string } | null;
  evidence_eligibility: { long_term_profile: false; reason: string };
}

export interface LearningSupportSessionResponse {
  session_status?: "inserted" | "duplicate" | string;
  response_status?: "inserted" | "duplicate" | string;
  session: LearningSupportSession;
}

export interface LearningSupportSeed {
  knowledgeId: string;
  knowledgeName: string;
  taskId?: string;
  phase: "prestudy" | "review";
  confusionType: string;
  note: string;
}

export interface SubjectiveTask {
  schema_version: string;
  task_id: string;
  domain: string;
  status: string;
  task_type: "short_answer" | "role_reversal";
  phase_eligibility: Array<"prestudy" | "review">;
  knowledge_ids: string[];
  knowledge_names: string[];
  target_abilities: string[];
  difficulty: number;
  cognitive_dimension: string;
  prompt: string;
  context_public: Record<string, unknown>;
  response_constraints: {
    min_characters: number;
    max_characters: number;
    citations_required: boolean;
  };
  standard_evidence_ids: string[];
  evidence_refs_public: Array<{
    evidence_id: string;
    source_title: string;
    article_ref: string;
  }>;
  review: Record<string, unknown>;
  source_versions: Record<string, unknown>;
  content_sha256: string;
}

export interface SubjectiveAttempt {
  attempt_id: string;
  task: SubjectiveTask;
  phase: "prestudy" | "review";
  response_text: string;
  confidence: number | null;
  status: string;
  ai_abstained: boolean;
  ai_score: number | null;
  ai_confidence: number;
  ai_feedback: {
    rubric_scores: Record<string, number>;
    strengths: string[];
    corrections: string[];
    suggested_revision: string;
    evidence_ids_used: string[];
    confidence: number;
    abstained: boolean;
    abstain_reason: string;
    score_is_formative_only: true;
  };
  citation_audit: {
    valid_standard_count: number;
    required: boolean;
    passed: boolean;
  };
  model_route?: Record<string, unknown> | null;
  evidence_eligibility: { long_term_profile: boolean; reason: string };
  teacher_review?: {
    decision: "approve" | "request_revision" | "reject";
    teacher_score: number | null;
    knowledge_status: "mastered" | "partial" | "missing" | "";
    feedback: string;
    error_tags: string[];
    learning_event_id: string;
    reviewed_at?: string | null;
  } | null;
  created_at?: string | null;
  student_ref?: string;
}

export interface SubjectiveCatalogResponse {
  schema_version: string;
  counts: { tasks: number; short_answer: number; role_reversal: number };
  tasks: SubjectiveTask[];
  warnings: string[];
}

export interface SubjectiveAttemptResponse {
  attempt_status: "inserted" | "duplicate" | string;
  attempt: SubjectiveAttempt;
}

export interface SubjectiveAttemptHistoryResponse {
  schema_version: string;
  attempts: SubjectiveAttempt[];
  privacy: string;
}

export interface TeacherSubjectiveQueueResponse {
  schema_version: string;
  attempts: SubjectiveAttempt[];
  privacy: string;
}

export interface TeachingReport {
  student_id: string;
  capability_radar: Array<{
    code: string;
    name: string;
    score: number | null;
    evidence_status?: string;
  }>;
  knowledge_gaps: KnowledgeGapEntry[];
  top_errors: Array<{ tag: string; count: number }>;
  growth_curve: GrowthPoint[];
  cases_played: string[];
  recommendations: RecommendationItem[];
  updated_at?: string;
  skill_cards?: SkillCardSummary[];
}

export interface SkillCardSummary {
  name: string;
  description: string;
  knowledge_point: string;
  stage: string;
  charge: string;
  slug: string;
  review_count: number;
  status_history: string[];
  updated_at: string;
}

export interface SkillCardDetail extends SkillCardSummary {
  content: string;
}
