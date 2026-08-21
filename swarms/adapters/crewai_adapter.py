"""
CrewAI Adapter
Wraps each specialist agent as a CrewAI Agent with domain-specific tools.
Tasks are now unit-agnostic and bilingual-aware.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

try:
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import BaseTool
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False

if HAS_CREWAI:
    class ExtractDrillingDataTool(BaseTool):
        name: str = "extract_drilling_data"
        description: str = "Extract drilling KPIs (Imperial or Metric/Russian) from a report."
        def _run(self, file_path: str) -> str:
            import json
            from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
            extracted, _, _ = PdfReportParser().extract_structured(Path(file_path))
            return json.dumps(extracted.get("drilling", {}), default=str)

    class ParseLasFileTool(BaseTool):
        name: str = "parse_las_file"
        description: str = "Parse a LAS file. Returns curves, well info, and pay intervals."
        def _run(self, file_path: str) -> str:
            import json
            from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser
            # Using defaults, but the parser itself handles metric depths automatically
            extracted, _, _ = LasParser(max_table_rows=None).extract_structured(Path(file_path))
            return json.dumps(extracted.get("logs", {}), default=str)

    class ParseCompletionSheetTool(BaseTool):
        name: str = "parse_completion_sheet"
        description: str = "Parse completion design sheets (bbls/m3, lbs/tons)."
        def _run(self, file_path: str) -> str:
            import json
            from skills.oil_and_gas_data_manager.parsers.spreadsheet_parser import SpreadsheetParser
            from skills.oil_and_gas_data_manager.parsers.csv_parser import CsvParser
            ext = Path(file_path).suffix.lower()
            parser = CsvParser() if ext == ".csv" else SpreadsheetParser()
            extracted, _, _ = parser.extract_structured(Path(file_path))
            return json.dumps(extracted.get("completions", {}), default=str)

def build_oilgas_crew(file_paths: list[str], well_context: dict | None = None) -> "Crew":
    if not HAS_CREWAI:
        raise ImportError("Install CrewAI: pip install crewai crewai-tools")

    context_str = str(well_context or {})
    files_str = "\n".join(f"  - {f}" for f in file_paths)

    orchestrator = Agent(
        role="Oil & Gas Data Orchestrator",
        goal="Route engineering files to specialists and synthesize findings.",
        backstory="Senior petroleum data engineer. Handles global datasets (US & Russian).",
        tools=[], verbose=True,
    )
    drilling_agent = Agent(
        role="Drilling Engineering Specialist",
        goal="Extract drilling KPIs, NPT, and mud properties from DDRs (English or Russian).",
        backstory="Expert drilling engineer. Recognizes both Imperial (ft/ppg) and Metric (m/g/cm3) units.",
        tools=[ExtractDrillingDataTool()], verbose=True,
    )
    petrophysics_agent = Agent(
        role="Petrophysics & Well Log Specialist",
        goal="Interpret LAS/DLIS logs, identify pay zones, compute properties.",
        backstory="Experienced petrophysicist. Adapts cutoffs based on basin (e.g., Western Siberia vs Permian).",
        tools=[ParseLasFileTool()], verbose=True,
    )
    completions_agent = Agent(
        role="Completions Engineering Specialist",
        goal="Review frac designs, validate proppant schedules (lbs/tons), and flag inconsistencies.",
        backstory="Completions engineer. Handles both US and international completion designs.",
        tools=[ParseCompletionSheetTool()], verbose=True,
    )
    report_agent = Agent(
        role="Engineering Report Writer",
        goal="Synthesize all domain findings into a comprehensive engineering report.",
        backstory="Senior engineering consultant. Translates complex multi-domain data into actionable summaries.",
        tools=[], verbose=True,
    )

    # Tasks (Updated to be Unit-Agnostic)
    routing_task = Task(
        description=f"Detect file types and disciplines for: {files_str}\nContext: {context_str}",
        expected_output="JSON routing manifest.", agent=orchestrator,
    )
    drilling_task = Task(
        description=f"Analyze drilling files: {files_str}\nExtract KPIs (ROP, WOB, Mud Weight) in whatever units are present (ft/hr or m/hr, ppg or sg).",
        expected_output="Structured drilling KPI JSON.", agent=drilling_agent, context=[routing_task],
    )
    logs_task = Task(
        description=f"Parse LAS files: {files_str}\nIdentify pay zones. Note: The parser automatically detects depth units (m or ft) from the LAS header.",
        expected_output="Petrophysical interpretation JSON.", agent=petrophysics_agent, context=[routing_task],
    )
    completions_task = Task(
        description=f"Parse completion sheets: {files_str}\nExtract stage counts, fluid volumes (bbls or m3), and proppant (lbs or tons).",
        expected_output="Completion design JSON.", agent=completions_agent, context=[routing_task],
    )
    synthesis_task = Task(
        description=f"Synthesize findings into a unified report. Context: {context_str}",
        expected_output="Complete unified engineering report.", agent=report_agent, 
        context=[drilling_task, logs_task, completions_task],
    )

    return Crew(
        agents=[orchestrator, drilling_agent, petrophysics_agent, completions_agent, report_agent],
        tasks=[routing_task, drilling_task, logs_task, completions_task, synthesis_task],
        process=Process.sequential, verbose=True,
    )
