"""
Specialist Domain Agents
"""
from .base_agent import BaseAgent, AgentResult
from .data_manager_agent import DataManagerAgent
from .drilling_agent import DrillingAgent
from .logs_agent import LogsAgent
from .completions_agent import CompletionsAgent
from .production_agent import ProductionAgent
from .directional_agent import DirectionalAgent
from .hse_agent import HSEAgent
from .report_agent import ReportAgent

__all__ = [
    "BaseAgent", "AgentResult", "DataManagerAgent",
    "DrillingAgent", "LogsAgent", "CompletionsAgent",
    "ProductionAgent", "DirectionalAgent", "HSEAgent", "ReportAgent"
]