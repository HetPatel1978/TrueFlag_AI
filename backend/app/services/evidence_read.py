"""Current-authority reads over frozen case evidence. No ingestion, model calls or network."""

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

import jwt
from pydantic import ValidationError
from sqlalchemy import select

from app.models import Alert, Assessment, User
from app.models.evidence import (
    CaseEvidenceLink,
    CaseEvidenceState,
    EvidenceAccount,
    EvidenceCustomer,
    EvidenceIdentity,
    EvidenceRecordVersion,
    EvidenceRelationship,
    EvidenceSourceAccess,
    EvidenceSourceVersion,
    EvidenceTransaction,
)
from app.schemas.evidence_read import (
    RETRIEVAL_VERSION,
    AnalyticsRequest,
    CaseContext,
    Coverage,
    CustomerItem,
    CustomerPage,
    CustomerRequest,
    EvidenceReference,
    EvidenceResponse,
    ModelSignal,
    ReadRequest,
    RelatedItem,
    RelatedPage,
    RelatedRequest,
    SnapshotIdentity,
    SourceReference,
    TransactionItem,
    TransactionPage,
    TransactionRequest,
    Window,
)
from app.services.assessment_api import _detail
from app.services.assessments import _read
from app.services.evidence import (
    EvidenceError,
    EvidenceNotFound,
    actor_lock,
    atomic,
    audit,
    case_lock,
    verify_release,
)
from app.services.evidence_analytics import calculate, in_window
from app.services.ingestion import digest
from app.services.snapshot_clock import SnapshotTime

MAX_RESPONSE_BYTES = 262144
SNAPSHOT_SECONDS = 900
KINDS = ("customer", "account", "relationship", "transaction")


class ReadInvalid(EvidenceError):
    pass


class SnapshotStale(EvidenceError):
    pass


class ReadLimit(EvidenceError):
    pass


@dataclass
class Context:
    actor: UUID
    case: object
    snapshot: SnapshotIdentity
    expires: int
    assessment_id: UUID | None
    rows: list
    sources: list
    identities: dict
    payloads: dict
    refs: list
    historical_excluded: int
    clock_epoch: int


def reference(row):
    return EvidenceReference(
        record_version_id=row.id,
        identity_id=row.identity_id,
        source_version_id=row.source_version_id,
        kind=row.kind,
        version=row.version,
        sha256=row.content_sha256,
    )


def normalized(body):
    return body.model_dump(mode="json", exclude={"snapshot", "cursor"})


