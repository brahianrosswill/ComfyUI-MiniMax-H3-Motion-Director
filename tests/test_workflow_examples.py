from __future__ import annotations

import json
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / "example_workflows"


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_all_example_workflows_are_valid_json_and_use_unique_node_id():
    paths = sorted(WORKFLOWS.glob("*.json"))
    assert paths, "At least one example workflow is required."

    for path in paths:
        workflow = _load(path)
        nodes = workflow.get("nodes")
        assert isinstance(nodes, list) and nodes, f"{path.name}: nodes are missing"
        node_types = {node.get("type") for node in nodes}
        assert "MiniMaxH3Director" not in node_types, (
            f"{path.name}: old AIMixer node ID would collide with the original extension"
        )
        assert "MiniMaxH3MotionDirector" in node_types, (
            f"{path.name}: independent Motion Director node is missing"
        )
        for director in (
            node for node in nodes if node.get("type") == "MiniMaxH3MotionDirector"
        ):
            names = [item["name"] for item in director.get("inputs", [])]
            required_new = {
                "bd_grp_motion",
                "motion_context_enabled",
                "context_length",
                "audio_context_enabled",
                "sampling_control",
                "sampler_name",
                "sampler",
                "sigmas",
            }
            assert required_new.issubset(names), (
                f"{path.name}: workflow still uses the pre-Motion input schema"
            )
            assert names.index("bd_grp_motion") < names.index("bd_grp_advanced")
            assert names.index("sampling_control") < names.index("steps")
            assert len(director["widgets_values"]) == 26, (
                f"{path.name}: stale widget order or extension-only values remain"
            )
            assert "internal" in director["widgets_values"] or "external" in director["widgets_values"]
            assert 22 in director["widgets_values"]


def test_external_sampling_example_has_connected_sampler_and_sigmas():
    path = WORKFLOWS / "minimax_h3_motion_director_t2v_external.json"
    workflow = _load(path)
    nodes = {node["id"]: node for node in workflow["nodes"]}
    director = next(
        node for node in nodes.values() if node["type"] == "MiniMaxH3MotionDirector"
    )
    inputs = {item["name"]: item for item in director["inputs"]}

    assert inputs["sampler"]["type"] == "SAMPLER"
    assert inputs["sampler"]["link"] is not None
    assert inputs["sigmas"]["type"] == "SIGMAS"
    assert inputs["sigmas"]["link"] is not None

    linked_types = {nodes[item[1]]["type"] for item in workflow["links"] if item[0] in {
        inputs["sampler"]["link"], inputs["sigmas"]["link"]
    }}
    assert linked_types == {"KSamplerSelect", "BasicScheduler"}

    widgets = director["widgets_values"]
    assert "external" in widgets
    assert 22 in widgets
    assert True in widgets

    sigma_shift = next(
        node for node in nodes.values() if node["type"] == "MiniMaxH3SigmaShift"
    )
    links = {item[0]: item for item in workflow["links"]}
    director_model_link = inputs["model"]["link"]
    scheduler = next(node for node in nodes.values() if node["type"] == "BasicScheduler")
    scheduler_model_link = next(
        item["link"] for item in scheduler["inputs"] if item["name"] == "model"
    )
    assert links[director_model_link][1] == sigma_shift["id"]
    assert links[scheduler_model_link][1] == sigma_shift["id"]


def test_every_external_example_link_targets_a_real_slot():
    workflow = _load(WORKFLOWS / "minimax_h3_motion_director_t2v_external.json")
    nodes = {node["id"]: node for node in workflow["nodes"]}

    for link_id, source_id, source_slot, target_id, target_slot, _kind in workflow["links"]:
        assert source_id in nodes, f"link {link_id}: missing source node"
        assert target_id in nodes, f"link {link_id}: missing target node"
        assert source_slot < len(nodes[source_id].get("outputs", [])), (
            f"link {link_id}: source slot is out of range"
        )
        assert target_slot < len(nodes[target_id].get("inputs", [])), (
            f"link {link_id}: target slot is out of range"
        )


def test_every_example_link_type_matches_saved_slots():
    for path in sorted(WORKFLOWS.glob("*.json")):
        workflow = _load(path)
        nodes = {node["id"]: node for node in workflow["nodes"]}
        for link_id, source_id, source_slot, target_id, target_slot, kind in workflow.get("links", []):
            assert source_id in nodes and target_id in nodes, (
                f"{path.name} link {link_id}: endpoint node is missing"
            )
            outputs = nodes[source_id].get("outputs", [])
            inputs = nodes[target_id].get("inputs", [])
            assert source_slot < len(outputs), (
                f"{path.name} link {link_id}: source slot is out of range"
            )
            assert target_slot < len(inputs), (
                f"{path.name} link {link_id}: target slot is out of range"
            )
            source_type = outputs[source_slot].get("type")
            target_type = inputs[target_slot].get("type")
            assert kind == "*" or source_type in {kind, "*"}, (
                f"{path.name} link {link_id}: source {source_type} != {kind}"
            )
            assert kind == "*" or target_type in {kind, "*"}, (
                f"{path.name} link {link_id}: target {target_type} != {kind}"
            )
