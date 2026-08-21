"""
Anthropic Agent SDK Adapter
Builds oil and gas specialist agents using the Anthropic Agent SDK.
Tool schemas now accept metric units and configurable cutoffs.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

OILGAS_TOOLS = [
    {
        "name": "detect_file_type",
        "description": "Detect the oil and gas file type and engineering discipline.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "parse_las_file",
        "description": "Parse a LAS well log file. Supports configurable petrophysical cutoffs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "gr_cutoff": {"type": "number", "description": "Gamma Ray cutoff (default 75 API)"},
                "rt_cutoff": {"type": "number", "description": "Resistivity cutoff (default 10 ohm-m)"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "extract_drilling_data",
        "description": "Extract drilling KPIs from a report. Handles both Imperial and Metric (Russian) units.",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "run_sanity_checks",
        "description": "Validate extracted engineering values against known limits (Unit-agnostic).",
        "input_schema": {
            "type": "object",
            "properties": {"extracted_data_json": {"type": "string"}},
            "required": ["extracted_data_json"],
        },
    },
]

def _execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    if tool_name == "detect_file_type":
        from skills.oil_and_gas_data_manager.skill import detect_file_type
        return json.dumps(detect_file_type(Path(tool_input["file_path"])), default=str)
    elif tool_name == "parse_las_file":
        from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser
        parser = LasParser(
            gr_cutoff=tool_input.get("gr_cutoff", 75.0), 
            rt_cutoff=tool_input.get("rt_cutoff", 10.0),
            max_table_rows=None
        )
        extracted, _, _ = parser.extract_structured(Path(tool_input["file_path"]))
        return json.dumps(extracted.get("logs", {}), default=str)
    elif tool_name == "extract_drilling_data":
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        parser = PdfReportParser()
        extracted, _, _ = parser.extract_structured(Path(tool_input["file_path"]))
        return json.dumps(extracted.get("drilling", {}), default=str)
    elif tool_name == "run_sanity_checks":
        from skills.oil_and_gas_data_manager.skill import run_sanity_checks
        extracted = json.loads(tool_input["extracted_data_json"])
        return json.dumps({"flags": run_sanity_checks(extracted)})
    return json.dumps({"error": f"Unknown tool: {tool_name}"})

def run_claude_oilgas_swarm(
    file_paths: list[str],
    well_context: dict | None = None,
    model: str = "claude-sonnet-4-5",
    api_key: str | None = None,
    max_iterations: int = 20,
) -> dict[str, Any]:
    if not HAS_ANTHROPIC:
        raise ImportError("Install Anthropic SDK: pip install anthropic")
        
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    files_str = "\n".join(f"  - {f}" for f in file_paths)
    context_str = json.dumps(well_context or {}, indent=2)

    system_prompt = """You are an expert petroleum engineer and AI agent orchestrator.
You analyze oil and gas data from global operations, including US Imperial and Russian Metric (Gazprom Neft) datasets.
CRITICAL RULES:
1. Use tools to extract data. NEVER fabricate engineering values.
2. The system automatically handles bilingual (English/Russian) text and unit-agnostic (Imperial/Metric) data.
3. If analyzing Russian documents, look for terms like "Ежсуточный отчет", "Механическая скорость", "Плотность раствора".
4. Apply engineering sanity checks. Flag quality issues explicitly.
5. Synthesize findings into a comprehensive engineering report."""

    user_message = f"""Analyze these oil and gas engineering files:
Files:
{files_str}
Well Context:
{context_str}
Instructions:
1. Detect file types and extract engineering data.
2. Run sanity checks.
3. Produce a comprehensive report with entity context, domain findings, and quality flags.
End your response with: ANALYSIS COMPLETE"""

    messages = [{"role": "user", "content": user_message}]
    tool_calls_log = []
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        response = client.messages.create(
            model=model, max_tokens=8192, system=system_prompt,
            tools=OILGAS_TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        
        if response.stop_reason == "end_turn": break
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result = _execute_tool(block.name, block.input)
                    tool_calls_log.append({"tool": block.name, "input": block.input})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": tool_result})
            messages.append({"role": "user", "content": tool_results})
        else: break

    final_text = ""
    for block in (messages[-1].get("content") if isinstance(messages[-1], dict) else messages[-1]):
        if hasattr(block, "text"): final_text += block.text
        elif isinstance(block, dict) and block.get("type") == "text": final_text += block.get("text", "")

    return {"report": final_text, "tool_calls": tool_calls_log, "iterations": iterations}
