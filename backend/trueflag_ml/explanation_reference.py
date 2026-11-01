"""Read-only approved historical explanation outputs; independent of artifact-side manifests."""

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from trueflag_ml.explanation_contract import ExplanationVerificationError
from trueflag_ml.loader import DEFAULT_ROOT

REFERENCE_ROOT = DEFAULT_ROOT.parent / "explanation_reference"
REFERENCE_FILES = MappingProxyType(
    {
        "explanations.jsonl": (
            "c09c102e789e894e287f400bee444c26f9cdf9e79a686a0f811041ecb12a6a7b",
            "extensions/outputs/full explanations/explanations.jsonl",
            64 * 1024 * 1024,
        ),
        "metadata.json": (
            "99e3c35b99b2c9aebb0cb80d32382976e77445914a814f83d75fe20a47fc396e",
            "extensions/outputs/full explanations/metadata.json",
            1024 * 1024,
        ),
        "verification.json": (
            "8195bf09bfe9d0dbb96c14b4a981321c706c97f56d556f2f8e405bd6fe179383",
            "extensions/outputs/full verification/verification.json",
            65536,
        ),
    }
)


def reference_snapshots(root=REFERENCE_ROOT, *, handoff=False):
    snapshots = {}
    try:
        root = Path(root).resolve(strict=True)
        for name, (expected, original, limit) in REFERENCE_FILES.items():
            path = (root / (original if handoff else name)).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ExplanationVerificationError("explanation_reference_location_invalid")
            with path.open("rb") as stream:
                content = stream.read(limit + 1)
            if len(content) > limit or hashlib.sha256(content).hexdigest() != expected:
                raise ExplanationVerificationError("explanation_reference_integrity_failed")
            snapshots[name] = content
    except FileNotFoundError:
        raise ExplanationVerificationError("explanation_reference_missing") from None
    except OSError:
        raise ExplanationVerificationError("explanation_reference_unreadable") from None
    return snapshots


def strict_json(content):
    def reject_constant(value):
        raise ValueError("nonfinite_json")

    try:
        return json.loads(content, parse_constant=reject_constant)
    except (ValueError, TypeError, UnicodeError):
        raise ExplanationVerificationError("explanation_reference_schema_invalid") from None
