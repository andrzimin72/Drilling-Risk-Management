"""
Report Agent
Final agent in the swarm. Synthesizes results from all domain agents
into a unified, cross-domain engineering report with conflict resolution.
"""
from __future__ import annotations
from typing import Any
from pathlib import Path
from .base_agent import BaseAgent, AgentResult

class ReportAgent(BaseAgent):
    """Synthesizes all agent results into a unified engineering report."""
    domain = "report"
    description = "Aggregates and synthesizes results from all specialist agents into a unified report."

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        return False

    async def _process(self, file_paths: list[Path], context: dict[str, Any]) -> AgentResult:
        return AgentResult(agent_name="ReportAgent", domain="report", status="skipped")

    async def synthesize(self, swarm_context: "SwarmContext") -> AgentResult:  # noqa: F821
        """Generate unified report from all agent results stored in swarm_context."""
        results = swarm_context.agent_results
        merged = _merge_entity_context(results)
        cross_checks = _run_cross_domain_checks(results)
        all_flags = _collect_all_flags(results)
        all_flags.extend(cross_checks)
        report_text = _format_report(swarm_context, results, merged, all_flags)
        
        return AgentResult(
            agent_name="ReportAgent",
            domain="report",
            status="success",
            extracted_data={
                "unified_entity_context": merged,
                "domain_results": {k: v.to_dict() for k, v in results.items()},
                "cross_domain_flags": cross_checks,
            },
            summary=report_text,
            quality_flags=all_flags,
            confidence=_compute_aggregate_confidence(results),
            files_processed=swarm_context.all_files,
        )

def _merge_entity_context(results: dict[str, "AgentResult"]) -> dict[str, Any]:  # noqa: F821
    merged: dict[str, Any] = {}
    for domain, result in results.items():
        data = result.extracted_data or {}
        for bucket in data.values():
            if not isinstance(bucket, dict):
                continue
            for field in ("well_name", "api", "operator", "field", "rig_name"):
                val = bucket.get(field)
                if val and val != "None" and str(val).strip():
                    if field not in merged:
                        merged[field] = val
    return merged

def _run_cross_domain_checks(results: dict[str, "AgentResult"]) -> list[str]:  # noqa: F821
    """Validate consistency across domain agent results (Unit-Agnostic)."""
    flags: list[str] = []
    drilling = _get_domain_data(results, "drilling")
    logs = _get_domain_data(results, "logs")
    completions = _get_domain_data(results, "completions")

    # LAS depth range vs. drilling total depth (Supports both Imperial and Metric)
    drill_depth = _safe_float(
        drilling.get("current_depth_ft") or 
        drilling.get("current_depth_m") or 
        drilling.get("measured_depth_ft") or 
        drilling.get("measured_depth_m")
    )
    
    if drill_depth and logs.get("depth_ranges"):
        log_depths = logs["depth_ranges"]
        if log_depths:
            max_log_depth = 0.0
            for d in log_depths:
                val = _safe_float(d.get("stop_ft") or d.get("stop_m") or d.get("stop") or 0)
                if val and val > max_log_depth:
                    max_log_depth = val
            
            if max_log_depth and drill_depth:
                if abs(max_log_depth - drill_depth) / max(drill_depth, 1) > 0.10:
                    flags.append(
                        f"CROSS_DOMAIN: LAS max depth {max_log_depth} vs. "
                        f"drilling total depth {drill_depth} (>10% mismatch)"
                    )

    # Completion stage count vs. pay zone count
    stage_count = _safe_float(completions.get("stage_count"))
    pay_count = logs.get("pay_zone_count", 0)
    if stage_count and pay_count and stage_count < pay_count * 0.5:
        flags.append(
            f"CROSS_DOMAIN: {int(stage_count)} frac stages vs. {pay_count} log-identified pay zones — "
            f"possible under-stimulation"
        )

    return flags

def _collect_all_flags(results: dict[str, "AgentResult"]) -> list[str]:  # noqa: F821
    all_flags: list[str] = []
    for domain, result in results.items():
        for flag in (result.quality_flags or []):
            if not flag.startswith(f"[{domain}]"):
                all_flags.append(f"[{domain}] {flag}")
            else:
                all_flags.append(flag)
    return all_flags

def _compute_aggregate_confidence(results: dict[str, "AgentResult"]) -> float:  # noqa: F821
    confs = [r.confidence for r in results.values() if r.confidence > 0]
    return round(sum(confs) / len(confs), 3) if confs else 0.0

def _format_report(swarm_ctx: Any, results: dict, merged: dict, flags: list[str]) -> str:
    lines = []
    well = merged.get("well_name", "Unknown Well")
    api = merged.get("api", " ")
    lines.append(f"SWARM REPORT — {well}" + (f" ({api})" if api else " "))
    lines.append("=" * 60)
    
    for field in ("operator", "field", "rig_name"):
        if merged.get(field):
            lines.append(f"{field.replace('_', ' ').title()}: {merged[field]}")
    lines.append("")
    
    domain_order = ["data_manager", "drilling", "logs", "completions", "production", "directional", "hse"]
    for domain in domain_order:
        result = results.get(domain)
        if result and result.status not in ("skipped", "error") and result.summary:
            label = domain.upper().replace("_", " ")
            lines.append(f"[{label}]")
            lines.append(result.summary)
            lines.append("")
            
    if flags:
        lines.append(f"QUALITY FLAGS ({len(flags)} total)")
        lines.append("-" * 40)
        for flag in flags[:20]:
            lines.append(f"  {flag}")
        if len(flags) > 20:
            lines.append(f"  ... and {len(flags) - 20} more")
            
    lines.append("")
    lines.append(f"Files processed: {len(swarm_ctx.all_files)}")
    active = sum(1 for r in results.values() if r.status == "success")
    lines.append(f"Agents succeeded: {active}/{len(results)}")
    return "\n".join(lines)

def _get_domain_data(results: dict, domain: str) -> dict:
    result = results.get(domain)
    if not result:
        return {}
    return result.extracted_data.get(domain, {})

def _safe_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
