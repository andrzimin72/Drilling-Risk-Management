"""
DLIS / LIS Log Container Parser
Parses DLIS and LIS binary well log container files using the `dlisio` library.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

try:
    import dlisio
    HAS_DLISIO = True
except ImportError:
    HAS_DLISIO = False

class DlisParser:
    """Parse DLIS and LIS well log containers."""
    def extract_text(self, path: Path) -> str:
        if not HAS_DLISIO:
            return f"[dlisio not installed — cannot parse {path.suffix.upper()} file]"
        try:
            summary_lines = []
            with dlisio.dlis(str(path)) as files:
                for f in files:
                    summary_lines.append(f"File: {f.fileheader}")
                    for origin in f.origins:
                        summary_lines.append(f"  Origin: {origin.name}, Well: {origin.well_name}")
                    for frame in f.frames:
                        summary_lines.append(f"  Frame: {frame.name}, Channels: {len(frame.channels)}")
            return "\n".join(summary_lines)
        except Exception as exc:
            return f"[DLIS READ ERROR: {exc}]"

    def extract_structured(
        self, path: Path, raw_text: str = ""
    ) -> tuple[dict[str, Any], list[dict], list[dict]]:
        if not HAS_DLISIO:
            return (
                {"drilling": {}, "directional": {}, "completions": {}, "logs": {"error": "dlisio library not installed"}, "production": {}},
                [],
                [{"source_section": "dlisio_unavailable", "page_or_depth_range": "", "confidence": 0.0}],
            )
            
        well_info: dict[str, Any] = {}
        channels: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        quality_notes: list[str] = []
        
        try:
            with dlisio.dlis(str(path)) as files:
                for f in files:
                    for origin in f.origins:
                        well_info.update({
                            "well_name": str(origin.well_name or "").strip() or None,
                            "field": str(origin.field_name or "").strip() or None,
                            "company": str(origin.company or "").strip() or None,
                            "file_set_name": str(f.fileheader.name or "").strip() or None,
                        })
                    for channel in f.channels:
                        ch = {
                            "name": str(channel.name), "long_name": str(channel.long_name or ""),
                            "units": str(channel.units or ""), "dimension": list(channel.dimension),
                            "axis": [str(a) for a in (channel.axis or [])],
                        }
                        try:
                            data = channel.curves()
                            if data is not None and len(data) > 0:
                                import numpy as np
                                flat = data.flatten()
                                valid = flat[~np.isnan(flat.astype(float, casting="safe"))]
                                if len(valid) > 0:
                                    ch["sample_count"] = len(flat)
                                    ch["min"] = float(np.nanmin(valid))
                                    ch["max"] = float(np.nanmax(valid))
                        except Exception:
                            ch["sample_count"] = None
                        channels.append(ch)
                    for frame in list(f.frames)[:1]:
                        try:
                            df = frame.curves()
                            if df is not None and len(df) > 0:
                                import numpy as np
                                cols = list(df.dtype.names or [])
                                sample = df[:min(100, len(df))]
                                rows = [[float(v) if isinstance(v, (int, float, np.floating)) else str(v) for v in row] for row in sample]
                                tables.append({"name": f"frame_{frame.name}_sample", "columns": cols, "rows": rows, "note": f"First {len(rows)} rows of {len(df)} total"})
                        except Exception:
                            pass
        except Exception as exc:
            quality_notes.append(f"DLIS_PARSE_ERROR: {exc}")
            
        extracted: dict[str, Any] = {
            "drilling": {"well_name": well_info.get("well_name"), "company": well_info.get("company")},
            "directional": {}, "completions": {},
            "logs": {"well_info": well_info, "channels": channels, "channel_count": len(channels)},
            "production": {},
        }
        references = [{"source_section": "DLIS_origins", "page_or_depth_range": "", "confidence": 0.90}]
        return extracted, tables, references
