"""
Drilling Agent
Specialist agent for daily drilling reports, morning reports, bit records,
BHA sheets, and WITSML exports.
Async parsing, Russian/Metric support, Pydantic enforcement.
RAG Predictive Risk integration for pad-level NPT warnings.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import DrillingDataSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

HANDLES_TYPES = {"pdf_document", "word_document", "text_file", "witsml_export", "csv_data"}
HANDLES_DISCIPLINES = {"drilling"}

class DrillingAgent(BaseAgent):
    """Extracts drilling KPIs, NPT events, mud properties, and BHA from DDRs."""
    domain = "drilling"
    description = (
        "Parses daily drilling reports and extracts KPIs: ROP, WOB, RPM, mud weight, "
        "standpipe pressure, NPT events, BHA components, and casing points."
    )
    skill_path = "skills/drilling_kpi_analyzer/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        return (
            file_info.get("detected_type") in HANDLES_TYPES
            or file_info.get("discipline") in HANDLES_DISCIPLINES
        )

    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        from skills.oil_and_gas_data_manager.parsers.csv_parser import CsvParser
        from skills.oil_and_gas_data_manager.skill import run_sanity_checks
        
        parser_pdf = PdfReportParser()
        parser_csv = CsvParser()
        all_drilling: dict[str, Any] = {}
        all_tables: list[dict] = []
        all_npt: list[dict] = []
        all_flags: list[str] = []
        processed: list[str] = []
        
        for path in file_paths:
            try:
                if path.suffix.lower() == ".csv":
                    # Phase 1: Async non-blocking parse (runs in background thread)
                    extracted, tables, refs = await self.safe_parse(parser_csv, 'extract_structured', path)
                else:
                    raw = await self.safe_parse(parser_pdf, 'extract_text', path)
                    extracted, tables, refs = await self.safe_parse(parser_pdf, 'extract_structured', path, raw_text=raw)
                    
                drill = extracted.get("drilling", {})
                all_drilling.update({k: v for k, v in drill.items() if v is not None})
                all_tables.extend(tables[:3])
                
                npt = drill.pop("npt_events", []) or []
                all_npt.extend(npt)
                
                flags = run_sanity_checks(extracted)
                all_flags.extend([f"[{path.name}] {f}" for f in flags])
                processed.append(str(path))
            except Exception as exc:  # noqa: BLE001
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        if all_npt:
            all_drilling["npt_events"] = all_npt
            
        npt_total = sum(
            float(e.get("duration_hrs") or 0)
            for e in all_npt
            if e.get("duration_hrs")
        )
        all_drilling["npt_hours"] = npt_total

        # --- PILLAR 2: RAG PREDICTIVE RISK INTEGRATION ---
        try:
            from skills.oil_and_gas_data_manager.rag_risk_advisor import PadRiskAdvisor
            
            pad_name = context.get("pad")
            well_name = context.get("well_name")
            current_depth = _safe_float(
                all_drilling.get("current_depth_m") or 
                all_drilling.get("measured_depth_m") or 
                all_drilling.get("current_depth_ft")
            )
            
            if pad_name and well_name and all_npt:
                advisor = PadRiskAdvisor()
                
                # 1. INGEST: Save this well's NPT events for future wells
                ingested = advisor.ingest_well_npt(pad_name, well_name, all_npt, current_depth)
                if ingested > 0:
                    all_flags.append(f"RAG: Ingested {ingested} NPT events into pad history database.")
                    
                # 2. QUERY: Warn the engineer if this depth has caused issues on this pad before
                if current_depth:
                    # Tolerance: 300m for metric, ~1000ft for imperial
                    tolerance = 300.0 if current_depth < 10000 else 1000.0
                    historical_risks = advisor.query_risks(pad_name, current_depth, depth_tolerance_m=tolerance)
                    if historical_risks:
                        top_risk = historical_risks[0]
                        warning_msg = (
                            f"PREDICTIVE_RISK: Historical data on pad '{pad_name}' shows "
                            f"Well {top_risk['historical_well']} experienced "
                            f"{top_risk['npt_hours']} hrs NPT at {top_risk['historical_depth_m']}m "
                            f"due to: '{top_risk['description'][:100]}'. "
                            f"Recommend reviewing mud properties and wellbore stability."
                        )
                        all_flags.append(warning_msg)
        except ImportError:
            pass # ChromaDB not installed, skip RAG features gracefully
        except Exception as e:
            logger.warning(f"RAG Risk Advisor failed: {e}")

        # --- PHASE 3: SCHEMA ENFORCEMENT ---
        validated_drilling = _validate_domain_data(all_drilling, DrillingDataSchema)
        
        summary = self._build_summary(validated_drilling, all_npt, npt_total, processed)
        return AgentResult(
            agent_name="DrillingAgent",
            domain="drilling",
            status="success" if validated_drilling else "partial",
            extracted_data={"drilling": validated_drilling},
            tables=all_tables,
            summary=summary,
            quality_flags=all_flags,
            confidence=0.80 if validated_drilling else 0.30,
            files_processed=processed,
        )

    def _build_summary(self, drilling: dict, npt_events: list, npt_total: float, processed: list[str]) -> str:
        parts = [f"Drilling Agent processed {len(processed)} file(s)."]
        # Unit-agnostic KPI display
        kpi_fields = ["rop_ft_hr", "rop_m_hr", "wob_klbs", "rpm", "mud_weight_ppg", "mud_weight_sg",
                      "current_depth_ft", "current_depth_m"]
        found_kpis = {k: drilling[k] for k in kpi_fields if drilling.get(k) is not None}
        if found_kpis:
            kpi_str = " | ".join(f"{k.replace('_ft_hr','').replace('_m_hr','').replace('_','').upper()} {v}"
                                  for k, v in found_kpis.items())
            parts.append(f"KPIs: {kpi_str}")
        if npt_events:
            parts.append(f"NPT: {len(npt_events)} event(s), {npt_total:.1f} total hrs")
        casing = drilling.get("casing_points", [])
        if casing:
            parts.append(f"Casing: {len(casing)} string(s) identified")
        return " | ".join(parts)

def _safe_float(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    """Safely validate and dump data using Pydantic."""
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
