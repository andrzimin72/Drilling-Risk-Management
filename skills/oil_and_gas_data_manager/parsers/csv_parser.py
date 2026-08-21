"""
CSV / Delimited Data Parser
Handles CSV and TSV exports. Detects delimiter, infers units, and classifies domain.
Bilingual (English/Russian) header classification.
"""
from __future__ import annotations
import csv
import io
import re
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "drilling": ["depth", "rop", "wob", "rpm", "torque", "spp", "mud", "flow", "bit", "hookload",
                 "глубина", "механическая скорость", "нагрузка", "обороты", "давление", "плотность", "долото"],
    "directional": ["inclination", "azimuth", "md", "tvd", "northing", "easting", "dogleg",
                    "зенитный угол", "азимут", "глубина по стволу", "твг", "интенсивность"],
    "production": ["oil", "gas", "water", "choke", "gor", "watercut", "tubing", "casing",
                   "дебит", "нефть", "газ", "вода", "обводненность", "газовый фактор"],
    "petrophysics": ["gr", "gamma", "resistivity", "rhob", "density", "nphi", "neutron", "sonic",
                     "гамма", "сопротивление", "плотность", "нейтронка", "акустика"],
}

class CsvParser:
    """Parse CSV/TSV engineering data files."""
    def extract_text(self, path: Path) -> str:
        try: return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc: return f"[READ ERROR: {exc}]"

    def extract_structured(
        self, path: Path, raw_text: str = ""
    ) -> tuple[dict[str, Any], list[dict], list[dict]]:
        text = raw_text or self.extract_text(path)
        if not text.strip():
            return ({"drilling": {}, "directional": {}, "completions": {}, "logs": {}, "production": {}}, [],
                    [{"source_section": "empty_file", "page_or_depth_range": "", "confidence": 0.0}])
                    
        delimiter = _detect_delimiter(text)
        headers, rows, unit_row_idx = _parse_csv_content(text, delimiter)
        if not headers:
            return ({"drilling": {}, "directional": {}, "completions": {}, "logs": {}, "production": {}}, [],
                    [{"source_section": "no_headers_detected", "page_or_depth_range": "", "confidence": 0.2}])
                    
        domain = _classify_domain(headers)
        units = _extract_units(text, headers, delimiter, unit_row_idx)
        stats = _compute_column_stats(headers, rows)
        header_with_units = _annotate_headers(headers, units)
        extracted = _map_to_domain(domain, headers, stats)
        
        tables = [{"name": path.stem, "type": domain, "columns": header_with_units, "rows": rows[:500], "total_rows": len(rows), "delimiter": repr(delimiter), "column_stats": stats}]
        references = [{"source_section": f"csv_file:{path.name}", "page_or_depth_range": f"{len(rows)} data rows", "confidence": 0.85, "domain": domain}]
        return extracted, tables, references

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", "\t", "|", ";")}
        return max(counts, key=lambda k: counts[k])

def _parse_csv_content(text: str, delimiter: str) -> tuple[list[str], list[list[Any]], int | None]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = list(reader)
    if not all_rows: return [], [], None
    headers = [h.strip() for h in all_rows[0]]
    unit_row_idx = None
    if len(all_rows) > 1:
        unit_pattern = re.compile(r"^(?:ft|m|ppg|psi|rpm|bbl|gal|lb|deg|api|bopd|mcfd|in|mm|kg|kN|kPa|hr|min|sec|us/ft|ohm\.m|g/cc|г/см3|м/ч|т/сут|л/с|м3)$", re.IGNORECASE)
        row2 = [str(v).strip() for v in all_rows[1]]
        unit_matches = sum(1 for v in row2 if unit_pattern.match(v))
        if unit_matches > len(headers) * 0.3:
            unit_row_idx = 1
            data_start = 2
        else:
            data_start = 1
    else:
        data_start = 1
        
    data_rows = []
    for row in all_rows[data_start:]:
        if any(v.strip() for v in row):
            cleaned = []
            for v in row:
                v = v.strip()
                try:
                    # Handle Russian decimal comma (e.g., "10,5")
                    v_clean = v.replace(",", ".") if v.count(",") == 1 and v.replace(",", "").replace(".", "").isdigit() else v
                    cleaned.append(float(v_clean) if "." in v_clean else int(v_clean))
                except (ValueError, TypeError):
                    cleaned.append(v if v else None)
            data_rows.append(cleaned)
    return headers, data_rows, unit_row_idx

