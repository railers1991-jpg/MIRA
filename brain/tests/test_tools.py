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
