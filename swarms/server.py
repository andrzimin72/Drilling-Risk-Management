"""
Oil and Gas Engineering MCP Server
Exposes the oil and gas skill library as MCP (Model Context Protocol) tools.
Compatible with: Claude Code, Cursor, Cline, Continue, and any MCP-enabled agent.
Added metric support and configurable petrophysics to tool schemas.
"""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Add parent directory to path for skill imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

try:
    from fastmcp import FastMCP
    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _tool_detect_file_type(file_path: str) -> dict[str, Any]:
    from skills.oil_and_gas_data_manager.skill import detect_file_type
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    return detect_file_type(path)

def _tool_extract_engineering_data(
    file_paths: list[str],
    project_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from skills.oil_and_gas_data_manager.skill import process_files
    return process_files(file_paths, project_context)

def _tool_parse_las_file(
    file_path: str, 
    gr_cutoff: float = 75.0, 
    rt_cutoff: float = 10.0
) -> dict[str, Any]:
    from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    # Phase 2: Pass configurable cutoffs
    parser = LasParser(gr_cutoff=gr_cutoff, rt_cutoff=rt_cutoff, max_table_rows=None)
    extracted, tables, references = parser.extract_structured(path)
    return {"extracted": extracted, "tables": tables[:3], "references": references}

def _tool_parse_drilling_report(file_path: str) -> dict[str, Any]:
    from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    parser = PdfReportParser()
    raw_text = parser.extract_text(path)
    extracted, tables, references = parser.extract_structured(path, raw_text)
    return {"extracted": extracted, "tables": tables[:5], "references": references}

def _tool_classify_discipline(text_sample: str) -> dict[str, Any]:
    from skills.oil_and_gas_data_manager.skill import classify_discipline
    discipline, doc_type, confidence = classify_discipline(text_sample)
    return {"discipline": discipline, "document_type": doc_type, "confidence": confidence}

def _tool_run_sanity_checks(extracted_data: dict[str, Any]) -> list[str]:
    from skills.oil_and_gas_data_manager.skill import run_sanity_checks
    return run_sanity_checks(extracted_data)

def _tool_get_skill_definition(skill_name: str) -> str:
    skill_map = {
        "oil_and_gas_data_manager": "skills/oil_and_gas_data_manager/SKILL.md",
        "drilling": "skills/drilling_kpi_analyzer/SKILL.md",
        "logs": "skills/well_log_interpreter/SKILL.md",
        "completions": "skills/completion_design_reviewer/SKILL.md",
        "production": "skills/production_data_analyst/SKILL.md",
        "directional": "skills/directional_survey_analyzer/SKILL.md",
        "hse": "skills/hse_incident_tracker/SKILL.md",
    }
    skill_key = skill_name.lower().replace("-", " ").replace(" ", "_")
    rel_path = skill_map.get(skill_key)
    if not rel_path:
        return f"Skill '{skill_name}' not found. Available: {list(skill_map.keys())}"
    root = Path(__file__).parent.parent
    skill_file = root / rel_path
    return skill_file.read_text() if skill_file.exists() else "SKILL.md not found"

# ---------------------------------------------------------------------------
# MCP server — FastMCP (preferred, simpler)
# ---------------------------------------------------------------------------
if HAS_FASTMCP:
    mcp = FastMCP(
        "Oil and Gas Engineering Skills",
        instructions=(
            "An MCP server providing oil and gas engineering data extraction tools. "
            "Supports both Imperial (US) and Metric (Russian/Gazprom Neft) units, "
            "and bilingual (English/Russian) document parsing."
        ),
    )

    @mcp.tool()
    def detect_file_type(file_path: str) -> dict:
        """Detect the oil and gas file type from a file path."""
        return _tool_detect_file_type(file_path)

    @mcp.tool()
    def extract_engineering_data(
        file_paths: list[str],
        project_name: str = "",
        well_name: str = "",
        api: str = "",
    ) -> list[dict]:
        """Full oil and gas data extraction pipeline (Bilingual & Unit-Agnostic)."""
        ctx = {}
        if project_name: ctx["project_name"] = project_name
        if well_name: ctx["well_name"] = well_name
        if api: ctx["api"] = api
        return _tool_extract_engineering_data(file_paths, ctx or None)

    @mcp.tool()
    def parse_las_file(
        file_path: str, 
        gr_cutoff: float = 75.0, 
        rt_cutoff: float = 10.0
    ) -> dict:
        """
        Parse a LAS 2.0/3.0 well log file. 
        Supports configurable petrophysical cutoffs for different geological basins.
        """
        return _tool_parse_las_file(file_path, gr_cutoff, rt_cutoff)

    @mcp.tool()
    def parse_drilling_report(file_path: str) -> dict:
        """Extract engineering entities from a PDF/DOCX drilling report (English or Russian)."""
        return _tool_parse_drilling_report(file_path)

    @mcp.tool()
    def classify_discipline(text_sample: str) -> dict:
        """Classify the engineering discipline from a text sample."""
        return _tool_classify_discipline(text_sample)

    @mcp.tool()
    def run_sanity_checks(extracted_data: dict) -> list:
        """Run engineering sanity checks (supports both Imperial and Metric limits)."""
        return _tool_run_sanity_checks(extracted_data)

    @mcp.tool()
    def get_skill_definition(skill_name: str) -> str:
        """Return the full SKILL.md definition for a named skill."""
        return _tool_get_skill_definition(skill_name)

    # Swarm tools with Metric & Petrophysics support
    @mcp.tool()
    async def run_well_performance_swarm(
        file_paths: list[str],
        well_name: str = "",
        api: str = "",
        lateral_length_ft: float = 0,
        lateral_length_m: float = 0,  # Phase 1: Metric support
        gr_cutoff: float = 75.0,      # Phase 2: Configurable petrophysics
        rt_cutoff: float = 10.0,
    ) -> dict:
        """Run the Well Performance Swarm. Supports metric units and custom cutoffs."""
        from swarms.patterns.well_performance_swarm import WellPerformanceSwarm
        swarm = WellPerformanceSwarm(
            well_name=well_name or None, api=api or None,
            lateral_length_ft=lateral_length_ft or None,
            lateral_length_m=lateral_length_m or None,
            gr_cutoff=gr_cutoff, rt_cutoff=rt_cutoff,
            verbose=False,
        )
        result = await swarm.run(file_paths)
        return result.to_dict()

    app = mcp

# ---------------------------------------------------------------------------
# Fallback: raw MCP SDK server (Simplified for brevity, uses same tools)
# ---------------------------------------------------------------------------
elif HAS_MCP:
    server = Server("oil-and-gas-skills")
    # ... (Standard MCP SDK tool registration would go here, mirroring FastMCP) ...
    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    app = None
else:
    app = None

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if HAS_FASTMCP:
        mcp.run()
    elif HAS_MCP:
        import asyncio
        asyncio.run(main())
    else:
        print("ERROR: Install MCP server dependencies: pip install fastmcp")
        sys.exit(1)
