"""
Oil and Gas Data Manager — main entry point.
Orchestrates file detection, routing, parsing, normalization,
project matching, and output assembly.
Phase 1 & 2: Bilingual (EN/RU) keywords, unit-agnostic sanity checks, Russian entity extraction.
Pillar 3: OpenTelemetry tracing integration.
"""
from __future__ import annotations
import json
import logging
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any

from .parsers.csv_parser import CsvParser
from .parsers.docx_parser import DocxParser
from .parsers.dlis_parser import DlisParser
from .parsers.las_parser import LasParser
from .parsers.pdf_reports import PdfReportParser
from .parsers.spreadsheet_parser import SpreadsheetParser
from .schemas.extraction_schema import ExtractionOutput
from .schemas.project_match_schema import ProjectContext, ProjectMatcher

# Pillar 3: Telemetry integration
from .telemetry import get_tracer, get_status_class

logger = logging.getLogger(__name__)
tracer = get_tracer("skill")
Status, StatusCode = get_status_class()

# ---------------------------------------------------------------------------
# Phase 1: Bilingual Keyword Dictionaries (English & Russian)
# ---------------------------------------------------------------------------
DRILLING_KEYWORDS = {
    # English
    "daily drilling report", "ddr", "morning report", "operations summary",
    "bit record", "npt", "weight on bit", "standpipe pressure",
    "mud weight", "rate of penetration", "rop", "bha",
    # Russian
    "ежсуточный отчет", "еср", "утренний отчет", "отчет о бурении",
    "долото", "нпт", "нагрузка на крюке", "вес на крюке", "осевая нагрузка",
    "давление на стояке", "плотность бурового раствора", "механическая скорость",
    "рейс", "кпбт", "забой", "бурильная колонна",
}
COMPLETION_KEYWORDS = {
    # English
    "frac", "stage", "cluster", "perforation", "proppant",
    "plug and perf", "toe sleeve", "stimulation", "pump schedule",
    "slurry rate", "isip", "treating pressure",
    # Russian
    "грп", "гидроразрыв", "стадия", "кластер", "перфорация", "проппант",
    "цементирование", "стимуляция", "закачка", "устьевое давление",
}
PRODUCTION_KEYWORDS = {
    # English
    "oil rate", "gas rate", "water rate", "production test",
    "allocation", "separator test", "choke", "gor", "water cut",
    "tubing pressure", "casing pressure",
    # Russian
    "дебит нефти", "дебит газа", "дебит воды", "испытание",
    "газовый фактор", "обводненность", "буферное давление", "затрубное давление",
}
SURVEY_KEYWORDS = {
    # English
    "survey station", "inclination", "azimuth", "dogleg",
    "measured depth", "true vertical depth", "northing", "easting",
    "trajectory", "minimum curvature",
    # Russian
    "инклинометрия", "зенитный угол", "азимут", "интенсивность",
    "искривление", "глубина по стволу", "истинная вертикальная глубина",
    "отход", "траектория", "минимальная кривизна", "твг", "мд",
}

# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------
LAS_MAGIC = b"~Version"
DLIS_MAGIC = b"DLIS"

def detect_file_type(path: Path) -> dict[str, Any]:
    """
    Determine the oil and gas file type using extension, MIME, magic bytes,
    and content inspection.
    Returns a dict with keys: extension, mime_type, detected_type, confidence.
    """
    with tracer.start_as_current_span("detect_file_type") as span:
        span.set_attribute("file.path", str(path))
        ext = path.suffix.lower()
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"

        # LAS detection
        if ext == ".las":
            return _make_detection("las_well_log", ext, mime_type, 0.99)
        # DLIS / LIS detection
        if ext in {".dlis", ".lis"}:
            return _make_detection("dlis_log_container", ext, mime_type, 0.99)
        # Check magic bytes for binary formats
        try:
            with open(path, "rb") as fh:
                header = fh.read(256)
            if LAS_MAGIC in header:
                return _make_detection("las_well_log", ext, mime_type, 0.95)
            if DLIS_MAGIC in header and ext in {".bin", ""}:
                return _make_detection("dlis_log_container", ext, mime_type, 0.80)
        except OSError:
            pass
        # Spreadsheet
        if ext in {".xlsx", ".xls", ".ods"}:
            return _make_detection("spreadsheet", ext, mime_type, 0.99)
        # CSV
        if ext == ".csv":
            return _make_detection("csv_data", ext, mime_type, 0.99)
        # JSON
        if ext == ".json":
            return _make_detection("json_export", ext, mime_type, 0.99)
        # Word document
        if ext in {".docx", ".doc"}:
            return _make_detection("word_document", ext, mime_type, 0.99)
        # PDF
        if ext == ".pdf" or mime_type == "application/pdf":
            return _make_detection("pdf_document", ext, mime_type, 0.90)
        # Plain text
        if ext in {".txt", ".log", ".dat"}:
            return _make_detection("text_file", ext, mime_type, 0.85)
        # WITSML
        if ext == ".xml":
            try:
                text_sample = path.read_text(errors="ignore")[:2000]
                if "witsml" in text_sample.lower() or "WITSML" in text_sample:
                    return _make_detection("witsml_export", ext, mime_type, 0.90)
            except OSError:
                pass
            return _make_detection("xml_document", ext, mime_type, 0.70)
        
        result = _make_detection("unknown", ext, mime_type, 0.10)
        span.set_attribute("file.detected_type", result["detected_type"])
        return result

