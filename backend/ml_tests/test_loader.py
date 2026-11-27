"""Run with unittest in .venv-ml for real-artifact acceptance; no private fixtures in CI."""

import hashlib
import importlib.util
import io
import json
import pickle
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.schemas.alerts import AlertFeatures  # noqa: E402
from trueflag_ml import loader  # noqa: E402
from trueflag_ml.loader import ModelLoadError  # noqa: E402
from trueflag_ml.trust import APPROVED_SHA256, CONTRACT_PATH, MODEL_PATH, SOURCE_MODULES  # noqa: E402


def synthetic(income=None):
    values = {name: 0 for name in AlertFeatures.model_fields}
    return {**values, "state": "__synthetic_unknown__", "kycRiskScore": 3, "income": income}


@contextmanager
def copied_bundle():
    snapshots = loader._verified_bundle(loader.DEFAULT_ROOT)
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        for relative, content in snapshots.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        yield root


class IntegrityAndRuntimeTests(unittest.TestCase):
    def assert_code(self, code, operation):
        with self.assertRaises(ModelLoadError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_missing_root_fails_without_exposing_path(self):
        with tempfile.TemporaryDirectory() as name:
            self.assert_code(
                "artifact_missing", lambda: loader.load_approved_pipeline(Path(name) / "missing")
            )

    def test_missing_model_fails_safely(self):
        with tempfile.TemporaryDirectory() as name:
            self.assert_code("artifact_missing", lambda: loader.load_approved_pipeline(Path(name)))

    def test_arbitrary_pickle_and_editable_manifest_cannot_grant_trust(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            marker = root / "must-not-execute"

            class Untrusted:
                def __reduce__(self):
                    return Path.write_text, (marker, "executed")

            payload = pickle.dumps(Untrusted())
            target = root / MODEL_PATH
            target.parent.mkdir()
            target.write_bytes(payload)
            (root / "baseline.manifest.json").write_text(
                json.dumps(
                    {
                        "records": [
                            {"local": MODEL_PATH, "sha256": hashlib.sha256(payload).hexdigest()}
                        ]
                    }
                )
            )
            self.assert_code(
                "artifact_integrity_failed", lambda: loader.load_approved_pipeline(root)
            )
            self.assertFalse(marker.exists())

    def test_oversized_model_is_rejected_before_deserialization(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            target = root / MODEL_PATH
            target.parent.mkdir()
            target.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            self.assert_code(
                "artifact_integrity_failed", lambda: loader.load_approved_pipeline(root)
            )

    def test_python_minor_version_mismatch_is_rejected(self):
        with patch.object(loader.sys, "version_info", (3, 12, 0)):
            self.assert_code("python_incompatible", loader.verify_runtime)

    def test_python_implementation_mismatch_is_rejected(self):
        with patch.object(loader.platform, "python_implementation", return_value="PyPy"):
            self.assert_code("python_incompatible", loader.verify_runtime)

    def test_python_architecture_mismatch_is_rejected(self):
        with patch.object(loader.struct, "calcsize", return_value=4):
            self.assert_code("python_incompatible", loader.verify_runtime)

    def test_dependency_mismatch_is_rejected(self):
        with patch.object(loader.importlib.metadata, "version", return_value="0.0.0"):
            self.assert_code("dependency_incompatible", loader.verify_runtime)

    def test_missing_dependency_is_rejected(self):
        with patch.object(
            loader.importlib.metadata,
            "version",
            side_effect=loader.importlib.metadata.PackageNotFoundError("private-marker"),
        ):
            self.assert_code("dependency_missing", loader.verify_runtime)

    def test_existing_package_is_preserved_and_rejected(self):
        namespace = types.ModuleType("trueflag")
        with patch.dict(sys.modules, {"trueflag": namespace}):
            with self.assertRaisesRegex(ModelLoadError, "module_namespace_conflict"):
                with loader._approved_modules({}):
                    self.fail("Must not enter a conflicting namespace")
            self.assertIs(sys.modules["trueflag"], namespace)

    def test_existing_child_module_also_blocks_loading(self):
        with patch.dict(sys.modules, {"trueflag.unapproved": types.ModuleType("unapproved")}):
            with self.assertRaisesRegex(ModelLoadError, "module_namespace_conflict"):
                with loader._approved_modules({}):
                    self.fail("Must not enter a conflicting namespace")

    def test_failed_module_execution_cleans_namespace(self):
        snapshots = {relative: b"raise RuntimeError('test-only')" for _, relative in SOURCE_MODULES}
        with self.assertRaises(RuntimeError):
            with loader._approved_modules(snapshots):
                self.fail("Must not enter after failed module import")
        self.assertFalse(any(n == "trueflag" or n.startswith("trueflag.") for n in sys.modules))


class ContractTests(unittest.TestCase):
    def contract(self):
        return {
            "structured_predictors": list(AlertFeatures.model_fields),
            "excluded_from_scorer": ["SAR", "csrNotes"],
        }

    def reject(self, contract):
        with self.assertRaisesRegex(ModelLoadError, "feature_contract_invalid"):
            loader._contract_fields(json.dumps(contract).encode())

    def test_contract_order_matches_ingestion_schema(self):
        fields = loader._contract_fields(json.dumps(self.contract()).encode())
        self.assertEqual(fields, tuple(AlertFeatures.model_fields))
        self.assertEqual(len(fields), 27)

    def test_missing_feature_is_rejected(self):
        contract = self.contract()
        contract["structured_predictors"].remove("income")
        self.reject(contract)

    def test_extra_feature_is_rejected(self):
        contract = self.contract()
        contract["structured_predictors"].append("SAR")
        self.reject(contract)

    def test_reordered_features_are_rejected(self):
        contract = self.contract()
        contract["structured_predictors"].reverse()
        self.reject(contract)

    def test_duplicated_feature_is_rejected(self):
        contract = self.contract()
        contract["structured_predictors"][-1] = "income"
        self.reject(contract)

    def test_excluded_predictor_overlap_is_rejected(self):
        contract = self.contract()
        contract["excluded_from_scorer"].append("income")
        self.reject(contract)

    def test_malformed_contract_is_rejected(self):
        for content in [b"{}", b"[]", b"bad-json", b"null"]:
            with self.subTest(content=content):
                with self.assertRaisesRegex(ModelLoadError, "feature_contract_invalid"):
                    loader._contract_fields(content)


HAS_REAL_RUNTIME = (loader.DEFAULT_ROOT / MODEL_PATH).is_file() and importlib.util.find_spec(
    "numpy"
) is not None


@unittest.skipUnless(
    HAS_REAL_RUNTIME, "Private model/scientific runtime absent; run .venv-ml acceptance"
)
class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A wrong installed scientific version is a failure here, never silently skipped.
        cls.loaded = loader.load_approved_pipeline()

    def test_actual_approved_artifact_is_fitted(self):
        forest = self.loaded.pipeline.named_steps["estimator"]
        self.assertEqual(len(forest.estimators_), 300)
        self.assertEqual(forest.min_samples_leaf, 5)
        self.assertEqual(self.loaded.pipeline.named_steps["fit_scope"].fit_count_, 1)
        self.assertEqual(self.loaded.model_sha256, APPROVED_SHA256[MODEL_PATH])
        self.assertEqual(tuple(forest.classes_), (0, 1))
        self.assertEqual(len(self.loaded.fields), 27)

    def test_dependency_mismatch_blocks_real_deserialization(self):
        import joblib

        with (
            patch.object(loader.importlib.metadata, "version", return_value="0.0.0"),
            patch.object(
                joblib, "load", side_effect=AssertionError("must not deserialize")
            ) as blocked,
        ):
            with self.assertRaisesRegex(ModelLoadError, "dependency_incompatible"):
                loader.load_approved_pipeline()
            blocked.assert_not_called()

    def test_deserializer_failure_is_sanitized_and_cleans_namespace(self):
        import joblib

        with patch.object(joblib, "load", side_effect=RuntimeError("private-exception-marker")):
            with self.assertRaises(ModelLoadError) as caught:
                loader.load_approved_pipeline()
        self.assertEqual(str(caught.exception), "pipeline_load_failed")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertFalse(any(n == "trueflag" or n.startswith("trueflag.") for n in sys.modules))

    def test_changed_positive_class_order_is_rejected(self):
        from copy import deepcopy

        changed = deepcopy(self.loaded.pipeline)
        changed.named_steps["estimator"].classes_ = changed.classes_[::-1]
        guard_type = type(changed.named_steps["fit_scope"])
        with self.assertRaisesRegex(ModelLoadError, "pipeline_incompatible"):
            loader._validate_fitted(changed, guard_type, self.loaded.fields)

    def test_missing_vs_zero_income_survives_fitted_preprocessing(self):
        import numpy as np

        pre = self.loaded.pipeline.named_steps["preprocessor"]
        numeric = pre.transformers_[1][2]
        index = pre.output_indices_["numeric"].start + numeric.index("income")
        missing = self.loaded.feature_frame(synthetic(None))
        zero = self.loaded.feature_frame(synthetic(0))
        self.assertTrue(np.isnan(missing.loc[0, "income"]))
        self.assertEqual(zero.loc[0, "income"], 0)
        self.assertTrue(np.isnan(pre.transform(missing)[0, index]))
        self.assertEqual(pre.transform(zero)[0, index], 0)
        self.assertEqual(pre.transform(zero).shape, (1, 41))
        self.assertEqual(pre.transformers_[0][2], ["state", "kycRiskScore"])

    def test_frame_reorders_keys_without_changing_values(self):
        values = {**synthetic(0), "totalSpend90d": -12.25, "nbrPurchases90d": 2**60 + 1}
        frame = self.loaded.feature_frame(dict(reversed(list(values.items()))))
        self.assertEqual(tuple(frame.columns), self.loaded.fields)
        self.assertEqual(frame.loc[0, "totalSpend90d"], -12.25)
        self.assertEqual(frame.loc[0, "nbrPurchases90d"], 2**60 + 1)
        self.assertEqual(frame.loc[0, "state"], values["state"])

    def test_invalid_feature_values_and_extra_labels_are_rejected(self):
        invalid = [
            {**synthetic(), "SAR": 1},
            {**synthetic(), "income": "0"},
            {**synthetic(), "income": True},
            {**synthetic(), "income": float("nan")},
            {**synthetic(), "income": float("inf")},
            {**synthetic(), "kycRiskScore": 7},
            {**synthetic(), "kycRiskScore": 3.5},
            {**synthetic(), "state": " "},
        ]
        missing = synthetic()
        del missing["income"]
        invalid.append(missing)
        for features in invalid:
            with self.subTest(fields=tuple(features)):
                with self.assertRaisesRegex(ModelLoadError, "feature_input_invalid"):
                    self.loaded.feature_frame(features)

    def test_corrupted_real_model_is_rejected(self):
        with copied_bundle() as root:
            path = root / MODEL_PATH
            content = bytearray(path.read_bytes())
            content[len(content) // 2] ^= 1
            path.write_bytes(content)
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                loader.load_approved_pipeline(root)

    def test_truncated_real_model_is_rejected(self):
        with copied_bundle() as root:
            path = root / MODEL_PATH
            path.write_bytes(path.read_bytes()[:64])
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                loader.load_approved_pipeline(root)

    def test_modified_real_contract_is_rejected(self):
        with copied_bundle() as root:
            path = root / CONTRACT_PATH
            contract = json.loads(path.read_bytes())
            contract["structured_predictors"].reverse()
            path.write_text(json.dumps(contract))
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                loader.load_approved_pipeline(root)

    def test_modified_compatibility_source_is_rejected(self):
        with copied_bundle() as root:
            path = root / SOURCE_MODULES[-1][1]
            path.write_bytes(path.read_bytes() + b"\nraise RuntimeError('must-not-execute')\n")
            with self.assertRaisesRegex(ModelLoadError, "artifact_integrity_failed"):
                loader.load_approved_pipeline(root)
        self.assertNotIn("trueflag", sys.modules)

    def test_missing_required_source_fails_safely(self):
        with copied_bundle() as root:
            (root / SOURCE_MODULES[-1][1]).unlink()
            with self.assertRaisesRegex(ModelLoadError, "artifact_missing"):
                loader.load_approved_pipeline(root)

    def test_only_verified_snapshot_is_deserialized_after_file_replacement(self):
        import joblib

        original_load = joblib.load
        with copied_bundle() as root:

            def replace_after_verification(stream, **kwargs):
                self.assertIsInstance(stream, io.BytesIO)
                self.assertEqual(
                    hashlib.sha256(stream.getvalue()).hexdigest(), APPROVED_SHA256[MODEL_PATH]
                )
                (root / MODEL_PATH).write_bytes(b"unapproved replacement")
                return original_load(stream, **kwargs)

            # Wrap the real deserializer; actual fitted artifact success is not substituted.
            with patch.object(joblib, "load", side_effect=replace_after_verification):
                result = loader.load_approved_pipeline(root)
            self.assertEqual(len(result.pipeline.named_steps["estimator"].estimators_), 300)

    def test_repeated_loading_preserves_import_path_and_cleans_namespace(self):
        before = list(sys.path)
        first, second = loader.load_approved_pipeline(), loader.load_approved_pipeline()
        self.assertEqual(sys.path, before)
        self.assertFalse(any(n == "trueflag" or n.startswith("trueflag.") for n in sys.modules))
        self.assertEqual(first.fields, second.fields)

    def test_loading_never_calls_fit_or_prediction(self):
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import OneHotEncoder

        with (
            patch.object(
                RandomForestClassifier, "fit", side_effect=AssertionError("fit forbidden")
            ),
            patch.object(
                RandomForestClassifier,
                "predict_proba",
                side_effect=AssertionError("score forbidden"),
            ),
            patch.object(
                RandomForestClassifier, "predict", side_effect=AssertionError("predict forbidden")
            ),
            patch.object(ColumnTransformer, "fit", side_effect=AssertionError("fit forbidden")),
            patch.object(
                ColumnTransformer, "fit_transform", side_effect=AssertionError("fit forbidden")
            ),
            patch.object(OneHotEncoder, "fit", side_effect=AssertionError("fit forbidden")),
        ):
            loaded = loader.load_approved_pipeline()
        self.assertEqual(loaded.pipeline.named_steps["fit_scope"].fit_count_, 1)


if __name__ == "__main__":
    unittest.main()
