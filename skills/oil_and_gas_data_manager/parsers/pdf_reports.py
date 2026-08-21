"""
PDF Report Parser
Extracts text, tables, and engineering entities from oil and gas PDF reports.
Bilingual (EN/RU) and Unit-Agnostic (Imperial/Metric).
Vision LLM Fallback for unreadable/scanned tables.
"""
from __future__ import annotations
import re
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Pillar 2: Try to import vision fallback
try:
    from .vision_fallback import extract_table_with_vision, render_pdf_page_to_image
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

PATTERNS: dict[str, str] = {
    # Identifiers (English & Russian)
    "well_name": r"(?:well\s+name|well|скважина|номер\s+скважины|№\s*скв)[:\s]+([A-Za-z0-9-_#/\sА-Яа-я]{3,40}?)(?:\n|,|API|UWI|куст)",
    "api": r"(?:API|UWI)[:\s#]*(\d{2}-\d{3}-\d{5}(?:-\d{4}(?:-\d{2})?)?)",
    "rig_name": r"(?:rig\s+name|rig|буровая|станок)[:\s]+([A-Za-z0-9-_#\sА-Яа-я]{3,30}?)(?:\n|,|well)",
    "operator": r"(?:operator|company|заказчик|оператор)[:\s]+([A-Za-z0-9\s&.,А-Яа-я]{3,50}?)(?:\n|well|rig)",
    "field": r"(?:field|месторождение)[:\s]+([A-Za-z0-9\s-А-Яа-я]{3,40}?)(?:\n|,|county|basin)",
    "report_date": r"(?:report\s+date|date\s+of\s+report|date|дата\s+отчета|дата)[:\s]+([A-Za-z0-9\s,/-А-Яа-я.]{5,20}?)(?:\n|rig|well)",
    
    # Depths (Imperial & Metric)
    "current_depth_ft": r"(?:current\s+depth|depth\s+at|bit\s+depth|drill\s+depth)[:\s]+([\d,]+\.?\d*)\s*(?:ft|feet)",
    "current_depth_m": r"(?:current\s+depth|depth\s+at|bit\s+depth|drill\s+depth|текущая\s+глубина|глубина\s+забоя|глубина\s+по\s+стволу|глубина)[:\s]+([\d,]+\.?\d*)\s*(?:м|метр|meter|m\b)",
    "measured_depth_ft": r"(?:measured\s+depth|MD)[:\s=]+([\d,]+\.?\d*)\s*(?:ft|feet)",
    "measured_depth_m": r"(?:measured\s+depth|MD|глубина\s+по\s+стволу|МГТ)[:\s=]+([\d,]+\.?\d*)\s*(?:м|метр)",
    "tvd_ft": r"(?:true\s+vertical\s+depth|TVD)[:\s=]+([\d,]+\.?\d*)\s*(?:ft|feet)",
    "tvd_m": r"(?:true\s+vertical\s+depth|TVD|истинная\s+вертикальная\s+глубина|ТВГ)[:\s=]+([\d,]+\.?\d*)\s*(?:м|метр)",
    
    # Drilling parameters (Imperial & Metric)
    "rop_ft_hr": r"(?:rate\s+of\s+penetration|ROP|avg\s+rop)[:\s]+([\d.]+)\s*(?:ft/hr|ft/h)",
    "rop_m_hr": r"(?:rate\s+of\s+penetration|ROP|avg\s+rop|механическая\s+скорость|скорость\s+бурения|МС)[:\s]+([\d.]+)\s*(?:м/ч|м/час|m/hr)",
    "wob_klbs": r"(?:weight\s+on\s+bit|WOB)[:\s]+([\d.]+)\s*(?:klbs?|kips?|klb)",
    "wob_tons": r"(?:weight\s+on\s+bit|WOB|нагрузка\s+на\s+долото|осевая\s+нагрузка|вес\s+на\s+крюке)[:\s]+([\d.]+)\s*(?:т|тонн|тс|tons)",
    "rpm": r"(?:rotary\s+speed|RPM|rotations?|обороты|частота\s+вращения)[:\s]+([\d.]+)\s*(?:rpm|RPM|об/мин)?",
    "spp_psi": r"(?:standpipe\s+pressure|SPP)[:\s]+([\d,]+)\s*(?:psi)",
    "spp_kpa": r"(?:standpipe\s+pressure|SPP|давление\s+на\s+стояке|ДН)[:\s]+([\d,]+)\s*(?:кПа|kPa|МПа|MPa)",
    "flow_rate_gpm": r"(?:flow\s+rate|pump\s+rate|circulation\s+rate|расход\s+раствора)[:\s]+([\d.]+)\s*(?:gpm|l/min|bpm|л/с|л/мин)",
    "mud_weight_ppg": r"(?:mud\s+weight|MW|drilling\s+fluid\s+weight)[:\s]+([\d.]+)\s*(?:ppg|lb/gal)",
    "mud_weight_sg": r"(?:mud\s+weight|MW|drilling\s+fluid\s+weight|плотность\s+раствора|плотность\s+бурового\s+раствора|ПВР)[:\s]+([\d.]+)\s*(?:г/см3|г/см³|sg|g/cm3)",
    
    # Completions
    "stage_count": r"(?:total\s+stages?|number\s+of\s+stages?|stages?\s+completed|количество\s+стадий|всего\s+стадий)[:\s]+(\d+)",
    "total_fluid_bbls": r"(?:total\s+fluid|fluid\s+volume|объем\s+жидкости|жидкость\s+закачки)[:\s]+([\d,]+\.?\d*)\s*(?:bbls?|barrels?|м3|m3)",
    "total_proppant_lbs": r"(?:total\s+proppant|proppant\s+placed|масса\s+проппанта|проппант)[:\s]+([\d,]+\.?\d*)\s*(?:lbs?|tons?|kg|т|кг)",
    "isip_psi": r"(?:ISIP|instantaneous\s+shut.in\s+pressure|давление\s+остановки|МГНТ)[:\s]+([\d,]+)\s*(?:psi|kPa|МПа|MPa)",
    
    # Production
    "oil_rate_bopd": r"(?:oil\s+rate|oil\s+production|дебит\s+нефти|добыча\s+нефти)[:\s]+([\d,]+\.?\d*)\s*(?:bopd|stb/d|bbl/d|т/сут)",
    "gas_rate_mcfd": r"(?:gas\s+rate|gas\s+production|дебит\s+газа|добыча\s+газа)[:\s]+([\d,]+\.?\d*)\s*(?:mcf/d|mscf/d|mcfd|тыс.\s*м3/сут)",
    "water_rate_bwpd": r"(?:water\s+rate|water\s+cut|bwpd|дебит\s+воды|обводненность)[:\s]+([\d,]+\.?\d*)\s*(?:bwpd|stb/d|м3/сут|%)",
    
    # NPT
    "npt_hours": r"(?:NPT|non-productive\s+time|flat\s+time|НПТ|непроизводительное\s+время)[:\s]+([\d.]+)\s*(?:hrs?|hours?|ч|час|часа)",
}

