"""
File Analysis Swarm
Routes any set of oil and gas files to the correct specialist agents
and returns a unified extraction report. Good for ad-hoc analysis.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from ..orchestrator import OrchestratorAgent, SwarmContext, SwarmResult

logger = logging.getLogger(__name__)

class FileAnalysisSwarm:
    """
    Auto-detect and analyze any set of oil and gas engineering files.
    Example:
        swarm = FileAnalysisSwarm()
        result = await swarm.run(["report.pdf", "log.las", "stages.xlsx"])
    """
    def __init__(self, verbose: bool = True) -> None:
        self.orchestrator = OrchestratorAgent(verbose=verbose)

    async def run(
        self,
        file_paths: list[str | Path],
        well_name: str | None = None,
        api: str | None = None,
        project_name: str | None = None,
    ) -> SwarmResult:
        logger.info(f"Starting File Analysis Swarm for {len(file_paths)} files")
        ctx = SwarmContext(
            well_name=well_name,
            api=api,
            project_name=project_name,
        )
        result = await self.orchestrator.run(file_paths, ctx)
        logger.info(f"File Analysis Swarm completed. Status: {result.status}")
        return result