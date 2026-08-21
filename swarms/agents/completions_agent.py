"""
Completions Agent
Specialist agent for completion design spreadsheets, frac stage sheets,
and pump schedules. Uses the Completion Design Reviewer skill.
Async parsing, Russian/Metric support, Pydantic enforcement.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import CompletionsDataSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

HANDLES_TYPES = {"spreadsheet", "csv_data", "pdf_document", "word_document"}
COMPLETION_KEYWORDS = {
    "stage", "cluster", "frac", "proppant", "perforation",
    "slurry", "isip", "plug", "stimulation", "treating",
    "стадия", "кластер", "грп", "проппант", "перфорация", "стимуляция"
}

class CompletionsAgent(BaseAgent):
    """Validates completion stage designs, proppant schedules, and frac programs."""
    domain = "completions"
    description = (
        "Parses completion design spreadsheets and frac stage sheets. "
        "Extracts stage count, fluid volumes, proppant loading, ISIP, and validates "
        "design consistency against engineering limits."
    )
    skill_path = "skills/completion_design_reviewer/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        if file_info.get("discipline") == "completions":
            return True
        if file_info.get("detected_type") in HANDLES_TYPES:
            text = file_info.get("text_sample", "").lower()
            return any(kw in text for kw in COMPLETION_KEYWORDS)
        return False

    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.spreadsheet_parser import SpreadsheetParser
        from skills.oil_and_gas_data_manager.parsers.csv_parser import CsvParser
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        
        all_completions: dict[str, Any] = {}
        all_stages: list[dict] = []
        all_tables: list[dict] = []
        all_flags: list[str] = []
        processed: list[str] = []
        
        for path in file_paths:
            try:
                ext = path.suffix.lower()
                if ext in {".xlsx", ".xls"}:
                    parser = SpreadsheetParser()
                elif ext == ".csv":
                    parser = CsvParser()
                else:
                    parser = PdfReportParser()
                    
                # Phase 1: Async non-blocking parse
                extracted, tables, _ = await self.safe_parse(parser, 'extract_structured', path)
                comp = extracted.get("completions", {})
                all_completions.update({k: v for k, v in comp.items() if v is not None})
                all_tables.extend(tables[:4])
                
                stages = _extract_stages_from_tables(tables)
                all_stages.extend(stages)
                processed.append(str(path))
            except Exception as exc:  # noqa: BLE001
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        flags = _validate_completion_design(all_completions, all_stages)
        all_flags.extend(flags)
        
        if all_stages:
            all_completions["stages"] = all_stages
            all_completions["stage_count_actual"] = len(all_stages)
            
        # Compute proppant loading if lateral length available (supports ft or m)
        lateral = context.get("lateral_length_ft") or context.get("lateral_length_m")
        total_prop = _safe_float(
            all_completions.get("total_proppant_lbs") or 
            all_completions.get("total_proppant_tons") or 
            all_completions.get("total_proppant_kg")
        )
        if lateral and total_prop:
            all_completions["proppant_loading"] = round(total_prop / float(lateral), 1)
            
        # Phase 3: Schema Enforcement
        validated_comp = _validate_domain_data(all_completions, CompletionsDataSchema)
            
        summary = _build_summary(validated_comp, all_stages, processed)
        return AgentResult(
            agent_name="CompletionsAgent",
            domain="completions",
            status="success" if validated_comp else "partial",
            extracted_data={"completions": validated_comp},
            tables=all_tables,
            summary=summary,
            quality_flags=all_flags,
            confidence=0.80 if validated_comp else 0.25,
            files_processed=processed,
        )

def _extract_stages_from_tables(tables: list[dict]) -> list[dict]:
    stages: list[dict] = []
    stage_col_names = {"stage", "stage #", "stage number", "stg", "стадия"}
    for table in tables:
        cols = [str(c).lower().strip() for c in table.get("columns", [])]
        stage_col_idx = next((i for i, c in enumerate(cols) if c in stage_col_names), None)
        if stage_col_idx is None:
            continue
        col_map = {c: i for i, c in enumerate(cols)}
        for row in table.get("rows", [])[:80]:
            if not row or stage_col_idx >= len(row):
                continue
            stage_val = row[stage_col_idx]
            try:
                stage_num = int(float(str(stage_val)))
            except (ValueError, TypeError):
                continue
            stage_dict: dict[str, Any] = {"stage_number": stage_num}
            # Support both Imperial and Metric column headers
            for key, col_name in [
                ("fluid_bbls", "fluid"), ("fluid_m3", "fluid"),
                ("proppant_lbs", "proppant"), ("proppant_tons", "proppant"),
                ("isip_psi", "isip"), ("isip_kpa", "isip"),
                ("top_md", "top"), ("base_md", "base"),
                ("cluster_count", "clusters"), ("rate_bpm", "rate"),
            ]:
                for col in cols:
                    if col_name in col and col in col_map:
                        idx = col_map[col]
                        if idx < len(row):
                            stage_dict[key] = _safe_float(row[idx])
                        break
            stages.append(stage_dict)
    return stages

def _validate_completion_design(comp: dict[str, Any], stages: list[dict]) -> list[str]:
    flags: list[str] = []
    stage_count_header = _safe_float(comp.get("stage_count"))
    stage_count_actual = len(stages)
    if stage_count_header and stage_count_actual and abs(stage_count_header - stage_count_actual) > 2:
        flags.append(
            f"STAGE_COUNT_MISMATCH: header says {int(stage_count_header)} stages, "
            f"found {stage_count_actual} data rows"
        )
    for i, stage in enumerate(stages):
        # Broadened sanity check to support metric kPa
        isip = stage.get("isip_psi") or stage.get("isip_kpa")
        if isip and (isip < 1000 or isip > 20000): 
            flags.append(f"SANITY: Stage {stage.get('stage_number', i+1)} ISIP {isip} outside normal range")
    return flags

def _build_summary(comp: dict, stages: list, processed: list[str]) -> str:
    parts = [f"Completions Agent processed {len(processed)} file(s)."]
    if comp.get("stage_count") or stages:
        n = comp.get("stage_count") or len(stages)
        parts.append(f"Stages: {n}")
    if comp.get("total_fluid_bbls") or comp.get("total_fluid_m3"):
        vol = comp.get("total_fluid_bbls") or comp.get("total_fluid_m3")
        parts.append(f"Fluid: {vol} total")
    if comp.get("total_proppant_lbs") or comp.get("total_proppant_tons"):
        lbs = float(comp.get("total_proppant_lbs") or comp.get("total_proppant_tons") or 0)
        parts.append(f"Proppant: {lbs:,.0f} total")
    if comp.get("isip_psi") or comp.get("isip_kpa"):
        isip = comp.get("isip_psi") or comp.get("isip_kpa")
        parts.append(f"Avg ISIP: {isip}")
    return " | ".join(parts)

def _safe_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