class PdfReportParser:
    """Parse oil and gas PDF reports with pdfplumber (primary) or pypdf (fallback)."""
    def extract_text(self, path: Path) -> str:
        if HAS_PDFPLUMBER: return self._extract_with_pdfplumber(path)
        if HAS_PYPDF: return self._extract_with_pypdf(path)
        try: return path.read_text(encoding="utf-8", errors="replace")
        except OSError: return ""

    def _extract_with_pdfplumber(self, path: Path) -> str:
        pages_text = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    pages_text.append(page.extract_text() or "")
        except Exception as exc:
            pages_text.append(f"[PDFPLUMBER ERROR: {exc}]")
        return "\n\n".join(pages_text)

    def _extract_with_pypdf(self, path: Path) -> str:
        pages_text = []
        try:
            reader = PdfReader(str(path))
            for page in reader.pages:
                pages_text.append(page.extract_text() or "")
        except Exception as exc:
            pages_text.append(f"[PYPDF ERROR: {exc}]")
        return "\n\n".join(pages_text)

    def extract_structured(
        self, path: Path, raw_text: str = ""
    ) -> tuple[dict[str, Any], list[dict], list[dict]]:
        text = raw_text or self.extract_text(path)
        entities = _extract_entities(text)
        extracted = _bucket_entities(entities)
        
        # Standard table extraction
        tables = self._extract_tables(path) if HAS_PDFPLUMBER else []
        
        # --- PILLAR 2: VISION LLM FALLBACK ---
        # If pdfplumber found 0 tables, but the PDF has multiple pages, try Vision LLM
        if not tables and HAS_VISION and path.suffix.lower() == ".pdf":
            logger.info(f"Standard parser found 0 tables in {path.name}. Triggering Vision LLM fallback...")
            img_bytes = render_pdf_page_to_image(path, page_index=0) # Try first page
            if img_bytes:
                vision_result = extract_table_with_vision(img_bytes)
                if vision_result.get("confidence", 0) > 0.5 and vision_result.get("rows"):
                    tables.append({
                        "name": "vision_extracted_table",
                        "columns": vision_result["columns"],
                        "rows": vision_result["rows"],
                        "source_page": 1,
                        "extraction_method": "vision_llm",
                        "confidence": vision_result["confidence"]
                    })
        
        npt_events = _extract_npt_events(text)
        if npt_events: extracted["drilling"]["npt_events"] = npt_events
        bha = _extract_bha(text)
        if bha: extracted["drilling"]["bha_components"] = bha
        casing = _extract_casing_points(text)
        if casing: extracted["drilling"]["casing_points"] = casing
        
        references = [{"source_section": "pdf_text_extraction", "page_or_depth_range": f"full document ({path.name})", "confidence": 0.75 if HAS_PDFPLUMBER else 0.60}]
        return extracted, tables, references

    def _extract_tables(self, path: Path) -> list[dict[str, Any]]:
        tables = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    for tbl_idx, table in enumerate(page.extract_tables() or []):
                        if not table or len(table) < 2: continue
                        header_row = table[0]
                        clean_headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header_row)]
                        clean_rows = [[str(cell).strip() if cell else None for cell in row] for row in table[1:]]
                        tables.append({"name": f"page_{page_num}_table_{tbl_idx + 1}", "columns": clean_headers, "rows": clean_rows, "source_page": page_num})
        except Exception:
            pass
        return tables

