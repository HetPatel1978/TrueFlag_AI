"""Internal approved reference curation and scoped PostgreSQL lexical reads. No network/LLM."""

from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

from sqlalchemy import Date, and_, cast, exists, func, literal_column, or_, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import aliased

from app.models import User
from app.models.references import (
    CorpusMember,
    CorpusRelease,
    ReferenceApproval,
    ReferenceChunk,
    ReferenceContext,
    ReferenceDocument,
    ReferenceEvent,
    ReferenceGrant,
    ReferenceSource,
    ReferenceVersion,
)
from app.schemas.references import (
    AS_OF,
    INDEX_VERSION,
    KNOWLEDGE_CUTOFF,
    PARSER_VERSION,
    Approval,
    Citation,
    DocumentSpec,
    ReferenceQuery,
    ReferenceResult,
    VersionSpec,
)
from app.schemas.regulatory_context import RegulatoryContext, RegulatoryPassage
from app.services.evidence import (
    EvidenceConflict,
    EvidenceError,
    EvidenceNotFound,
    actor_lock,
    atomic,
    audit,
    case_lock,
)
from app.services.ingestion import digest
from app.services.reference_parser import approved_url, extract


class ReferenceInvalid(EvidenceError):
    pass


class ReferenceBlocked(EvidenceError):
    pass


def version_manifest(document, spec, extracted, source):
    return digest(
        {
            "source": {"key": source.key, "publisher": source.publisher, "host": source.host},
            "document": document.model_dump(mode="json"),
            "metadata": spec.model_dump(mode="json"),
            "parser_version": PARSER_VERSION,
            "extracted_sha256": extracted["extracted_sha256"],
            "chunks": [
                {k: v for k, v in chunk.items() if k != "body_text"}
                for chunk in extracted["chunks"]
                if chunk["section"] in spec.sections
            ],
        }
    )


def document_spec(row):
    return DocumentSpec.model_validate({k: getattr(row, k) for k in DocumentSpec.model_fields})


def version_spec(row):
    return VersionSpec.model_validate(
        {
            k: tuple(row.sections) if k == "sections" else getattr(row, k)
            for k in VersionSpec.model_fields
        }
    )


def _withdrawn(*, source=None, version=None, release=None):
    conditions = []
    if source is not None:
        conditions.append(ReferenceEvent.source_id == source)
    if version is not None:
        conditions.append(ReferenceEvent.version_id == version)
    if release is not None:
        conditions.append(ReferenceEvent.release_id == release)
    return exists(select(ReferenceEvent.id).where(or_(*conditions)))


