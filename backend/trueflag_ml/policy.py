"""Verified frozen rules producing human-controlled recommendations; no scoring or mutation."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

from trueflag_ml.loader import DEFAULT_ROOT
from trueflag_ml.scoring import ScoreResult, ScoringInputError, validate_record_id
from trueflag_ml.trust import APPROVED_SHA256, MODEL_PATH, MODEL_VERSION

MODES = ("Efficiency", "Balanced", "Coverage")
POLICY_PATH = "contracts/selected_policy_settings.json"
POLICY_SHA256 = "c530a4f71c554172a0dde4d2574f28efdc2ee860a4e32c74bd1ec548d359ac3f"


class PolicyLoadError(Exception):
    """Stable reason code only; no paths or artifact content."""


class PolicyInputError(Exception):
    """Stable input failure reason without submitted data."""


@dataclass(frozen=True)
class FrozenPolicySet:
    thresholds: Mapping[str, float]
    priority_mapping: Mapping[str, tuple[int, ...]]
    model_version: str = MODEL_VERSION
    model_sha256: str = APPROVED_SHA256[MODEL_PATH]
    policy_sha256: str = POLICY_SHA256

    @property
    def version(self):
        # Original artifact has no independent policy version; preserve its content identity.
        return f"{self.model_version}:{self.policy_sha256}"


@dataclass(frozen=True)
class PolicyRecommendation:
    record_id: str | None
    model_score: float | None
    selected_policy: str | None
    policy_version: str | None
    policy_sha256: str | None
    model_version: str | None
    model_sha256: str | None
    threshold: float | None
    kyc_risk_score: int | None
    priority_group: str | None
    recommended_route: Literal["retain_human_review", "review_reduction_candidate", "manual_review"]
    override_reason: str | None
    processing_status: Literal["processed", "failed"]
    routing_reason: str
    score_based_retention: bool = False
    coverage_protection: bool = False
    coverage_changed_route: bool = False
    human_decision_required: Literal[True] = True


def validate_score(value):
    if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
        raise PolicyInputError("invalid_score")
    return float(value)


def validate_priority(kyc, declared=None):
    if (
        type(kyc) not in (int, float)
        or not 0 <= kyc <= 6
        or not math.isfinite(kyc)
        or kyc != int(kyc)
    ):
        raise PolicyInputError("invalid_kyc")
    priority = "High" if kyc >= 3 else "Standard"
    if declared is not None:
        if type(declared) is not str or declared not in {"Standard", "High"}:
            raise PolicyInputError("invalid_priority")
        if declared != priority:
            raise PolicyInputError("priority_mismatch")
    return int(kyc), priority


def _parse_settings(content):
    from app.schemas.alerts import AlertFeatures

    try:
        settings = json.loads(content)
        thresholds = settings["thresholds"]
        priorities = settings["priority_mapping"]
        if (
            settings["model"] != "RF"
            or settings["model_version"] != MODEL_VERSION
            or settings["pipeline_sha256"] != APPROVED_SHA256[MODEL_PATH]
            or settings["scorer_predictors"] != list(AlertFeatures.model_fields)
            or set(thresholds) != set(MODES)
            or any(type(value) is not float or not 0 < value < 1 for value in thresholds.values())
            or not thresholds["Coverage"] == thresholds["Balanced"] < thresholds["Efficiency"]
            or priorities["Standard"] != [0, 1, 2]
            or priorities["High"] != [3, 4, 5, 6]
            or any(
                type(value) is not int
                for group in ["Standard", "High"]
                for value in priorities[group]
            )
        ):
            raise PolicyLoadError("policy_schema_invalid")
        return FrozenPolicySet(
            MappingProxyType(dict(thresholds)),
            MappingProxyType({name: tuple(priorities[name]) for name in ["Standard", "High"]}),
        )
    except (ValueError, KeyError, TypeError):
        raise PolicyLoadError("policy_schema_invalid") from None


def load_approved_policy(artifact_root: Path | None = None):
    try:
        root = (DEFAULT_ROOT if artifact_root is None else Path(artifact_root)).resolve(strict=True)
        path = (root / POLICY_PATH).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise PolicyLoadError("policy_location_invalid")
        with path.open("rb") as stream:
            content = stream.read(65537)
        if len(content) > 65536 or hashlib.sha256(content).hexdigest() != POLICY_SHA256:
            raise PolicyLoadError("policy_integrity_failed")
    except FileNotFoundError:
        raise PolicyLoadError("policy_artifact_missing") from None
    except OSError:
        raise PolicyLoadError("policy_artifact_unreadable") from None
    return _parse_settings(content)


class RiskPolicyEngine:
    def __init__(self, artifact_root: Path | None = None):
        self._settings = None
        self.load_failure = None
        try:
            self._settings = load_approved_policy(artifact_root)
        except PolicyLoadError as error:
            self.load_failure = str(error)
        except Exception:
            self.load_failure = "policy_load_failed"

    @property
    def ready(self):
        return self._settings is not None

    @property
    def settings(self):
        return self._settings

    def _manual(self, record_id, mode, reason):
        settings = self._settings
        return PolicyRecommendation(
            record_id=record_id,
            model_score=None,
            selected_policy=mode,
            policy_version=settings.version if settings else None,
            policy_sha256=settings.policy_sha256 if settings else None,
            model_version=settings.model_version if settings else None,
            model_sha256=settings.model_sha256 if settings else None,
            threshold=settings.thresholds[mode] if settings and mode else None,
            kyc_risk_score=None,
            priority_group=None,
            recommended_route="manual_review",
            override_reason=None,
            processing_status="failed",
            routing_reason=reason,
        )

    def evaluate(self, score_result, policy=None, *, kyc_risk_score=None, priority_group=None):
        record_id = None
        mode = policy if type(policy) is str and policy in MODES else None
        try:
            if type(score_result) is ScoreResult:
                validate_record_id(score_result.record_id)
                record_id = score_result.record_id
            if not self.ready:
                return self._manual(record_id, mode, "policy_unavailable")
            if mode is None:
                raise PolicyInputError("invalid_policy")
            if type(score_result) is not ScoreResult:
                raise PolicyInputError("invalid_score_result")
            if (
                type(score_result.model_version) is not str
                or score_result.model_version != self._settings.model_version
                or type(score_result.model_sha256) is not str
                or score_result.model_sha256 != self._settings.model_sha256
                or type(score_result.positive_class_label) is not int
                or score_result.positive_class_label != 1
            ):
                raise PolicyInputError("model_identity_invalid")
            if (
                type(score_result.processing_status) is not str
                or score_result.processing_status != "processed"
                or score_result.reason is not None
            ):
                raise PolicyInputError("scoring_failed_manual_review_required")
            score = validate_score(score_result.score)
            kyc, priority = validate_priority(kyc_risk_score, priority_group)
            return self._recommend(record_id, score, mode, kyc, priority)
        except ScoringInputError:
            return self._manual(None, mode, "invalid_record_id")
        except PolicyInputError as error:
            return self._manual(record_id, mode, str(error))
        except Exception:
            return self._manual(record_id, mode, "policy_evaluation_failed")

    def _recommend(self, record_id, score, mode, kyc, priority):
        settings = self._settings
        threshold = settings.thresholds[mode]
        above = score >= threshold
        protect = mode == "Coverage" and kyc in settings.priority_mapping["High"]
        changed = protect and not above
        reason = (
            "score_at_or_above_threshold_and_coverage_high_priority"
            if above and protect
            else "score_at_or_above_threshold"
            if above
            else "coverage_high_priority_protection"
            if protect
            else "score_below_threshold"
        )
        return PolicyRecommendation(
            record_id=record_id,
            model_score=score,
            selected_policy=mode,
            policy_version=settings.version,
            policy_sha256=settings.policy_sha256,
            model_version=settings.model_version,
            model_sha256=settings.model_sha256,
            threshold=threshold,
            kyc_risk_score=kyc,
            priority_group=priority,
            recommended_route="retain_human_review"
            if above or protect
            else "review_reduction_candidate",
            override_reason="coverage_high_priority_protection" if changed else None,
            processing_status="processed",
            routing_reason=reason,
            score_based_retention=above,
            coverage_protection=protect,
            coverage_changed_route=changed,
        )
