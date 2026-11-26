"""Deployment-owned build identity. Never reads configuration or deserializes model files."""

import hashlib
import json
import re
from pathlib import Path

from app.core.schema import EXPECTED_SCHEMA_REVISION

RELEASE_CONTRACT = "trueflag.release.v1"
VERSIONS = {"backend_version": "0.1.0", "frontend_version": "0.1.0", "worker_version": "0.1.0"}
METADATA_PATH = Path(__file__).resolve().parents[1] / "_release.json"
FIELDS = {
    "contract",
    "git_commit",
    "source_state",
    "source_sha256",
    "build_id",
    "backend_version",
    "frontend_version",
    "worker_version",
    "expected_schema_revision",
    "image_digest",
}


class ReleaseCompatibilityError(Exception):
    def __init__(self, code):
        allowed = {
            "release_metadata_invalid",
            "release_contract_incompatible",
            "schema_incompatible",
            "schema_missing",
            "schema_unavailable",
            "database_unavailable",
            "python_incompatible",
            "ml_incompatible",
        }
        self.code = code if code in allowed else "release_contract_incompatible"
        super().__init__(self.code)


def unknown_identity():
    return dict(
        contract=RELEASE_CONTRACT,
        git_commit="unknown",
        source_state="unknown",
        source_sha256="unknown",
        build_id="unknown",
        **VERSIONS,
        expected_schema_revision=EXPECTED_SCHEMA_REVISION,
        image_digest="unknown",
    )


def identity_digest(value):
    data = {k: v for k, v in value.items() if k != "build_id"}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_identity(value):
    if (
        type(value) is not dict
        or set(value) != FIELDS
        or any(type(v) is not str for v in value.values())
    ):
        raise ReleaseCompatibilityError("release_metadata_invalid")
    if (
        value["contract"] != RELEASE_CONTRACT
        or any(value[k] != v for k, v in VERSIONS.items())
        or value["expected_schema_revision"] != EXPECTED_SCHEMA_REVISION
    ):
        raise ReleaseCompatibilityError("release_contract_incompatible")
    for key, pattern in {
        "git_commit": r"[a-f0-9]{40}",
        "source_sha256": r"[a-f0-9]{64}",
        "build_id": r"[a-f0-9]{64}",
        "image_digest": r"sha256:[a-f0-9]{64}",
        "source_state": r"clean|dirty",
    }.items():
        if value[key] != "unknown" and re.fullmatch(pattern, value[key]) is None:
            raise ReleaseCompatibilityError("release_metadata_invalid")
    if value["build_id"] != "unknown" and value["build_id"] != identity_digest(value):
        raise ReleaseCompatibilityError("release_metadata_invalid")
    return dict(value)


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def load_identity(path=None):
    path = METADATA_PATH if path is None else Path(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(8193)
        if len(data) > 8192:
            raise ValueError
        value = validate_identity(json.loads(data, object_pairs_hook=_pairs))
    except FileNotFoundError:
        return {**unknown_identity(), "metadata_status": "unknown"}
    except ReleaseCompatibilityError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise ReleaseCompatibilityError("release_metadata_invalid") from None
    return {**value, "metadata_status": "available"}
