from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.models import (
    ClassEnrollmentRecord,
    ContentReviewRecord,
    CourseClassRecord,
    LearnerProfileRecord,
    LearningEventRecord,
    User,
)
from src.core.role_service import resolve_user_role
from src.case_bundle.service import CaseBundleService, get_case_bundle_service
from src.knowledge.service import KnowledgeService, get_knowledge_service


class TeacherPermissionError(RuntimeError):
    pass


class TeacherObjectNotFoundError(RuntimeError):
    pass


class TeacherConflictError(RuntimeError):
    pass


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _student_ref(class_id: str, student_id: str) -> str:
    digest = hashlib.sha256(f"{class_id}|{student_id}".encode("utf-8")).hexdigest()
    return f"student-{digest[:12]}"


class TeacherService:
    def __init__(
        self,
        knowledge: KnowledgeService | None = None,
        case_bundles: CaseBundleService | None = None,
        min_aggregate_size: int | None = None,
    ) -> None:
        self.knowledge = knowledge or get_knowledge_service()
        self.case_bundles = case_bundles or get_case_bundle_service()
        if min_aggregate_size is None:
            try:
                min_aggregate_size = int(
                    str(os.environ.get("SIMLAW_TEACHER_MIN_AGGREGATE_SIZE") or "3")
                )
            except ValueError:
                min_aggregate_size = 3
        self.min_aggregate_size = max(1, int(min_aggregate_size))

    @staticmethod
    def require_teacher(*, session: Session, user: User) -> str:
        role = resolve_user_role(session=session, user=user)
        if role not in {"teacher", "admin"}:
            raise TeacherPermissionError("teacher role is required")
        return role

    def _owned_class(
        self,
        *,
        session: Session,
        teacher: User,
        class_id: str,
        role: str | None = None,
    ) -> CourseClassRecord:
        current_role = role or self.require_teacher(session=session, user=teacher)
        record = session.get(CourseClassRecord, str(class_id))
        if record is None:
            raise TeacherObjectNotFoundError("class not found")
        if current_role != "admin" and record.teacher_user_id != str(teacher.id):
            raise TeacherPermissionError("class is owned by another teacher")
        return record

    @staticmethod
    def _serialize_class(session: Session, record: CourseClassRecord) -> dict[str, Any]:
        student_count = session.scalar(
            select(func.count())
            .select_from(ClassEnrollmentRecord)
            .where(
                ClassEnrollmentRecord.class_id == record.id,
                ClassEnrollmentRecord.status == "active",
            )
        )
        return {
            "class_id": record.id,
            "course_id": record.course_id,
            "name": record.name,
            "term": record.term,
            "status": record.status,
            "student_count": int(student_count or 0),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def list_classes(self, *, session: Session, teacher: User) -> dict[str, Any]:
        role = self.require_teacher(session=session, user=teacher)
        query = select(CourseClassRecord).order_by(
            CourseClassRecord.term.desc(), CourseClassRecord.created_at.desc()
        )
        if role != "admin":
            query = query.where(CourseClassRecord.teacher_user_id == str(teacher.id))
        rows = session.scalars(query).all()
        return {
            "schema_version": "teacher-class-list-v1",
            "role": role,
            "classes": [self._serialize_class(session, row) for row in rows],
        }

    def create_class(
        self,
        *,
        session: Session,
        teacher: User,
        course_id: str,
        name: str,
        term: str,
    ) -> dict[str, Any]:
        self.require_teacher(session=session, user=teacher)
        normalized_name = str(name or "").strip()
        normalized_term = str(term or "").strip()
        normalized_course = str(course_id or "undergraduate-criminal-law").strip()
        if not normalized_name or not normalized_term:
            raise ValueError("class name and term are required")
        existing = session.scalar(
            select(CourseClassRecord).where(
                CourseClassRecord.teacher_user_id == str(teacher.id),
                CourseClassRecord.course_id == normalized_course,
                CourseClassRecord.term == normalized_term,
                CourseClassRecord.name == normalized_name,
            )
        )
        if existing is not None:
            return {"class_status": "duplicate", "classroom": self._serialize_class(session, existing)}
        record = CourseClassRecord(
            teacher_user_id=str(teacher.id),
            course_id=normalized_course,
            name=normalized_name,
            term=normalized_term,
            status="active",
        )
        session.add(record)
        session.flush()
        return {"class_status": "inserted", "classroom": self._serialize_class(session, record)}

    def enroll_student(
        self,
        *,
        session: Session,
        teacher: User,
        class_id: str,
        student_email: str,
    ) -> dict[str, Any]:
        role = self.require_teacher(session=session, user=teacher)
        classroom = self._owned_class(
            session=session, teacher=teacher, class_id=class_id, role=role
        )
        email = str(student_email or "").strip().lower()
        student = session.scalar(select(User).where(User.email == email))
        if student is None:
            raise TeacherObjectNotFoundError("student account not found")
        if resolve_user_role(session=session, user=student) != "student":
            raise ValueError("only student-role accounts can be enrolled")
        existing = session.scalar(
            select(ClassEnrollmentRecord).where(
                ClassEnrollmentRecord.class_id == classroom.id,
                ClassEnrollmentRecord.student_user_id == student.id,
            )
        )
        status = "inserted"
        if existing is None:
            existing = ClassEnrollmentRecord(
                class_id=classroom.id,
                student_user_id=student.id,
                status="active",
            )
            session.add(existing)
            session.flush()
        elif existing.status == "active":
            status = "duplicate"
        else:
            existing.status = "active"
            status = "reactivated"
        return {
            "enrollment_status": status,
            "class_id": classroom.id,
            "student_ref": _student_ref(classroom.id, str(student.id)),
        }

    def class_analytics(
        self,
        *,
        session: Session,
        teacher: User,
        class_id: str,
    ) -> dict[str, Any]:
        role = self.require_teacher(session=session, user=teacher)
        classroom = self._owned_class(
            session=session, teacher=teacher, class_id=class_id, role=role
        )
        student_ids = list(
            session.scalars(
                select(ClassEnrollmentRecord.student_user_id).where(
                    ClassEnrollmentRecord.class_id == classroom.id,
                    ClassEnrollmentRecord.status == "active",
                )
            ).all()
        )
        events = []
        profiles = []
        if student_ids:
            events = list(
                session.scalars(
                    select(LearningEventRecord).where(
                        LearningEventRecord.user_id.in_(student_ids)
                    )
                ).all()
            )
            profiles = list(
                session.scalars(
                    select(LearnerProfileRecord).where(
                        LearnerProfileRecord.user_id.in_(student_ids)
                    )
                ).all()
            )

        event_types = Counter(str(row.event_type) for row in events)
        active_students = len({str(row.user_id) for row in events})
        detail_suppressed = len(student_ids) < self.min_aggregate_size
        knowledge_counts: dict[str, Counter[str]] = defaultdict(Counter)
        knowledge_names: dict[str, str] = {}
        confusion_counts: Counter[str] = Counter()
        capability_sum: dict[str, float] = defaultdict(float)
        capability_students: Counter[str] = Counter()
        error_counts: Counter[str] = Counter()
        provisional_count = 0

        for record in ([] if detail_suppressed else profiles):
            profile = record.profile_json if isinstance(record.profile_json, dict) else {}
            for knowledge_id, state in (profile.get("knowledge") or {}).items():
                if not isinstance(state, dict):
                    continue
                kid = str(knowledge_id)
                latest = str(state.get("latest") or "insufficient")
                knowledge_counts[kid][latest] += 1
                if str(state.get("evidence_status") or "") == "provisional":
                    knowledge_counts[kid]["provisional"] += 1
                    provisional_count += 1
                name = str(state.get("knowledge_name") or "").strip()
                if name:
                    knowledge_names[kid] = name
            for knowledge_id, state in (profile.get("confusions") or {}).items():
                if isinstance(state, dict):
                    # Aggregate only the count. Raw student notes are intentionally excluded.
                    confusion_counts[str(knowledge_id)] += int(state.get("count") or 0)
                    name = str(state.get("knowledge_name") or "").strip()
                    if name:
                        knowledge_names[str(knowledge_id)] = name
            for code, state in (profile.get("capabilities") or {}).items():
                if isinstance(state, dict) and state.get("mean") is not None:
                    capability_sum[str(code)] += float(state["mean"])
                    capability_students[str(code)] += 1
            for tag, count in (profile.get("error_tag_counts") or {}).items():
                error_counts[str(tag)] += int(count or 0)

        knowledge_rows = []
        all_knowledge_ids = set(knowledge_counts) | set(confusion_counts)
        for knowledge_id in all_knowledge_ids:
            counts = knowledge_counts[knowledge_id]
            card = self.knowledge.card_by_id.get(knowledge_id) or {}
            knowledge_rows.append(
                {
                    "knowledge_id": knowledge_id,
                    "knowledge_name": knowledge_names.get(knowledge_id)
                    or str(card.get("canonical_name") or knowledge_id),
                    "mastered_students": counts["mastered"],
                    "partial_students": counts["partial"],
                    "missing_students": counts["missing"],
                    "provisional_students": counts["provisional"],
                    "confusion_count": confusion_counts[knowledge_id],
                }
            )
        knowledge_rows.sort(
            key=lambda row: (
                -(row["missing_students"] + row["partial_students"] + row["confusion_count"]),
                row["knowledge_name"],
            )
        )
        capabilities = [
            {
                "code": code,
                "mean": round(capability_sum[code] / capability_students[code], 4),
                "student_count": capability_students[code],
            }
            for code in sorted(capability_sum)
            if capability_students[code]
        ]
        return {
            "schema_version": "teacher-class-analytics-v1",
            "classroom": self._serialize_class(session, classroom),
            "summary": {
                "student_count": len(student_ids),
                "active_student_count": active_students,
                "learning_event_count": len(events),
                "task_attempt_count": event_types["task_attempt_assessment"],
                "case_stage_event_count": event_types["case_stage_assessment"],
                "confusion_event_count": event_types["confusion_annotation"],
                "provisional_knowledge_states": provisional_count,
            },
            "event_type_counts": dict(event_types),
            "knowledge": knowledge_rows,
            "capabilities": capabilities,
            "top_error_tags": [
                {"tag": tag, "count": count} for tag, count in error_counts.most_common(10)
            ],
            "privacy": {
                "aggregation": "teacher_owned_class_only",
                "student_emails_included": False,
                "raw_confusion_notes_included": False,
                "small_group_detail_suppressed": detail_suppressed,
                "minimum_aggregate_size": self.min_aggregate_size,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                "聚合结果是形成性证据，不是正式成绩",
                "小班样本必须由教师结合课堂判断，不得用于学生排名",
                (
                    f"当前班级不足{self.min_aggregate_size}人，知识/能力/错误细分已抑制"
                    if detail_suppressed
                    else "当前班级达到最小聚合人数，仅展示匿名班级级细分"
                ),
            ],
        }

    def _review_objects(self) -> dict[tuple[str, str], dict[str, Any]]:
        objects: dict[tuple[str, str], dict[str, Any]] = {}
        for bundle in self.case_bundles.bundles:
            objects[("case_bundle", bundle["case_bundle_id"])] = {
                "object_type": "case_bundle",
                "object_id": bundle["case_bundle_id"],
                "object_version": bundle["content_sha256"],
                "title": bundle["title"],
                "subtitle": (
                    f"{bundle['runtime_case_id']} · {bundle['case_cause']} · "
                    f"原案{bundle['original_case_id']}"
                ),
                "review_status": bundle["review"]["status"],
                "standard_evidence_ids": list(bundle.get("evidence_ids") or []),
                "unresolved_legal_basis_fragments": list(
                    bundle.get("unresolved_legal_basis_fragments") or []
                ),
            }
        for card in self.knowledge.cards:
            objects[("knowledge_card", card["knowledge_id"])] = {
                "object_type": "knowledge_card",
                "object_id": card["knowledge_id"],
                "object_version": card["content_sha256"],
                "title": card["canonical_name"],
                "subtitle": card["chapter"],
                "review_status": card["review_status"],
                "standard_evidence_ids": list(card.get("standard_evidence_ids") or []),
            }
        for task in self.knowledge.tasks:
            public = self.knowledge.public_task(task)
            objects[("task_item", task["task_id"])] = {
                "object_type": "task_item",
                "object_id": task["task_id"],
                "object_version": task["content_sha256"],
                "title": task["knowledge_name"],
                "subtitle": task["stem"],
                "review_status": task["status"],
                "difficulty": task.get("difficulty"),
                "cognitive_dimension": task.get("cognitive_dimension"),
                "standard_evidence_ids": list(task.get("standard_evidence_ids") or []),
                "public_task": public,
            }
        return objects

    @staticmethod
    def _serialize_review(record: ContentReviewRecord) -> dict[str, Any]:
        return {
            "review_id": record.review_id,
            "object_type": record.object_type,
            "object_id": record.object_id,
            "object_version": record.object_version,
            "decision": record.decision,
            "note": record.note,
            "payload_sha256": record.payload_sha256,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def review_catalog(self, *, session: Session, teacher: User) -> dict[str, Any]:
        self.require_teacher(session=session, user=teacher)
        reviews = session.scalars(
            select(ContentReviewRecord)
            .where(ContentReviewRecord.teacher_user_id == str(teacher.id))
            .order_by(ContentReviewRecord.created_at.desc())
        ).all()
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for review in reviews:
            latest.setdefault(
                (review.object_type, review.object_id), self._serialize_review(review)
            )
        objects = []
        for key, value in self._review_objects().items():
            objects.append({**value, "latest_teacher_review": latest.get(key)})
        objects.sort(key=lambda row: (row["object_type"], row["title"], row["object_id"]))
        return {
            "schema_version": "teacher-content-review-catalog-v1",
            "counts": {
                "case_bundles": len(self.case_bundles.bundles),
                "knowledge_cards": len(self.knowledge.cards),
                "task_items": len(self.knowledge.tasks),
                "teacher_review_events": len(reviews),
            },
            "objects": objects,
            "boundary": "审核事件是不可变覆盖记录，不会直接改写冻结的源内容",
        }

    def teacher_case_bundle(
        self,
        *,
        session: Session,
        teacher: User,
        case_id: str,
    ) -> dict[str, Any]:
        self.require_teacher(session=session, user=teacher)
        bundle = self.case_bundles.teacher_bundle(case_id)
        if bundle is None:
            raise TeacherObjectNotFoundError("case bundle not found")
        return {
            "schema_version": "teacher-case-bundle-response-v1",
            "case_bundle": bundle,
            "boundary": (
                "teacher-only reference projection; review events do not rewrite this content"
            ),
        }

    def submit_review(
        self,
        *,
        session: Session,
        teacher: User,
        review_id: str,
        object_type: str,
        object_id: str,
        object_version: str,
        decision: str,
        note: str,
    ) -> dict[str, Any]:
        self.require_teacher(session=session, user=teacher)
        normalized_decision = str(decision or "").strip()
        if normalized_decision not in {"approve", "request_revision", "reject"}:
            raise ValueError("unsupported review decision")
        objects = self._review_objects()
        target = objects.get((str(object_type), str(object_id)))
        if target is None:
            raise TeacherObjectNotFoundError("review object not found")
        if str(object_version) != str(target["object_version"]):
            raise ValueError("review object_version is stale or invalid")
        payload = {
            "review_id": str(review_id),
            "teacher_user_id": str(teacher.id),
            "object_type": str(object_type),
            "object_id": str(object_id),
            "object_version": str(object_version),
            "decision": normalized_decision,
            "note": str(note or "").strip(),
        }
        digest = _hash_payload(payload)
        existing = session.get(ContentReviewRecord, str(review_id))
        if existing is not None:
            if existing.payload_sha256 != digest:
                raise TeacherConflictError("review_id payload conflict")
            return {"review_status": "duplicate", "review": self._serialize_review(existing)}
        record = ContentReviewRecord(
            review_id=str(review_id),
            teacher_user_id=str(teacher.id),
            object_type=str(object_type),
            object_id=str(object_id),
            object_version=str(object_version),
            decision=normalized_decision,
            note=str(note or "").strip(),
            payload_sha256=digest,
        )
        session.add(record)
        session.flush()
        return {"review_status": "inserted", "review": self._serialize_review(record)}

    def review_audit(self, *, session: Session, teacher: User) -> dict[str, Any]:
        self.require_teacher(session=session, user=teacher)
        rows = session.scalars(
            select(ContentReviewRecord)
            .where(ContentReviewRecord.teacher_user_id == str(teacher.id))
            .order_by(ContentReviewRecord.created_at.desc())
            .limit(200)
        ).all()
        return {
            "schema_version": "teacher-content-review-audit-v1",
            "reviews": [self._serialize_review(row) for row in rows],
        }


__all__ = [
    "TeacherConflictError",
    "TeacherObjectNotFoundError",
    "TeacherPermissionError",
    "TeacherService",
]
