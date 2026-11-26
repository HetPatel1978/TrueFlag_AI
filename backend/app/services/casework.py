"""Human-only append journal. Existing source and numeric verification remain authoritative."""

import hashlib
import re
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models import AuditEvent, Case, User
from app.models.casework import CaseworkEntry
from app.schemas.casework import ACTION, POLICY, CaseworkPage, Entry
from app.services.case_workflows import WorkflowForbidden
from app.services.draft_api import DraftAPIService
from app.services.evidence import EvidenceBlocked, EvidenceConflict, EvidenceNotFound, atomic, audit
from app.services.ingestion import digest

KINDS = {
    "note",
    "information_request",
    "information_response",
    "finding_review",
    "escalation",
    "supervisor_response",
    "resolution",
}


class CaseworkService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.gateway = DraftAPIService(engine, settings)
        self.coordinator = self.gateway.drafts.coordinator
        self.reader = self.coordinator.reader

    def _context(self, session, actor, case_id, token=None):
        # Established advisory gate -> actor -> case order, including draft revalidation.
        self.coordinator._gate(session)
        return self.reader._context(session, actor, case_id, token=token)

    def _entries(self, session, case_id):
        rows = session.scalars(
            select(CaseworkEntry)
            .where(CaseworkEntry.case_id == case_id)
            .order_by(CaseworkEntry.revision)
            .limit(1001)
        ).all()
        if len(rows) > 1000:
            raise EvidenceBlocked("casework_capacity")
        for row in rows:
            self._integrity(session, row)
        return rows

    def _integrity(self, session, row):
        content = dict(
            id=str(row.id),
            case_id=str(row.case_id),
            actor_id=str(row.actor_id),
            author=row.author,
            revision=row.revision,
            kind=row.kind,
            parent_id=str(row.parent_id) if row.parent_id else None,
            payload=row.payload,
            binding=row.binding,
        )
        if row.content_sha256 != digest(content):
            raise EvidenceBlocked("casework_integrity_failure")
        event = session.get(AuditEvent, row.audit_event_id)
        if (
            event is None
            or event.actor_id != row.actor_id
            or event.resource_id != str(row.case_id)
            or event.action != "evidence.casework." + row.kind
            or event.details
            != dict(
                entry_id=str(row.id),
                content_sha256=row.content_sha256,
                revision=row.revision,
                policy_version=POLICY,
            )
        ):
            raise EvidenceBlocked("casework_audit_invalid")

    def _visible(self, row, context):
        b = row.binding
        available = {r.record_version_id: r.model_dump(mode="json") for r in context.refs}
        return (
            b["evidence_revision"] == context.snapshot.evidence_revision
            and b["access_revision"] == context.snapshot.access_revision
            and all(
                available.get(UUID(r["record_version_id"])) == r
                for r in row.payload["supporting_records"]
            )
        )

    def _project(self, row, context):
        visible = self._visible(row, context)
        return Entry(
            id=row.id,
            case_id=row.case_id,
            actor_id=row.actor_id,
            author=row.author,
            recorded_at=row.created_at
            if row.created_at.tzinfo
            else row.created_at.replace(tzinfo=timezone.utc),
            revision=row.revision,
            kind=row.kind,
            parent_id=row.parent_id,
            content_sha256=row.content_sha256,
            payload=row.payload if visible else None,
            binding=row.binding if visible else None,
            content_status="available" if visible else "withheld_source_changed",
        )

    def _open(self, rows, kind, response):
        answered = {r.parent_id for r in rows if r.kind == response}
        return [r for r in rows if r.kind == kind and r.id not in answered]

    @atomic
    def history(self, session, actor, case_id, *, limit=20, offset=0):
        if (
            type(limit) is not int
            or not 1 <= limit <= 20
            or type(offset) is not int
            or not 0 <= offset <= 1000
        ):
            raise EvidenceBlocked("casework_page_invalid")
        context = self._context(session, actor, case_id)
        rows = self._entries(session, case_id)
        resolution = next(
            (r.payload["outcome"] for r in reversed(rows) if r.kind == "resolution"), None
        )
        audit(session, actor, "casework.read", case_id, returned=min(limit, len(rows)))
        self.reader.ensure_clock(context.clock_epoch)
        return CaseworkPage(
            items=[
                self._project(r, context) for r in list(reversed(rows))[offset : offset + limit]
            ],
            total=len(rows),
            revision=rows[-1].revision if rows else 0,
            limit=limit,
            offset=offset,
            open_information_requests=len(
                self._open(rows, "information_request", "information_response")
            ),
            pending_escalations=len(self._open(rows, "escalation", "supervisor_response")),
            resolution=resolution,
            allowed_resolutions=self.settings.casework_allowed_resolutions,
        )

    def _finding(self, session, actor, case_id, command):
        detail = self.gateway.detail.__wrapped__(
            self.gateway, session, actor, case_id, command.draft_run_id
        )
        body = detail.draft
        if body is None or body.content_sha256 != command.expected_draft_sha256:
            raise EvidenceConflict("finding_stale_or_unavailable")
        finding = next((f for f in body.findings if f.reference_id == command.reference_id), None)
        if finding is None:
            raise EvidenceNotFound("finding_not_found")
        return dict(
            mode=detail.mode,
            draft_sha256=body.content_sha256,
            investigation_run_id=str(body.investigation_run_id),
            manifest_sha256=body.manifest_sha256,
            claim_type=finding.claim_type,
            supporting_evidence=[str(r) for r in finding.supporting_evidence],
        )

    def _requirements(self, session, rows, context, *, require_review):
        if self._open(rows, "information_request", "information_response"):
            raise EvidenceConflict("open_information_requests")
        if not any(r.kind == "note" and self._visible(r, context) for r in rows):
            raise EvidenceConflict("current_note_required")
        reviews = {}
        for row in rows:
            if (
                row.kind == "finding_review"
                and row.binding["case_version"] == context.case.version
                and self._visible(row, context)
            ):
                reviews[(row.payload["draft_run_id"], row.payload["reference_id"])] = row
        if require_review and not reviews:
            raise EvidenceConflict("finding_review_required")
        for row in reviews.values():
            if not self._visible(row, context) or row.payload["decision"] in {
                "defer",
                "further_investigation",
            }:
                raise EvidenceConflict("finding_review_incomplete")
            command = ACTION.validate_python(
                {
                    **row.payload,
                    "snapshot": "x" * 32,
                    "expected_revision": 0,
                    "kind": "finding_review",
                }
            )
            self._finding(session, row.actor_id, context.case.id, command)

    @atomic
    def submit(self, session, actor, case_id, key, command):
        # Revalidation protects internal callers too; never accept a forged constructed object.
        command = ACTION.validate_json(ACTION.dump_json(command))
        if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise EvidenceBlocked("invalid_casework_key")
        context = self._context(session, actor, case_id, command.snapshot)
        user = session.get(User, actor)
        key_sha = hashlib.sha256(key.encode()).hexdigest()
        payload = command.model_dump(mode="json", exclude={"snapshot", "expected_revision"})
        request_sha = digest(dict(case_id=str(case_id), payload=payload))
        prior = session.scalar(
            select(CaseworkEntry).where(
                CaseworkEntry.actor_id == actor, CaseworkEntry.key_sha256 == key_sha
            )
        )
        if prior:
            if prior.case_id != case_id or prior.request_sha256 != request_sha:
                raise EvidenceConflict("casework_idempotency_conflict")
            self._integrity(session, prior)
            self.reader._decode(session, command.snapshot, "snapshot")
            return self._project(prior, context)
        rows = self._entries(session, case_id)
        revision = rows[-1].revision if rows else 0
        if (
            command.expected_revision != revision
            or revision >= 1000
            or context.case.status == "closed"
        ):
            raise EvidenceConflict("casework_changed_or_closed")
        references = {r.record_version_id: r for r in context.refs}
        if len({r.record_version_id for r in command.supporting_records}) != len(
            command.supporting_records
        ) or any(references.get(r.record_version_id) != r for r in command.supporting_records):
            raise EvidenceNotFound("supporting_record_unavailable")
        parent = next((r for r in rows if r.id == getattr(command, "parent_id", None)), None)
        if getattr(command, "parent_id", None) and parent is None:
            raise EvidenceNotFound("casework_parent_unavailable")
        binding = dict(
            policy_version=POLICY,
            snapshot_sha256=context.snapshot.sha256,
            case_version=context.snapshot.case_version,
            evidence_revision=context.snapshot.evidence_revision,
            access_revision=context.snapshot.access_revision,
            assessment_id=str(context.assessment_id) if context.assessment_id else None,
        )
        if (
            command.kind == "note"
            and parent
            and (parent.kind != "note" or parent.actor_id != actor)
        ):
            raise WorkflowForbidden("note_correction_forbidden")
        if command.kind == "information_response":
            if parent.kind != "information_request" or parent.id not in {
                r.id for r in self._open(rows, "information_request", "information_response")
            }:
                raise EvidenceConflict("information_request_not_open")
            if parent.payload["responsible_party"] == "supervisor" and user.role == "analyst":
                raise WorkflowForbidden("supervisor_response_required")
            if command.status == "resolved" and not command.supporting_records:
                raise EvidenceConflict("supporting_record_required")
        if command.kind == "finding_review":
            binding["finding"] = self._finding(session, actor, case_id, command)
        if command.kind == "escalation" and self._open(rows, "escalation", "supervisor_response"):
            raise EvidenceConflict("escalation_already_pending")
        if command.kind in {"supervisor_response", "resolution"}:
            if user.role not in {"supervisor", "admin"}:
                raise WorkflowForbidden("supervisor_required")
            outcome = getattr(command, "proposed_outcome", getattr(command, "outcome", None))
            if outcome not in self.settings.casework_allowed_resolutions:
                raise EvidenceBlocked("resolution_not_enabled")
        if command.kind == "supervisor_response":
            if parent.kind != "escalation" or parent.id not in {
                r.id for r in self._open(rows, "escalation", "supervisor_response")
            }:
                raise EvidenceConflict("escalation_not_pending")
            if parent.actor_id == actor:
                raise WorkflowForbidden("self_approval_forbidden")
            if command.decision == "approve_resolution" and (
                not self._visible(parent, context)
                or parent.binding["case_version"] != context.case.version
            ):
                raise EvidenceConflict("escalation_stale")
            if command.decision == "approve_resolution":
                self._requirements(session, rows, context, require_review=True)
        if command.kind == "resolution":
            if (
                parent.kind != "supervisor_response"
                or parent.payload["decision"] != "approve_resolution"
                or parent.payload["proposed_outcome"] != command.outcome
                or parent.revision != revision
                or not self._visible(parent, context)
                or parent.binding["case_version"] != context.case.version
            ):
                raise EvidenceConflict("current_supervisor_approval_required")
            escalation = next(r for r in rows if r.id == parent.parent_id)
            if escalation.actor_id == actor or parent.actor_id != actor:
                raise WorkflowForbidden("resolution_separation_required")
            self._requirements(session, rows, context, require_review=True)
        entry_id, audit_id = uuid4(), uuid4()
        created = session.scalar(select(func.clock_timestamp()))
        content = dict(
            id=str(entry_id),
            case_id=str(case_id),
            actor_id=str(actor),
            author=user.username,
            revision=revision + 1,
            kind=command.kind,
            parent_id=str(parent.id) if parent else None,
            payload=payload,
            binding=binding,
        )
        content_sha = digest(content)
        event = AuditEvent(
            id=audit_id,
            created_at=created,
            actor_id=actor,
            action="evidence.casework." + command.kind,
            resource_id=str(case_id),
            details=dict(
                entry_id=str(entry_id),
                content_sha256=content_sha,
                revision=revision + 1,
                policy_version=POLICY,
            ),
        )
        session.add(event)
        session.flush()
        row = CaseworkEntry(
            id=entry_id,
            created_at=created,
            case_id=case_id,
            actor_id=actor,
            author=user.username,
            revision=revision + 1,
            kind=command.kind,
            parent_id=parent.id if parent else None,
            key_sha256=key_sha,
            request_sha256=request_sha,
            content_sha256=content_sha,
            payload=payload,
            binding=binding,
            audit_event_id=audit_id,
        )
        session.add(row)
        if command.kind == "resolution":
            # Only this explicit, confirmed four-eyes human command can change case state.
            context.case.status = (
                "closed"
                if command.outcome in {"investigation_completed", "no_further_action_recommended"}
                else "in_review"
            )
            context.case.disposition = "close" if context.case.status == "closed" else None
            context.case.version += 1
        self.reader._decode(session, command.snapshot, "snapshot")
        session.flush()
        return self._project(row, context)

    @atomic
    def supervisor_queue(self, session, actor, *, limit=20, offset=0):
        self.coordinator._gate(session)
        from app.services.case_workflows import active_actor

        active_actor(session, actor, manager=True)
        self.reader.clock.observe()
        responses = select(CaseworkEntry.parent_id).where(
            CaseworkEntry.kind == "supervisor_response"
        )
        query = (
            select(CaseworkEntry)
            .join(Case, CaseworkEntry.case_id == Case.id)
            .where(
                CaseworkEntry.kind == "escalation",
                CaseworkEntry.id.not_in(responses),
                Case.status != "closed",
            )
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(
            query.order_by(CaseworkEntry.created_at, CaseworkEntry.id).offset(offset).limit(limit)
        ).all()
        # Queue intentionally contains identifiers/attribution only. Casework retrieval rechecks sources.
        audit(session, actor, "casework.supervisor_queue", "casework-queue", returned=len(rows))
        return dict(
            items=[
                dict(
                    case_id=str(r.case_id),
                    escalation_id=str(r.id),
                    author=r.author,
                    recorded_at=r.created_at,
                )
                for r in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
