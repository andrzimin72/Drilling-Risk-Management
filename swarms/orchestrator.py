"""
Swarm Orchestrator
Plans, dispatches, and aggregates work across all specialist agents.
Supports parallel execution, dependency ordering, and result merging.
OpenTelemetry tracing + SQLite checkpointing for crash recovery.
Integrated Risk Management System with Word report generation.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .agents.base_agent import AgentResult
from .agents.data_manager_agent import DataManagerAgent
from .agents.drilling_agent import DrillingAgent
from .agents.logs_agent import LogsAgent
from .agents.completions_agent import CompletionsAgent
from .agents.production_agent import ProductionAgent
from .agents.directional_agent import DirectionalAgent
from .agents.hse_agent import HSEAgent
from .agents.report_agent import ReportAgent

# Pillar 3: Telemetry and Checkpointing
from .telemetry import init_telemetry, get_tracer, get_status_class
from .checkpoint import CheckpointManager

# Pillar 4: Risk Management
try:
    from .risk_manager import RiskScoringEngine, RiskRegistry
    HAS_RISK_MANAGER = True
except ImportError:
    HAS_RISK_MANAGER = False

logger = logging.getLogger(__name__)

# Initialize telemetry at module load
init_telemetry(service_name="oil_gas_swarm", enable_console_exporter=False)
tracer = get_tracer("orchestrator")
Status, StatusCode = get_status_class()


# ---------------------------------------------------------------------------
# Swarm context — shared state across all agents
# ---------------------------------------------------------------------------
@dataclass
class SwarmContext:
    """Mutable shared context passed to all agents in the swarm."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    well_name: str | None = None
    api: str | None = None
    pad: str | None = None
    field_name: str | None = None
    operator: str | None = None
    project_name: str | None = None
    lateral_length_ft: float | None = None
    lateral_length_m: float | None = None
    total_manhours: float | None = None
    gr_cutoff: float | None = None
    rt_cutoff: float | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    all_files: list[str] = field(default_factory=list)
    agent_results: dict[str, AgentResult] = field(default_factory=dict)
    status: str = "pending"
    started_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None

    def to_agent_context(self) -> dict[str, Any]:
        return {
            "well_name": self.well_name, "api": self.api, "pad": self.pad,
            "field_name": self.field_name, "operator": self.operator,
            "project_name": self.project_name,
            "lateral_length_ft": self.lateral_length_ft,
            "lateral_length_m": self.lateral_length_m,
            "total_manhours": self.total_manhours,
            "gr_cutoff": self.gr_cutoff, "rt_cutoff": self.rt_cutoff,
        }

    def elapsed_seconds(self) -> float:
        end = self.completed_at or time.monotonic()
        return round(end - self.started_at, 2)


