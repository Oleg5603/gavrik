from pathlib import Path

import pytest

from multi_agent import GROUP_NAME, IterationLimitError, QUALITY_GATES, ROLES, WorkflowState


def test_all_requested_roles_have_explicit_contracts():
    assert GROUP_NAME == "ПРОЕКТ"
    assert len(ROLES) == 13
    assert all(role.inputs and role.outputs and role.exit_condition for role in ROLES.values())


def test_iteration_limit_escalates_to_human(tmp_path: Path):
    state = WorkflowState(tmp_path / "state.json", max_iterations=2)
    assert state.begin_iteration("developer_qa") == 1
    assert state.begin_iteration("developer_qa") == 2
    with pytest.raises(IterationLimitError, match="нужен человек"):
        state.begin_iteration("developer_qa")


def test_gate_requires_approvals_and_no_blockers(tmp_path: Path):
    state = WorkflowState(tmp_path / "state.json")
    state.data["approvals"] = list(QUALITY_GATES["implementation"])
    assert state.gate_passed("implementation")
    state.data["findings"].append({"severity": "high", "status": "open"})
    assert not state.gate_passed("implementation")
