"""Isolated academic retrieval. Never admits, approves or publishes regulatory sources."""

import hashlib
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from app.models import Alert
from app.models.evidence import EvidenceSource
from app.schemas.investigations import InputManifest
from app.schemas.references import ReferenceQuery
from app.schemas.research_demo import (
    ResearchBinding,
    ResearchBindingV2,
    ResearchBindingV3,
    ResearchBindingV4,
    ResearchCitation,
    ResearchExcerptCitation,
    ResearchProviderInput,
    ResearchRetrieval,
    ResearchRetrievalV2,
    ResearchRetrievalV3,
    RetrievalResult,
    RetrievalResultV2,
)
from app.services.evidence import EvidenceBlocked, atomic, audit
from app.services.evidence_read import SnapshotStale
from app.services.ingestion import digest
from app.services.investigation_draft_verifier import minimize, validate_proposal
from app.services.investigation_provider import strict_json
from app.services.investigation_verifier import VerificationFailed
from app.services.reference_parser import extract
from app.services.regulatory_investigation import RegulatoryInvestigationService
from app.services import research_retrieval

ROOT = Path(__file__).resolve().parents[3]
PROPOSAL_SHA = "832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1"


def sha(value):
    return hashlib.sha256(value).hexdigest()


class ResearchCitationFailure(VerificationFailed):
    """Fixed reason code recorded in the verification result; never provider text."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class ResearchEvidenceService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.bridge = RegulatoryInvestigationService(engine, settings)
        self.coordinator = self.bridge.coordinator

    def _environment(self, session):
        settings = self.settings
        if (
            not settings.academic_research_enabled
            or settings.app_env not in {"local", "test"}
            or sys.platform != "win32"
            or session.bind.dialect.name != "postgresql"
            or session.bind.url.host not in {"127.0.0.1", "localhost"}
        ):
            raise EvidenceBlocked("academic_research_disabled")

    def corpus_view(self, session):
        """Administrator view of the retrieval corpus. Every hash check runs; no case data."""
        self._environment(session)
        source, _ = self._corpus()
        return {
            "status": "unapproved_research_only",
            "title": source["title"],
            "publisher": source["publisher"],
            "url": source["url"],
            "snapshot_date": source["snapshot_date"],
            "sections": len(self._corpus_chunks),
            "fingerprint_verified": True,
            "raw_sha256": source["raw_sha256"],
            "extracted_sha256": source["extracted_sha256"],
            "method": "text_match_ts_rank_cd",
            "top_k": research_retrieval.TOP_K,
        }

    def test_retrieval(self, session, query_text):
        """Same OR query and ts_rank_cd ranking as per-case retrieval. Read-only; no AI call."""
        self._environment(session)
        _, chunks = self._corpus()
        terms = research_retrieval.query_terms(query_text)
        if not terms:
            return {
                "terms": [],
                "total_sections": len(chunks),
                "matched_sections": 0,
                "min_relative_score": research_retrieval.MIN_RELATIVE_SCORE,
                "strong_matches": 0,
                "results": [],
            }
        ranked, matched = research_retrieval.rank(
            session, chunks, research_retrieval.or_query(terms)
        )
        ranked = research_retrieval.strong_matches(ranked)  # same rule as per-case retrieval
        by_section = {c["section"]: c for c in chunks}
        return {
            "terms": terms,
            "total_sections": len(chunks),
            "matched_sections": int(matched),
            "min_relative_score": research_retrieval.MIN_RELATIVE_SCORE,
            "strong_matches": len(ranked),
            "results": [
                {
                    "rank": n,
                    "section": section,
                    "title": research_retrieval.title_of(by_section[section]["body_text"]),
                    "score": score,
                }
                for n, (section, score) in enumerate(ranked, start=1)
            ],
        }

    def _scope(self, session, actor, case):
        settings = self.settings
        if (
            not settings.academic_research_enabled
            or settings.app_env not in {"local", "test"}
            or sys.platform != "win32"
            or session.bind.dialect.name != "postgresql"
            or session.bind.url.host not in {"127.0.0.1", "localhost"}
            or not settings.academic_research_scope_file
        ):
            raise EvidenceBlocked("academic_research_disabled")
        path = Path(settings.academic_research_scope_file).resolve(strict=True)
        if not any(p.name == "windows-native" and p.parent.name == "runtime" for p in path.parents):
            raise EvidenceBlocked("research_private_scope_required")
        raw = path.read_bytes()
        if len(raw) > 8192 or sha(raw) != settings.academic_research_scope_sha256:
            raise EvidenceBlocked("research_scope_changed")
        scope = strict_json(raw.decode(), 8192)
        database, cluster = session.execute(
            text("SELECT current_database(),system_identifier::text FROM pg_control_system()")
        ).one()
        if (
            scope.get("purpose") != "academic_research_unapproved_v1"
            or scope.get("production_publication_authorized") is not False
            or scope.get("as_of") != "2026-11-02"
            or scope.get("source_proposal_sha256") != PROPOSAL_SHA
            or scope.get("database") != database
            or not database.startswith(("tf_windows_app_", "tf_windows_test_"))
            or scope.get("cluster_id") != cluster
            or str(actor) not in scope.get("actors", [])
            or str(case) not in scope.get("cases", [])
            or len(scope.get("cases", [])) > 3
            or len(scope.get("actors", [])) > 4
        ):
            raise EvidenceBlocked("research_scope_denied")
        self.coordinator.reader._context(session, actor, case)
        return sha(raw)

    def _catalog(self):
        raw = (ROOT / "contracts/regulatory_source_proposals.json").read_bytes()
        if sha(raw) != PROPOSAL_SHA:
            raise EvidenceBlocked("research_catalog_changed")
        proposal = strict_json(raw.decode(), 65536)
        metadata = (
            ROOT / "assets/local/regulatory/proposed/ecfr-title31-metadata.json"
        ).read_bytes()
        if sha(metadata) != proposal["validity_evidence"]["sha256"]:
            raise EvidenceBlocked("research_snapshot_metadata_changed")
        source = proposal["sources"][0]
        if source["key"] != "ecfr-us-banks" or source["snapshot_date"] != "2026-11-02":
            raise EvidenceBlocked("research_catalog_invalid")
        path = ROOT / "assets/local/regulatory/proposed/ecfr-bank-2026-11-02.xml"
        with path.open("rb") as stream:
            data = stream.read(1048577)
        parsed = extract(data, "application/xml")
        if any(
            parsed[k] != source[k] for k in ("raw_sha256", "extracted_sha256", "parser_version")
        ):
            raise EvidenceBlocked("research_source_changed")
        chunks = []
        for expected in source["sections"]:
            chunk = next((c for c in parsed["chunks"] if c["section"] == expected["section"]), None)
            if chunk is None or any(chunk[k] != v for k, v in expected.items()):
                raise EvidenceBlocked("research_source_changed")
            chunks.append(chunk)
        self._corpus_chunks = [c for c in parsed["chunks"] if c.get("body_text", "").strip()]
        return source, chunks

    def _corpus(self):
        """All sections of the verified snapshot (raw/extracted hashes checked by _catalog)."""
        source, _ = self._catalog()
        return source, self._corpus_chunks

    def _citation(self, source, chunk, actor, case, run, query):
        identity = digest(
            dict(
                actor=str(actor),
                case=str(case),
                run=str(run),
                source=source["raw_sha256"],
                section=chunk["section"],
                text=chunk["text_sha256"],
                query=query.model_dump(mode="json"),
            )
        )
        return ResearchCitation(
            reference_id=uuid5(NAMESPACE_URL, "trueflag.academic-citation.v1:" + identity),
            source_url=source["url"],
            publisher=source["publisher"],
            raw_sha256=source["raw_sha256"],
            extracted_sha256=source["extracted_sha256"],
            parser_version=source["parser_version"],
            **{k: v for k, v in chunk.items() if k != "body_text"},
            text=chunk["body_text"],
        )

    def _excerpt_citation(self, source, chunk, actor, case, run, query, excerpt_text):
        excerpt_sha = sha(excerpt_text.encode())
        identity = digest(
            dict(
                actor=str(actor),
                case=str(case),
                run=str(run),
                source=source["raw_sha256"],
                section=chunk["section"],
                text=chunk["text_sha256"],
                excerpt=excerpt_sha,
                query=query.model_dump(mode="json"),
            )
        )
        return ResearchExcerptCitation(
            reference_id=uuid5(NAMESPACE_URL, "trueflag.academic-citation.v2:" + identity),
            source_url=source["url"],
            publisher=source["publisher"],
            raw_sha256=source["raw_sha256"],
            extracted_sha256=source["extracted_sha256"],
            parser_version=source["parser_version"],
            **{k: v for k, v in chunk.items() if k != "body_text"},
            text=excerpt_text,
            excerpt_sha256=excerpt_sha,
            section_text_bytes=len(chunk["body_text"].encode()),
        )

    def _retrieve(self, session, actor, case, run, inputs, *, relative=True, excerpts=True):
        """Per-case retrieval: mapped case terms, OR query, top 3 by ts_rank_cd > 0, no padding.

        ``relative`` (v3+) drops results below 25% of the top score; ``excerpts`` (v4) sends
        each strong match as a bounded excerpt of its most query-relevant lines. Older records
        are re-run with their own flags so their stored retrieval still matches exactly."""
        self._scope(session, actor, case)
        source, chunks = self._corpus()
        terms = research_retrieval.map_terms(inputs)
        while terms and len(" ".join(terms)) > 256:
            terms.pop()
        if not terms:
            raise EvidenceBlocked("research_context_unavailable")
        expression = research_retrieval.or_query(terms)
        ranked, matched = research_retrieval.rank(session, chunks, expression)
        if relative:
            ranked = research_retrieval.strong_matches(ranked)
        if not ranked:
            raise EvidenceBlocked("research_context_unavailable")
        query = ReferenceQuery(query=" ".join(terms), limit=research_retrieval.TOP_K)
        by_section = {c["section"]: c for c in chunks}
        passages, results, used = [], [], 0
        budget = research_retrieval.PASSAGE_BUDGET_BYTES
        for position, (section, score) in enumerate(ranked, start=1):
            chunk = by_section[section]
            body = chunk["body_text"]
            extra, result_cls = {}, RetrievalResult
            if excerpts:
                scores = research_retrieval.score_lines(session, body, expression)
                text_sent, spans = research_retrieval.excerpt(body, scores)
                citation = self._excerpt_citation(
                    source, chunk, actor, case, run, query, text_sent
                )
                extra = dict(
                    excerpt_sha256=citation.excerpt_sha256,
                    excerpt_bytes=len(text_sent.encode()),
                    excerpt_spans=[dict(start=a, end=b) for a, b in spans],
                )
                result_cls = RetrievalResultV2
            else:
                citation = self._citation(source, chunk, actor, case, run, query)
            size = len((text_sent if excerpts else body).encode())  # bytes actually sent
            sent = used + size <= budget
            if sent:
                used += size
                passages.append(citation)
            results.append(
                result_cls(
                    reference_id=citation.reference_id,
                    rank=position,
                    section=section,
                    title=research_retrieval.title_of(body),
                    score=score,
                    chunk_sha256=chunk["text_sha256"],
                    text_bytes=len(body.encode()),
                    sent=sent,
                    **extra,
                )
            )
        if not passages:
            raise EvidenceBlocked("research_context_unavailable")
        threshold = (
            dict(
                min_relative_score=research_retrieval.MIN_RELATIVE_SCORE,
                strong_matches=len(results),
            )
            if relative
            else {}
        )
        retrieval_cls = (
            ResearchRetrievalV3
            if excerpts
            else ResearchRetrievalV2
            if relative
            else ResearchRetrieval
        )
        retrieval = retrieval_cls(
            **threshold,
            inputs=list(inputs),
            terms=terms,
            query=expression,
            total_chunks=len(chunks),
            matched_chunks=int(matched),
            passage_budget_bytes=budget,
            results=results,
        )
        return query, passages, retrieval

    def _research_again(self, session, actor, binding, run):
        """Re-run the binding's own retrieval; any difference invalidates the binding."""
        if isinstance(binding, ResearchBindingV2):
            _, passages, retrieval = self._retrieve(
                session,
                actor,
                binding.case_id,
                run,
                binding.retrieval.inputs,
                relative=isinstance(binding, ResearchBindingV3),
                excerpts=isinstance(binding, ResearchBindingV4),
            )
            return passages == binding.passages and retrieval == binding.retrieval
        return self._search(session, actor, binding.case_id, run, binding.query) == binding.passages

    def source_texts(self, binding):
        """Full text of each retrieved section from the hash-verified snapshot, for display."""
        if not isinstance(binding, ResearchBindingV2):
            return []
        _, chunks = self._corpus()
        by_section = {c["section"]: c for c in chunks}
        texts = []
        for r in binding.retrieval.results:
            chunk = by_section.get(r.section)
            if chunk is None or chunk["text_sha256"] != r.chunk_sha256:
                raise VerificationFailed("research_context_invalidated")
            texts.append(
                dict(
                    reference_id=str(r.reference_id),
                    section=r.section,
                    chunk_sha256=r.chunk_sha256,
                    text=chunk["body_text"],
                )
            )
        return texts

    def _search(self, session, actor, case, run, query):
        self._scope(session, actor, case)
        source, chunks = self._catalog()
        # Same PostgreSQL English lexical primitives as the approved service;
        # input is the complete, hash-verified research sections, never a published release.
        rows = (
            session.execute(
                text("""WITH candidates AS (
              SELECT * FROM jsonb_to_recordset(CAST(:chunks AS jsonb))
                AS c(section text, body_text text)
            ) SELECT section FROM candidates
            WHERE (CAST(:section AS text) IS NOT NULL AND section=:section)
               OR (CAST(:query AS text) IS NOT NULL AND to_tsvector('english',body_text)
                   @@ plainto_tsquery('english',:query))
            ORDER BY CASE WHEN CAST(:query AS text) IS NULL THEN 0 ELSE
              ts_rank_cd(to_tsvector('english',body_text),plainto_tsquery('english',:query)) END DESC,
              section LIMIT :limit"""),
                {
                    "chunks": json.dumps(chunks),
                    "section": query.section,
                    "query": query.query,
                    "limit": min(query.limit, 2),
                },
            )
            .scalars()
            .all()
        )
        selected = []
        for key in rows:
            chunk = next(c for c in chunks if c["section"] == key)
            identity = digest(
                dict(
                    actor=str(actor),
                    case=str(case),
                    run=str(run),
                    source=source["raw_sha256"],
                    section=key,
                    text=chunk["text_sha256"],
                    query=query.model_dump(mode="json"),
                )
            )
            selected.append(
                ResearchCitation(
                    reference_id=uuid5(NAMESPACE_URL, "trueflag.academic-citation.v1:" + identity),
                    source_url=source["url"],
                    publisher=source["publisher"],
                    raw_sha256=source["raw_sha256"],
                    extracted_sha256=source["extracted_sha256"],
                    parser_version=source["parser_version"],
                    **{k: v for k, v in chunk.items() if k != "body_text"},
                    text=chunk["body_text"],
                )
            )
        if not selected:
            raise EvidenceBlocked("research_context_unavailable")
        return selected

    @atomic
    def prepare(self, session, actor, case, run, query=None):
        self.coordinator._gate(session)
        scope_sha = self._scope(session, actor, case)
        packet = self.bridge._packet(session, actor, case, run)
        parent = self.coordinator._run(session, run)
        alert = session.get(Alert, parent.alert_id)
        if alert is None or alert.data_classification != "synthetic":
            raise EvidenceBlocked("synthetic_scope_required")
        manifest = InputManifest.model_validate(parent.input_manifest)
        if not manifest.sources:
            raise EvidenceBlocked("synthetic_evidence_required")
        observed = self.coordinator.reader.clock.observe()
        if query is None:
            query, passages, retrieval = self._retrieve(
                session, actor, case, run, research_retrieval.case_inputs(packet)
            )
            extra, cls = {"retrieval": retrieval}, ResearchBindingV4
        else:
            passages, extra, cls = self._search(session, actor, case, run, query), {}, ResearchBinding
        binding = cls(
            case_id=case,
            actor_id=actor,
            investigation_run_id=run,
            packet_sha256=digest(packet.model_dump(mode="json")),
            scope_sha256=scope_sha,
            query=query,
            passages=passages,
            snapshot=manifest.snapshot,
            clock_epoch=observed.epoch,
            prepared_second=observed.second,
            expires_second=observed.second + 900,
            binding_sha256="0" * 64,
            **extra,
        )
        binding = binding.model_copy(
            update={
                "binding_sha256": digest(
                    binding.model_dump(mode="json", exclude={"binding_sha256"})
                )
            }
        )
        audit(
            session,
            actor,
            "investigation.research_prepared",
            run,
            binding_sha256=binding.binding_sha256,
            passages=len(binding.passages),
            production_publication_authorized=False,
        )
        return binding

    def _revalidate(self, session, actor, binding, *, require_current=True):
        if not isinstance(binding, ResearchBinding) or binding.actor_id != actor:
            raise VerificationFailed("research_binding_invalid")
        if (
            digest(binding.model_dump(mode="json", exclude={"binding_sha256"}))
            != binding.binding_sha256
        ):
            raise VerificationFailed("research_binding_invalid")
        if self._scope(session, actor, binding.case_id) != binding.scope_sha256:
            raise VerificationFailed("research_scope_changed")
        packet = self.bridge._packet(session, actor, binding.case_id, binding.investigation_run_id)
        observed = self.coordinator.reader.clock.observe()
        parent = self.coordinator._run(session, binding.investigation_run_id)
        manifest = InputManifest.model_validate(parent.input_manifest)
        alert = session.get(Alert, manifest.alert_id)
        if (
            alert is None
            or alert.data_classification != "synthetic"
            or any(
                session.get(EvidenceSource, source.source_id) is None
                or session.get(EvidenceSource, source.source_id).classification != "synthetic"
                for source in manifest.sources
            )
        ):
            raise EvidenceBlocked("synthetic_evidence_required")
        same_epoch = observed.epoch == binding.clock_epoch
        if require_current and not same_epoch:
            # A stale clock epoch is lifecycle expiry, not tampering: retire via SnapshotStale.
            raise SnapshotStale("research_context_expired")
        if (
            (same_epoch and observed.second < binding.prepared_second)
            or binding.expires_second - binding.prepared_second != 900
            or manifest.snapshot != binding.snapshot
            or digest(packet.model_dump(mode="json")) != binding.packet_sha256
            or not self._research_again(session, actor, binding, binding.investigation_run_id)
        ):
            raise VerificationFailed("research_context_invalidated")
        if require_current and observed.second >= binding.expires_second:
            # Genuine expiry of an intact binding: the existing audited retirement path applies.
            raise SnapshotStale("research_context_expired")
        return packet

    def passages_for_read(self, session, actor, binding):
        """Public research text only; never refresh or authorize a dispatch snapshot."""
        if not isinstance(binding, ResearchBinding) or binding.actor_id != actor:
            raise VerificationFailed("research_binding_invalid")
        if (
            digest(binding.model_dump(mode="json", exclude={"binding_sha256"}))
            != binding.binding_sha256
        ):
            raise VerificationFailed("research_binding_invalid")
        if self._scope(session, actor, binding.case_id) != binding.scope_sha256:
            raise VerificationFailed("research_scope_changed")
        parent = self.coordinator._run(session, binding.investigation_run_id)
        context, manifest = self.coordinator._current(session, parent)
        if (
            parent.case_id != binding.case_id
            or parent.actor_id != actor
            or manifest.snapshot != binding.snapshot
            or not self._research_again(session, actor, binding, parent.id)
        ):
            raise VerificationFailed("research_context_invalidated")
        self.coordinator.reader.ensure_clock(context.clock_epoch)
        observed = self.coordinator.reader.clock.observe()
        current = (
            observed.epoch == binding.clock_epoch
            and binding.prepared_second <= observed.second < binding.expires_second
            and binding.expires_second - binding.prepared_second == 900
        )
        return binding.passages, "current" if current else "expired"

    @atomic
    def provider_input(self, session, actor, binding, *, require_current=True):
        # require_current=False only re-reads a completed, stored result: every tamper,
        # evidence and passage check still runs; only the dispatch time window is skipped.
        packet = self._revalidate(session, actor, binding, require_current=require_current)
        values = minimize(packet).model_dump(exclude={"regulatory_context"})
        return ResearchProviderInput(
            **values,
            regulatory_binding_sha256=binding.binding_sha256,
            regulatory_passages=binding.passages,
        )

    @atomic
    def verify(self, session, actor, binding, proposal):
        packet = self._revalidate(session, actor, binding)
        allowed = {p.reference_id for p in binding.passages}
        cited = proposal.regulatory_citations
        if (
            proposal.regulatory_binding_sha256 != binding.binding_sha256
            or not cited
            or len(cited) != len(set(cited))
            or not set(cited) <= allowed
        ):
            raise ResearchCitationFailure("research_citation_invalid")
        links = getattr(proposal, "finding_citations", None) or []
        if links:
            findings = {
                f.reference_id
                for group in ("financial_observations", "unusual_activity", "model_signals")
                for f in getattr(proposal, group)
            }
            pairs = [(l.finding_reference_id, l.regulatory_citation) for l in links]
            # Each link must name a returned finding and a source from the retrieved set that
            # the proposal itself cites; anything else is rejected, never silently dropped.
            if (
                len(pairs) != len(set(pairs))
                or any(f not in findings for f, _ in pairs)
                or any(c not in allowed or c not in set(cited) for _, c in pairs)
            ):
                raise ResearchCitationFailure("research_finding_citation_invalid")
        validate_proposal(packet, proposal)
        audit(
            session,
            actor,
            "investigation.research_verified",
            binding.investigation_run_id,
            binding_sha256=binding.binding_sha256,
            citations=len(cited),
            finding_citations=len(links),
            legal_correctness_verified=False,
        )
        return [p for p in binding.passages if p.reference_id in cited]
