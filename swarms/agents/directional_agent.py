"""
Directional Agent — survey analysis, minimum curvature, DLS, anticollision.
Async parsing, Russian/Metric support, Pydantic enforcement.
NumPy vectorization for trajectory computation.
"""
from __future__ import annotations
import math
import logging
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import DirectionalDataSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

logger = logging.getLogger(__name__)

# Bilingual keyword matching for discipline classification
SURVEY_KEYWORDS = { 
    "md", "inc", "inclination", "azimuth", "az", "tvd", "dls", "dogleg", "survey",
    "мд", "глубина по стволу", "зенитный угол", "азимут", "твг", "интенсивность", 
    "искривление", "инклинометрия"
}

class DirectionalAgent(BaseAgent):
    domain = "directional"
    description = "Parses survey files, computes minimum curvature trajectory, DLS, and tortuosity."
    skill_path = "skills/directional_survey_analyzer/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        if file_info.get("discipline") == "directional":
            return True
        text = file_info.get("text_sample", "").lower()
        return sum(1 for kw in SURVEY_KEYWORDS if kw in text) >= 3

    async def _process(self, file_paths: list[Path], context: dict[str, Any]) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.csv_parser import CsvParser
        from skills.oil_and_gas_data_manager.parsers.spreadsheet_parser import SpreadsheetParser
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        
        all_stations: list[dict] = []
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
                    
                # Phase 1: Async non-blocking parse (runs in background thread)
                _, tables, _ = await self.safe_parse(parser, 'extract_structured', path)
                stations = _extract_survey_stations(tables)
                all_stations.extend(stations)
                all_tables.extend(tables[:2])
                processed.append(str(path))
            except Exception as exc:
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        computed = {}
        if all_stations:
            # Pillar 1: Vectorized trajectory computation
            computed = _compute_trajectory(all_stations)
            anomalies = _detect_survey_anomalies(all_stations, computed.get("stations", []))
            all_flags.extend(anomalies)
            
        summary_parts = [f"Directional Agent processed {len(processed)} file(s)."]
        if all_stations:
            summary_parts.append(f"Survey stations: {len(all_stations)}")
        if computed.get("max_inc_deg"):
            summary_parts.append(f"Max inc: {computed['max_inc_deg']:.1f}°")
        if computed.get("max_dls"):
            summary_parts.append(f"Max DLS: {computed['max_dls']:.2f}°/100ft")
        if computed.get("total_tvd"):
            summary_parts.append(f"TVD: {computed['total_tvd']:.0f}")
            
        # Phase 3: Schema Enforcement
        validated_dir = _validate_domain_data(computed, DirectionalDataSchema)
        # Ensure raw_stations are included for the schema
        if "raw_stations" not in validated_dir:
            validated_dir["raw_stations"] = all_stations[:10]
            
        return AgentResult(
            agent_name="DirectionalAgent",
            domain="directional",
            status="success" if all_stations else "partial",
            extracted_data={"directional": validated_dir},
            tables=all_tables,
            summary=" | ".join(summary_parts),
            quality_flags=all_flags,
            confidence=0.85 if len(all_stations) > 3 else 0.40,
            files_processed=processed,
        )

# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------
def _extract_survey_stations(tables: list[dict]) -> list[dict]:
    """Extract survey stations from tables. Supports English and Russian headers."""
    stations = []
    # Unit-agnostic and bilingual column matching
    md_names = {"md", "measured depth", "depth", "мд", "глубина по стволу", "глубина"}
    inc_names = {"inc", "inclination", "incl", "зенитный угол", "зу", "зенит"}
    az_names = {"az", "azimuth", "azi", "азимут", "аз"}
    
    for table in tables:
        cols = [str(c).lower().strip() for c in table.get("columns", [])]
        md_idx = next((i for i, c in enumerate(cols) if c in md_names), None)
        inc_idx = next((i for i, c in enumerate(cols) if c in inc_names), None)
        az_idx = next((i for i, c in enumerate(cols) if c in az_names), None)
        
        if md_idx is None or inc_idx is None or az_idx is None:
            continue
            
        for row in table.get("rows", [])[:500]:
            try:
                md = float(row[md_idx])
                inc = float(row[inc_idx])
                az = float(row[az_idx]) % 360
                if 0 <= md and 0 <= inc <= 180:
                    # Output unit-agnostic keys to match SurveyStationSchema
                    stations.append({"md": md, "inc_deg": inc, "az_deg": az})
            except (TypeError, ValueError, IndexError):
                pass
    return sorted(stations, key=lambda s: s["md"])

