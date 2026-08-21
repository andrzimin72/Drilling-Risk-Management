"""
Pad Analysis Swarm
Runs per-well sub-swarms in parallel across all wells on a pad.
Aggregates pad-level statistics and cross-well comparisons.
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Any

from ..orchestrator import OrchestratorAgent, SwarmContext, SwarmResult

logger = logging.getLogger(__name__)

def _get_val(data: dict, *keys: str) -> Any:
    """Return the first non-None value for a list of unit-agnostic keys."""
    for k in keys:
        val = data.get(k)
        if val is not None:
            return val
    return None

class PadAnalysisSwarm:
    """
    Analyze all wells on a pad simultaneously.
    Each well gets its own sub-swarm running in parallel.
    """
    def __init__(
        self,
        pad_name: str | None = None,
        operator: str | None = None,
        field_name: str | None = None,
        verbose: bool = False,
    ) -> None:
        self.pad_name = pad_name
        self.operator = operator
        self.field_name = field_name
        self.verbose = verbose

    async def run(self, wells: dict[str, list[str | Path]]) -> dict[str, Any]:
        if not wells:
            return {"error": "No wells provided"}
            
        logger.info(f"Starting Pad Analysis Swarm for {len(wells)} wells on pad '{self.pad_name}'")
        
        tasks = {}
        for well_name, file_paths in wells.items():
            orchestrator = OrchestratorAgent(verbose=False)
            ctx = SwarmContext(
                well_name=well_name,
                pad=self.pad_name,
                operator=self.operator,
                field_name=self.field_name,
            )
            task = asyncio.create_task(
                orchestrator.run(file_paths, ctx),
                name=f"well_{well_name}",
            )
            tasks[well_name] = task

        done_tasks = await asyncio.gather(*tasks.values(), return_exceptions=True)
        well_results: dict[str, SwarmResult | Exception] = dict(zip(tasks.keys(), done_tasks))
        
        pad_summary = _aggregate_pad_stats(well_results)
        
        succeeded = sum(1 for r in well_results.values() if isinstance(r, SwarmResult))
        logger.info(f"Pad Analysis Swarm complete — {succeeded}/{len(wells)} wells succeeded")
        
        return {
            "pad_name": self.pad_name,
            "operator": self.operator,
            "well_count": len(wells),
            "per_well_results": {
                wn: r.to_dict() if isinstance(r, SwarmResult) else {"error": str(r)}
                for wn, r in well_results.items()
            },
            "pad_summary": pad_summary,
        }

def _aggregate_pad_stats(results: dict[str, Any]) -> dict[str, Any]:
    """Compute pad-level aggregates from all well SwarmResults (Unit-Agnostic)."""
    ip30_values: list[float] = []
    npt_hrs_values: list[float] = []
    stage_counts: list[int] = []
    pay_values: list[float] = []
    
    for well_name, result in results.items():
        if not isinstance(result, SwarmResult):
            continue
            
        # Production (IP30) - Supports both Imperial and Metric
        prod = _dig(result.agent_results, "production.extracted_data.production")
        if prod:
            ip = prod.get("ip_metrics", {})
            ip30 = _get_val(ip, "ip30_rate", "ip30_bopd")
            if ip30:
                ip30_values.append(float(ip30))
                
        # Drilling (NPT)
        drilling = _dig(result.agent_results, "drilling.extracted_data.drilling")
        if drilling:
            npt = _get_val(drilling, "npt_hours")
            if npt is not None:
                npt_hrs_values.append(float(npt))
                
        # Completions (Stages)
        comp = _dig(result.agent_results, "completions.extracted_data.completions")
        if comp and comp.get("stage_count"):
            try:
                stage_counts.append(int(float(str(comp["stage_count"]))))
            except (ValueError, TypeError):
                pass
                
        # Logs (Net Pay) - Supports both Imperial and Metric
        logs = _dig(result.agent_results, "logs.extracted_data.logs")
        if logs:
            pay = _get_val(logs, "total_net_pay", "total_net_pay_ft", "total_net_pay_m")
            if pay is not None:
                try:
                    pay_values.append(float(pay))
                except (ValueError, TypeError):
                    pass

    summary: dict[str, Any] = {}
    if ip30_values:
        summary["avg_ip30"] = round(sum(ip30_values) / len(ip30_values), 1)
        summary["max_ip30"] = round(max(ip30_values), 1)
        summary["min_ip30"] = round(min(ip30_values), 1)
    if stage_counts:
        summary["avg_stage_count"] = round(sum(stage_counts) / len(stage_counts), 1)
        summary["total_stages_all_wells"] = sum(stage_counts)
    if pay_values:
        summary["avg_net_pay"] = round(sum(pay_values) / len(pay_values), 1)
    if npt_hrs_values:
        summary["avg_npt_hours"] = round(sum(npt_hrs_values) / len(npt_hrs_values), 1)
        
    return summary

def _dig(d: dict, path: str) -> Any:
    """Nested dict access using dot-path notation."""
    parts = path.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current