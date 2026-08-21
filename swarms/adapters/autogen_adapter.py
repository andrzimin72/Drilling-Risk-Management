"""
AutoGen / AG2 Adapter
Builds an AutoGen multi-agent conversation with oil and gas specialist agents.
System prompts updated for global (Metric/Russian) operations.
"""
from __future__ import annotations
from typing import Any

try:
    import autogen
    HAS_AUTOGEN = True
except ImportError:
    try:
        import ag2 as autogen
        HAS_AUTOGEN = True
    except ImportError:
        HAS_AUTOGEN = False

def _make_oilgas_functions() -> dict[str, Any]:
    import json
    from pathlib import Path

    def extract_drilling(file_path: str) -> str:
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        extracted, _, _ = PdfReportParser().extract_structured(Path(file_path))
        return json.dumps(extracted.get("drilling", {}), default=str, indent=2)

    def parse_las(file_path: str, gr_cutoff: float = 75.0, rt_cutoff: float = 10.0) -> str:
        from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser
        extracted, _, _ = LasParser(gr_cutoff=gr_cutoff, rt_cutoff=rt_cutoff, max_table_rows=None).extract_structured(Path(file_path))
        return json.dumps(extracted.get("logs", {}), default=str, indent=2)

    def detect_file(file_path: str) -> str:
        from skills.oil_and_gas_data_manager.skill import detect_file_type
        return json.dumps(detect_file_type(Path(file_path)), default=str)

    def run_sanity_checks(extracted_json: str) -> str:
        from skills.oil_and_gas_data_manager.skill import run_sanity_checks
        return json.dumps({"flags": run_sanity_checks(json.loads(extracted_json))})

    return {
        "extract_drilling_data": {"func": extract_drilling, "description": "Extract drilling KPIs (Imperial or Metric)"},
        "parse_las_file": {"func": parse_las, "description": "Parse LAS file with configurable cutoffs"},
        "detect_oil_gas_file_type": {"func": detect_file, "description": "Detect file type"},
        "run_engineering_sanity_checks": {"func": run_sanity_checks, "description": "Validate extracted values"},
    }

def build_oilgas_autogen_swarm(
    file_paths: list[str],
    llm_config: dict | None = None,
    well_context: dict | None = None,
) -> tuple[Any, Any]:
    if not HAS_AUTOGEN:
        raise ImportError("Install AutoGen: pip install pyautogen or ag2")

    default_llm = llm_config or {"config_list": [{"model": "gpt-4o", "api_key": "YOUR_API_KEY"}], "temperature": 0}
    functions = _make_oilgas_functions()
    files_str = ", ".join(file_paths)
    context_str = str(well_context or {})

    system_base = (
        "You are an expert petroleum engineer. "
        "You handle global datasets, including US Imperial and Russian Metric (Gazprom Neft) units. "
        "Always use function calls to extract data — never fabricate engineering values. "
        f"Files available: {files_str}. Context: {context_str}."
    )

    orchestrator = autogen.AssistantAgent(
        name="OilGasOrchestrator",
        llm_config={**default_llm, "functions": [
            {"name": "detect_oil_gas_file_type", "description": functions["detect_oil_gas_file_type"]["description"],
             "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}
        ]},
        system_message=system_base + " You are the orchestrator. Detect files, delegate to specialists, and synthesize.",
    )

    drilling_agent = autogen.AssistantAgent(
        name="DrillingAgent",
        llm_config={**default_llm, "functions": [
            {"name": "extract_drilling_data", "description": functions["extract_drilling_data"]["description"],
             "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
            {"name": "run_engineering_sanity_checks", "description": functions["run_engineering_sanity_checks"]["description"],
             "parameters": {"type": "object", "properties": {"extracted_json": {"type": "string"}}, "required": ["extracted_json"]}}
        ]},
        system_message=system_base + " You are the drilling specialist. Extract KPIs and run sanity checks.",
    )

    logs_agent = autogen.AssistantAgent(
        name="LogsAgent",
        llm_config={**default_llm, "functions": [
            {"name": "parse_las_file", "description": functions["parse_las_file"]["description"],
             "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "gr_cutoff": {"type": "number"}, "rt_cutoff": {"type": "number"}}, "required": ["file_path"]}}
        ]},
        system_message=system_base + " You are the petrophysics specialist. Parse logs and identify pay zones.",
    )

    user_proxy = autogen.UserProxyAgent(
        name="UserProxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=12,
        is_termination_msg=lambda x: "FINAL REPORT COMPLETE" in str(x.get("content", "")),
        function_map={k: v["func"] for k, v in functions.items()},
    )

    groupchat = autogen.GroupChat(
        agents=[orchestrator, drilling_agent, logs_agent, user_proxy],
        messages=[], max_round=15, speaker_selection_method="round_robin",
    )
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=default_llm)
    return manager, user_proxy
