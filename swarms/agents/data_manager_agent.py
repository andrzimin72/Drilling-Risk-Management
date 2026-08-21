"""
Data Manager Agent
First agent in every swarm. Detects file types, routes each file to the
correct specialist agent, and builds the initial SwarmContext file manifest.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .base_agent import BaseAgent, AgentResult

ROUTING_TABLE: dict[str, str] = {
    "las_well_log": "logs",
    "dlis_log_container": "logs",
    "pdf_document": "auto",
    "word_document": "auto",
    "spreadsheet": "auto",
    "csv_data": "auto",
    "json_export": "auto",
    "text_file": "auto",
    "witsml_export": "drilling",
    "xml_document": "drilling",
    "unknown": "data_manager",
}

DISCIPLINE_TO_DOMAIN: dict[str, str] = {
    "drilling": "drilling",
    "completions": "completions",
    "production": "production",
    "directional": "directional",
    "petrophysics": "logs",
    "hse": "hse",
    "unknown": "drilling",
}

class DataManagerAgent(BaseAgent):
    """Detects file types and builds the routing manifest for the swarm."""
    domain = "data_manager"
    description = (
        "Detects oil and gas file types, classifies engineering discipline, "
        "and routes each file to the correct specialist agent."
    )

    def can_handle(self, file_info: dict[str, Any]) -> bool:
        return True

    async def _process(
        self,
        file_paths: list[Path],
        context: dict[str, Any],
    ) -> AgentResult:
        from skills.oil_and_gas_data_manager.skill import detect_file_type, classify_discipline
        
        manifest: list[dict[str, Any]] = []
        routing: dict[str, list[str]] = {
            "drilling": [], "logs": [], "completions": [],
            "production": [], "directional": [], "hse": [],
        }
        
        for path in file_paths:
            if not path.exists():
                manifest.append({"path": str(path), "error": "not found"})
                continue
                
            detection = detect_file_type(path)
            detected_type = detection["detected_type"]
            
            domain = ROUTING_TABLE.get(detected_type, "auto")
            if domain == "auto":
                try:
                    text_sample = await self.safe_parse(path, 'read_text', encoding="utf-8", errors="replace")
                    text_sample = text_sample[:3000]
                except Exception:
                    text_sample = ""
                discipline, doc_type, conf = classify_discipline(text_sample)
                domain = DISCIPLINE_TO_DOMAIN.get(discipline, "drilling")
                
            # HSE override: supports both English and Russian safety keywords
            hse_keywords = {
                "incident", "near miss", "npt", "injury", "h2s", "safety stop",
                "инцидент", "микронепроизводство", "травма", "сероводород", "h2s", 
                "остановка работ", "потеря времени", "охрана труда"
            }
            if detected_type in {"pdf_document", "word_document", "text_file"}:
                try:
                    text_check = await self.safe_parse(path, 'read_text', encoding="utf-8", errors="replace")
                    text_check = text_check[:2000].lower()
                    if any(kw in text_check for kw in hse_keywords):
                        if "hse" not in routing:
                            routing["hse"] = []
                        routing["hse"].append(str(path))
                except Exception:
                    pass
                    
            if domain in routing:
                routing[domain].append(str(path))
                
            manifest.append({
                "path": str(path),
                "filename": path.name,
                "detected_type": detected_type,
                "confidence": detection["confidence"],
                "routed_to": domain,
            })
            
        summary_parts = [f"Classified {len(manifest)} files:"]
        for domain, paths in routing.items():
            if paths:
                summary_parts.append(f"  {domain}: {len(paths)} file(s)")
                
        return AgentResult(
            agent_name="DataManagerAgent",
            domain="data_manager",
            status="success",
            extracted_data={
                "manifest": manifest,
                "routing": routing,
                "file_count": len(manifest),
            },
            summary="\n".join(summary_parts),
            confidence=0.90,
            files_processed=[str(p) for p in file_paths],
        )