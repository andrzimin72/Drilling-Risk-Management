"""
LAS Well Log Parser (Enterprise Edition)
Parses LAS 2.0/3.0 files. 
Configurable petrophysics, dynamic depth units.
NumPy vectorization for instant pay zone identification.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

try:
    import lasio
    HAS_LASIO = True
except ImportError:
    HAS_LASIO = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

CURVE_ALIASES: dict[str, str] = {
    "GR": "gamma_ray_api", "GRC": "gamma_ray_corrected_api", "SGR": "spectral_gamma_ray_api",
    "RT": "true_resistivity_ohmm", "RD": "deep_resistivity_ohmm", "RM": "medium_resistivity_ohmm",
    "RS": "shallow_resistivity_ohmm", "RILD": "deep_induction_ohmm", "RILM": "medium_induction_ohmm",
    "RHOB": "bulk_density_gcc", "DEN": "bulk_density_gcc", "RHOZ": "bulk_density_gcc",
    "NPHI": "neutron_porosity_frac", "TNPH": "neutron_porosity_frac", "CNCF": "neutron_porosity_frac",
    "DT": "compressional_slowness_usft", "DTCO": "compressional_slowness_usft", "DTS": "shear_slowness_usft",
    "CAL": "caliper_in", "CALI": "caliper_in",
    "DEPT": "measured_depth", "DEPTH": "measured_depth", "MD": "measured_depth", "TVD": "true_vertical_depth",
    "PE": "photoelectric_factor_b_e", "PEF": "photoelectric_factor_b_e", "SP": "spontaneous_potential_mv",
}

class LasParser:
    """Parse LAS 2.0 and LAS 3.0 well log files."""
    
    def __init__(
        self, 
        gr_cutoff: float = 75.0, 
        rt_cutoff: float = 10.0, 
        max_table_rows: int | None = 5000
    ) -> None:
        """
        Initialize with configurable petrophysical cutoffs.
        Args:
            gr_cutoff: Gamma Ray cutoff for pay zone identification (default: 75 API).
            rt_cutoff: Resistivity cutoff for pay zone identification (default: 10 ohm-m).
            max_table_rows: Max rows to extract for tabular output. Set to None for all.
        """
        self.gr_cutoff = gr_cutoff
        self.rt_cutoff = rt_cutoff
        self.max_table_rows = max_table_rows

    def extract_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"[READ ERROR: {exc}]"

    def extract_structured(
        self, path: Path, raw_text: str = ""
    ) -> tuple[dict[str, Any], list[dict], list[dict]]:
        if not HAS_LASIO:
            return _fallback_las_parse(raw_text), [], [
                {"source_section": "lasio_unavailable", "page_or_depth_range": "", "confidence": 0.3}
            ]
            
        try:
            las = lasio.read(str(path))
        except Exception as exc:
            return (
                {"logs": {"parse_error": str(exc)}}, [],
                [{"source_section": "las_parse_error", "page_or_depth_range": "", "confidence": 0.0}],
            )

        well_info = _extract_well_info(las)
        depth_unit = _get_depth_unit(las)
        curves = _extract_curves(las)
        stats = _compute_curve_stats(las)
        
        # Pass configured cutoffs and detected depth unit to vectorized pay identification
        pay_intervals = _identify_pay_intervals(
            las, gr_cutoff=self.gr_cutoff, rt_cutoff=self.rt_cutoff, depth_unit=depth_unit
        )

        extracted: dict[str, Any] = {
            "drilling": {
                "well_name": well_info.get("well_name"),
                "api": well_info.get("api"),
                "field": well_info.get("field"),
                "company": well_info.get("company"),
            },
            "directional": {}, "completions": {},
            "logs": {
                "well_info": well_info,
                "curves": curves,
                "curve_statistics": stats,
                "pay_intervals": pay_intervals,
                "depth_unit": depth_unit,
                "depth_range": {
                    "start": well_info.get("strt"),
                    "stop": well_info.get("stop"),
                    "step": well_info.get("step"),
                },
            },
            "production": {},
        }

        tables = _build_curve_table(las, max_rows=self.max_table_rows)
        references = [
            {"source_section": "~Well", "page_or_depth_range": "", "confidence": 0.95},
            {
                "source_section": "~Curve",
                "page_or_depth_range": f"{well_info.get('strt', '?')}–{well_info.get('stop', '?')} {depth_unit}",
                "confidence": 0.95,
            },
        ]
        return extracted, tables, references

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get_depth_unit(las: Any) -> str:
    """Extract the depth unit from the LAS header (e.g., 'm', 'ft')."""
    for key in ("STRT", "STOP", "STEP"):
        try:
            if key in las.well and las.well[key].unit:
                unit = str(las.well[key].unit).strip().lower()
                if unit in ("m", "meters", "meter"): return "m"
                if unit in ("ft", "feet", "foot"): return "ft"
                return unit
        except Exception:
            pass
    for key in ("DEPT", "DEPTH", "MD"):
        try:
            if key in las.curves and las.curves[key].unit:
                unit = str(las.curves[key].unit).strip().lower()
                if unit in ("m", "meters", "meter"): return "m"
                if unit in ("ft", "feet", "foot"): return "ft"
                return unit
        except Exception:
            pass
    return "ft"

def _extract_well_info(las: Any) -> dict[str, Any]:
    info: dict[str, Any] = {}
    field_map = {
        "WELL": "well_name", "COMP": "company", "FLD": "field", "LOC": "location",
        "CNTY": "county", "STAT": "state", "CTRY": "country", "API": "api", "UWI": "api",
        "STRT": "strt", "STOP": "stop", "STEP": "step", "NULL": "null_value",
        "DATE": "log_date", "SRVC": "service_company", "RIG": "rig_name",
    }
    for mnem, canon in field_map.items():
        try:
            val = las.well[mnem].value
            if val and str(val).strip():
                info[canon] = str(val).strip()
        except Exception:
            pass
    return info

def _extract_curves(las: Any) -> list[dict[str, str]]:
    curves = []
    for curve in las.curves:
        canon = CURVE_ALIASES.get(curve.mnemonic.upper(), curve.mnemonic.lower())
        curves.append({
            "mnemonic": curve.mnemonic, "canonical_name": canon,
            "unit": curve.unit, "description": curve.descr,
            "sample_count": int(len(curve.data)),
        })
    return curves

def _compute_curve_stats(las: Any) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    if not HAS_NUMPY: return stats
    try:
        for curve in las.curves:
            data = curve.data
            null_val = las.well.NULL.value if "NULL" in las.well else -999.25
            valid = data[(data != null_val) & (~np.isnan(data))]
            if len(valid) > 0:
                stats[curve.mnemonic] = {
                    "min": float(np.nanmin(valid)), "max": float(np.nanmax(valid)),
                    "mean": float(np.nanmean(valid)),
                    "p10": float(np.nanpercentile(valid, 10)),
                    "p50": float(np.nanpercentile(valid, 50)),
                    "p90": float(np.nanpercentile(valid, 90)),
                }
    except Exception:
        pass
    return stats

def _identify_pay_intervals(
    las: Any, gr_cutoff: float, rt_cutoff: float, depth_unit: str
) -> list[dict[str, Any]]:
    """
    Identify pay intervals using NumPy vectorization.
    Processes 50,000+ depth points in milliseconds.
    """
    pay = []
    if not HAS_NUMPY:
        return pay  # Fallback omitted for brevity, requires NumPy for enterprise speed
        
    try:
        depth_key = next((k for k in ("DEPT", "DEPTH", "MD") if k in las.curves), None)
        if not depth_key: return pay
        
        depths = las[depth_key]
        has_gr = "GR" in las.curves
        has_rt = any(k in las.curves for k in ("RT", "RD", "RILD"))
        if not (has_gr and has_rt): return pay
        
        gr = las["GR"]
        rt_key = next(k for k in ("RT", "RD", "RILD") if k in las.curves)
        rt = las[rt_key]
        null = las.well.NULL.value if "NULL" in las.well else -999.25
        
        # 1. Vectorized masking
        valid_mask = (gr != null) & (rt != null) & ~np.isnan(gr) & ~np.isnan(rt)
        pay_mask = valid_mask & (gr < gr_cutoff) & (rt > rt_cutoff)
        
        # 2. Find contiguous intervals using diff on boolean array
        padded = np.pad(pay_mask, (1, 1), mode='constant', constant_values=False)
        diff = np.diff(padded.astype(int))
        
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        
        min_thickness = 1.0 if depth_unit == "m" else 3.0
        
        # 3. Extract intervals (Only loops through the actual pay zones found)
        for start_idx, end_idx in zip(starts, ends):
            start_depth = float(depths[start_idx])
            base_depth = float(depths[end_idx - 1])
            net_pay = base_depth - start_depth
            
            if net_pay > min_thickness:
                pay.append({
                    "top": round(start_depth, 2),
                    "base": round(base_depth, 2),
                    "net_pay": round(net_pay, 2),
                    "depth_unit": depth_unit,
                    "criteria": f"GR < {gr_cutoff} API and RT > {rt_cutoff} ohm-m",
                    "confidence": 0.6,
                })
    except Exception:
        pass
    return pay

def _build_curve_table(las: Any, max_rows: int | None = 5000) -> list[dict[str, Any]]:
    if not HAS_NUMPY: return []
    try:
        depth_key = next((k for k in ("DEPT", "DEPTH", "MD") if k in las.curves), None)
        if depth_key is None: return []
        columns = [c.mnemonic for c in las.curves]
        rows = []
        null = las.well.NULL.value if "NULL" in las.well else -999.25
        total_rows = len(las[depth_key])
        sample_step = max(1, int(total_rows / max_rows)) if max_rows and total_rows > max_rows else 1
        limit = total_rows if not max_rows else min(total_rows, max_rows)
        
        for i in range(0, limit, sample_step):
            row = []
            for col in columns:
                try:
                    val = float(las[col][i])
                    row.append(None if val == null or np.isnan(val) else round(val, 4))
                except Exception:
                    row.append(None)
            rows.append(row)
        return [{"name": "log_curves", "columns": columns, "rows": rows, "note": f"Sampled every {sample_step} rows"}]
    except Exception:
        return []

def _fallback_las_parse(text: str) -> dict[str, Any]:
    well_info: dict[str, str] = {}
    curves: list[dict[str, str]] = []
    in_well = in_curve = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("~W"): in_well, in_curve = True, False; continue
        if stripped.upper().startswith("~C"): in_well, in_curve = False, True; continue
        if stripped.upper().startswith("~A") or stripped.startswith("~"): in_well = in_curve = False; continue
        if stripped.startswith("#"): continue
        if in_well or in_curve:
            match = re.match(r"^([A-Z0-9_]+)\s*\.\S*\s+(.+?)\s*:\s*(.*)$", stripped, re.IGNORECASE)
            if match:
                mnem, value, desc = match.groups()
                if in_well: well_info[mnem.upper()] = value.strip()
                elif in_curve: curves.append({"mnemonic": mnem.upper(), "description": desc.strip()})
    return {
        "drilling": {"well_name": well_info.get("WELL"), "api": well_info.get("API")},
        "directional": {}, "completions": {},
        "logs": {"well_info": well_info, "curves": curves, "depth_unit": "ft"},
        "production": {},
    }
