"""Load only the approved fitted RF from verified in-memory snapshots; never fit or score."""

import hashlib
import importlib.metadata
import io
import json
import platform
import struct
import sys
import threading
import types
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from trueflag_ml.trust import (
    APPROVED_SHA256,
    CONTRACT_PATH,
    MODEL_PATH,
    MODEL_VERSION,
    REQUIRED_VERSIONS,
    SOURCE_MODULES,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "assets/local/baseline"
_IMPORT_LOCK = threading.RLock()


class ModelLoadError(Exception):
    """Stable reason code only: do not expose paths, source bytes or dependency exceptions."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def verify_runtime() -> Mapping[str, str]:
    if (
        sys.version_info[:2] != (3, 11)
        or platform.python_implementation() != "CPython"
        or struct.calcsize("P") != 8
    ):
        raise ModelLoadError("python_incompatible")
    try:
        installed = {name: importlib.metadata.version(name) for name in REQUIRED_VERSIONS}
    except importlib.metadata.PackageNotFoundError:
        raise ModelLoadError("dependency_missing") from None
    if installed != dict(REQUIRED_VERSIONS):
        raise ModelLoadError("dependency_incompatible")
    return MappingProxyType(installed)


def _verified_bundle(root: Path) -> dict[str, bytes]:
    snapshots = {}
    try:
        directory = root.resolve(strict=True)
        if not directory.is_dir():
            raise ModelLoadError("artifact_missing")
        for relative, expected in APPROVED_SHA256.items():
            path = (directory / relative).resolve(strict=True)
            if not path.is_relative_to(directory) or not path.is_file():
                raise ModelLoadError("artifact_location_invalid")
            # Limit memory before hashing; none of the approved files exceeds 2 MiB.
            limit = 8 * 1024 * 1024 if relative == MODEL_PATH else 256 * 1024
            with path.open("rb") as stream:
                data = stream.read(limit + 1)
            if len(data) > limit or hashlib.sha256(data).hexdigest() != expected:
                raise ModelLoadError("artifact_integrity_failed")
            snapshots[relative] = data
    except FileNotFoundError:
        raise ModelLoadError("artifact_missing") from None
    except OSError:
        raise ModelLoadError("artifact_unreadable") from None
    return snapshots


def _contract_fields(content: bytes) -> tuple[str, ...]:
    from app.schemas.alerts import BASELINE_CONTRACT_SHA256, AlertFeatures

    try:
        contract = json.loads(content)
        fields = contract["structured_predictors"]
        excluded = contract["excluded_from_scorer"]
        if (
            APPROVED_SHA256[CONTRACT_PATH] != BASELINE_CONTRACT_SHA256
            or fields != list(AlertFeatures.model_fields)
            or len(fields) != 27
            or set(fields).intersection(excluded)
        ):
            raise ModelLoadError("feature_contract_invalid")
    except (ValueError, TypeError, KeyError):
        raise ModelLoadError("feature_contract_invalid") from None
    return tuple(fields)


@contextmanager
def _approved_modules(snapshots: Mapping[str, bytes]):
    # No sys.path insertion, disk imports, bytecode caches or unverified package discovery.
    # The caller holds the process-wide loader lock; use only in the isolated ML process.
    if any(name == "trueflag" or name.startswith("trueflag.") for name in sys.modules):
        raise ModelLoadError("module_namespace_conflict")
    owned = []
    try:
        for name, relative in SOURCE_MODULES:
            module = types.ModuleType(name)
            module.__file__ = f"<approved:{name}>"
            module.__package__ = "trueflag" if name == "trueflag" else name.rpartition(".")[0]
            module.__spec__ = ModuleSpec(name, loader=None, is_package=name == "trueflag")
            if name == "trueflag":
                module.__path__ = []
            sys.modules[name] = module
            owned.append(name)
            exec(compile(snapshots[relative], module.__file__, "exec"), module.__dict__)
        yield sys.modules["trueflag.model_feasibility"].TrainingScopeGuard
    finally:
        for name in reversed(owned):
            sys.modules.pop(name, None)


def _feature_frame(features: Mapping, fields: tuple[str, ...]):
    import numpy as np
    import pandas as pd
    from pydantic import ValidationError

    from app.schemas.alerts import AlertFeatures

    try:
        values = AlertFeatures.model_validate(dict(features)).model_dump()
        if values["income"] is None:
            values["income"] = np.nan
        return pd.DataFrame([values], columns=fields)
    except (ValidationError, ValueError, TypeError, OverflowError):
        raise ModelLoadError("feature_input_invalid") from None


@dataclass(frozen=True)
class LoadedPipeline:
    # Trusted internal handle, never a response DTO or a fit/predict API.
    pipeline: object
    fields: tuple[str, ...]
    dependencies: Mapping[str, str]
    model_version: str = MODEL_VERSION
    model_sha256: str = APPROVED_SHA256[MODEL_PATH]
    contract_sha256: str = APPROVED_SHA256[CONTRACT_PATH]

    def feature_frame(self, features: Mapping):
        """Validate the existing transport schema and order columns; null income alone becomes NaN."""
        return _feature_frame(features, self.fields)


def _validate_fitted(pipeline, guard_type, fields):
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer, OneHotEncoder
    from sklearn.utils.validation import check_is_fitted

    if type(pipeline) is not Pipeline or tuple(pipeline.named_steps) != (
        "fit_scope",
        "preprocessor",
        "estimator",
    ):
        raise ModelLoadError("pipeline_incompatible")
    guard, pre, forest = (pipeline.named_steps[name] for name in pipeline.named_steps)
    if (
        type(guard) is not guard_type
        or guard.fit_count_ != 1
        or len(guard.allowed_ids) != 6000
        or guard.fit_ids_sha256_
        != hashlib.sha256("\n".join(guard.allowed_ids).encode()).hexdigest()
        or type(pre) is not ColumnTransformer
        or type(forest) is not RandomForestClassifier
    ):
        raise ModelLoadError("pipeline_incompatible")
    check_is_fitted(pre, ["transformers_", "feature_names_in_", "output_indices_"])
    check_is_fitted(forest, ["estimators_", "classes_", "n_features_in_"])
    if (
        tuple(pre.feature_names_in_) != fields
        or pre.n_features_in_ != 27
        or not np.array_equal(forest.classes_, [0, 1])
        or forest.n_estimators != 300
        or len(forest.estimators_) != 300
        or forest.min_samples_leaf != 5
        or not forest.__sklearn_tags__().input_tags.allow_nan
    ):
        raise ModelLoadError("pipeline_incompatible")
    numeric = [name for name in fields if name not in {"state", "kycRiskScore"}]
    categories, numbers = pre.transformers_[:2]
    encoder = pre.named_transformers_["categories"]
    if (
        categories[0] != "categories"
        or categories[2] != ["state", "kycRiskScore"]
        or type(encoder) is not OneHotEncoder
        or encoder.handle_unknown != "ignore"
        or encoder.sparse_output
        or numbers[0] != "numeric"
        or type(numbers[1]) is not FunctionTransformer
        or numbers[1].func is not None
        or numbers[2] != numeric
        or pre.remainder != "drop"
    ):
        raise ModelLoadError("preprocessing_incompatible")
    check_is_fitted(encoder, ["categories_"])
    # Transform synthetic validation rows only: never predict, fit, impute or read private rows.
    sample = {name: 0 for name in fields}
    sample.update(state="__trueflag_loader_validation__", income=None, kycRiskScore=3)
    missing = _feature_frame(sample, fields)
    zero = _feature_frame({**sample, "income": 0}, fields)
    matrix = pre.transform(pd.concat([missing, zero], ignore_index=True))
    income_index = pre.output_indices_["numeric"].start + numeric.index("income")
    if (
        matrix.shape != (2, 41)
        or len(pre.get_feature_names_out()) != 41
        or forest.n_features_in_ != 41
        or not np.isnan(matrix[0, income_index])
        or matrix[1, income_index] != 0
    ):
        raise ModelLoadError("preprocessing_incompatible")
    for tree in forest.estimators_:
        check_is_fitted(tree, ["tree_"])
        if tree.n_features_in_ != 41:
            raise ModelLoadError("pipeline_incompatible")


def load_approved_pipeline(artifact_root: Path | None = None) -> LoadedPipeline:
    """Deployment-owned bundle root only; fixed filenames/hashes cannot be supplied by clients."""
    snapshots = _verified_bundle(DEFAULT_ROOT if artifact_root is None else Path(artifact_root))
    dependencies = verify_runtime()
    try:
        fields = _contract_fields(snapshots[CONTRACT_PATH])
        import joblib
        from sklearn.exceptions import InconsistentVersionWarning

        with _IMPORT_LOCK, _approved_modules(snapshots) as guard_type, warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            # Deserialize the exact bytes already hashed: no second file open / TOCTOU window.
            pipeline = joblib.load(io.BytesIO(snapshots[MODEL_PATH]), mmap_mode=None)
            _validate_fitted(pipeline, guard_type, fields)
        return LoadedPipeline(pipeline, fields, dependencies)
    except ModelLoadError:
        raise
    except Exception:
        raise ModelLoadError("pipeline_load_failed") from None
