import json

import pytest

from multi_agent import SUBORDINATE_AGENTS, orchestrator_context
from site_orchestrator.core import AGENTS, ContractError, SiteOrchestrator


def order(command="site.create", **overrides):
    value = {
        "command": command,
        "project_key": "demo-site",
        "correlation_id": "job-1",
        "request": "Create a service website",
        "constraints": {},
        "approval_scope": [],
    }
    value.update(overrides)
    return value


def test_registered_as_gavrik_subordinate():
    item = SUBORDINATE_AGENTS["site-orchestrator"]
    assert item["parent"] == "orchestrator"
    assert "site-orchestrator" in orchestrator_context().lower()


def test_compact_team_has_independent_quality_and_release_gates():
    assert len(AGENTS) == 6
    assert AGENTS["quality"].key != AGENTS["engineer"].key
    assert AGENTS["security_release"].gate == "release"


def test_create_writes_atomic_state_and_event(tmp_path):
    result = SiteOrchestrator(tmp_path).dispatch(order())
    assert result["parent"] == "gavrik"
    assert result["status"] == "planning"
    assert (tmp_path / ".site-orchestrator" / "state.json").exists()
    event = json.loads((tmp_path / ".site-orchestrator" / "events.jsonl").read_text(encoding="utf-8"))
    assert event["type"] == "dispatch"


def test_release_is_blocked_without_explicit_owner_approval(tmp_path):
    result = SiteOrchestrator(tmp_path).dispatch(order("site.release"))
    assert result["status"] == "ready_for_approval"
    assert result["approvals_needed"] == [
        {"scope": "publish", "human_approval": True, "via": "gavrik"}
    ]


def test_release_requires_both_scope_and_human_approval(tmp_path):
    partial = SiteOrchestrator(tmp_path).dispatch(
        order("site.release", approval_scope=["publish"], human_approval=False)
    )
    assert partial["status"] == "ready_for_approval"
    released = SiteOrchestrator(tmp_path).dispatch(
        order("site.release", approval_scope=["publish"], human_approval=True)
    )
    assert released["status"] == "released"


def test_invalid_command_is_rejected(tmp_path):
    with pytest.raises(ContractError):
        SiteOrchestrator(tmp_path).dispatch(order("site.destroy"))


def test_prepared_create_waits_for_publish_approval(tmp_path):
    result = SiteOrchestrator(tmp_path).dispatch(order(release_prepared=True))
    assert result["status"] == "ready_for_approval"
    assert result["approvals_needed"][0]["scope"] == "publish"


def test_external_preview_requires_its_own_approval(tmp_path):
    blocked = SiteOrchestrator(tmp_path).dispatch(order("site.preview", external_preview=True))
    assert blocked["status"] == "ready_for_approval"
    assert blocked["approvals_needed"][0]["scope"] == "preview_external"


def test_handoff_has_machine_readable_evidence_and_dependencies(tmp_path):
    result = SiteOrchestrator(tmp_path).dispatch(
        order(artifacts=["dist/index.html"], evidence=[{"check": "build", "verdict": "pass"}])
    )
    assert result["artifacts"][0]["path"] == "dist/index.html"
    assert result["evidence"][0]["verdict"] == "pass"
    assert result["assignments"][1]["dependencies"]