class ReferenceService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def _curator(self, session, actor_id):
        actor_lock(session, actor_id, write=True)
        session.execute(
            sql_text(
                "SELECT pg_advisory_xact_lock(6075990640000000000 + 'reference_sources'::regclass::oid::bigint)"
            )
        )
        # Same short context lock used by reads; approvals/supersession cannot race disclosure.
        session.scalars(
            select(ReferenceContext).order_by(ReferenceContext.id).with_for_update()
        ).all()

    def _test_origin(self, origin, review_kind=None):
        if origin == "synthetic_test":
            if self.settings.app_env != "test" or review_kind not in (None, "test_fixture"):
                raise ReferenceBlocked("test_corpus_not_permitted")
        elif review_kind is not None and review_kind != "human":
            raise ReferenceBlocked("human_approval_required")

    def _version(self, session, version_id):
        if type(version_id) is not UUID:
            raise ReferenceInvalid("invalid_reference_identity")
        version = session.get(ReferenceVersion, version_id)
        if version is None:
            raise EvidenceNotFound("reference_not_found")
        return version

    def _verify(self, session, version):
        document = session.get(ReferenceDocument, version.document_id)
        source = session.get(ReferenceSource, document.source_id)
        if approved_url(document.url) != source.host:
            raise ReferenceInvalid("reference_provenance_mismatch")
        result = extract(version.raw, version.media_type)
        spec = version_spec(version)
        if (
            version.parser_version != PARSER_VERSION
            or result["raw_sha256"] != version.raw_sha256
            or result["extracted"] != version.extracted
            or result["extracted_sha256"] != version.extracted_sha256
            or version_manifest(document_spec(document), spec, result, source)
            != version.manifest_sha256
        ):
            raise ReferenceInvalid("reference_integrity_failure")
        expected = {c["section"]: c for c in result["chunks"] if c["section"] in version.sections}
        chunks = session.scalars(
            select(ReferenceChunk).where(ReferenceChunk.version_id == version.id)
        ).all()
        if len(chunks) != len(expected) or set(expected) != set(version.sections):
            raise ReferenceInvalid("reference_membership_failure")
        for row in chunks:
            exp = expected[row.section]
            if any(getattr(row, k) != v for k, v in exp.items()):
                raise ReferenceInvalid("reference_chunk_integrity_failure")
        return document, chunks

    @atomic
    def register_source(self, session, actor_id, key, publisher, host):
        self._curator(session, actor_id)
        if (
            type(key) is not str
            or not 3 <= len(key) <= 80
            or type(publisher) is not str
            or not 3 <= len(publisher) <= 160
            or approved_url("https://" + host + "/") != host
        ):
            raise ReferenceInvalid("invalid_reference_source")
        prior = session.scalar(select(ReferenceSource).where(ReferenceSource.key == key))
        if prior:
            if (prior.publisher, prior.host, prior.owner_id) != (publisher, host, actor_id):
                raise EvidenceConflict("reference_source_conflict")
            return prior.id
        if session.scalar(select(func.count()).select_from(ReferenceSource)) >= 100:
            raise ReferenceBlocked("reference_source_capacity")
        row = ReferenceSource(key=key, publisher=publisher, host=host, owner_id=actor_id)
        session.add(row)
        session.flush()
        audit(session, actor_id, "reference.source_registered", row.id)
        return row.id

    @atomic
    def admit(self, session, actor_id, source_id, document, spec, raw):
        self._curator(session, actor_id)
        if not isinstance(document, DocumentSpec) or not isinstance(spec, VersionSpec):
            raise ReferenceInvalid("invalid_reference_contract")
        document = DocumentSpec.model_validate_json(document.model_dump_json())
        spec = VersionSpec.model_validate_json(spec.model_dump_json())
        self._test_origin(document.origin)
        source = session.scalar(
            select(ReferenceSource)
            .where(ReferenceSource.id == source_id, ReferenceSource.owner_id == actor_id)
            .with_for_update()
        )
        if source is None or approved_url(document.url) != source.host:
            raise EvidenceNotFound("reference_not_found")
        extracted = extract(raw, spec.media_type)
        if extracted["raw_sha256"] != spec.raw_sha256 or len(set(spec.sections)) != len(
            spec.sections
        ):
            raise ReferenceInvalid("source_digest_or_section_mismatch")
        chunks = [c for c in extracted["chunks"] if c["section"] in spec.sections]
        if len(chunks) != len(spec.sections):
            raise ReferenceInvalid("complete_section_not_found")
        manifest = version_manifest(document, spec, extracted, source)
        doc = session.scalar(select(ReferenceDocument).where(ReferenceDocument.key == document.key))
        if doc:
            if doc.source_id != source_id or document_spec(doc) != document:
                raise EvidenceConflict("reference_document_conflict")
        else:
            doc = ReferenceDocument(source_id=source_id, **document.model_dump())
            session.add(doc)
            session.flush()
        prior = session.scalar(
            select(ReferenceVersion).where(
                ReferenceVersion.document_id == doc.id, ReferenceVersion.manifest_sha256 == manifest
            )
        )
        if prior:
            self._verify(session, prior)
            return prior.id
        previous = session.scalar(
            select(ReferenceVersion)
            .where(ReferenceVersion.document_id == doc.id)
            .order_by(ReferenceVersion.version.desc())
            .limit(1)
        )
        if previous and previous.version >= 100:
            raise ReferenceBlocked("reference_version_capacity")
        data = spec.model_dump(exclude={"sections"})
        row = ReferenceVersion(
            id=uuid4(),
            document_id=doc.id,
            version=previous.version + 1 if previous else 1,
            raw=raw,
            sections=list(spec.sections),
            extracted=extracted["extracted"],
            extracted_sha256=extracted["extracted_sha256"],
            manifest_sha256=manifest,
            parser_version=PARSER_VERSION,
            supersedes_id=previous.id if previous else None,
            admitted_by=actor_id,
            **data,
        )
        session.add(row)
        session.flush()
        for chunk in chunks:
            session.add(
                ReferenceChunk(
                    id=uuid5(row.id, chunk["section"]),
                    version_id=row.id,
                    document_id=doc.id,
                    **chunk,
                )
            )
        session.flush()
        self._verify(session, row)
        audit(
            session,
            actor_id,
            "reference.version_admitted",
            row.id,
            manifest_sha256=manifest,
            chunks=len(chunks),
            origin=document.origin,
        )
        return row.id

    @atomic
    def approve_version(self, session, actor_id, version_id, approval):
        self._curator(session, actor_id)
        if not isinstance(approval, Approval):
            raise ReferenceInvalid("invalid_reference_approval")
        approval = Approval.model_validate_json(approval.model_dump_json())
        row = self._version(session, version_id)
        document, _ = self._verify(session, row)
        self._test_origin(document.origin, approval.review_kind)
        if row.manifest_sha256 != approval.manifest_sha256:
            raise EvidenceConflict("stale_reference_approval")
        prior = session.scalar(
            select(ReferenceApproval).where(ReferenceApproval.version_id == version_id)
        )
        if prior:
            return prior.id
        if row.temporal_basis == "unknown" or row.verified_through is None:
            raise ReferenceBlocked("reference_validity_unestablished")
        if row.temporal_basis == "reviewed_interval" and (
            row.effective_from is None or row.publication_date is None
        ):
            raise ReferenceBlocked("reference_validity_unestablished")
        if row.temporal_basis == "official_dated_snapshot" and (
            row.snapshot_date is None
            or document.origin == "official_curated"
            and (
                session.get(ReferenceSource, document.source_id).host
                not in {"ecfr.gov", "www.ecfr.gov"}
                or row.media_type != "application/xml"
                or urlsplit(document.url).path
                != f"/api/versioner/v1/full/{row.snapshot_date.isoformat()}/title-31.xml"
            )
        ):
            raise ReferenceBlocked("unsupported_snapshot_provenance")
        if document.origin == "official_curated" and (
            actor_id == row.admitted_by or approval.review_reference_sha256 is None
        ):
            raise ReferenceBlocked("independent_source_review_required")
        review = ReferenceApproval(
            version_id=version_id,
            reviewer_id=actor_id,
            manifest_sha256=approval.manifest_sha256,
            review_kind=approval.review_kind,
            attestation=approval.attestation,
        )
        session.add(review)
        session.flush()
        audit(
            session,
            actor_id,
            "reference.version_approved",
            version_id,
            manifest_sha256=approval.manifest_sha256,
            review_kind=approval.review_kind,
            review_reference_sha256=approval.review_reference_sha256,
        )
        return review.id

    def _release_manifest(self, session, version_ids):
        if (
            type(version_ids) is not tuple
            or not 1 <= len(version_ids) <= 50
            or len(set(version_ids)) != len(version_ids)
        ):
            raise ReferenceInvalid("invalid_corpus_membership")
        versions = [self._version(session, i) for i in sorted(version_ids, key=str)]
        if len({v.document_id for v in versions}) != len(versions):
            raise ReferenceInvalid("ambiguous_document_versions")
        return versions, digest(
            {
                "index_version": INDEX_VERSION,
                "scope": ["US", "us_bank", "en", AS_OF.isoformat(), KNOWLEDGE_CUTOFF.isoformat()],
                "versions": [
                    {"id": str(v.id), "manifest_sha256": v.manifest_sha256} for v in versions
                ],
            }
        )

    @atomic
    def proposed_release(self, session, actor_id, version_ids):
        self._curator(session, actor_id)
        _, manifest = self._release_manifest(session, version_ids)
        return manifest

    @atomic
    def publish(self, session, actor_id, version_ids, approval):
        self._curator(session, actor_id)
        if not isinstance(approval, Approval):
            raise ReferenceInvalid("invalid_corpus_approval")
        approval = Approval.model_validate_json(approval.model_dump_json())
        versions, manifest = self._release_manifest(session, version_ids)
        if approval.manifest_sha256 != manifest:
            raise EvidenceConflict("stale_corpus_approval")
        for version in versions:
            document, _ = self._verify(session, version)
            self._test_origin(document.origin, approval.review_kind)
            review = session.scalar(
                select(ReferenceApproval).where(ReferenceApproval.version_id == version.id)
            )
            if (
                review is None
                or review.manifest_sha256 != version.manifest_sha256
                or review.review_kind != approval.review_kind
            ):
                raise ReferenceBlocked("unapproved_reference_version")
            if session.scalar(select(_withdrawn(source=document.source_id, version=version.id))):
                raise ReferenceBlocked("withdrawn_reference_version")
        prior = session.scalar(
            select(CorpusRelease).where(CorpusRelease.manifest_sha256 == manifest)
        )
        if prior:
            return session.scalar(
                select(ReferenceContext.id).where(ReferenceContext.release_id == prior.id)
            )
        total = session.scalar(
            select(func.count())
            .select_from(ReferenceChunk)
            .where(ReferenceChunk.version_id.in_(version_ids))
        )
        if total > 1000:
            raise ReferenceBlocked("corpus_chunk_capacity")
        release = CorpusRelease(
            id=uuid4(),
            manifest_sha256=manifest,
            published_by=actor_id,
            review_kind=approval.review_kind,
            index_version=INDEX_VERSION,
        )
        session.add(release)
        session.flush()
        for version in versions:
            session.add(
                CorpusMember(
                    release_id=release.id, version_id=version.id, document_id=version.document_id
                )
            )
        session.flush()
        context = ReferenceContext(
            release_id=release.id,
            jurisdiction="US",
            entity="us_bank",
            language="en",
            as_of=AS_OF,
            knowledge_cutoff=KNOWLEDGE_CUTOFF,
            approved_by=actor_id,
        )
        session.add(context)
        session.flush()
        audit(
            session,
            actor_id,
            "reference.corpus_published",
            release.id,
            manifest_sha256=manifest,
            context_id=str(context.id),
            review_kind=approval.review_kind,
        )
        return context.id

    @atomic
    def grant(self, session, actor_id, context_id, reader_id, active):
        self._curator(session, actor_id)
        if type(active) is not bool or type(context_id) is not UUID or type(reader_id) is not UUID:
            raise ReferenceInvalid("invalid_reference_grant")
        context = session.scalar(
            select(ReferenceContext).where(ReferenceContext.id == context_id).with_for_update()
        )
        if context is None or session.get(User, reader_id) is None:
            raise EvidenceNotFound("reference_not_found")
        prior = session.get(ReferenceGrant, (context_id, reader_id))
        if prior is None:
            session.add(
                ReferenceGrant(
                    context_id=context_id,
                    actor_id=reader_id,
                    active=active,
                    revision=1,
                    changed_by=actor_id,
                )
            )
        elif prior.active != active:
            prior.active = active
            prior.revision += 1
            prior.changed_by = actor_id
        else:
            return
        audit(
            session,
            actor_id,
            "reference.access_granted" if active else "reference.access_revoked",
            context_id,
            reader_id=str(reader_id),
        )

    @atomic
    def withdraw(self, session, actor_id, *, source_id=None, version_id=None, release_id=None):
        self._curator(session, actor_id)
        if sum(v is not None for v in (source_id, version_id, release_id)) != 1:
            raise ReferenceInvalid("invalid_reference_withdrawal")
        conditions = []
        for value, model, column in (
            (source_id, ReferenceSource, ReferenceEvent.source_id),
            (version_id, ReferenceVersion, ReferenceEvent.version_id),
            (release_id, CorpusRelease, ReferenceEvent.release_id),
        ):
            if value is not None:
                if type(value) is not UUID or session.get(model, value) is None:
                    raise EvidenceNotFound("reference_not_found")
                conditions.append(column == value)
        # Serialize with all readers using the approved context/release locks.
        contexts = session.scalars(
            select(ReferenceContext).order_by(ReferenceContext.id).with_for_update()
        ).all()
        if session.scalar(select(ReferenceEvent.id).where(*conditions)):
            return
        session.add(
            ReferenceEvent(
                source_id=source_id,
                version_id=version_id,
                release_id=release_id,
                action="withdraw",
                actor_id=actor_id,
            )
        )
        audit(
            session,
            actor_id,
            "reference.withdrawn",
            source_id or version_id or release_id,
            context_count=len(contexts),
        )

    def _context(self, session, actor_id, case_id):
        actor_lock(session, actor_id, write=False)
        case_lock(session, actor_id, case_id)
        identity = self.settings.regulatory_context_id
        if identity is None:
            return None, None
        context = session.scalar(
            select(ReferenceContext).where(ReferenceContext.id == identity).with_for_update()
        )
        grant = session.get(ReferenceGrant, (identity, actor_id))
        if context is None or grant is None or not grant.active:
            raise EvidenceNotFound("reference_not_found")
        if (
            context.jurisdiction,
            context.entity,
            context.language,
            context.as_of,
            context.knowledge_cutoff,
        ) != ("US", "us_bank", "en", AS_OF, KNOWLEDGE_CUTOFF):
            raise ReferenceBlocked("unapproved_reference_scope")
        release = session.get(CorpusRelease, context.release_id)
        self._test_origin(
            "synthetic_test" if release.review_kind == "test_fixture" else "official_curated",
            release.review_kind,
        )
        return context, release

    def _base(self, context):
        return (
            select(ReferenceChunk, ReferenceVersion, ReferenceDocument, ReferenceSource)
            .join(ReferenceVersion, ReferenceChunk.version_id == ReferenceVersion.id)
            .join(CorpusMember, CorpusMember.version_id == ReferenceVersion.id)
            .join(ReferenceApproval, ReferenceApproval.version_id == ReferenceVersion.id)
            .join(ReferenceDocument, ReferenceVersion.document_id == ReferenceDocument.id)
            .join(ReferenceSource, ReferenceDocument.source_id == ReferenceSource.id)
            .where(
                CorpusMember.release_id == context.release_id,
                ReferenceApproval.manifest_sha256 == ReferenceVersion.manifest_sha256,
                ~_withdrawn(
                    source=ReferenceSource.id,
                    version=ReferenceVersion.id,
                    release=context.release_id,
                ),
            )
        )

    def _applicable(self, context):
        newer = aliased(ReferenceVersion)
        newer_approval = aliased(ReferenceApproval)
        superseded = exists(
            select(newer.id)
            .join(newer_approval, newer_approval.version_id == newer.id)
            .where(
                newer.document_id == ReferenceVersion.document_id,
                newer.version > ReferenceVersion.version,
                or_(
                    newer.effective_from <= context.as_of,
                    and_(
                        newer.temporal_basis == "official_dated_snapshot",
                        newer.snapshot_date == context.as_of,
                    ),
                ),
                or_(
                    newer.publication_date.is_(None),
                    newer.publication_date <= context.knowledge_cutoff,
                ),
                newer.verified_through >= context.as_of,
                cast(func.timezone("America/New_York", newer.retrieved_at), Date)
                <= context.knowledge_cutoff,
            )
        )
        valid = or_(
            and_(
                ReferenceVersion.temporal_basis == "official_dated_snapshot",
                ReferenceVersion.snapshot_date == context.as_of,
            ),
            and_(
                ReferenceVersion.temporal_basis == "reviewed_interval",
                ReferenceVersion.publication_date.is_not(None),
                ReferenceVersion.effective_from <= context.as_of,
                or_(
                    ReferenceVersion.effective_to.is_(None),
                    ReferenceVersion.effective_to > context.as_of,
                ),
            ),
        )
        return and_(
            ReferenceDocument.jurisdiction == context.jurisdiction,
            ReferenceDocument.entity == context.entity,
            ReferenceDocument.language == context.language,
            ReferenceDocument.authority.in_(["binding_regulation", "statute", "guidance"]),
            ReferenceDocument.origin
            == ("synthetic_test" if self.settings.app_env == "test" else "official_curated"),
            ReferenceVersion.verified_through >= context.as_of,
            or_(
                ReferenceVersion.publication_date.is_(None),
                ReferenceVersion.publication_date <= context.knowledge_cutoff,
            ),
            cast(func.timezone("America/New_York", ReferenceVersion.retrieved_at), Date)
            <= context.knowledge_cutoff,
            valid,
            ~superseded,
        )

    def _citation(self, context, chunk, version, document, source):
        limitations = [
            "legal_context_not_customer_violation_evidence",
            "conditional_provisions_and_cross_references_require_review",
        ]
        if document.origin == "synthetic_test":
            limitations.append("synthetic_fixture_not_legal_authority")
        if version.publication_date is None:
            limitations.append("exact_publication_date_not_established")
        if version.effective_from is None:
            limitations.append("exact_legal_commencement_not_established_dated_snapshot_only")
        return Citation(
            reference_id=uuid5(context.id, str(chunk.id) + ":" + chunk.text_sha256),
            context_id=context.id,
            release_id=context.release_id,
            document_id=document.id,
            version_id=version.id,
            chunk_id=chunk.id,
            publisher=source.publisher,
            title=document.title,
            authority=document.authority,
            origin=document.origin,
            source_url=document.url,
            section=chunk.section,
            locator=chunk.locator,
            start_byte=chunk.start_byte,
            end_byte=chunk.end_byte,
            text=chunk.body_text,
            text_sha256=chunk.text_sha256,
            raw_sha256=version.raw_sha256,
            extracted_sha256=version.extracted_sha256,
            parser_version=version.parser_version,
            publication_date=version.publication_date,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            snapshot_date=version.snapshot_date,
            temporal_basis=version.temporal_basis,
            verified_through=version.verified_through,
            retrieved_at=version.retrieved_at,
            as_of=context.as_of,
            jurisdiction=context.jurisdiction,
            entity=context.entity,
            language=context.language,
            limitations=limitations,
        )

    def _finish(self, session, actor, case_id, context, status, passages, query_sha):
        result = ReferenceResult(
            status=status,
            context_id=context.id if context else None,
            release_id=context.release_id if context else None,
            release_sha256=session.get(CorpusRelease, context.release_id).manifest_sha256
            if context
            else None,
            passages=passages,
            limitations=[
                "historical_development_scope_2026_11_02",
                "not_a_complete_BSA_corpus",
                "references_are_context_not_legal_findings",
            ],
        )
        if len(result.model_dump_json().encode()) > 262144:
            raise ReferenceBlocked("reference_response_limit")
        audit(
            session,
            actor,
            "reference.retrieved",
            case_id,
            context_id=str(context.id) if context else None,
            query_sha256=query_sha,
            response_sha256=digest(result.model_dump(mode="json")),
            returned=len(passages),
            index_version=INDEX_VERSION,
            status=status,
        )
        return result

    @atomic
    def retrieve_reference_context(self, session, actor_id, case_id, request):
        if not isinstance(request, ReferenceQuery):
            raise ReferenceInvalid("invalid_reference_query")
        request = ReferenceQuery.model_validate_json(request.model_dump_json())
        context, release = self._context(session, actor_id, case_id)
        qsha = digest(request.model_dump(mode="json"))
        if context is None:
            return self._finish(session, actor_id, case_id, None, "unavailable", [], qsha)
        if session.scalar(select(_withdrawn(release=release.id))):
            return self._finish(session, actor_id, case_id, context, "withdrawn", [], qsha)
        vector = func.to_tsvector(literal_column("'english'::regconfig"), ReferenceChunk.body_text)
        statement = self._base(context).where(self._applicable(context))
        if request.section is not None:
            statement = statement.where(ReferenceChunk.section == request.section)
            rank = None
        else:
            terms = func.websearch_to_tsquery(literal_column("'english'::regconfig"), request.query)
            if session.scalar(select(func.numnode(terms))) == 0:
                return self._finish(session, actor_id, case_id, context, "ambiguous", [], qsha)
            statement = statement.where(vector.op("@@")(terms))
            rank = func.ts_rank_cd(vector, terms)
        # All authority/scope/date/access predicates are in WHERE before rank/order/limit.
        order = [ReferenceChunk.section, ReferenceChunk.id]
        if rank is not None:
            order.insert(0, rank.desc())
        rows = session.execute(statement.order_by(*order).limit(request.limit)).all()
        passages = []
        for chunk, version, document, source in rows:
            self._verify(session, version)
            passages.append(self._citation(context, chunk, version, document, source))
        status = "available" if passages else "empty"
        if not passages:
            active = session.scalar(
                self._base(context)
                .with_only_columns(func.count(), maintain_column_froms=True)
                .order_by(None)
            )
            scoped = session.scalar(
                self._base(context)
                .where(
                    ReferenceDocument.jurisdiction == context.jurisdiction,
                    ReferenceDocument.entity == context.entity,
                )
                .with_only_columns(func.count(), maintain_column_froms=True)
                .order_by(None)
            )
            applicable = session.scalar(
                self._base(context)
                .where(self._applicable(context))
                .with_only_columns(func.count(), maintain_column_froms=True)
                .order_by(None)
            )
            status = (
                "withdrawn"
                if not active
                else "inapplicable"
                if not scoped
                else "outdated"
                if not applicable
                else "empty"
            )
        return self._finish(session, actor_id, case_id, context, status, passages, qsha)

    @atomic
    def resolve_citation(self, session, actor_id, case_id, reference_id):
        if type(reference_id) is not UUID:
            raise ReferenceInvalid("invalid_reference_identity")
        context, release = self._context(session, actor_id, case_id)
        if context is None or session.scalar(select(_withdrawn(release=release.id))):
            raise EvidenceNotFound("reference_not_found")
        rows = session.execute(
            self._base(context).where(self._applicable(context)).limit(1001)
        ).all()
        if len(rows) > 1000:
            raise ReferenceBlocked("corpus_resolution_limit")
        for chunk, version, document, source in rows:
            if uuid5(context.id, str(chunk.id) + ":" + chunk.text_sha256) == reference_id:
                self._verify(session, version)
                return self._finish(
                    session,
                    actor_id,
                    case_id,
                    context,
                    "available",
                    [self._citation(context, chunk, version, document, source)],
                    digest({"reference_id": str(reference_id)}),
                )
        raise EvidenceNotFound("reference_not_found")

    @atomic
    def validate_regulatory_selection(self, session, actor_id, case_id, citations):
        """Fresh, atomic source/permission fencing for future investigator handoff.

        This is not an LLM tool or public endpoint. Caller selections have no authority:
        compare every field against the current approved stored source before returning.
        """
        if (
            type(citations) is not tuple
            or not 1 <= len(citations) <= 5
            or any(not isinstance(c, Citation) for c in citations)
        ):
            raise ReferenceInvalid("invalid_regulatory_selection")
        supplied = [Citation.model_validate_json(c.model_dump_json()) for c in citations]
        if len({c.reference_id for c in supplied}) != len(supplied):
            raise ReferenceInvalid("duplicate_regulatory_selection")
        context, release = self._context(session, actor_id, case_id)
        if context is None or session.scalar(select(_withdrawn(release=release.id))):
            raise EvidenceNotFound("reference_not_found")
        rows = session.execute(
            self._base(context).where(self._applicable(context)).limit(1001)
        ).all()
        if len(rows) > 1000:
            raise ReferenceBlocked("corpus_resolution_limit")
        expected = {c.reference_id: c for c in supplied}
        found = {}
        for chunk, version, document, source in rows:
            identity = uuid5(context.id, str(chunk.id) + ":" + chunk.text_sha256)
            if identity not in expected:
                continue
            self._verify(session, version)
            current = self._citation(context, chunk, version, document, source)
            if current != expected[identity]:
                raise EvidenceNotFound("reference_not_found")
            review = session.scalar(
                select(ReferenceApproval).where(ReferenceApproval.version_id == version.id)
            )
            # Review dossier references live in immutable audit metadata, not source text.
            from app.models import AuditEvent

            event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence.reference.version_approved",
                    AuditEvent.resource_id == str(version.id),
                )
            )
            review_hash = event.details.get("review_reference_sha256") if event else None
            if document.origin == "official_curated" and (
                review.review_kind != "human"
                or review.reviewer_id == version.admitted_by
                or review_hash is None
            ):
                raise ReferenceBlocked("independent_source_review_required")
            found[identity] = RegulatoryPassage(
                source_id=source.id,
                source_key=source.key,
                version_manifest_sha256=version.manifest_sha256,
                approval_id=review.id,
                reviewer_reference=review.reviewer_id,
                review_reference_sha256=review_hash,
                review_kind=review.review_kind,
                citation=current,
            )
        if set(found) != set(expected):
            raise EvidenceNotFound("reference_not_found")
        ordered = [found[c.reference_id] for c in supplied]
        result = self._finish(
            session,
            actor_id,
            case_id,
            context,
            "available",
            [s.citation for s in ordered],
            digest([str(c.reference_id) for c in supplied]),
        )
        payload = dict(
            case_id=str(case_id),
            result=result.model_dump(mode="json"),
            sources=[s.model_dump(mode="json") for s in ordered],
        )
        envelope = RegulatoryContext(
            case_id=case_id, result=result, sources=tuple(ordered), context_sha256=digest(payload)
        )
        if len(envelope.model_dump_json().encode()) > 262144:
            raise ReferenceBlocked("reference_response_limit")
        audit(
            session,
            actor_id,
            "reference.selection_verified",
            case_id,
            context_sha256=envelope.context_sha256,
            selected=len(ordered),
        )
        return envelope
