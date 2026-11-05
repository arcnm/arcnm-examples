#!/usr/bin/env python3
"""A LlamaIndex agent that prices parts through ARCNM's MCP server.

    export ARCNM_MCP_TOKEN="ak_live_…"    # arcnm.io → Settings → API keys
    export ANTHROPIC_API_KEY="…"          # or swap in any LlamaIndex LLM
    pip install llama-index-tools-mcp llama-index-llms-anthropic
    python mcp/llamaindex/agent.py "Which of my last five calculations was the most expensive per unit, and why?"

No ARCNM package to install: LlamaIndex's own MCP client lists the server's
tools and the agent picks among them. Reading results is free; a tool that
starts a calculation (upload_and_quote, quote_part) uses one from your plan.
"""

from __future__ import annotations

import asyncio
import os
import sys

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.anthropic import Anthropic
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

MCP_URL = "https://api.arcnm.io/mcp-server/mcp"

# Leave this as None for every default tool. Listing a few keeps the agent's
# context small and makes it impossible for it to start a calculation.
READ_ONLY_TOOLS = [
    "check_quota",
    "list_calculations",
    "get_calculation",
    "explain_cost",
    "get_cost_breakdown",
    "get_process_plan",
    "list_environments",
]


async def main(question: str) -> None:
    token = os.environ.get("ARCNM_MCP_TOKEN")
    if not token:
        sys.exit("ARCNM_MCP_TOKEN is not set. Create an API key at arcnm.io → Settings → API keys.")

    client = BasicMCPClient(MCP_URL, headers={"Authorization": f"Bearer {token}"})
    tools = await McpToolSpec(client=client, allowed_tools=READ_ONLY_TOOLS).to_tool_list_async()

    agent = FunctionAgent(
        tools=tools,
        llm=Anthropic(model="claude-sonnet-5-5"),
        system_prompt=(
            "You answer questions about manufactured parts with ARCNM's tools. "
            "Quote figures exactly as the tools return them, with their currency."
        ),
    )
    print(await agent.run(question))


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "How many calculations do I have left this month?"))
