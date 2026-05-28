from __future__ import annotations

from mira.agent.tools import BRAIN_TOOLS, TOOL_NAMES, TOOLS


def test_tools_have_valid_shape() -> None:
    for tool in TOOLS:
        assert {"name", "description", "input_schema"} <= tool.keys()
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_tool_names_unique() -> None:
    names = [t["name"] for t in TOOLS]
    assert len(names) == len(set(names))
    assert TOOL_NAMES == set(names)


def test_brain_tools_subset_of_all_tools() -> None:
    assert BRAIN_TOOLS <= TOOL_NAMES
    assert "remember" in BRAIN_TOOLS


def test_read_screen_tool_present() -> None:
    assert "read_screen" in TOOL_NAMES


def test_tool_result_block_text_only() -> None:
    from mira.agent.orchestrator import Orchestrator

    block = Orchestrator._tool_result_block({"id": "tu_1", "output": "ok"})
    assert block == {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}


def test_tool_result_block_with_image() -> None:
    from mira.agent.orchestrator import Orchestrator

    block = Orchestrator._tool_result_block(
        {"id": "tu_2", "output": "captured 1000 bytes", "image_b64": "aGVsbG8="}
    )
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "tu_2"
    assert isinstance(block["content"], list)
    assert block["content"][0] == {"type": "text", "text": "captured 1000 bytes"}
    assert block["content"][1]["type"] == "image"
    assert block["content"][1]["source"]["media_type"] == "image/png"
    assert block["content"][1]["source"]["data"] == "aGVsbG8="
