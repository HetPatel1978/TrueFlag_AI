"""Offline launch-package boundaries; these tests do not establish native acceptance."""

import importlib.util
import json
from pathlib import Path

import pytest


def script(name):
    path = Path(__file__).resolve().parents[2] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_source_copy_excludes_secrets_assets_and_build_caches(tmp_path):
    root, target = tmp_path / "repo", tmp_path / "export"
    for directory in ("backend", "frontend", "scripts", "contracts"):
        (root / directory).mkdir(parents=True)
    (root / "backend/app.py").write_text("current_uncommitted_source = True")
    (root / "backend/.env").write_text("not_a_real_credential")
    (root / "backend/private.key").write_text("not_a_real_key")
    (root / "backend/assets").mkdir()
    (root / "backend/assets/private.csv").write_text("synthetic_private_fixture")
    (root / "frontend/node_modules").mkdir()
    (root / "frontend/node_modules/cache.js").write_text("cache")
    script("prepare_native_demo").copy_public(root, target)
    assert (target / "backend/app.py").read_text() == "current_uncommitted_source = True"
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "backend/app.py"
    ]


def test_compose_is_isolated_loopback_only_and_contains_no_live_credentials():
    plan = script("prepare_native_demo").compose_document(1000, 1000, "tf_native_demo_test", None)
    assert all(n["internal"] for n in plan["networks"].values())
    assert "ports" not in plan["services"]["db"]
    assert "ports" not in plan["services"]["testdb"]
    for service in plan["services"].values():
        assert service.get("restart", "no") == "no"
        assert all(p.startswith("127.0.0.1:") for p in service.get("ports", []))
        assert "env_file" not in service
        assert "ANTHROPIC_API_KEY" not in json.dumps(service)
    assert plan["services"]["draft-worker"]["profiles"] == ["gated-ai"]
    assert plan["services"]["acceptance"]["networks"] == ["acceptance"]
    assert plan["services"]["db"]["networks"] == ["application"]
    assert "test-database:/var/lib/postgresql/data" not in plan["services"]["db"]["volumes"]


@pytest.fixture
def receipt():
    return {
        "candidate_build_id": "a" * 64,
        "expected_schema": "0023_durable_regulatory_start",
        "pytest_exit_code": 0,
        "required_test_counts": {"total": 10, "skipped": 0, "failed": 0, "errors": 0},
        "clock": {
            "samples": 600,
            "host_backsteps": 0,
            "database_backsteps": 0,
            "database_outside_host_roundtrip": 0,
            "sampler_errors": [],
        },
        "provider_requests": 0,
    }


def test_only_matching_tested_build_can_pass_runtime_admission(receipt):
    check = script("native_demo_runtime").acceptance_passed
    assert check(receipt, "a" * 64)
    assert not check(receipt, "b" * 64)
    assert not check(receipt, "unknown")
    assert not check({}, "a" * 64)


@pytest.mark.parametrize("field", ["skipped", "failed", "errors"])
def test_skipped_or_failed_required_tests_block_runtime(receipt, field):
    receipt["required_test_counts"][field] = 1
    assert not script("native_demo_runtime").acceptance_passed(receipt, "a" * 64)


@pytest.mark.parametrize(
    "field", ["host_backsteps", "database_backsteps", "database_outside_host_roundtrip"]
)
def test_unhealthy_clock_receipt_cannot_start_application(receipt, field):
    receipt["clock"][field] = 1
    assert not script("native_demo_runtime").acceptance_passed(receipt, "a" * 64)


def test_native_runtime_rejects_provider_activation_and_inherited_credentials(
    tmp_path, monkeypatch
):
    runtime = script("native_demo_runtime")
    config = {
        "DATABASE_URL": "not_a_real_connection",
        "JWT_SECRET": "not_a_real_secret",
        "BATCH_ASSESSMENT_DISPATCH_ENABLED": "true",
        "INVESTIGATION_SIMULATION_ENABLED": "false",
        "INVESTIGATION_EXTERNAL_ENABLED": "false",
        "ANTHROPIC_SYNTHETIC_DEMO_ENABLED": "false",
        "ANTHROPIC_ANALYST_GENERATION_ENABLED": "false",
        "REGULATORY_INVESTIGATION_ENABLED": "false",
    }
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(
        runtime.os, "environ", {"PATH": "offline", "ANTHROPIC_API_KEY": "synthetic_sentinel"}
    )
    runtime.load_environment(path)
    assert "ANTHROPIC_API_KEY" not in runtime.os.environ
    config["ANTHROPIC_ANALYST_GENERATION_ENABLED"] = "true"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="separate_provider_or_source_activation_required"):
        runtime.load_environment(path)
