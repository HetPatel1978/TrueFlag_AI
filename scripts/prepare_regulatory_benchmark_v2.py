"""Prepare unreviewed v2 research artifacts; never admit, approve or publish sources."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = "contracts/regulatory_benchmark_v2.json"
ANSWERS = "contracts/regulatory_provisional_answer_keys_v2.json"
REVIEW = "contracts/regulatory_independent_review_v2.json"
GROUPS = {
    "A": "regulatory_relevance_and_ranking",
    "B": "historical_applicability_and_source_classification",
    "C": "citation_integrity_and_factual_support",
    "D": "abstention_and_missing_coverage",
    "E": "security_authorization_and_adversarial_controls",
}
ECFR = "ecfr-us-banks"
FAQ = "fincen-sar-faqs"
DATED = "fincen-sar-faqs-october-2025"
LABEL_FIELDS = (
    "reviewer_id",
    "qualifications",
    "reviewed_at",
    "relevant_source_section_keys",
    "expected_candidate_status",
    "expected_runtime_status",
    "authority_classes",
    "applicability_findings",
    "citation_support_grade",
    "exceptions_preserved",
    "abstention_grade",
    "rationale",
    "disagreements",
    "adjudicator_id",
    "adjudicated_at",
    "adjudication_status",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(name):
    return json.loads((ROOT / name).read_bytes())


def definition(identity, question, need, sections, summary, qualifications, **kwargs):
    """Engineering research hypotheses ONLY; short paraphrases, never legal certification."""
    return dict(
        id=identity,
        question=question,
        information_need=need,
        sections=sections,
        summary=summary,
        qualifications=qualifications,
        **kwargs,
    )


def questions():
    return [
        definition(
            "sar-bank",
            "Under the proposed historical bank provision, when does a transaction require a SAR?",
            "Identify the transaction nexus, aggregation threshold and suspicion conditions together.",
            [(ECFR, "1020.320", "(a)(1)-(2), (b), (c), (e)")],
            "Paragraph (a)(2) combines a bank nexus, at least $5,000 individually or in aggregate, "
            "and specified knowledge/suspicion conditions. Paragraph (a)(1) also permits voluntary reports.",
            "Do not turn the amount alone into a filing decision. Preserve exceptions, timing and "
            "confidentiality; charter-specific Title 12 rules are outside this candidate corpus.",
        ),
        definition(
            "aml-program",
            "Which AML program elements apply to a bank with or without a Federal functional regulator?",
            "Distinguish paragraphs (a) and (b), their common elements and incorporated requirements.",
            [(ECFR, "1020.210", "(a)(1)-(3), (b)(1)-(3)")],
            "Both categories include controls, independent testing, responsible personnel, training "
            "and risk-based ongoing CDD. Paragraph (a) incorporates regulator rules; paragraph (b) "
            "requires a written program and governing-body approval.",
            "Confirm actual bank category. Sections 1010.610, 1010.620 and full 1010.230 and "
            "regulator rules are not independently covered; do not claim complete program compliance.",
        ),
        definition(
            "sar-exceptions",
            "What qualified SAR reporting exceptions appear in 31 CFR 1020.320(c)?",
            "Retain both exceptions and their reporting prerequisites.",
            [(ECFR, "1020.320", "(c), read with (a)-(b)")],
            "Paragraph (c) addresses reported robbery/burglary and specified securities events "
            "reported under 17 CFR 240.17f-1.",
            "Neither event name alone establishes an exception. Verify the required prior reporting "
            "and the actual facts; the securities cross-reference is not in the candidate corpus.",
        ),
        definition(
            "critical-items",
            "How should available and unknown critical/non-critical SAR fields be handled?",
            "Separate filing-field guidance from obligations to obtain additional customer data.",
            [(FAQ, "faq-1", "complete FAQ 1, including final qualification")],
            "The frozen FAQ distinguishes requested information/Unknown for critical fields and "
            "available information for non-critical fields; unavailable non-critical information "
            "may be left blank under its stated qualifications.",
            "This is nonbinding operational guidance, not a new data-collection mandate. Whole-page "
            "historical validity and referenced FIN-2012-G002 remain unverified; abstain operationally.",
        ),
        definition(
            "amended-sar",
            "What does the frozen FAQ propose for correcting or amending a previously filed SAR?",
            "Identify prior filing linkage, complete resubmission and acknowledgement context.",
            [(FAQ, "faq-6", "complete FAQ 6")],
            "The FAQ describes selecting the correction option, linking the prior BSA ID, "
            "completing the report, identifying corrections in the narrative and receiving a new ID.",
            "This is an unapproved historical UI procedure, not an instruction to submit a SAR. "
            "Verify current filing specifications separately; no filing action is performed.",
        ),
        definition(
            "recordkeeping",
            "What do the proposed bank regulation and FAQ say about filed SARs and supporting records?",
            "Separate binding retention duties from the operational FAQ summary.",
            [(ECFR, "1020.320", "(b)(1), (d), (e)"), (FAQ, "faq-11", "complete FAQ 11")],
            "Paragraph (d) describes five-year retention from filing of a SAR copy and original "
            "or business-record-equivalent supporting documentation, identification of that "
            "documentation and availability to specified authorities on request.",
            "Keep confidentiality conditions. The bank regulation can support partial retrieval "
            "while FAQ historical validity is unresolved; do not conflate filed-SAR records with "
            "documentation of a decision not to file.",
        ),
        definition(
            "continuing-sar",
            "Is continuing-activity guidance a mandatory review cycle, and how is its optional timeline described?",
            "Reconcile the frozen updated FAQ with separately dated guidance and initial filing deadlines.",
            [
                (FAQ, "faq-16", "complete FAQ 16 and its update marker"),
                (DATED, "question-2", "pages 2-3; Question 2 and footnote 9"),
                (DATED, "question-3", "pages 3-4; Question 3 and footnotes 10-13"),
            ],
            "The dated guidance distinguishes optional continuing-activity practices from initial "
            "filing deadlines; a separate post-SAR review is not required merely by that guidance.",
            "The frozen FAQ's update marker dates that answer, not the whole HTML page. Neither "
            "guidance version is approved or currently retrievable; reconcile full context and "
            "amendment history before proposing an operational answer.",
        ),
        definition(
            "threshold-with-conditions",
            "A U.S. bank observes two linked $2,500 attempts and has facts suggesting BSA evasion. "
            "Which threshold and non-amount conditions must a reviewer assess?",
            "Evaluate aggregation and attempted transactions without equating a score/amount to guilt.",
            [(ECFR, "1020.320", "(a)(1)-(2), (b), (c)")],
            "The proposed provision includes attempted transactions and aggregation to at least "
            "$5,000 together with enumerated suspicion criteria.",
            "Linkage, actual suspicion facts, reporting entity and exceptions require human "
            "assessment; this hypothetical does not itself authorize filing.",
            request={"query": '"aggregates" "attempted"'},
        ),
        definition(
            "below-threshold",
            "A bank sees a single $3,000 suspicious transaction. Does the amount alone establish "
            "that no SAR could be appropriate or required under any applicable rule?",
            "Distinguish 1020.320's threshold, voluntary reports and unexamined parallel rules.",
            [(ECFR, "1020.320", "(a)(1)-(2), (g)")],
            "Paragraph (a)(1) permits voluntary reporting. Falling below paragraph (a)(2)'s "
            "threshold is not a complete determination under every other applicable rule.",
            "Aggregation and charter/regulator-specific requirements remain unknown. Insufficient "
            "coverage requires abstention from a universal no-filing conclusion.",
            request={"query": '"voluntary" OR "whose reporting is not required"'},
            candidate_status="partial",
        ),
        definition(
            "identified-suspect-clock",
            "Facts potentially supporting a bank SAR are initially detected and a suspect is already "
            "identified. What filing clock and urgent-notification qualification should be retrieved?",
            "Locate the initial-detection clock rather than the system alert creation time.",
            [(ECFR, "1020.320", "(b)(3)")],
            "Paragraph (b)(3) uses 30 calendar days from initial detection of facts that may form "
            "a filing basis, with immediate notification for situations requiring immediate attention.",
            "Actual initial detection and reportability are factual/legal review inputs. Software "
            "ingestion time is not automatically that date.",
            request={"query": '"30 calendar days" "initial detection"'},
        ),
        definition(
            "unidentified-suspect-clock",
            "No suspect was identified when reportable bank activity was detected. Is an unlimited "
            "delay allowed while identification continues?",
            "Retrieve both the conditional extension and the outer filing limit.",
            [(ECFR, "1020.320", "(b)(3)")],
            "The provision allows an additional 30 calendar days to identify a suspect, but "
            "does not allow reporting later than 60 days from initial detection of a reportable transaction.",
            "The extension is conditional, not the ordinary deadline or permission to ignore urgency.",
            request={"query": '"suspect" "60 calendar days"'},
        ),
        definition(
            "continuing-guidance-conflict",
            "An internal note calls a 90-day post-SAR review mandatory, but a separately dated "
            "government FAQ describes a different boundary. Can the coordinator resolve this from "
            "the currently eligible candidate passages?",
            "Identify source conflict, optional guidance and the need for approved complete sources.",
            [
                (DATED, "question-2", "pages 2-3; Question 2"),
                (DATED, "question-3", "pages 3-4; Question 3"),
                (FAQ, "faq-16", "complete FAQ 16"),
                (ECFR, "1020.320", "(b)(3), initial filing only"),
            ],
            "The proposed research flags the internal note for review; initial filing provisions "
            "alone do not answer the optional continuing-guidance question.",
            "Do not elevate guidance to binding law or invent an ongoing-review obligation. "
            "The required guidance is excluded; abstain from resolving the conflict operationally.",
            request={"query": '"continuing" "90"'},
            candidate_status="unavailable",
            candidate_eligible=[],
        ),
        definition(
            "sar-confidentiality-request",
            "A customer asks whether a SAR exists and a private litigant demands the SAR. "
            "Which confidentiality restrictions and qualified disclosures must a bank reviewer examine?",
            "Preserve the prohibition, response requirements, exceptions and underlying-record distinction.",
            [(ECFR, "1020.320", "(e)(1)(i)-(ii), (e)(2)")],
            "Paragraph (e) protects SARs and information revealing their existence, prescribes "
            "handling of requests and distinguishes qualified disclosures and underlying facts/documents.",
            "Do not disclose a SAR or make a categorical claim that every underlying transaction "
            "record is itself a SAR. A qualified reviewer must assess the actual request.",
            request={"query": '"confidentiality" "disclose"'},
        ),
        definition(
            "qualified-reporting-exception",
            "A bank records an attempted robbery and a separate missing-security event. What "
            "additional reporting facts are necessary before relying on either SAR exception?",
            "Retrieve complete paragraph (c), not a truncated list of exempt event names.",
            [(ECFR, "1020.320", "(c), including 17 CFR 240.17f-1 cross-reference")],
            "The robbery/burglary and securities exceptions have different prerequisite reporting "
            "conditions. The event labels alone do not demonstrate those conditions.",
            "Missing law-enforcement or securities-report facts require abstention on exception "
            "application. The cross-referenced securities rule is expansion-dependent.",
            request={"query": '"robbery" "securities"'},
        ),
        definition(
            "bank-category-program",
            "A private bank lacks a Federal functional regulator. Can the program be assessed "
            "solely using the paragraph for federally regulated banks?",
            "Choose the correct bank category and preserve written-program/governing-body requirements.",
            [(ECFR, "1020.210", "(a), (b)(1)-(3)")],
            "The proposed section separately addresses banks lacking a Federal functional "
            "regulator in paragraph (b), including governing-body approval and availability to FinCEN.",
            "Verify the institution's actual category and incorporated provisions; retrieval of "
            "this section alone is not a complete compliance assessment.",
            request={"query": '"lacking" "board of directors"'},
        ),
        definition(
            "cdd-coverage-boundary",
            "Does the bank-program CDD paragraph establish every current beneficial-ownership "
            "collection exemption for a legal-entity customer?",
            "Retrieve ongoing CDD duties but identify missing full 1010.230/exemption history.",
            [(ECFR, "1020.210", "(a)(2)(v), (b)(2)(v); cross-reference 1010.230")],
            "The section describes customer risk profiles and ongoing risk-based monitoring/updates. "
            "Its cross-reference does not supply the complete beneficial-ownership exemption framework.",
            "Current exemptions and amendments are outside the candidate corpus. Abstain from "
            "that part and request independently reviewed expansion sources.",
            request={"query": '"customer due diligence"'},
            candidate_status="partial",
            expansion=["31 CFR 1010.230 and applicable dated exemption/amendment instruments"],
        ),
        definition(
            "supporting-document-request",
            "A filed SAR is four years old and an identified competent authority requests its "
            "supporting documents. Which retention and availability provisions are relevant?",
            "Distinguish filed-SAR support from a decision not to file, and verify requester authority.",
            [(ECFR, "1020.320", "(d), (e)")],
            "Paragraph (d) addresses five years from SAR filing, supporting-document identification "
            "and availability to specified authorities; paragraph (e) preserves confidentiality context.",
            "The hypothetical does not establish the requester's authority, authenticity or exact "
            "retention start. No customer document is disclosed by this benchmark.",
            request={"query": '"supporting documentation" "five years"'},
        ),
        definition(
            "historical-not-current",
            "Can a November 2, 2026 dated bank snapshot alone certify the legal position on "
            "November 4, 2026?",
            "Reject temporal extrapolation even when the same section number matches.",
            [(ECFR, "1020.320", "complete dated snapshot, including source note")],
            "A dated snapshot supplies a historical research identity, not proof that no intervening "
            "change occurred. No current-law certification is proposed.",
            "The requested date exceeds the frozen verification boundary; obtain dated primary "
            "evidence and qualified review or abstain.",
            request={"section": "1020.320"},
            test_scope={"as_of": "2026-11-04"},
            candidate_status="unavailable",
            candidate_eligible=[],
        ),
        definition(
            "near-ctr-insufficient-facts",
            "A transaction is near $10,000, but its purpose, customer circumstances and applicable "
            "reporting-entity rule are unknown. Is a SAR obligation established by the amount alone?",
            "Identify missing evasion/suspicion evidence and institution applicability before any conclusion.",
            [
                (DATED, "question-1", "pages 1-2; Question 1 and footnotes 1-8"),
                (ECFR, "1020.320", "(a)(2)(ii), conditional bank application only"),
            ],
            "The separately dated guidance says proximity to the CTR threshold alone is "
            "insufficient. The available case facts also fail to establish institution applicability.",
            "The guidance is not admitted, and missing facts cannot be invented. Abstain from "
            "a filing/criminal conclusion and request evidence plus approved applicable sources.",
            request={"query": '"structuring" "CTR"'},
            candidate_status="unavailable",
            candidate_eligible=[],
        ),
    ]


def source_registry():
    sources = load("contracts/regulatory_source_proposals.json")["sources"]
    registry = {s["key"]: s for s in sources}
    # Actual acquisition metadata, not a fabricated historical fetch time. Public metadata
    # permits deterministic template checks without requiring private source copies in CI.
    pdf = dict(
        filename="fincen-sar-faqs-october-2025.pdf",
        url="https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf",
        raw_sha256="5ed61b76f65ca1640f2d40e1afe3db40c77622620e81aefd08bc5273e0de4cac",
        bytes=284868,
        media_type="application/pdf",
        retrieved_at="2026-11-05T03:51:23.098334+00:00",
    )
    landing = dict(
        filename="fincen-sar-faqs-october-2025-landing.html",
        url="https://www.fincen.gov/resources/statutes-regulations/guidance/"
        "frequently-asked-questions-regarding-suspicious-activity",
        raw_sha256="371aa3f12a3d1ac661ebf910fe36591bc8ce7c5638b84e64c294ebe4a64eb36f",
        bytes=31853,
        media_type="text/html",
        retrieved_at="2026-11-05T03:51:23.807798+00:00",
    )
    registry[DATED] = dict(
        key=DATED,
        publisher="FinCEN, Federal Reserve, FDIC, NCUA and OCC",
        title="Frequently Asked Questions Regarding Suspicious Activity Reporting Requirements",
        url=pdf["url"],
        raw_sha256=pdf["raw_sha256"],
        raw_bytes=pdf["bytes"],
        retrieved_at=pdf["retrieved_at"],
        acquisition_date_timezone="America/New_York",
        issued_date="2025-10-09",
        effective_from=None,
        effective_to=None,
        verified_through=None,
        historical_applicability="requires_independent_review; issuance is not a composite validity interval",
        authority="guidance",
        status="research_only_not_admitted_not_approved",
        parser_status="PDF unsupported by current production XML/HTML/text parser",
        sections=[
            dict(section="question-1", locator="pages 1-2; Question 1 and footnotes 1-8"),
            dict(section="question-2", locator="pages 2-3; Question 2 and footnote 9"),
            dict(section="question-3", locator="pages 3-4; Question 3 and footnotes 10-13"),
            dict(section="question-4", locator="page 4; Question 4 and footnote 14"),
        ],
        issuance_evidence=landing,
        research_provenance=dict(
            method="Read official PDF and official issued-date landing page; locally SHA-256 verified",
            original_path="assets/local/regulatory/research_v2/" + pdf["filename"],
            landing_path="assets/local/regulatory/research_v2/" + landing["filename"],
            extraction=None,
            note="No PDF parser admission, automated text replacement or inherited HTML publication date",
        ),
    )
    return registry


def source_reference(registry, key, section, locator):
    source = registry[key]
    selected = next(s for s in source["sections"] if s["section"] == section)
    return dict(
        source_key=key,
        section=section,
        relevant_locator=locator,
        source_locator=selected["locator"],
        source_raw_sha256=source["raw_sha256"],
        extracted_sha256=source.get("extracted_sha256"),
        section_text_sha256=selected.get("text_sha256"),
        start_byte=selected.get("start_byte"),
        end_byte=selected.get("end_byte"),
        authority=source["authority"],
        version=source.get("snapshot_date")
        or source.get("issued_date")
        or "2026-11-04 acquisition only",
        publication_status=source["status"],
    )


def build():
    baseline = load("contracts/regulatory_independent_review.json")
    original = load("contracts/regulatory_evaluation_proposals.json")
    registry = source_registry()
    definitions = questions()
    old_requests = {c["id"]: c["request"] for c in original["cases"]}
    cases, answers = [], []
    for index, item in enumerate(definitions):
        request = item.get("request", old_requests.get(item["id"]))
        refs = [source_reference(registry, *ref) for ref in item["sections"]]
        labels = [f"{r['source_key']}:{r['section']}" for r in refs]
        eligible = item.get("candidate_eligible", [v for v in labels if v.startswith(ECFR + ":")])
        availability = item.get(
            "candidate_status",
            "available"
            if len(eligible) == len(labels)
            else "partial"
            if eligible
            else "unavailable",
        )
        cases.append(
            dict(
                id=item["id"],
                kind="existing_question" if index < 7 else "new_scenario",
                baseline_id=item["id"] if index < 7 else None,
                question=item["question"],
                information_need=item["information_need"],
                groups=["A", "B", "C", "D"],
                request=request,
                test_scope=item.get("test_scope", {}),
                technical_expectation="Runtime must withhold all unapproved passages; candidate labels are provisional.",
                fixture="hash_verified_unapproved_official_versions_in_disposable_PostgreSQL_schema",
            )
        )
        answers.append(
            dict(
                id=item["id"],
                status="engineering_research_proposal_not_independent_ground_truth",
                question=item["question"],
                expected_information_need=item["information_need"],
                source_references=refs,
                proposed_answer=item["summary"],
                exceptions_and_qualifications=item["qualifications"],
                historical_applicability="US bank / 2026-11-02 / knowledge cutoff 2026-11-04; "
                "institution category and full amendment/effective-date chain require qualified review.",
                proposed_relevance_labels=labels,
                candidate_eligible_source_section_keys=eligible,
                expected_status=dict(
                    runtime="unavailable_unapproved_corpus", candidate=availability
                ),
                required_abstention="No operative legal answer from unapproved sources; never infer missing facts, "
                "current validity, complete coverage or a filing decision. Partial retrieval requires partial abstention.",
                expansion_dependencies=item.get("expansion", []),
                research_provenance="Frozen government source locators/hashes plus separately acquired dated "
                "FinCEN PDF; engineering paraphrase only, not an independent legal review.",
                proposed_rationale="Selected complete sections address this information need; paragraph/FAQ "
                "locators narrow research attention without discarding surrounding qualifications.",
                unresolved_reviewer_questions=[
                    "Do the mapped complete sections directly support each proposed statement and its exceptions?",
                    "Are the institution, historical interval, amendment chain and authority classification correct?",
                    "Is candidate coverage complete, partial or absent, and what must remain unanswered?",
                ],
                reviewer_required_fields=list(LABEL_FIELDS),
            )
        )
    for item in baseline["cases"][7:]:
        identity = item["id"]
        procedure = item["procedure"]
        expected = next(
            c["expected"] for c in original["negative_acceptance_cases"] if c["id"] == identity
        )
        cases.append(
            dict(
                id=identity,
                kind="security_control",
                baseline_id=identity,
                question="Verify technical boundary: " + identity,
                information_need=expected,
                groups=["E", "D"]
                if identity not in {"exceptions", "embedded-instructions"}
                else ["E", "C"],
                procedure=procedure,
                technical_expectation=expected,
                fixture="existing explicit v1 procedure + v2 PostgreSQL/API assertion; synthetic-only "
                "publication/supersession controls remain separately identified",
            )
        )
        refs = [
            source_reference(registry, ECFR, "1020.320", "complete section, including (c) and (e)")
        ]
        if identity == "unapproved-guidance":
            refs = [
                source_reference(
                    registry, FAQ, "faq-1", "complete FAQ 1; historical validity unknown"
                )
            ]
        answers.append(
            dict(
                id=identity,
                status="engineering_control_expectation_not_independent_ground_truth",
                question="Verify technical boundary: " + identity,
                expected_information_need=expected,
                source_references=refs,
                proposed_answer="No legal answer is requested; assert the named technical boundary.",
                proposed_relevance_labels=[],
                candidate_eligible_source_section_keys=[],
                expected_status=dict(
                    runtime="hidden_resource_or_no_passages", candidate="control_specific"
                ),
                exceptions_and_qualifications="Synthetic source text is not authority; simulated candidate "
                "supersession is not proof of actual legal amendment. Parser inertness does not validate future LLM safety.",
                required_abstention="No legal interpretation or source publication from this control.",
                research_provenance="Preserved v1 procedure, independent protected API/service and SQL fixture assertions.",
                proposed_rationale=expected,
                historical_applicability="Fixed historical US-bank scope only; mutated scope must be rejected.",
                expansion_dependencies=[],
                unresolved_reviewer_questions=[
                    "Does this fixture exercise the stated boundary without claiming legal relevance?"
                ],
                reviewer_required_fields=list(LABEL_FIELDS),
            )
        )
    # Keep the historical 19 in order, followed by the 12 new scenarios.
    order = [c["id"] for c in baseline["cases"]] + [
        c["id"] for c in cases if c["kind"] == "new_scenario"
    ]
    cases = sorted(cases, key=lambda c: order.index(c["id"]))
    answers = sorted(answers, key=lambda c: order.index(c["id"]))
    benchmark = dict(
        schema_version="trueflag.regulatory-benchmark.v2",
        status="proposed_unreviewed_not_publication_authorization",
        scope=baseline["scope"],
        baseline_sha256={
            p: sha((ROOT / p).read_bytes())
            for p in (
                "contracts/regulatory_source_proposals.json",
                "contracts/regulatory_evaluation_proposals.json",
                "contracts/regulatory_independent_review.json",
            )
        },
        groups=GROUPS,
        counts=dict(existing_questions=7, security_controls=12, new_scenarios=12, unique_cases=31),
        metric_rules=dict(
            precision_at_5="Unique relevant returned source:section keys / 5, absent slots count as misses.",
            recall_at_5="Unique relevant returned keys / all proposed relevant keys; excluded sources remain visible misses.",
            mrr="Reciprocal rank of first proposed relevant key; macro mean over the stated question population.",
            coverage="Syntactic locator/hash integrity is separate from human-reviewed claim support.",
            applicability="Technical scope/date/authority predicates are separate from human legal applicability.",
            abstention="Measure full/partial/missing candidate coverage separately from approved-only runtime withholding.",
            groups="Overlapping tags; never sum group sizes or average control outcomes into relevance scores.",
            independence="No independently adjudicated metric until real reviewer identities, labels and adjudication exist.",
        ),
        cases=cases,
    )
    answer_file = dict(
        schema_version="trueflag.regulatory-provisional-answer-keys.v2",
        status="engineering_research_only_unreviewed",
        benchmark_sha256=sha(encoded(benchmark)),
        approved_sources=0,
        independently_adjudicated_cases=0,
        sources=registry,
        cases=answers,
    )
    review = dict(
        schema_version="trueflag.independent-regulatory-review.v2",
        status="blank_pending_independent_human_labeling",
        benchmark_sha256=sha(encoded(benchmark)),
        provisional_research_sha256=sha(encoded(answer_file)),
        baseline_sha256=benchmark["baseline_sha256"],
        scope=baseline["scope"],
        instructions=[
            "Review independently against complete source versions before consulting engineering answer hypotheses.",
            "Use a private copy; do not commit reviewer identity or customer information.",
            "Keep legal relevance, authority/date applicability, citation support, abstention and technical security separate.",
            "Record source:section labels and qualifications; a second reviewer adjudicates disagreements.",
            "Supplying labels never approves or publishes a source or authorizes a SAR/case decision.",
        ],
        cases=[
            dict(
                id=c["id"],
                question=c["question"],
                information_need=c["information_need"],
                independent_label=dict.fromkeys(LABEL_FIELDS),
            )
            for c in cases
        ],
    )
    return {BENCHMARK: benchmark, ANSWERS: answer_file, REVIEW: review}


def reviewer_data_present(value):
    return any(v is not None for c in value["cases"] for v in c["independent_label"].values())


def write_artifacts(artifacts, *, check=False, root=ROOT):
    # Preflight every output before writing any; never overwrite partial independent review.
    for name, value in artifacts.items():
        path = root / name
        if (
            name == REVIEW
            and path.exists()
            and reviewer_data_present(json.loads(path.read_bytes()))
        ):
            raise ValueError("Refusing to overwrite or accept partial independent reviewer work")
        if check and (not path.is_file() or path.read_bytes() != encoded(value)):
            raise ValueError("Versioned proposal byte drift")
    if not check:
        for name, value in artifacts.items():
            (root / name).write_bytes(encoded(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = build()
    write_artifacts(artifacts, check=args.check)
    print(
        json.dumps(
            dict(
                status="proposed_only",
                cases=31,
                independent_labels=0,
                hashes={p: sha(encoded(v)) for p, v in artifacts.items()},
            )
        )
    )


if __name__ == "__main__":
    main()