@dataclass
class SwarmResult:
    """Final aggregated result from a completed swarm run."""
    task_id: str
    status: str
    well_name: str | None
    api: str | None
    files_processed: int
    agents_succeeded: int
    agents_failed: int
    elapsed_seconds: float
    agent_results: dict[str, dict[str, Any]]
    unified_report: str
    quality_flags: list[str]
    cross_domain_flags: list[str]
    # Pillar 4: Risk Management
    risk_registry: Any = None  # RiskRegistry instance
    risk_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        # Serialize risk registry if present
        if self.risk_registry is not None:
            try:
                d["risk_summary"] = self.risk_registry.get_summary()
                d["risk_count"] = len(self.risk_registry.risks)
            except Exception:
                d["risk_summary"] = None
        return d


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class OrchestratorAgent:
    """Plans and coordinates the agent swarm."""

    def __init__(
        self,
        verbose: bool = True,
        agents: list | None = None,
        checkpoint_enabled: bool = True,
        risk_management_enabled: bool = True,
        report_language: str = "ru",
    ) -> None:
        self.verbose = verbose
        self._domain_agents = agents or [
            DrillingAgent(verbose=verbose), LogsAgent(verbose=verbose),
            CompletionsAgent(verbose=verbose), ProductionAgent(verbose=verbose),
            DirectionalAgent(verbose=verbose), HSEAgent(verbose=verbose),
        ]
        self._data_manager = DataManagerAgent(verbose=verbose)
        self._report_agent = ReportAgent(verbose=verbose)

        # Pillar 3: Checkpoint
        self.checkpoint_enabled = checkpoint_enabled
        self.checkpoint_manager = CheckpointManager() if checkpoint_enabled else None

        # Pillar 4: Risk Management
        self.risk_management_enabled = risk_management_enabled and HAS_RISK_MANAGER
        self.report_language = report_language

    async def run(
        self,
        file_paths: list[str | Path],
        context: SwarmContext | None = None,
        generate_risk_report: bool = False,
        report_output_path: str | Path | None = None,
    ) -> SwarmResult:
        """
        Run the full swarm pipeline with optional risk report generation.
        
        Args:
            file_paths: Files to process
            context: Optional pre-populated SwarmContext
            generate_risk_report: If True, generate branded Word report
            report_output_path: Path for the Word report (default: auto-generated)
        """
        with tracer.start_as_current_span("swarm.run") as root_span:
            root_span.set_attribute("swarm.file_count", len(file_paths))

            ctx = context or SwarmContext()

            # Deterministic task_id for recovery
            if not context or not context.task_id:
                file_hash = hashlib.md5("|".join(str(p) for p in sorted(file_paths)).encode()).hexdigest()[:8]
                ctx.task_id = f"swarm_{file_hash}"

            root_span.set_attribute("swarm.task_id", ctx.task_id)
            ctx.all_files = [str(p) for p in file_paths]

            # Checkpoint recovery
            if self.checkpoint_manager:
                saved_status = self.checkpoint_manager.get_status(ctx.task_id)
                if saved_status == "complete":
                    logger.info(f"[Swarm {ctx.task_id}] Checkpoint: task already complete.")
                    root_span.set_attribute("swarm.checkpoint_hit", True)
                    return self._load_cached_result(ctx)
                elif saved_status == "running":
                    logger.info(f"[Swarm {ctx.task_id}] Checkpoint: resuming.")
                    root_span.set_attribute("swarm.checkpoint_resume", True)
                    self._restore_context_from_checkpoint(ctx)

            ctx.status = "running"
            if self.verbose:
                logger.info(f"[Swarm {ctx.task_id}] Starting — {len(file_paths)} file(s)")

            # Phase 1: Data Manager
            with tracer.start_as_current_span("agent.data_manager") as dm_span:
                dm_result = await self._data_manager.run(file_paths, ctx.to_agent_context())
                ctx.agent_results["data_manager"] = dm_result
                dm_span.set_attribute("agent.status", dm_result.status)
                if self.checkpoint_manager:
                    self.checkpoint_manager.save_agent_result(ctx.task_id, "data_manager", dm_result)

            routing: dict[str, list[str]] = {}
            if dm_result.status == "success":
                routing = dm_result.extracted_data.get("routing", {})
                manifest = dm_result.extracted_data.get("manifest", [])
                _update_context_from_manifest(ctx, manifest)

            # Phase 2: Domain agents in parallel
            tasks: list[asyncio.Task] = []
            agent_domain_map: dict[asyncio.Task, str] = {}

            for agent in self._domain_agents:
                if agent.domain in ctx.agent_results:
                    if self.verbose:
                        logger.info(f"  ⏭ {agent.domain}: skipped (restored from checkpoint)")
                    continue

                domain_files = routing.get(agent.domain, []) or ctx.all_files
                task = asyncio.create_task(
                    agent.run(domain_files, ctx.to_agent_context()),
                    name=agent.__class__.__name__,
                )
                tasks.append(task)
                agent_domain_map[task] = agent.domain

            if tasks:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
                for task in done:
                    domain = agent_domain_map[task]
                    try:
                        result = task.result()
                        ctx.agent_results[domain] = result
                        if self.checkpoint_manager:
                            self.checkpoint_manager.save_agent_result(ctx.task_id, domain, result)
                        if self.verbose:
                            status_icon = "✓" if result.status == "success" else "~"
                            logger.info(f"  {status_icon} {domain}: {result.status} ({result.duration_seconds}s)")
                    except Exception as exc:
                        logger.exception(f"Agent {domain} crashed")
                        err_result = AgentResult(
                            agent_name=domain, domain=domain, status="error", error=str(exc)
                        )
                        ctx.agent_results[domain] = err_result
                        if self.checkpoint_manager:
                            self.checkpoint_manager.save_agent_result(ctx.task_id, domain, err_result)

            # Phase 3: Report synthesis
            with tracer.start_as_current_span("agent.report") as report_span:
                report_result = await self._report_agent.synthesize(ctx)
                ctx.agent_results["report"] = report_result
                report_span.set_attribute("agent.status", report_result.status)
                if self.checkpoint_manager:
                    self.checkpoint_manager.save_agent_result(ctx.task_id, "report", report_result)

            ctx.status = "complete"
            ctx.completed_at = time.monotonic()

            if self.checkpoint_manager:
                self.checkpoint_manager.mark_complete(ctx.task_id, f"Processed {len(ctx.all_files)} files")

            root_span.set_attribute("swarm.status", "complete")
            root_span.set_attribute("swarm.elapsed_seconds", ctx.elapsed_seconds())

            swarm_result = _build_swarm_result(ctx, report_result)

            # Phase 4: Risk Management
            if self.risk_management_enabled:
                swarm_result = self._run_risk_analysis(
                    swarm_result, ctx,
                    generate_report=generate_risk_report,
                    report_path=report_output_path,
                )

            return swarm_result

    def _run_risk_analysis(
        self,
        swarm_result: SwarmResult,
        ctx: SwarmContext,
        generate_report: bool = False,
        report_path: str | Path | None = None,
    ) -> SwarmResult:
        """Run risk analysis and optionally generate Word report."""
        try:
            with tracer.start_as_current_span("risk_analysis"):
                logger.info(f"[Swarm {ctx.task_id}] Running risk analysis...")

                # Generate risks
                engine = RiskScoringEngine(language=self.report_language)
                risks = engine.generate_all_risks(swarm_result)

                # Build registry
                registry = RiskRegistry(
                    well_name=ctx.well_name,
                    pad_name=ctx.pad,
                )
                registry.add_risks(risks)
                swarm_result.risk_registry = registry

                summary = registry.get_summary()
                logger.info(
                    f"[Swarm {ctx.task_id}] Risk analysis complete: "
                    f"{summary['total_risks']} risks "
                    f"({summary['critical_count']} critical, {summary['high_count']} high)"
                )

                # Generate Word report if requested
                if generate_report:
                    try:
                        from .report_generator import ReportGenerator

                        if report_path is None:
                            well_slug = (ctx.well_name or "unknown").replace(" ", "_")
                            report_path = Path(f"risk_report_{well_slug}_{ctx.task_id}.docx")

                        generator = ReportGenerator(language=self.report_language)
                        output = generator.generate(swarm_result, registry, report_path)
                        swarm_result.risk_report_path = str(output)
                        logger.info(f"[Swarm {ctx.task_id}] Risk report generated: {output}")
                    except ImportError as e:
                        logger.warning(f"Cannot generate Word report: {e}")
                    except Exception as e:
                        logger.error(f"Failed to generate risk report: {e}")

        except Exception as e:
            logger.error(f"Risk analysis failed: {e}")

        return swarm_result

    def _restore_context_from_checkpoint(self, ctx: SwarmContext) -> None:
        if not self.checkpoint_manager:
            return
        saved_results = self.checkpoint_manager.load_agent_results(ctx.task_id)
        for domain, result_dict in saved_results.items():
            try:
                ctx.agent_results[domain] = AgentResult(**{
                    k: v for k, v in result_dict.items()
                    if k in AgentResult.__dataclass_fields__
                })
            except Exception as exc:
                logger.warning(f"Failed to restore agent result for {domain}: {exc}")

    def _load_cached_result(self, ctx: SwarmContext) -> SwarmResult:
        saved_results = self.checkpoint_manager.load_agent_results(ctx.task_id)
        for domain, result_dict in saved_results.items():
            try:
                ctx.agent_results[domain] = AgentResult(**{
                    k: v for k, v in result_dict.items()
                    if k in AgentResult.__dataclass_fields__
                })
            except Exception:
                pass
        report_result = ctx.agent_results.get("report")
        if not report_result:
            report_result = AgentResult(
                agent_name="ReportAgent", domain="report", status="success",
                summary="[Loaded from checkpoint]"
            )
        swarm_result = _build_swarm_result(ctx, report_result)

        # Re-run risk analysis on cached result
        if self.risk_management_enabled:
            swarm_result = self._run_risk_analysis(swarm_result, ctx)

        return swarm_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _update_context_from_manifest(ctx: SwarmContext, manifest: list[dict]) -> None:
    for item in manifest:
        for field_name in ("well_name", "api", "operator", "field", "pad"):
            val = item.get(field_name)
            if val and not getattr(ctx, field_name, None):
                setattr(ctx, field_name, val)


def _build_swarm_result(ctx: SwarmContext, report_result: AgentResult) -> SwarmResult:
    succeeded = sum(1 for r in ctx.agent_results.values() if r.status in ("success", "partial"))
    failed = sum(1 for r in ctx.agent_results.values() if r.status == "error")
    cross_flags = report_result.extracted_data.get("cross_domain_flags", [])
    all_flags = report_result.quality_flags or []

    return SwarmResult(
        task_id=ctx.task_id, status=ctx.status, well_name=ctx.well_name, api=ctx.api,
        files_processed=len(ctx.all_files), agents_succeeded=succeeded, agents_failed=failed,
        elapsed_seconds=ctx.elapsed_seconds(),
        agent_results={k: v.to_dict() for k, v in ctx.agent_results.items()},
        unified_report=report_result.summary, quality_flags=all_flags, cross_domain_flags=cross_flags,
    )
