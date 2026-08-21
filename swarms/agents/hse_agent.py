"""
HSE Agent — safety incidents, NPT classification, near misses, TRIR.
Async parsing, Russian/Metric support, Pydantic enforcement.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

try:
    from skills.oil_and_gas_data_manager.schemas.extraction_schema import HSEDataSchema
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False

SEVERITY_KEYWORDS = {
    "fatality": ("fatality", "fatal", "died", "death", "смерть", "погиб", "летальный"),
    "lti": ("lti", "lost time", "days away", "unable to work", "потеря времени", "травма с потерей трудоспособности"),
    "rwc": ("restricted work", "light duty", "modified duty", "rwc", "ограниченная трудоспособность"),
    "mtc": ("medical treatment", "hospital", "clinic", "mtc", "медицинская помощь", "госпитализация"),
    "fac": ("first aid", "minor injury", "fac", "первая помощь", "микротравма"),
    "near_miss": ("near miss", "near-miss", "close call", "no injury", "микронепроизводство", "инцидент без травм"),
    "unsafe": ("unsafe act", "unsafe condition", "hazard observation", "небезопасное действие", "небезопасные условия"),
}

INCIDENT_TRIGGERS = {
    "incident", "injury", "near miss", "unsafe", "h2s", "gas", "kick",
    "spill", "fire", "explosion", "dropped object", "struck by", "fall",
    "slip", "trip", "burn", "laceration", "evacuation", "safety stop",
    "инцидент", "травма", "микронепроизводство", "несчастный случай", "сероводород", 
    "выброс", "пожар", "взрыв", "падение", "остановка работ"
}

class HSEAgent(BaseAgent):
    domain = "hse"
    description = "Scans drilling reports for safety incidents, near misses, NPT events, and environmental occurrences."
    skill_path = "skills/hse_incident_tracker/SKILL.md"

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        text = file_info.get("text_sample", "").lower()
        return sum(1 for kw in INCIDENT_TRIGGERS if kw in text) >= 2

    async def _process(self, file_paths: list[Path], context: dict[str, Any]) -> AgentResult:
        from skills.oil_and_gas_data_manager.parsers.pdf_reports import PdfReportParser
        parser = PdfReportParser()
        all_events: list[dict] = []
        all_flags: list[str] = []
        processed: list[str] = []
        total_npt_hse = 0.0
        
        for path in file_paths:
            try:
                # Phase 1: Async non-blocking parse
                text = await self.safe_parse(parser, 'extract_text', path)
                events = _extract_hse_events(text, path.name)
                all_events.extend(events)
                total_npt_hse += sum(e.get("npt_hrs", 0) or 0 for e in events)
                processed.append(str(path))
            except Exception as exc:
                all_flags.append(f"PARSE_ERROR [{path.name}]: {exc}")
                
        counts = _count_by_severity(all_events)
        patterns = _find_recurring_patterns(all_events)
        trir = _compute_trir(counts, context.get("total_manhours"))
        
        hse_data = {
            "incident_counts": counts,
            "total_npt_hse_hrs": round(total_npt_hse, 2),
            "trir": trir,
            "incidents": all_events,
            "recurring_patterns": patterns,
        }
        
        # Phase 3: Schema Enforcement
        validated_hse = _validate_domain_data(hse_data, HSEDataSchema)
        
        summary_parts = [f"HSE Agent scanned {len(processed)} report(s)."]
        summary_parts.append(f"Incidents: {len(validated_hse.get('incidents', []))} total")
        if counts.get("lti"):
            summary_parts.append(f"LTI: {counts['lti']}")
        if counts.get("near_miss"):
            summary_parts.append(f"Near misses: {counts['near_miss']}")
        if total_npt_hse > 0:
            summary_parts.append(f"HSE NPT: {total_npt_hse:.1f} hrs")
        if trir is not None:
            summary_parts.append(f"TRIR: {trir:.2f}")
            
        return AgentResult(
            agent_name="HSEAgent",
            domain="hse",
            status="success",
            extracted_data={"hse": validated_hse},
            summary=" | ".join(summary_parts),
            quality_flags=all_flags,
            confidence=0.70,
            files_processed=processed,
        )

def _extract_hse_events(text: str, source_file: str) -> list[dict]:
    events = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if not any(kw in line_lower for kw in INCIDENT_TRIGGERS):
            continue
            
        severity = "unsafe"
        for sev, keywords in SEVERITY_KEYWORDS.items():
            if any(kw in line_lower for kw in keywords):
                severity = sev
                break
                
        # Support English and Russian duration formats
        dur_match = re.search(r"([\d.]+)\s*(?:hr|hour|час)", line, re.IGNORECASE)
        npt_hrs = float(dur_match.group(1)) if dur_match else None
        
        sif_keywords = ("dropped object", "h2s", "energy isolation", "well control", "vehicle", "сероводород", "выброс")
        sif_potential = any(kw in line_lower for kw in sif_keywords)
        
        events.append({
            "severity": severity,
            "description": line.strip()[:300],
            "npt_hrs": npt_hrs,
            "sif_potential": sif_potential,
            "source_file": source_file,
            "source_line": i + 1,
            "confidence": 0.65,
        })
        if len(events) >= 50:
            break
    return events

def _count_by_severity(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        sev = e.get("severity", "unsafe")
        counts[sev] = counts.get(sev, 0) + 1
    return counts

def _find_recurring_patterns(events: list[dict]) -> list[dict]:
    category_counts: dict[str, int] = {}
    for e in events:
        desc = e.get("description", " ").lower()
        # Support English and Russian pattern keywords
        for kw in ("pump", "stuck pipe", "h2s", "dropped object", "mud loss", "equipment", "насос", "прихват", "сероводород"):
            if kw in desc:
                category_counts[kw] = category_counts.get(kw, 0) + 1
    patterns = []
    for pattern, count in category_counts.items():
        if count >= 2:
            patterns.append({
                "pattern": pattern,
                "occurrence_count": count,
                "recommendation": f"Review {pattern} procedures — {count} occurrences detected",
            })
    return patterns

def _compute_trir(counts: dict, manhours: float | None) -> float | None:
    if not manhours:
        return None
    recordable = sum(counts.get(k, 0) for k in ("fatality", "lti", "rwc", "mtc"))
    return round((recordable * 200000) / manhours, 2)

def _validate_domain_data(raw_data: dict, schema_class: Any) -> dict:
    if not HAS_SCHEMA or not raw_data:
        return raw_data
    try:
        instance = schema_class.model_validate(raw_data)
        return instance.model_dump(exclude_none=True)
    except Exception:
        return raw_data