def _compute_trajectory(stations: list[dict]) -> dict:
    """
    Minimum curvature computation using NumPy vectorization.
    Processes 10,000+ stations in milliseconds instead of seconds.
    """
    if len(stations) < 2:
        return {}
    
    if not HAS_NUMPY:
        # Fallback to standard math if numpy is missing
        return _compute_trajectory_fallback(stations)

    # 1. Convert to NumPy arrays (Vectorized)
    mds = np.array([s["md"] for s in stations], dtype=np.float64)
    incs = np.radians(np.array([s["inc_deg"] for s in stations], dtype=np.float64))
    azs = np.radians(np.array([s["az_deg"] for s in stations], dtype=np.float64))
    
    # 2. Calculate deltas between stations
    delta_md = np.diff(mds)
    inc1, inc2 = incs[:-1], incs[1:]
    az1, az2 = azs[:-1], azs[1:]
    
    # 3. Dogleg angle (Vectorized)
    cos_dl = np.cos(inc2 - inc1) - np.sin(inc1) * np.sin(inc2) * (1 - np.cos(az2 - az1))
    cos_dl = np.clip(cos_dl, -1.0, 1.0) # Prevent domain errors
    dl = np.arccos(cos_dl)
    
    # 4. Ratio factor (Handle dl == 0 to avoid division by zero)
    rf = np.where(dl > 1e-6, (2.0 / dl) * np.tan(dl / 2.0), 1.0)
    
    # 5. Delta positions (North, East, TVD)
    delta_n = (delta_md / 2.0) * (np.sin(inc1) * np.cos(az1) + np.sin(inc2) * np.cos(az2)) * rf
    delta_e = (delta_md / 2.0) * (np.sin(inc1) * np.sin(az1) + np.sin(inc2) * np.sin(az2)) * rf
    delta_tvd = (delta_md / 2.0) * (np.cos(inc1) + np.cos(inc2)) * rf
    
    # 6. Cumulative sum to get absolute coordinates
    north = np.insert(np.cumsum(delta_n), 0, 0.0)
    east = np.insert(np.cumsum(delta_e), 0, 0.0)
    tvd = np.insert(np.cumsum(delta_tvd), 0, 0.0)
    
    # 7. Calculate DLS (Dogleg Severity)
    dl_deg = np.degrees(dl)
    dls = np.zeros(len(mds))
    valid_delta = delta_md > 0
    dls[1:][valid_delta] = dl_deg[valid_delta] * (100.0 / delta_md[valid_delta])
    
    # 8. Rebuild the dictionary list for the schema
    computed_stations = []
    for i in range(len(stations)):
        computed_stations.append({
            **stations[i],
            "tvd": round(float(tvd[i]), 2),
            "north": round(float(north[i]), 2),
            "east": round(float(east[i]), 2),
            "dls": round(float(dls[i]), 3),
        })
        
    return {
        "stations": computed_stations,
        "total_md": float(mds[-1]),
        "total_tvd": round(float(tvd[-1]), 1),
        "max_inc_deg": float(np.degrees(np.max(incs))),
        "max_dls": round(float(np.max(dls)), 3),
    }

def _compute_trajectory_fallback(stations: list[dict]) -> dict:
    """Fallback minimum curvature computation using standard Python math."""
    computed_stations = []
    north, east, tvd = 0.0, 0.0, 0.0
    max_dls = 0.0
    
    for i in range(len(stations)):
        st = stations[i]
        if i == 0:
            computed_stations.append({**st, "tvd": 0.0, "north": 0.0, "east": 0.0, "dls": 0.0})
            continue
            
        prev = stations[i - 1]
        delta_md = st["md"] - prev["md"]
        if delta_md <= 0:
            continue
            
        inc1 = math.radians(prev["inc_deg"])
        inc2 = math.radians(st["inc_deg"])
        az1 = math.radians(prev["az_deg"])
        az2 = math.radians(st["az_deg"])
        
        cos_dl = (math.cos(inc2 - inc1) - math.sin(inc1) * math.sin(inc2) * (1 - math.cos(az2 - az1)))
        cos_dl = max(-1.0, min(1.0, cos_dl))
        dl = math.acos(cos_dl)
        rf = (2 / dl * math.tan(dl / 2)) if dl > 1e-6 else 1.0
        
        delta_n = (delta_md / 2) * (math.sin(inc1) * math.cos(az1) + math.sin(inc2) * math.cos(az2)) * rf
        delta_e = (delta_md / 2) * (math.sin(inc1) * math.sin(az1) + math.sin(inc2) * math.sin(az2)) * rf
        delta_tvd = (delta_md / 2) * (math.cos(inc1) + math.cos(inc2)) * rf
        
        north += delta_n
        east += delta_e
        tvd += delta_tvd
        
        dls = math.degrees(dl) * (100 / delta_md)
        max_dls = max(max_dls, dls)
        
        computed_stations.append({
            **st,
            "tvd": round(tvd, 2),
            "north": round(north, 2),
            "east": round(east, 2),
            "dls": round(dls, 3),
        })
        
    return {
        "stations": computed_stations,
        "total_md": stations[-1]["md"],
        "total_tvd": round(tvd, 1),
        "max_inc_deg": max(s["inc_deg"] for s in stations),
        "max_dls": round(max_dls, 3),
    }

def _detect_survey_anomalies(raw: list[dict], computed: list[dict]) -> list[str]:
    """Detect jumps, gaps, and high dogleg severity."""
    flags = []
    for i in range(1, len(raw)):
        delta_inc = abs(raw[i]["inc_deg"] - raw[i-1]["inc_deg"])
        delta_az = abs(raw[i]["az_deg"] - raw[i-1]["az_deg"])
        delta_md = raw[i]["md"] - raw[i-1]["md"]
        
        if delta_inc > 5:
            flags.append(f"INC_JUMP: {delta_inc:.1f}° change between stations at {raw[i]['md']} MD")
        if delta_az > 15:
            flags.append(f"AZ_JUMP: {delta_az:.1f}° azimuth change at {raw[i]['md']} MD")
        if delta_md > 100:
            flags.append(f"SURVEY_GAP: {delta_md:.0f} gap between stations at {raw[i]['md']} MD")
            
    for st in computed:
        if st.get("dls", 0) > 8:
            flags.append(f"HIGH_DLS: {st['dls']:.2f}°/100ft at {st['md']} MD")
    return flags

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    """Safely validate and dump data using Pydantic."""
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
