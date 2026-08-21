"""
Production Agent
Specialist agent for production test reports and time-series production data.
Async parsing, Russian/Metric support, Pydantic enforcement.
"""
from __future__ import annotations
import statistics
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import ProductionDataSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

PRODUCTION_KEYWORDS = {
    "oil rate", "gas rate", "water rate", "bopd", "mcfd", "bwpd",
    "production test", "separator", "choke", "gor", "water cut",
    "decline", "ip30", "ip90", "eur",
    "дебит нефти", "дебит газа", "дебит воды", "газовый фактор", "обводненность"
}

class ProductionAgent(BaseAgent):
    """Extracts production rates, computes IP metrics, and detects anomalies."""
    domain = "production"
    description = (
        "Parses production test reports and time-series data. Extracts oil/gas/water rates, "
        "pressures, GOR, water cut, and IP30/IP90 averages. Flags anomalous behavior."
    )
    skill_path = "skills/production_data_analyst/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        if file_info.get("discipline") == "production":
            return True
        text = file_info.get("text_sample", "").lower()
        return sum(1 for kw in PRODUCTION_KEYWORDS if kw in text) >= 2

    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        from skills.oil_and_gas_data_manager.parsers.spreadsheet_parser import SpreadsheetParser
        from skills.oil_and_gas_data_manager.parsers.csv_parser import CsvParser
        
        all_tests: list[dict] = []
        all_production: dict[str, Any] = {}
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
                prod = extracted.get("production", {})
                if prod:
                    all_tests.append({**prod, "source_file": path.name})
                    all_production.update({k: v for k, v in prod.items() if v is not None})
                    
                ts_data = _extract_time_series(tables)
                if ts_data:
                    all_production["time_series"] = ts_data
                all_tables.extend(tables[:3])
                processed.append(str(path))
            except Exception as exc:  # noqa: BLE001
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        ip_metrics = _compute_ip_metrics(all_production.get("time_series", []))
        if ip_metrics:
            all_production["ip_metrics"] = ip_metrics
            
        anomalies = _detect_anomalies(all_production)
        all_flags.extend(anomalies)
        all_production["production_tests"] = all_tests
        
        # Phase 3: Schema Enforcement
        validated_prod = _validate_domain_data(all_production, ProductionDataSchema)
        
        summary = _build_summary(validated_prod, ip_metrics, processed)
        return AgentResult(
            agent_name="ProductionAgent",
            domain="production",
            status="success" if validated_prod else "partial",
            extracted_data={"production": validated_prod},
            tables=all_tables,
            summary=summary,
            quality_flags=all_flags,
            confidence=0.75 if validated_prod else 0.20,
            files_processed=processed,
        )

def _extract_time_series(tables: list[dict]) -> list[dict]:
    ts_rows: list[dict] = []
    # Support English and Russian date/rate headers
    date_col_names = {"date", "month", "period", "timestamp", "дата", "месяц"}
    rate_col_names = {"oil", "qo", "bopd", "oil rate", "gas", "qg", "mcfd", "water", "qw",
                      "дебит", "нефть", "газ", "вода"}
    for table in tables:
        cols = [str(c).lower().strip() for c in table.get("columns", [])]
        has_date = any(c in date_col_names for c in cols)
        has_rate = any(any(r in c for r in rate_col_names) for c in cols)
        if not (has_date and has_rate):
            continue
        col_map = {c: i for i, c in enumerate(cols)}
        for row in table.get("rows", [])[:365]:
            if not row:
                continue
            row_dict: dict[str, Any] = {}
            for col_key, col_idx in col_map.items():
                if col_idx < len(row) and row[col_idx] is not None:
                    row_dict[col_key] = row[col_idx]
            if row_dict:
                ts_rows.append(row_dict)
    return ts_rows

def _compute_ip_metrics(time_series: list[dict]) -> dict[str, float]:
    if not time_series:
        return {}
    oil_col = None
    # Check for English and Russian oil rate columns
    for candidate in ("oil", "qo", "bopd", "oil rate", "oil_rate", "дебит нефти", "нефть"):
        if any(candidate in str(k).lower() for k in (time_series[0] if time_series else {}).keys()):
            oil_col = candidate
            break
    if not oil_col:
        for k in (time_series[0] if time_series else {}).keys():
            if "date" not in str(k).lower() and "дата" not in str(k).lower():
                oil_col = k
                break
    if not oil_col:
        return {}
        
    rates: list[float] = []
    for row in time_series:
        for k, v in row.items():
            if oil_col.lower() in str(k).lower():
                try:
                    rates.append(float(v))
                    break
                except (TypeError, ValueError):
                    pass
    if not rates:
        return {}
        
    metrics: dict[str, float] = {}
    for days, label in [(30, "ip30"), (60, "ip60"), (90, "ip90"), (180, "ip180"), (365, "ip365")]:
        if len(rates) >= days:
            metrics[f"{label}_rate"] = round(statistics.mean(rates[:days]), 1)
        elif rates:
            metrics[f"{label}_rate"] = round(statistics.mean(rates), 1)
    if rates:
        metrics["peak_rate"] = round(max(rates), 1)
    return metrics

def _detect_anomalies(production: dict) -> list[str]:
    flags: list[str] = []
    ts = production.get("time_series", [])
    if not ts:
        return flags
    gor_values = []
    for row in ts:
        for k, v in row.items():
            if "gor" in str(k).lower() or "газовый фактор" in str(k).lower():
                try:
                    gor_values.append(float(v))
                except (TypeError, ValueError):
                    pass
    if len(gor_values) > 6:
        first_half_avg = statistics.mean(gor_values[:len(gor_values)//2])
        second_half_avg = statistics.mean(gor_values[len(gor_values)//2:])
        if first_half_avg > 0 and (second_half_avg - first_half_avg) / first_half_avg > 0.50:
            flags.append(f"GOR_BREAKTHROUGH: GOR increased {(second_half_avg/first_half_avg - 1)*100:.0f}% over production history")
    return flags

def _build_summary(prod: dict, ip: dict, processed: list[str]) -> str:
    parts = [f"Production Agent processed {len(processed)} file(s)."]
    tests = prod.get("production_tests", [])
    if tests:
        parts.append(f"Production tests: {len(tests)}")
    if prod.get("oil_rate_bopd") or prod.get("oil_rate_t_day"):
        rate = prod.get("oil_rate_bopd") or prod.get("oil_rate_t_day")
        parts.append(f"Latest oil rate: {rate}")
    if ip.get("ip30_rate"):
        parts.append(f"IP30: {ip['ip30_rate']}")
    if ip.get("ip90_rate"):
        parts.append(f"IP90: {ip['ip90_rate']}")
    if ip.get("peak_rate"):
        parts.append(f"Peak: {ip['peak_rate']}")
    return " | ".join(parts)

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
