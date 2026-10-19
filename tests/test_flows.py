"""Structural validation of the Duo flow YAMLs against the documented v1 rules.

Rules encoded here come from:
- https://docs.gitlab.com/user/duo_agent_platform/flows/custom_flows_schema/ (restricted fields)
- flow registry v1 spec (components, prompts, routers, inputs/outputs)
- known_tools.txt (tool names from the GitLab agent tools docs)
This does not replace running the flow on GitLab; it catches config mistakes before upload.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FLOWS = sorted((ROOT / ".gitlab" / "duo" / "flows").glob("*.yaml"))
KNOWN_TOOLS = {l.strip() for l in (ROOT / "tests" / "known_tools.txt").read_text().splitlines()
               if l.strip() and not l.startswith("#")}
FORBIDDEN_TOP = {"name", "description", "product_group"}
ALLOWED_TOP = {"version", "environment", "components", "routers", "flow", "prompts", "coding_environment", "include"}
COMPONENT_TYPES = {"AgentComponent", "DeterministicStepComponent", "OneOffComponent", "HumanInputComponent"}
BUILTIN_TARGETS = {"end", "abort"}


def load(p):
    return yaml.safe_load(p.read_text())


def input_var(i):
    if isinstance(i, str):
        return i.split(":", 1)[1].split(".")[-1]
    return i.get("as") or i["from"].split(":", 1)[1].split(".")[-1]


def test_flows_exist():
    assert {p.name for p in FLOWS} == {"mr-risk-gate.yaml", "pipeline-medic.yaml"}


@pytest.mark.parametrize("path", FLOWS, ids=lambda p: p.name)
def test_flow_structure(path):
    f = load(path)
    assert f["version"] == "v1"
    assert f["environment"] == "ambient"  # only value custom flows support
    assert not (set(f) & FORBIDDEN_TOP), "custom flows reject name/description/product_group"
    assert set(f) <= ALLOWED_TOP
    names = [c["name"] for c in f["components"]]
    assert len(names) == len(set(names))
    for n in names:
        assert ":" not in n and "." not in n
    prompts = {p["prompt_id"]: p for p in f.get("prompts", [])}
    for p in prompts.values():
        assert "model" not in p, "model in prompts is restricted"
        assert {"prompt_id", "name", "unit_primitives", "prompt_template"} <= set(p)
        assert "stop" not in p.get("params", {})
    for c in f["components"]:
        assert c["type"] in COMPONENT_TYPES
        assert "response_schema_id" not in c and "response_schema_version" not in c
        if c["type"] in ("AgentComponent", "OneOffComponent"):
            assert c["prompt_id"] in prompts, f"{c['name']} references missing prompt"
            assert c.get("prompt_version") is None  # local prompt
            for tool in c.get("toolset", []):
                tname = tool if isinstance(tool, str) else next(iter(tool))
                assert tname in KNOWN_TOOLS, f"unknown tool {tname}"
            # every {{var}} in the user template must be provided by an input
            provided = {input_var(i) for i in c.get("inputs", ["context:goal"])}
            used = set(re.findall(r"{{\s*(\w+)\s*}}", prompts[c["prompt_id"]]["prompt_template"]["user"]))
            assert used <= provided, f"{c['name']} template uses {used - provided} without inputs"
            # inputs from other components must reference real components
            for i in c.get("inputs", []):
                src = i if isinstance(i, str) else i["from"]
                m = re.match(r"context:(\w+)\.", src)
                if m:
                    assert m.group(1) in names
    assert f["flow"]["entry_point"] in names
    targets = set(names) | BUILTIN_TARGETS
    routed_from = set()
    for r in f["routers"]:
        assert r["from"] in names
        routed_from.add(r["from"])
        if "to" in r:
            assert r["to"] in targets
        else:
            assert set(r["condition"]["routes"].values()) <= targets
    assert routed_from == set(names), "every component needs an outgoing router"


def _reachable(f):
    graph = {}
    for r in f["routers"]:
        graph.setdefault(r["from"], set()).update(
            [r["to"]] if "to" in r else r["condition"]["routes"].values())
    seen, stack = set(), [f["flow"]["entry_point"]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, ()))
    return seen


@pytest.mark.parametrize("path", FLOWS, ids=lambda p: p.name)
def test_all_components_reachable_and_terminate(path):
    f = load(path)
    seen = _reachable(f)
    assert {c["name"] for c in f["components"]} <= seen
    assert "end" in seen


def test_risk_gate_routes_low_risk_past_test_author():
    f = load(ROOT / ".gitlab/duo/flows/mr-risk-gate.yaml")
    routes = next(r for r in f["routers"] if r["from"] == "risk_triage")["condition"]["routes"]
    assert routes["LOW"] == "release_scribe"
    assert routes["HIGH"] == routes["MEDIUM"] == routes["default_route"] == "test_author"


def test_no_flow_can_merge_or_approve():
    risky = {"merge_merge_request", "approve_merge_request"}
    for p in FLOWS:
        for c in load(p)["components"]:
            tools = {t if isinstance(t, str) else next(iter(t)) for t in c.get("toolset", [])}
            assert not tools & risky


def test_release_captain_agent_is_read_only():
    a = load(ROOT / ".gitlab/duo/agents/release-captain.yaml")
    assert set(a["tools"]) <= KNOWN_TOOLS
    writes = {t for t in a["tools"] if t.startswith(("create_", "update_", "edit_", "delete_")) or t == "run_command"}
    assert not writes


def test_ci_yaml_parses_and_has_lifecycle_stages():
    ci = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    assert ci["stages"] == ["lint", "test", "secure", "risk", "package", "deploy", "monitor", "release", "govern"]
    for job in ("unit_tests", "mr_risk_score", "pages", "post_deploy_probe", "evidence_bundle", "create_release"):
        assert job in ci
    assert ci["pages"]["rules"][0]["when"] == "manual"  # human approves production
