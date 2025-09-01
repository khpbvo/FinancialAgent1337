from __future__ import annotations

import logging
import os
from typing import Any

from ..config.env import load_settings

logger = logging.getLogger("finagent.openai")


def build_agents() -> dict[str, Any]:
    """
    Construct orchestrator + specialists. If the Agents SDK is missing, raise a clear error.
    """
    try:
        from agents import Agent, WebSearchTool
        from agents.mcp import MCPServerStdio
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "OpenAI Agents SDK not available. Install 'openai-agents' to run agents."
        ) from e

    s = load_settings()
    fs_server = MCPServerStdio(
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", s.repo_root],
        },
        cache_tools_list=True,
    )

    debt_expert = Agent(
        name="DebtExpert",
        instructions=(
            "Je helpt met schulden, betalingsregelingen, prioritering en aflossing."
        ),
        tools=[WebSearchTool()],
        mcp_servers=[fs_server],
        model=s.model,
    )

    investment_expert = Agent(
        name="InvestmentExpert",
        instructions=(
            "Je adviseert over beleggingsstrategie, risicoprofiel en portefeuille."
        ),
        tools=[WebSearchTool()],
        mcp_servers=[fs_server],
        model=s.model,
    )

    from .spending_tools import spend_by_category

    spending_expert = Agent(
        name="SpendingAnalysisExpert",
        instructions=(
            "Je analyseert transacties, herkent categorieën en geeft budgetadvies."
        ),
        tools=[WebSearchTool(), spend_by_category],
        mcp_servers=[fs_server],
        model=s.model,
    )

    orchestrator = Agent(
        name="FinancialOrchestrator",
        instructions=(
            "Je routeert naar de juiste specialist en geeft zelf nooit inhoudelijke antwoorden."
        ),
        handoffs=[debt_expert, investment_expert, spending_expert],
        tools=[WebSearchTool()],
        mcp_servers=[fs_server],
        model=s.model,
    )

    return {
        "orchestrator": orchestrator,
        "debt": debt_expert,
        "invest": investment_expert,
        "spending": spending_expert,
    }
