import re
from pathlib import Path

from langform.bridge import capability_report


def test_bridge_reports_stable_protocol_and_exact_executable_operations():
    report = capability_report()
    assert report["bridgeVersion"] == "1.0.0"
    assert report["supportedObjectives"] == ["processing", "packaging"]
    source = Path("src/langform/bridge_local.py").read_text()
    dispatched = set()
    for condition in re.findall(r"^\s*(?:if|elif) operation (== [^\n:]+|in \{[^\n]+?\}):", source, re.MULTILINE):
        dispatched.update(re.findall(r'"([^"]+)"', condition))
    assert set(report["supportedOperations"]) == dispatched
    assert len(report["supportedOperations"]) == len(set(report["supportedOperations"]))


def test_report_does_not_share_mutable_lists_between_heartbeats():
    report = capability_report()
    report["supportedOperations"].clear()
    report["supportedObjectives"].clear()
    assert "classify_project_prompt" in capability_report()["supportedOperations"]
    assert capability_report()["supportedObjectives"] == ["processing", "packaging"]


def test_registration_and_heartbeat_both_send_capabilities():
    import ast
    source = Path("src/langform/bridge.py").read_text()
    tree = ast.parse(source)
    for endpoint in ("register", "heartbeat"):
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "call"
                 and node.args and isinstance(node.args[0], ast.Constant)
                 and node.args[0].value == endpoint]
        assert calls
        for call in calls:
            assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == "capability_report" for node in ast.walk(call.args[1]))
