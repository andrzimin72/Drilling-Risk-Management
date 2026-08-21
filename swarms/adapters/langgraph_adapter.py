"""
LangGraph Adapter
Builds a LangGraph state machine where each specialist agent is a node.
State includes metric/cutoff params. Fixed asyncio execution.
"""
from __future__ import annotations
import asyncio
from typing import Any, TypedDict

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

if HAS_LANGGRAPH:
    class OilGasState(TypedDict):
        files: list[str]
        well_context: dict[str, Any]
        file_manifest: list[dict]
        drilling_result: dict
        logs_result: dict
        completions_result: dict
        production_result: dict
        directional_result: dict
        hse_result: dict
        final_report: str
        quality_flags: list[str]
        # Phase 1 & 2 additions
        gr_cutoff: float
        rt_cutoff: float
        lateral_length_m: float | None

    def _run_async(coro):
        """Safely run an async agent from a sync LangGraph node."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # We are inside an existing event loop (e.g. Jupyter, FastAPI)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)

    def data_manager_node(state: OilGasState) -> OilGasState:
        from pathlib import Path
        from swarms.agents.data_manager_agent import DataManagerAgent
        agent = DataManagerAgent(verbose=False)
        result = _run_async(agent.run(state["files"], state["well_context"]))
        state["file_manifest"] = result.extracted_data.get("manifest", [])
        state["well_context"]["_routing"] = result.extracted_data.get("routing", {})
        return state

    def drilling_node(state: OilGasState) -> OilGasState:
        from swarms.agents.drilling_agent import DrillingAgent
        files = state["well_context"].get("_routing", {}).get("drilling", state["files"])
        if not files:
            state["drilling_result"] = {"status": "skipped"}
            return state
        agent = DrillingAgent(verbose=False)
        result = _run_async(agent.run(files, state["well_context"]))
        state["drilling_result"] = result.to_dict()
        state["quality_flags"].extend(result.quality_flags or [])
        return state

    def logs_node(state: OilGasState) -> OilGasState:
        from swarms.agents.logs_agent import LogsAgent
        files = state["well_context"].get("_routing", {}).get("logs", [])
        if not files:
            state["logs_result"] = {"status": "skipped"}
            return state
        # Pass cutoffs from state to context
        ctx = {**state["well_context"], "gr_cutoff": state.get("gr_cutoff", 75.0), "rt_cutoff": state.get("rt_cutoff", 10.0)}
        agent = LogsAgent(verbose=False)
        result = _run_async(agent.run(files, ctx))
        state["logs_result"] = result.to_dict()
        state["quality_flags"].extend(result.quality_flags or [])
        return state

    def report_node(state: OilGasState) -> OilGasState:
        well = state["well_context"].get("well_name", "Unknown Well")
        parts = [f"LANGGRAPH SWARM REPORT — {well}", "=" * 50]
        for domain, key in [("drilling", "drilling_result"), ("logs", "logs_result"), ("completions", "completions_result")]:
            result = state.get(key, {})
            if result and result.get("status") not in ("skipped", None):
                parts.append(f"\n[{domain.upper()}]\n{result.get('summary', 'No summary')}")
        if state.get("quality_flags"):
            parts.append(f"\nQUALITY FLAGS ({len(state['quality_flags'])})")
            parts.extend(f"  {f}" for f in state["quality_flags"][:10])
        state["final_report"] = "\n".join(parts)
        return state

    def build_oilgas_langgraph(files: list[str], well_context: dict | None = None, gr_cutoff: float = 75.0, rt_cutoff: float = 10.0) -> Any:
        if not HAS_LANGGRAPH:
            raise ImportError("Install LangGraph: pip install langgraph")
            
        builder = StateGraph(OilGasState)
        builder.add_node("data_manager", data_manager_node)
        builder.add_node("drilling", drilling_node)
        builder.add_node("logs", logs_node)
        builder.add_node("report", report_node)

        builder.set_entry_point("data_manager")
        builder.add_edge("data_manager", "drilling")
        builder.add_edge("data_manager", "logs")
        builder.add_edge("drilling", "report")
        builder.add_edge("logs", "report")
        builder.add_edge("report", END)

        graph = builder.compile()
        
        initial_state = {
            "files": files,
            "well_context": well_context or {},
            "quality_flags": [],
            "file_manifest": [],
            "drilling_result": {}, "logs_result": {}, "completions_result": {},
            "production_result": {}, "directional_result": {}, "hse_result": {},
            "final_report": "",
            "gr_cutoff": gr_cutoff,
            "rt_cutoff": rt_cutoff,
            "lateral_length_m": None,
        }
        return graph, initial_state
else:
    def build_oilgas_langgraph(*args, **kwargs):
        raise ImportError("Install LangGraph: pip install langgraph")