def _make_detection(
    detected_type: str,
    ext: str,
    mime_type: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "extension": ext,
        "mime_type": mime_type,
        "detected_type": detected_type,
        "confidence": confidence,
    }

def classify_discipline(text: str) -> tuple[str, str, float]:
    """
    Infer discipline and document type from text content using keyword matching.
    Supports both English and Russian oilfield terminology.
    Returns (discipline, document_type, confidence).
    """
    text_lower = text.lower()
    def score(keywords: set[str]) -> float:
        hits = sum(1 for kw in keywords if kw in text_lower)
        return hits / len(keywords) if keywords else 0

    scores = {
        "drilling": score(DRILLING_KEYWORDS),
        "completions": score(COMPLETION_KEYWORDS),
        "production": score(PRODUCTION_KEYWORDS),
        "directional": score(SURVEY_KEYWORDS),
    }
    best_discipline, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score < 0.05:
        return "unknown", "unknown", 0.1

    doc_type_map = {
        "drilling": "daily_drilling_report",
        "completions": "completion_design",
        "production": "production_test_report",
        "directional": "directional_survey",
    }
    return best_discipline, doc_type_map[best_discipline], min(best_score * 5, 0.95)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def route_to_parser(
    path: Path,
    detection: dict[str, Any],
    text_sample: str = "",
) -> Any:
    """Return the appropriate parser instance for a given file."""
    detected_type = detection["detected_type"]
    if detected_type == "las_well_log":
        return LasParser()
    if detected_type in {"dlis_log_container"}:
        return DlisParser()
    if detected_type == "spreadsheet":
        return SpreadsheetParser()
    if detected_type == "csv_data":
        return CsvParser()
    if detected_type == "word_document":
        return DocxParser()
    if detected_type == "pdf_document":
        return PdfReportParser()
    if detected_type in {"text_file", "unknown"}:
        return PdfReportParser()  # Fallback text parser
    return PdfReportParser()

# ---------------------------------------------------------------------------
# Phase 1 & 2: Unit-Agnostic Sanity Checks (Imperial & Metric)
# ---------------------------------------------------------------------------
SANITY_CHECKS: list[tuple[str, Any, Any, str]] = [
    # Imperial
    ("mud_weight_ppg", 6.0, 22.0, "mud_weight outside expected 6–22 ppg range"),
    ("rop_ft_hr", 0.0, 1000.0, "ROP exceeds 1000 ft/hr — verify units"),
    ("depth_ft", 0.0, 50000.0, "Depth exceeds 50,000 ft — verify units"),
    # Metric
    ("mud_weight_sg", 1.0, 2.8, "mud_weight outside expected 1.0–2.8 sg range"),
    ("rop_m_hr", 0.0, 100.0, "ROP exceeds 100 m/hr — verify units"),
    ("depth_m", 0.0, 15000.0, "Depth exceeds 15,000 m — verify units"),
    # Universal
    ("inclination_deg", 0.0, 180.0, "inclination value exceeds 180 degrees"),
    ("dogleg_severity", 0.0, 20.0, "dogleg severity > 20 deg/100ft — flag for review"),
    ("treating_pressure_psi", 0.0, 20000.0, "treating pressure > 20,000 psi"),
    ("treating_pressure_kpa", 0.0, 140000.0, "treating pressure > 140,000 kPa"),
]

def run_sanity_checks(extracted: dict[str, Any]) -> list[str]:
    """Run engineering sanity checks and return a list of warning strings."""
    flags = []
    flat = _flatten_dict(extracted)
    for field_key, min_val, max_val, message in SANITY_CHECKS:
        for key, value in flat.items():
            if field_key in key.lower():
                try:
                    num = float(value)
                    if not (min_val <= num <= max_val):
                        flags.append(f"SANITY: {message} (value={num}, field={key})")
                except (TypeError, ValueError):
                    pass

    # TVD > MD check (Unit agnostic)
    tvd = flat.get("tvd") or flat.get("true_vertical_depth") or flat.get("tvd_m") or flat.get("tvd_ft")
    md = flat.get("md") or flat.get("measured_depth") or flat.get("md_m") or flat.get("md_ft")
    if tvd and md:
        try:
            if float(tvd) > float(md):
                flags.append("SANITY: TVD exceeds MD — impossible geometry")
        except (TypeError, ValueError):
            pass
    return flags

