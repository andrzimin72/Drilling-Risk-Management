"""
QA Swarm
All agents run validation against the full dataset simultaneously.
Returns a unified QA report: pass/warn/fail per domain.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from ..orchestrator import OrchestratorAgent, SwarmContext, SwarmResult

logger = logging.getLogger(__name__)

class QASwarm:
    """
    Quality assurance swarm — validate a dataset across all domains.
    """
    def __init__(self, verbose: bool = True) -> None:
        self.orchestrator = OrchestratorAgent(verbose=verbose)

    async def run(
        self,
        file_paths: list[str | Path],
        well_name: str | None = None,
        api: str | None = None,
    ) -> SwarmResult:
        logger.info("Starting QA Swarm for dataset validation")
        ctx = SwarmContext(well_name=well_name, api=api)
        result = await self.orchestrator.run(file_paths, ctx)
        
        scorecard = _build_qa_scorecard(result)
        result.unified_report = scorecard + "\n\n" + result.unified_report
        logger.info("QA Swarm completed")
        return result

def _build_qa_scorecard(result: SwarmResult) -> str:
    """Build a domain-by-domain QA scorecard."""
    lines = ["QA SCORECARD", "=" * 60]
    domain_checks = {
        "drilling": _qa_drilling,
        "logs": _qa_logs,
        "completions": _qa_completions,
        "production": _qa_production,
        "directional": _qa_directional,
        "hse": _qa_hse,
    }
    
    overall_score = 0
    max_score = 0
    
    for domain, checker in domain_checks.items():
        agent_result = result.agent_results.get(domain, {})
        extracted = agent_result.get("extracted_data", {}).get(domain, {})
        flags = agent_result.get("quality_flags", [])
        
        score, total, checks = checker(extracted, flags)
        overall_score += score
        max_score += total
        
        pct = round(score / total * 100) if total > 0 else 0
        status = "PASS" if pct >= 80 else ("WARN" if pct >= 50 else "FAIL")
        
        lines.append(f"\n[{domain.upper()}] {status} ({score}/{total} checks — {pct}%)")
        for check_name, check_pass, note in checks:
            icon = "✓" if check_pass else "✗"
            line = f"  {icon} {check_name}"
            if note:
                line += f": {note}"
            lines.append(line)
            
    overall_pct = round(overall_score / max_score * 100) if max_score > 0 else 0
    lines.insert(2, f"OVERALL: {overall_score}/{max_score} ({overall_pct}%)")
    lines.insert(3, "")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Domain QA Checkers (Unit-Agnostic)
# ---------------------------------------------------------------------------
def _qa_drilling(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name: str, passed: bool, note: str = "") -> None:
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    chk("Well name extracted", bool(data.get("well_name")))
    # Unit-agnostic ROP check
    chk("ROP data present", bool(data.get("rop_ft_hr") or data.get("rop_m_hr")))
    # Unit-agnostic Mud Weight check
    chk("Mud weight present", bool(
        data.get("mud_weight_ppg") or data.get("mud_weight_sg") or 
        data.get("mud_weight_in_ppg") or data.get("mud_weight_in_sg")
    ))
    # Unit-agnostic Depth check
    chk("Current depth present", bool(
        data.get("current_depth_ft") or data.get("current_depth_m") or 
        data.get("measured_depth_ft") or data.get("measured_depth_m")
    ))
    chk("NPT logged", bool(data.get("npt_events") or data.get("npt_hours")))
    chk("No sanity failures", not any("SANITY" in f for f in flags),
        f"{sum(1 for f in flags if 'SANITY' in f)} failures" if any("SANITY" in f for f in flags) else "")
    return s, len(checks), checks

def _qa_logs(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name, passed, note=""):
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    curves = data.get("curves", [])
    curve_names = {c.get("mnemonic", "") for c in curves}
    chk("GR curve present", "GR" in curve_names or "SGR" in curve_names)
    chk("Resistivity curve present", any(m in curve_names for m in ("RT", "RD", "RILD", "ILD")))
    chk("Density curve present", any(m in curve_names for m in ("RHOB", "DEN", "RHOZ")))
    chk("Depth range valid", bool(data.get("depth_ranges") or data.get("depth_range")))
    chk("Pay intervals computed", isinstance(data.get("pay_intervals"), list))
    return s, len(checks), checks

def _qa_completions(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name, passed, note=""):
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    chk("Stage count present", bool(data.get("stage_count") or data.get("stage_count_actual")))
    # Unit-agnostic fluid/proppant
    chk("Fluid volume present", bool(data.get("total_fluid_bbls") or data.get("total_fluid_m3")))
    chk("Proppant weight present", bool(data.get("total_proppant_lbs") or data.get("total_proppant_tons") or data.get("total_proppant_kg")))
    chk("ISIP data present", bool(data.get("isip_psi") or data.get("isip_kpa")))
    chk("No stage count mismatch", not any("MISMATCH" in f for f in flags))
    return s, len(checks), checks

def _qa_production(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name, passed, note=""):
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    ip = data.get("ip_metrics", {})
    # Unit-agnostic rates
    chk("Oil rate data present", bool(
        data.get("oil_rate_bopd") or data.get("oil_rate_t_day") or 
        ip.get("ip30_rate") or ip.get("ip30_bopd")
    ))
    chk("IP30 computed", bool(ip.get("ip30_rate") or ip.get("ip30_bopd")))
    chk("No GOR breakthrough", not any("GOR" in f for f in flags))
    return s, len(checks), checks

def _qa_directional(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name, passed, note=""):
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    stations = data.get("raw_stations", data.get("stations", []))
    chk("Survey stations present", len(stations) >= 3, f"only {len(stations)} stations" if stations else "none found")
    chk("No inclination jumps", not any("INC_JUMP" in f for f in flags))
    chk("No high DLS", not any("HIGH_DLS" in f for f in flags))
    chk("No survey gaps", not any("SURVEY_GAP" in f for f in flags))
    return s, len(checks), checks

def _qa_hse(data: dict, flags: list) -> tuple[int, int, list]:
    checks, s = [], 0
    def chk(name, passed, note=""):
        nonlocal s
        checks.append((name, passed, note))
        if passed: s += 1

    counts = data.get("incident_counts", {})
    chk("No fatalities", counts.get("fatality", 0) == 0)
    chk("No LTIs", counts.get("lti", 0) == 0)
    chk("SIF potentials reviewed",
        not data.get("incidents") or 
        all(e.get("severity") != "near_miss" or not e.get("sif_potential") for e in data.get("incidents", [])),
        f"{sum(1 for e in data.get('incidents',[]) if e.get('sif_potential'))} SIF events" if data.get("incidents") else "")
    return s, len(checks), checks