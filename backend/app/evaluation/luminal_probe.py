"""Prepare exact request bytes using the existing adapter. No transport or activation."""

import hashlib
from decimal import Decimal

from app.schemas.provider_live import LiveProviderConfig
from app.services.ingestion import digest
from app.services.investigation_draft_verifier import minimize
from app.services.luminal_provider import request_body

PROBE_VERSION = "trueflag.luminal-probe-proposal.v1"
PUBLISHED_INPUT_RATE = Decimal("0.1425")
PUBLISHED_OUTPUT_RATE = Decimal("0.5700")
SAFETY_FACTOR = Decimal("2")
TERMS_REVIEW_SHA256 = "0fa6f6c4e8434988546f12f47e847a64ff63d35f3ddf88c3e2582fe2715e66b6"


def prepare_request(packet, probe):
    if probe not in {"A", "B", "C"}:
        raise ValueError("unknown_probe")
    incoming, outgoing = {"A": (8192, 512), "B": (16384, 1024), "C": (32768, 2048)}[probe]
    upper_rate = PUBLISHED_OUTPUT_RATE * SAFETY_FACTOR
    reservation = Decimal(incoming + outgoing) * upper_rate / 1_000_000
    config = LiveProviderConfig(
        approval_id="PENDING-HUMAN-APPROVAL-NOT-A-GRANT",
        terms_sha256=TERMS_REVIEW_SHA256,
        max_input_tokens=incoming,
        max_output_tokens=outgoing,
        total_token_budget=incoming + outgoing,
        max_request_bytes=incoming,
        max_attempts=1,
        input_usd_per_million=PUBLISHED_INPUT_RATE * SAFETY_FACTOR,
        output_usd_per_million=upper_rate,
        max_cost_usd=reservation,
    )
    minimized = minimize(packet)
    if probe == "A":
        # Further minimize the unavailable-evidence case; never invent observed zero activity.
        minimized = minimized.model_copy(update={"financial_facts": [], "evidence_references": []})
    wire = request_body(minimized, config)
    projected = dict(
        probe=probe,
        configuration=config.model_dump(mode="json"),
        provider_input_sha256=digest(minimized.model_dump(mode="json")),
        request_sha256=hashlib.sha256(wire).hexdigest(),
        request_size_bytes=len(wire),
        input_token_ceiling=incoming,
        output_token_ceiling=outgoing,
        conservative_reservation_usd=str(reservation),
        source_packet_sha256=minimized.packet_sha256,
        source_transactions=len(packet.transactions),
        evidence_requires_abstention=minimized.evidence_requires_abstention,
        token_count_basis="byte_admission_not_verified_provider_tokenizer",
        rate_basis="public_indexed_listing_not_approved_billing_contract",
    )
    return wire, projected


def approval_package(items):
    if len(items) != 3 or {p["probe"] for p in items} != {"A", "B", "C"}:
        raise ValueError("exactly_three_distinct_probes_required")
    reserved = sum((Decimal(p["conservative_reservation_usd"]) for p in items), Decimal(0))
    if reserved > Decimal("1.00") or len({p["request_sha256"] for p in items}) != 3:
        raise ValueError("invalid_probe_budget_or_identity")
    package = dict(
        schema_version=PROBE_VERSION,
        approval_status="pending_human_review",
        activation_authorized=False,
        provider="luminal",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
        destination="https://flash.luminal.cloud/v1/chat/completions",
        terms_review_sha256=TERMS_REVIEW_SHA256,
        privacy_review_sha256="ceefc6b9c408c8da9ed2963d6fbc855800a6413dbc5b5e28a49e8c29728328bc",
        maximum_external_attempts=3,
        application_spend_ceiling_usd="1.00",
        objective_conflict_resolution="stricter_1_USD_limit_from_sections_5_and_8",
        proposed_reservation_total_usd=str(reserved),
        safety_factor=str(SAFETY_FACTOR),
        automatic_paid_retries=False,
        unknown_usage_retains_full_reservation=True,
        provider_invoice_cap_verified=False,
        pricing_and_tokenizer_upper_bound_verified=False,
        owner_approval=None,
        approved_at=None,
        expires_at=None,
        approvals={
            name: None
            for name in [
                "provider_model",
                "privacy_retention_training_subprocessors",
                "minimal_synthetic_transfer",
                "three_call_limit",
                "one_USD_with_billing_uncertainty",
                "network_destination",
                "exact_payload_hashes",
                "emergency_abort",
            ]
        },
        probes=sorted(items, key=lambda p: p["probe"]),
        live_inference_requests_executed=0,
    )
    return dict(**package, package_sha256=digest(package))
