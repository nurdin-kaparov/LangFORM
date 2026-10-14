import anyio
import pytest


def test_mcp_in_memory_context_tools(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from mcp import Client
    from langform.mcp_server import mcp

    monkeypatch.setenv("LANGFORM_WORKSPACE", str(tmp_path / ".langform"))

    async def run():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"register_asset", "request_context", "get_context_package"}.issubset(names)
            assert not {"shell", "plan", "memory", "web_search"} & names
            result = await client.call_tool("list_assets", {})
            assert not result.is_error

    anyio.run(run)