# ---------------------------------------------------------------------------
# Entity extraction helpers
# ---------------------------------------------------------------------------
def _extract_entities(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    for field, pattern in PATTERNS.items():
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip().rstrip(",. \t")
                entities[field] = value
        except re.error:
            pass
    return entities

def _bucket_entities(entities: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Sort extracted entities into domain buckets (Unit-Agnostic)."""
    DRILLING_FIELDS = {
        "well_name", "api", "rig_name", "operator", "field", "report_date",
        "current_depth_ft", "current_depth_m", "measured_depth_ft", "measured_depth_m", 
        "tvd_ft", "tvd_m", "rop_ft_hr", "rop_m_hr", "wob_klbs", "wob_tons", "rpm", 
        "spp_psi", "spp_kpa", "flow_rate_gpm", "mud_weight_ppg", "mud_weight_sg", "npt_hours",
    }
    COMPLETION_FIELDS = {"stage_count", "total_fluid_bbls", "total_proppant_lbs", "isip_psi"}
    PRODUCTION_FIELDS = {"oil_rate_bopd", "gas_rate_mcfd", "water_rate_bwpd"}
    
    result: dict[str, dict[str, Any]] = {"drilling": {}, "directional": {}, "completions": {}, "logs": {}, "production": {}}
    for field, value in entities.items():
        if field in DRILLING_FIELDS: result["drilling"][field] = value
        elif field in COMPLETION_FIELDS: result["completions"][field] = value
        elif field in PRODUCTION_FIELDS: result["production"][field] = value
    return result

def _extract_npt_events(text: str) -> list[dict[str, Any]]:
    events = []
    npt_block_pattern = re.compile(r"(NPT|Non-Productive Time|Flat Time|НПТ|Непроизводительное время)[:\s](.*?)(?=\n\n|\Z)", re.IGNORECASE | re.DOTALL)
    for match in npt_block_pattern.finditer(text):
        block = match.group(2).strip()
        for line in block.splitlines():
            line = line.strip()
            if not line: continue
            dur_match = re.search(r"([\d.]+)\s*(?:hr|hour|ч|час)", line, re.IGNORECASE)
            duration = float(dur_match.group(1)) if dur_match else None
            events.append({"description": line[:200], "duration_hrs": duration, "raw_text": line})
            if len(events) >= 50: break
    return events

def _extract_bha(text: str) -> list[dict[str, str]]:
    components = []
    bha_section = re.search(r"(?:BHA|Bottom\s+Hole\s+Assembly|Drill\s+String|КПБТ|Забойная\s+компоновка)[:\s](.*?)(?=\n\n|Bit\s+Record|Mud\s+Properties|\Z)", text, re.IGNORECASE | re.DOTALL)
    if bha_section:
        for line in bha_section.group(1).splitlines():
            line = line.strip()
            if len(line) > 5:
                components.append({"component": line[:200]})
            if len(components) >= 30: break
    return components

def _extract_casing_points(text: str) -> list[dict[str, Any]]:
    points = []
    pattern = re.compile(
        r"(\d{1,2}(?:[- ]\d/\d)?[ "' ]?\s*(?:in|inch|мм|mm)?(?:\s+conductor|surface|intermediate|production|liner|кондуктор|техническая|эксплуатационная)?(?:\s+casing|pipe|string|колонна)?) "
        r".*?(?:set|landed|cemented|shoe|установлен|зацементирован).*?([\d,]+)\s*(?:ft|feet|m\b|м|метр)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        points.append({"casing_string": match.group(1).strip(), "set_depth": match.group(2).replace(",", "")})
    return points[:15]