def _flatten_dict(d: dict, prefix: str = "") -> dict[str, Any]:
    result = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_dict(v, full_key))
        else:
            result[full_key] = v
    return result

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def process_files(
    file_paths: list[str | Path],
    project_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Process one or more oil and gas files.
    Args:
        file_paths: List of file paths to process.
        project_context: Optional dict with project metadata for matching.
    Returns:
        List of extraction output dicts (one per file).
    """
    with tracer.start_as_current_span("process_files") as span:
        span.set_attribute("files.count", len(file_paths))
        
        ctx = ProjectContext(**(project_context or {})) if project_context else None
        matcher = ProjectMatcher(ctx) if ctx else None
        results = []
        
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                results.append({
                    "file_info": {"filename": path.name},
                    "quality_flags": [f"FILE_NOT_FOUND: {path}"],
                })
                continue

            with tracer.start_as_current_span(f"process_file:{path.name}") as file_span:
                file_span.set_attribute("file.path", str(path))
                
                detection = detect_file_type(path)
                file_span.set_attribute("file.detected_type", detection["detected_type"])
                
                parser = route_to_parser(path, detection)
                raw_text = ""
                try:
                    raw_text = parser.extract_text(path)
                except Exception as exc:
                    raw_text = ""
                    detection["parse_error"] = str(exc)

                discipline, doc_type, disc_confidence = classify_discipline(raw_text)
                file_span.set_attribute("file.discipline", discipline)

                extracted = {}
                tables = []
                references = []
                try:
                    extracted, tables, references = parser.extract_structured(path, raw_text)
                except Exception as exc:
                    extracted = {}
                    tables = []
                    references = [{"source_section": "parse_error", "page_or_depth_range": "", "confidence": 0.0}]

                quality_flags = run_sanity_checks(extracted)
                entity_context = _extract_entity_context(raw_text, extracted)
                project_match = {}
                if matcher:
                    project_match = matcher.score(entity_context)

                output = ExtractionOutput(
                    project_match=project_match,
                    file_info={
                        "filename": path.name,
                        "file_type": detection["detected_type"],
                        "mime_type": detection["mime_type"],
                        "discipline": discipline,
                        "document_type": doc_type,
                    },
                    entity_context=entity_context,
                    extracted_data=extracted,
                    tables=tables,
                    references=references,
                    quality_flags=quality_flags,
                )
                results.append(output.model_dump())
                file_span.set_attribute("file.quality_flags_count", len(quality_flags))
        
        span.set_attribute("results.count", len(results))
        return results

def _extract_entity_context(text: str, extracted: dict[str, Any]) -> dict[str, str]:
    """
    Pull well/asset identifiers from text and extracted data.
    Supports US API/UWI and Russian well/pad naming conventions.
    """
    context: dict[str, str] = {}

    # US API/UWI pattern
    api_match = re.search(r"\b(\d{2}-\d{3}-\d{5}-\d{4}(?:-\d{2})?)\b", text)
    if api_match:
        context["api"] = api_match.group(1)

    # Phase 1: Russian Well/Cluster/Pad patterns
    well_ru_match = re.search(r"(?:скважина|скв\.?)\s*№?\s*([A-Za-z0-9А-Яа-я\-]+)", text, re.IGNORECASE)
    if well_ru_match and "api" not in context:
        context["well_name"] = well_ru_match.group(1)

    pad_ru_match = re.search(r"(?:куст|куст\.?)\s*№?\s*([A-Za-z0-9А-Яа-я\-]+)", text, re.IGNORECASE)
    if pad_ru_match:
        context["pad"] = pad_ru_match.group(1)

    # Date patterns (English and Russian)
    date_match = re.search(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|"
        r"\d{1,2}[.-]\d{1,2}[.-]\d{2,4}|"
        r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if date_match:
        context["report_date"] = date_match.group(1)

    # Pull from extracted if available
    for field in ("well_name", "operator", "field", "basin", "pad", "api", "report_date"):
        drill = extracted.get("drilling", {})
        if isinstance(drill, dict) and field in drill and drill[field]:
            context[field] = str(drill[field])

    return context

# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    
    if len(sys.argv) < 2:
        print("Usage: python skill.py <file1> [file2 ...] [--project '{json}']")
        sys.exit(1)
    
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    project_json = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--project" and i + 2 < len(sys.argv):
            project_json = json.loads(sys.argv[i + 2])
    
    logger.info(f"Processing {len(files)} file(s)...")
    outputs = process_files(files, project_json)
    print(json.dumps(outputs, indent=2, default=str))