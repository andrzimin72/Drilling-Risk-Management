"""
Well Performance Swarm
Full well analysis: all domain agents run in parallel against a complete
well dataset. Cross-domain insights synthesized by the report agent.
"""
from __future__ import annotations
import logging
from pathlib import Path

from ..orchestrator import OrchestratorAgent, SwarmContext, SwarmResult

logger = logging.getLogger(__name__)

class WellPerformanceSwarm:
    """
    Complete well performance analysis using all specialist agents.
    """
    def __init__(
        self,
        well_name: str | None = None,
        api: str | None = None,
        pad: str | None = None,
        field_name: str | None = None,
        operator: str | None = None,
        lateral_length_ft: float | None = None,
        lateral_length_m: float | None = None,  # Phase 1: Metric support
        total_manhours: float | None = None,
        gr_cutoff: float | None = None,         # Phase 2: Configurable petrophysics
        rt_cutoff: float | None = None,
        verbose: bool = True,
    ) -> None:
        self.orchestrator = OrchestratorAgent(verbose=verbose)
        
        # Build context, filtering out None values
        self._context_kwargs = {
            "well_name": well_name,
            "api": api,
            "pad": pad,
            "field_name": field_name,
            "operator": operator,
            "lateral_length_ft": lateral_length_ft,
            "lateral_length_m": lateral_length_m,
            "total_manhours": total_manhours,
            "gr_cutoff": gr_cutoff,
            "rt_cutoff": rt_cutoff,
        }
        # Remove None values so SwarmContext uses defaults or ignores them
        self._context_kwargs = {k: v for k, v in self._context_kwargs.items() if v is not None}

    async def run(self, file_paths: list[str | Path]) -> SwarmResult:
        logger.info(f"Starting Well Performance Swarm for well: {self._context_kwargs.get('well_name', 'Unknown')}")
        ctx = SwarmContext(**self._context_kwargs)
        result = await self.orchestrator.run(file_paths, ctx)
        logger.info(f"Well Performance Swarm completed. Status: {result.status}")
        return result