class EvidenceReadService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.clock = SnapshotTime(engine)
        self.key = hmac.digest(
            settings.jwt_secret.get_secret_value().encode(),
            b"trueflag.evidence-read.signing.v2",
            "sha256",
        )
        self.issuer = settings.jwt_issuer + ":evidence"

    def _sign(self, content):
        return jwt.encode(
            {**content, "iss": self.issuer, "aud": RETRIEVAL_VERSION}, self.key, algorithm="HS256"
        )

    def _decode(self, session, token, kind):
        try:
            if type(token) is not str or not 32 <= len(token) <= 4096:
                raise ValueError
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["HS256"],
                audience=RETRIEVAL_VERSION,
                issuer=self.issuer,
                options={"verify_exp": False, "verify_iat": False, "verify_nbf": False},
            )
            expected = {"kind", "scope", "actor", "case", "expires", "clock_epoch", "iss", "aud"}
            expected |= {"assessment"} if kind == "snapshot" else {"query", "operation", "offset"}
            if (
                set(claims) != expected
                or claims["kind"] != kind
                or type(claims["expires"]) is not int
                or type(claims["clock_epoch"]) is not int
                or claims["clock_epoch"] < 1
                or type(claims["scope"]) is not str
                or len(claims["scope"]) != 64
            ):
                raise ValueError
        except Exception:
            raise ReadInvalid("invalid_or_expired_evidence_token") from None
        observed = self.clock.observe()
        if (
            claims["expires"] <= observed.second
            or claims["expires"] > observed.second + SNAPSHOT_SECONDS
            or claims["clock_epoch"] != observed.epoch
        ):
            raise ReadInvalid("invalid_or_expired_evidence_token")
        return claims

    def ensure_clock(self, epoch):
        if self.clock.observe().epoch != epoch:
            raise ReadInvalid("invalid_or_expired_evidence_token")

    def _claims(self, context, kind):
        return {
            "kind": kind,
            "scope": context.snapshot.sha256,
            "actor": str(context.actor),
            "case": str(context.case.id),
            "expires": context.expires,
            "clock_epoch": context.clock_epoch,
        }

    def _snapshot_token(self, context):
        return self._sign(
            {
                **self._claims(context, "snapshot"),
                "assessment": str(context.assessment_id) if context.assessment_id else None,
            }
        )

    def _assessment(self, session, context):
        if context.assessment_id is None:
            return None
        row = session.scalar(
            select(Assessment).where(
                Assessment.id == context.assessment_id, Assessment.case_id == context.case.id
            )
        )
        if row is None:
            raise EvidenceNotFound("evidence_not_found")
        return _detail(_read(session, row))

    def _context(self, session, actor, case_id, *, token=None, assessment_id=None):
        actor_lock(session, actor, write=False)
        case = case_lock(session, actor, case_id)
        observed = self.clock.observe()
        claims = self._decode(session, token, "snapshot") if token is not None else None
        if claims:
            if claims["actor"] != str(actor) or claims["case"] != str(case_id):
                raise EvidenceNotFound("evidence_not_found")
            try:
                assessment_id = (
                    UUID(claims["assessment"]) if claims["assessment"] is not None else None
                )
            except (ValueError, TypeError):
                raise ReadInvalid("invalid_evidence_snapshot") from None
        elif assessment_id is not None and type(assessment_id) is not UUID:
            raise ReadInvalid("invalid_assessment_selection")
        # Filtering precedes ordering, limits and any count or projection. Never query related cases.
        visible = session.scalars(
            select(EvidenceRecordVersion)
            .join(CaseEvidenceLink, CaseEvidenceLink.record_version_id == EvidenceRecordVersion.id)
            .join(
                EvidenceSourceAccess,
                (EvidenceSourceAccess.case_id == CaseEvidenceLink.case_id)
                & (EvidenceSourceAccess.source_id == CaseEvidenceLink.source_id),
            )
            .where(
                CaseEvidenceLink.case_id == case_id,
                CaseEvidenceLink.active.is_(True),
                EvidenceSourceAccess.active.is_(True),
            )
            .order_by(EvidenceRecordVersion.id)
            .limit(1001)
        ).all()
        if len(visible) > 1000:
            raise ReadLimit("evidence_snapshot_limit")
        releases = session.scalars(
            select(EvidenceSourceVersion).where(
                EvidenceSourceVersion.id.in_({r.source_version_id for r in visible})
            )
        ).all()
        latest = {}
        for release in releases:
            if (
                release.source_id not in latest
                or release.version > latest[release.source_id].version
            ):
                latest[release.source_id] = release
        selected = {r.id for r in latest.values()}
        rows = [r for r in visible if r.source_version_id in selected]
        if len(rows) > 200 or len(latest) > 10:
            raise ReadLimit("evidence_snapshot_limit")
        sources, linked = [], {r.id for r in rows}
        alert = session.get(Alert, case.alert_id)
        for release in sorted(latest.values(), key=lambda r: str(r.id)):
            # Existing trusted integrity check; unlinked payloads are never projected or analyzed.
            bundle, members = verify_release(session, release)
            sources.append(
                SourceReference(
                    source_id=release.source_id,
                    source_version_id=release.id,
                    version=release.version,
                    sha256=release.content_sha256,
                    generator_version=bundle.generator_version,
                    coverage=release.coverage,
                    window=Window(start=release.window_start, end=release.as_of),
                    membership_complete={r.id for r in members}.issubset(linked),
                    case_input_reconciliation="matches_declared_inputs"
                    if release.declarations == alert.features
                    else "differs_from_immutable_case_input",
                )
            )
        state = session.get(CaseEvidenceState, case_id)
        role = session.get(User, actor).role
        content = {
            "actor": str(actor),
            "role": role,
            "case": str(case_id),
            "case_version": case.version,
            "case_state": case.status,
            "human_disposition": case.disposition,
            "assigned_to": str(case.assigned_to) if case.assigned_to else None,
            "evidence_revision": state.evidence_revision if state else 0,
            "access_revision": state.access_revision if state else 0,
            "assessment_id": str(assessment_id) if assessment_id else None,
            "visible": [reference(r).model_dump(mode="json") for r in visible],
            "selected": [s.model_dump(mode="json") for s in sources],
            "version": RETRIEVAL_VERSION,
        }
        sha = digest(content)
        if claims and claims["scope"] != sha:
            raise SnapshotStale("evidence_snapshot_invalidated")
        identity = SnapshotIdentity(
            id=uuid5(NAMESPACE_URL, "evidence-snapshot:" + sha),
            sha256=sha,
            case_id=case_id,
            case_version=case.version,
            evidence_revision=content["evidence_revision"],
            access_revision=content["access_revision"],
        )
        ids = {r.identity_id for r in rows}
        identities = {
            r.id: r
            for r in session.scalars(select(EvidenceIdentity).where(EvidenceIdentity.id.in_(ids)))
        }
        payloads = {}
        for kind, model in (
            ("customer", EvidenceCustomer),
            ("account", EvidenceAccount),
            ("relationship", EvidenceRelationship),
            ("transaction", EvidenceTransaction),
        ):
            record_ids = [r.id for r in rows if r.kind == kind]
            payloads[kind] = {
                r.record_version_id: r
                for r in session.scalars(
                    select(model).where(model.record_version_id.in_(record_ids))
                )
            }
        return Context(
            actor,
            case,
            identity,
            claims["expires"] if claims else observed.second + SNAPSHOT_SECONDS,
            assessment_id,
            rows,
            sources,
            identities,
            payloads,
            [reference(r) for r in rows],
            len(visible) - len(rows),
            claims["clock_epoch"] if claims else observed.epoch,
        )

    def _validate(self, request, model):
        if not isinstance(request, model):
            raise ReadInvalid("invalid_evidence_request")
        try:
            return model.model_validate_json(request.model_dump_json())
        except ValidationError:
            raise ReadInvalid("invalid_evidence_request") from None

    def _handles(self, context, kind):
        return {r.identity_id for r in context.rows if r.kind == kind}

    def _transactions(self, context):
        accounts, transactions = (
            self._handles(context, "account"),
            self._handles(context, "transaction"),
        )
        result = []
        for row in context.rows:
            if row.kind != "transaction":
                continue
            payload = context.payloads["transaction"][row.id]
            result.append(
                TransactionItem(
                    reference=reference(row),
                    account_handle=payload.account_id if payload.account_id in accounts else None,
                    counterparty_handle=payload.counterparty_id
                    if payload.counterparty_id in accounts
                    else None,
                    amount=payload.amount,
                    currency=payload.currency,
                    event_at=payload.event_at,
                    original_time=payload.original_time,
                    event_kind=payload.event_kind,
                    direction=payload.direction,
                    channel=payload.channel,
                    reverses_handle=payload.reverses_id
                    if payload.reverses_id in transactions
                    else None,
                )
            )
        return sorted(
            result,
            key=lambda r: (
                r.event_at is None,
                r.event_at or datetime.max.replace(tzinfo=timezone.utc),
                str(r.reference.record_version_id),
            ),
        )

    def _filtered(self, context, query):
        if query.account_handle is not None and query.account_handle not in self._handles(
            context, "account"
        ):
            raise EvidenceNotFound("evidence_not_found")
        result, stats = (
            [],
            {"unknown_time_excluded": 0, "outside_window_excluded": 0, "filter_excluded": 0},
        )
        for row in self._transactions(context):
            if (
                (query.account_handle is not None and row.account_handle != query.account_handle)
                or (query.currency is not None and row.currency != query.currency)
                or (query.direction is not None and row.direction != query.direction)
                or (
                    getattr(query, "event_kind", None) is not None
                    and row.event_kind != query.event_kind
                )
            ):
                stats["filter_excluded"] += 1
            elif query.window is not None and row.event_at is None:
                stats["unknown_time_excluded"] += 1
            elif query.window is not None and not in_window(row, query.window):
                stats["outside_window_excluded"] += 1
            else:
                result.append(row)
        return result, stats

    def _coverage(self, context, window=None, stats=None):
        stats = stats or {"unknown_time_excluded": 0}
        limitations = [
            "synthetic_observations_only",
            "settlement_status_not_recorded",
            "sampling_metadata_not_recorded",
            "rf_inputs_not_transaction_derivations",
        ]
        if not context.sources or all(s.coverage == "unavailable" for s in context.sources):
            status = "unavailable"
            limitations.append("insufficient_transaction_evidence")
        else:
            complete = all(
                s.membership_complete
                and s.coverage == "complete_declared_window"
                and (
                    window is None
                    or (s.window.start <= window.start and s.window.end >= window.end)
                )
                for s in context.sources
            )
            status = (
                "complete_declared_window"
                if complete and not stats["unknown_time_excluded"]
                else "partial"
            )
            if status == "partial":
                limitations.append("incomplete_evidence_not_zero_activity")
        return Coverage(
            status=status,
            requested=window,
            historical_versions_excluded=context.historical_excluded,
            limitations=limitations,
            **stats,
        )

    def _page(self, session, context, query, operation, items):
        offset = 0
        qsha = digest(normalized(query))
        if query.cursor:
            cursor = self._decode(session, query.cursor, "cursor")
            if (
                cursor["actor"] != str(context.actor)
                or cursor["case"] != str(context.case.id)
                or cursor["scope"] != context.snapshot.sha256
                or cursor["query"] != qsha
                or cursor["operation"] != operation
                or cursor["expires"] != context.expires
                or type(cursor["offset"]) is not int
                or not 0 <= cursor["offset"] <= len(items)
            ):
                raise ReadInvalid("invalid_evidence_cursor")
            offset = cursor["offset"]
        page = items[offset : offset + query.limit]
        next_offset = offset + len(page)
        cursor = (
            self._sign(
                {
                    **self._claims(context, "cursor"),
                    "query": qsha,
                    "operation": operation,
                    "offset": next_offset,
                }
            )
            if next_offset < len(items)
            else None
        )
        return page, cursor

    def _respond(self, session, context, operation, query, data, classification, coverage=None):
        self.ensure_clock(context.clock_epoch)
        coverage = coverage or self._coverage(context)
        parameters = (
            normalized(query)
            if query is not None
            else {"assessment_id": str(context.assessment_id) if context.assessment_id else None}
        )
        # Cursor position affects a page reference; token signatures/expiry do not affect facts.
        value = {
            "operation": operation,
            "parameters": parameters,
            "snapshot": context.snapshot.model_dump(mode="json"),
            "coverage": coverage.model_dump(mode="json"),
            "data": data.model_dump(mode="json", exclude={"snapshot_token", "next_cursor"}),
        }
        sha = digest(value)
        result = EvidenceResponse[type(data)](
            reference_id=uuid5(NAMESPACE_URL, RETRIEVAL_VERSION + ":" + sha),
            reference_sha256=sha,
            classification=classification,
            snapshot=context.snapshot,
            sources=context.sources,
            evidence=context.refs,
            coverage=coverage,
            parameters=parameters,
            data=data,
        )
        if len(result.model_dump_json().encode()) > MAX_RESPONSE_BYTES:
            raise ReadLimit("evidence_response_limit")
        audit(
            session,
            context.actor,
            "retrieval." + operation,
            context.case.id,
            reference_id=str(result.reference_id),
            reference_sha256=sha,
            snapshot_id=str(context.snapshot.id),
            snapshot_sha256=context.snapshot.sha256,
            evidence_revision=context.snapshot.evidence_revision,
            access_revision=context.snapshot.access_revision,
            request_sha256=digest(parameters),
            response_sha256=digest(result.model_dump(mode="json", exclude={"data"})),
            record_count=len(context.refs),
            retrieval_version=RETRIEVAL_VERSION,
        )
        return result

    @atomic
    def get_case_context(self, session, actor_id, case_id, assessment_id=None):
        context = self._context(session, actor_id, case_id, assessment_id=assessment_id)
        model = self._assessment(session, context)
        available = [k for k in KINDS if context.payloads[k]]
        data = CaseContext(
            case_id=case_id,
            state=context.case.status,
            disposition=context.case.disposition,
            snapshot_token=self._snapshot_token(context),
            selected_assessment_id=assessment_id,
            model_signal=model,
            available_categories=available,
            missing_categories=[k for k in KINDS if k not in available],
            account_handles=sorted(self._handles(context, "account"), key=str),
        )
        return self._respond(session, context, "case_context", None, data, "case_context")

    @atomic
    def get_transactions(self, session, actor_id, case_id, request):
        query = self._validate(request, TransactionRequest)
        context = self._context(session, actor_id, case_id, token=query.snapshot)
        rows, stats = self._filtered(context, query)
        page, cursor = self._page(session, context, query, "transactions", rows)
        return self._respond(
            session,
            context,
            "transactions",
            query,
            TransactionPage(items=page, total=len(rows), next_cursor=cursor),
            "source_observations",
            self._coverage(context, query.window, stats),
        )

    @atomic
    def get_customer_context(self, session, actor_id, case_id, request):
        query = self._validate(request, CustomerRequest)
        context = self._context(session, actor_id, case_id, token=query.snapshot)
        groups = {}
        for payload in context.payloads["customer"].values():
            groups.setdefault((payload.source_id, payload.subject_key), set()).add(
                (payload.annual_income, payload.currency, payload.kyc_score)
            )
        source_dates = {s.source_id: s.window.end for s in context.sources}
        items = []
        for row in context.rows:
            if row.kind != "customer":
                continue
            payload = context.payloads["customer"][row.id]
            age = max(0, (source_dates[row.source_id] - payload.observed_at).days)
            items.append(
                CustomerItem(
                    reference=reference(row),
                    customer_handle=row.identity_id,
                    alias=payload.alias,
                    observed_at=payload.observed_at,
                    annual_income=payload.annual_income,
                    currency=payload.currency,
                    declared_kyc_score=payload.kyc_score,
                    age_days_at_source_as_of=age,
                    stale=age > query.stale_after_days
                    if query.stale_after_days is not None
                    else None,
                    contradictory_observations=len(groups[(row.source_id, payload.subject_key)])
                    > 1,
                )
            )
        items.sort(key=lambda r: (r.observed_at, str(r.reference.record_version_id)))
        page, cursor = self._page(session, context, query, "customers", items)
        coverage = self._coverage(context)
        coverage.limitations.append("declared_expected_activity_not_recorded")
        if any(r.contradictory_observations for r in items):
            coverage.limitations.append("contradictory_kyc_observations")
        return self._respond(
            session,
            context,
            "customers",
            query,
            CustomerPage(items=page, total=len(items), next_cursor=cursor),
            "source_observations",
            coverage,
        )

    @atomic
    def get_related_evidence(self, session, actor_id, case_id, request):
        query = self._validate(request, RelatedRequest)
        context = self._context(session, actor_id, case_id, token=query.snapshot)
        accounts, customers = self._handles(context, "account"), self._handles(context, "customer")
        if query.entity_handle is not None and query.entity_handle not in accounts | customers:
            raise EvidenceNotFound("evidence_not_found")
        edges = [
            p
            for p in context.payloads["relationship"].values()
            if p.account_id in accounts
            and p.customer_id in customers
            and (
                query.entity_handle is None or query.entity_handle in (p.account_id, p.customer_id)
            )
        ]
        selected_accounts = (
            accounts
            if query.entity_handle is None
            else ({query.entity_handle} & accounts) | {p.account_id for p in edges}
        )
        refs = {r.record_version_id: r for r in context.refs}
        items = [
            RelatedItem(
                reference=refs[p.record_version_id],
                kind="account",
                account_handle=next(
                    r.identity_id for r in context.rows if r.id == p.record_version_id
                ),
                customer_handle=None,
                alias=p.alias,
                currency=p.currency,
                relation=None,
                observed_at=None,
                opened_at=p.opened_at,
            )
            for p in context.payloads["account"].values()
            if refs[p.record_version_id].identity_id in selected_accounts
        ]
        items += [
            RelatedItem(
                reference=refs[p.record_version_id],
                kind="relationship",
                account_handle=p.account_id,
                customer_handle=p.customer_id,
                alias=None,
                currency=None,
                relation=p.relation,
                observed_at=p.observed_at,
            )
            for p in edges
        ]
        items.sort(key=lambda r: str(r.reference.record_version_id))
        page, cursor = self._page(session, context, query, "related", items)
        coverage = self._coverage(context)
        coverage.limitations.append("curated_documents_not_admitted")
        return self._respond(
            session,
            context,
            "related",
            query,
            RelatedPage(items=page, total=len(items), next_cursor=cursor),
            "source_observations",
            coverage,
        )

    @atomic
    def get_model_assessment(self, session, actor_id, case_id, request):
        query = self._validate(request, ReadRequest)
        context = self._context(session, actor_id, case_id, token=query.snapshot)
        data = ModelSignal(assessment=self._assessment(session, context))
        coverage = self._coverage(context)
        if data.assessment is None:
            coverage.limitations.append("no_stored_assessment_selected")
        return self._respond(
            session, context, "model_assessment", query, data, "model_signal", coverage
        )

    @atomic
    def calculate_activity(self, session, actor_id, case_id, request):
        query = self._validate(request, AnalyticsRequest)
        context = self._context(session, actor_id, case_id, token=query.snapshot)
        _, stats = self._filtered(context, query)
        coverage = self._coverage(context, query.window, stats)
        result = calculate(self._transactions(context), query, coverage)
        if result.unmatched_reversals:
            coverage.limitations.append("unresolved_reversals_not_netted")
        if query.calculation == "kyc_comparison":
            coverage.limitations.append("declared_expected_activity_not_recorded")
        return self._respond(session, context, "activity", query, result, "derived_fact", coverage)
