"""
Project Match Schema and Matching Logic
Scores how well extracted file identifiers match the active project context.
Russian well/pad normalization.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ProjectContext:
    """Active project metadata provided by the user."""
    project_name: Optional[str] = None
    well_name: Optional[str] = None
    well_name_aliases: list[str] = field(default_factory=list)
    api: Optional[str] = None
    pad: Optional[str] = None
    field_name: Optional[str] = None
    basin: Optional[str] = None
    operator: Optional[str] = None
    service_companies: list[str] = field(default_factory=list)
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None

class ProjectMatcher:
    """Score extracted entity context against the active project."""
    def __init__(self, context: Optional[ProjectContext] = None) -> None:
        self.context = context

    def score(self, entity_context: dict[str, Any]) -> dict[str, Any]:
        if not self.context:
            return {"project_name": None, "match_confidence": 0.0, "matched_identifiers": []}
            
        ctx = self.context
        matched: list[str] = []
        score = 0.0
        max_score = 0.0

        # API/UWI match
        max_score += 3.0
        if ctx.api and entity_context.get("api"):
            if _normalize_api(ctx.api) == _normalize_api(entity_context["api"]):
                score += 3.0
                matched.append(f"api:{entity_context['api']}")

        # Well name match
        max_score += 3.0
        all_well_names = []
        if ctx.well_name: all_well_names.append(ctx.well_name)
        all_well_names.extend(ctx.well_name_aliases)
        
        extracted_well = entity_context.get("well_name", "")
        if extracted_well and all_well_names:
            for known_name in all_well_names:
                if _names_match(known_name, extracted_well):
                    score += 3.0
                    matched.append(f"well_name:{extracted_well}")
                    break

        # Field match
        max_score += 1.5
        if ctx.field_name and entity_context.get("field"):
            if _names_match(ctx.field_name, entity_context["field"]):
                score += 1.5
                matched.append(f"field:{entity_context['field']}")

        # Operator match
        max_score += 1.5
        if ctx.operator and entity_context.get("operator"):
            if _names_match(ctx.operator, entity_context["operator"]):
                score += 1.5
                matched.append(f"operator:{entity_context['operator']}")

        # Pad match
        max_score += 0.5
        if ctx.pad and entity_context.get("pad"):
            if _names_match(ctx.pad, entity_context["pad"]):
                score += 0.5
                matched.append(f"pad:{entity_context['pad']}")

        # Basin match
        max_score += 0.5
        if ctx.basin and entity_context.get("basin"):
            if _names_match(ctx.basin, entity_context["basin"]):
                score += 0.5
                matched.append(f"basin:{entity_context['basin']}")

        confidence = round(score / max_score, 3) if max_score > 0 else 0.0
        return {"project_name": ctx.project_name, "match_confidence": confidence, "matched_identifiers": matched}

def _normalize_api(api: str) -> str:
    return re.sub(r"\D", "", api)

def _names_match(a: str, b: str) -> bool:
    """Fuzzy name comparison: normalize whitespace, case, and common oilfield abbreviations."""
    def normalize(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"\s+", " ", s)
        # Strip common prefixes/suffixes (English and Russian)
        for tok in ("#", "-", " ", "well ", "no. ", "no  ", "unit ", "скважина ", "скв. ", "скв ", "куст "):
            s = s.replace(tok, " ")
        return s.strip()
        
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    if na in nb or nb in na: return True
    return False