def _classify_domain(headers: list[str]) -> str:
    headers_lower = " ".join(h.lower() for h in headers)
    best_domain, best_score = "unknown", 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in headers_lower)
        if score > best_score: best_score, best_domain = score, domain
    return best_domain if best_score > 0 else "unknown"

def _extract_units(text: str, headers: list[str], delimiter: str, unit_row_idx: int | None) -> dict[str, str]:
    units: dict[str, str] = {}
    for h in headers:
        match = re.search(r"[\(\[]\s*([a-zA-Z0-9/_.а-яА-Я]+)\s*[\)\]]", h)
        if match:
            base_name = re.sub(r"\s*[\(\[].*?[\)\]]", "", h).strip()
            units[base_name] = match.group(1)
    if unit_row_idx is not None:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for i, row in enumerate(reader):
            if i == unit_row_idx:
                for header, unit in zip(headers, row):
                    if unit.strip(): units[header] = unit.strip()
                break
    return units

def _annotate_headers(headers: list[str], units: dict[str, str]) -> list[str]:
    return [f"{h} ({units[h]})" if h in units else h for h in headers]

def _compute_column_stats(headers: list[str], rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for col_idx, header in enumerate(headers):
        values = [float(row[col_idx]) for row in rows if col_idx < len(row) and isinstance(row[col_idx], (int, float)) and row[col_idx] == row[col_idx]]
        if values:
            stats[header] = {"count": len(values), "min": min(values), "max": max(values), "mean": round(sum(values) / len(values), 4)}
    return stats

def _map_to_domain(domain: str, headers: list[str], stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {"drilling": {}, "directional": {}, "completions": {}, "logs": {}, "production": {}}
    headers_lower = {h.lower(): h for h in headers}
    
    mappings = {
        "drilling": [
            ("rop_ft_hr", ["rop", "rate of penetration"]), ("rop_m_hr", ["механическая скорость", "мс"]),
            ("wob_klbs", ["wob", "weight on bit"]), ("wob_tons", ["нагрузка на долото", "осевая нагрузка"]),
            ("rpm", ["rpm", "rotary speed", "обороты"]),
            ("mud_weight_ppg", ["mw", "mud weight"]), ("mud_weight_sg", ["плотность раствора", "пвр"]),
            ("depth_ft", ["depth", "md"]), ("depth_m", ["глубина", "глубина по стволу"]),
        ],
        "directional": [
            ("measured_depth_ft", ["md", "measured depth", "depth"]), ("measured_depth_m", ["глубина по стволу", "мгт"]),
            ("inclination_deg", ["inc", "inclination", "зенитный угол", "зу"]),
            ("azimuth_deg", ["az", "azimuth", "азимут"]),
            ("tvd_ft", ["tvd", "true vertical depth"]), ("tvd_m", ["твг", "истинная вертикальная глубина"]),
            ("dogleg_severity", ["dls", "dogleg", "интенсивность"]),
        ],
        "production": [
            ("oil_rate_bopd", ["oil", "oil rate", "qo"]), ("oil_rate_t_day", ["дебит нефти", "нефть"]),
            ("gas_rate_mcfd", ["gas", "gas rate", "qg"]), ("gas_rate_m3_day", ["дебит газа", "газ"]),
            ("water_rate_bwpd", ["water", "water rate", "qw"]), ("water_rate_m3_day", ["дебит воды", "вода"]),
            ("choke_size", ["choke"]),
        ],
        "petrophysics": [
            ("gamma_ray_api", ["gr", "gamma ray", "gamma", "гамма"]),
            ("deep_resistivity_ohmm", ["rt", "rd", "resistivity", "сопротивление"]),
            ("bulk_density_gcc", ["rhob", "density", "плотность"]),
            ("neutron_porosity_frac", ["nphi", "neutron", "нейтронка"]),
        ],
    }
    
    for canon, variants in mappings.get(domain, []):
        for v in variants:
            if v in headers_lower:
                col_stats = stats.get(headers_lower[v])
                if col_stats:
                    result[domain if domain != "petrophysics" else "logs"][canon] = col_stats
                break
    return result
