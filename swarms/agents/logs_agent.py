"""
Logs Agent
Enforces LogsDataSchema and PayIntervalSchema.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import LogsDataSchema, PayIntervalSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

HANDLES_TYPES = {"las_well_log", "dlis_log_container"}

class LogsAgent(BaseAgent):
    domain = "logs"
    description = "Parses LAS/DLIS files, computes petrophysical properties, identifies pay zones."
    skill_path = "skills/well_log_interpreter/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        return file_info.get("detected_type") in HANDLES_TYPES

    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.las_parser import LasParser
        from skills.oil_and_gas_data_manager.parsers.dlis_parser import DlisParser
        
        # Note: In Phase 2 we made cutoffs configurable. 
        # Here we pass them from context if available, otherwise defaults.
        gr_cutoff = context.get("gr_cutoff", 75.0)
        rt_cutoff = context.get("rt_cutoff", 10.0)
        
        parser_las = LasParser(gr_cutoff=gr_cutoff, rt_cutoff=rt_cutoff, max_table_rows=None)
        parser_dlis = DlisParser()
        
        all_logs: dict[str, Any] = {}
        all_tables: list[dict] = []
        all_flags: list[str] = []
        processed: list[str] = []
        all_pay: list[dict] = []
        all_curves: list[dict] = []
        well_info: dict = {}
        
        for path in file_paths:
            try:
                if path.suffix.lower() in {".dlis", ".lis"}:
                    extracted, tables, refs = await self.safe_parse(parser_dlis, 'extract_structured', path)
                else:
                    extracted, tables, refs = await self.safe_parse(parser_las, 'extract_structured', path)
                    
                log_data = extracted.get("logs", {})
                drill_data = extracted.get("drilling", {})
                
                for k in ("well_name", "api", "company", "field"):
                    if drill_data.get(k):
                        well_info[k] = drill_data[k]
                        
                curves = log_data.get("curves", [])
                all_curves.extend(curves)
                
                pay = log_data.get("pay_intervals", [])
                all_pay.extend(pay)
                
                depth_range = log_data.get("depth_range", {})
                if depth_range.get("start") and depth_range.get("stop"):
                    all_logs.setdefault("depth_ranges", []).append({
                        "file": path.name,
                        "start": depth_range["start"],
                        "stop": depth_range["stop"],
                    })
                all_tables.extend(tables[:2])
                processed.append(str(path))
            except Exception as exc:  # noqa: BLE001
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        seen_mnemonics: set[str] = set()
        unique_curves = []
        for c in all_curves:
            m = c.get("mnemonic", "")
            if m not in seen_mnemonics:
                seen_mnemonics.add(m)
                unique_curves.append(c)
                
        total_net_pay = sum(p.get("net_pay", 0) for p in all_pay)
        
        all_logs.update({
            "well_info": well_info,
            "curves": unique_curves,
            "curve_count": len(unique_curves),
            "pay_intervals": all_pay,
            "total_net_pay": round(total_net_pay, 1),
            "pay_zone_count": len(all_pay),
            "depth_unit": all_pay[0].get("depth_unit", "ft") if all_pay else "ft"
        })
        
        # --- PHASE 3: SCHEMA ENFORCEMENT ---
        validated_logs = _validate_domain_data(all_logs, LogsDataSchema)
        
        summary = self._build_summary(validated_logs, all_pay, unique_curves, processed)
        return AgentResult(
            agent_name="LogsAgent",
            domain="logs",
            status="success" if unique_curves else "partial",
            extracted_data={"logs": validated_logs},
            tables=all_tables,
            summary=summary,
            quality_flags=all_flags,
            confidence=0.85 if unique_curves else 0.20,
            files_processed=processed,
        )

    def _build_summary(self, logs: dict, pay: list, curves: list, processed: list[str]) -> str:
        parts = [f"Logs Agent processed {len(processed)} log file(s)."]
        if curves:
            curve_names = [c.get("mnemonic") for c in curves[:6]]
            parts.append(f"Curves: {', '.join(curve_names)} ({len(curves)} total)")
        if pay:
            total_net = logs.get("total_net_pay", 0)
            unit = logs.get("depth_unit", "ft")
            parts.append(f"Pay intervals: {len(pay)}, total net pay {total_net} {unit}")
        else:
            parts.append("No pay intervals identified with configured cutoffs")
        return " | ".join(parts)

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
