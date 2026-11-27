"""Versioned scenario specifications; source expectations are not model-generated labels."""

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.services.ingestion import digest
from app.services.synthetic_evidence import bundle_manifest, generate_scenario

ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT / "contracts/investigation_eval_dataset_v1.json"
RUBRIC_PATH = ROOT / "contracts/investigation_eval_rubric_v1.json"
DATASET_VERSION = "trueflag.ai-evaluation-dataset.v1"


def dataset():
    value = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = value["cases"]
    if value["version"] != DATASET_VERSION or len(cases) != 36:
        raise ValueError("evaluation_dataset_invalid")
    if len({c["case_key"] for c in cases}) != len(cases):
        raise ValueError("evaluation_dataset_duplicates")
    partitions = [
        {c["seed"] for c in cases if c["split"] == split} for split in ["development", "heldout"]
    ]
    if partitions[0] & partitions[1] or any(len(p) != 18 for p in partitions):
        raise ValueError("evaluation_partition_overlap")
    return value


def rubric():
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))


def source_bundle(spec):
    ns = uuid5(NAMESPACE_URL, DATASET_VERSION)
    return generate_scenario(uuid5(ns, spec["case_key"]), spec["seed"], spec["profile"])


def case_provenance(spec):
    bundle = source_bundle(spec)
    return dict(
        dataset_version=DATASET_VERSION,
        case_key=spec["case_key"],
        split=spec["split"],
        category=spec["category"],
        bundle_sha256=digest(bundle_manifest(bundle)),
        generator_version=bundle.generator_version,
        labels="engineering_reference_only",
    )
