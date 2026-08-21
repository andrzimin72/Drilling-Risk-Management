"""
Vision LLM Fallback Parser
Uses multimodal LLMs to extract tables from scanned or poorly formatted 
Russian oil and gas PDFs where deterministic parsers (pdfplumber) fail.
"""
from __future__ import annotations
import base64
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import pypdfium2 as pdfium  # Pure Python, no system dependencies like poppler
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False

# Specialized prompt for Russian O&G documents
VISION_PROMPT = """You are an expert petroleum engineer and data extraction specialist.
You are looking at an image of a Russian oil and gas document (e.g., Ежсуточный отчет бурения, Журнал ГИС, or similar).

Your task: Extract the primary tabular data from this image.
CRITICAL RULES:
1. Recognize Russian oilfield terminology: 
   - "Механическая скорость" -> rop_m_hr
   - "Плотность раствора" / "ПВР" -> mud_weight_sg
   - "Глубина по стволу" / "Забой" -> depth_m
   - "Зенитный угол" -> inclination_deg
   - "Нагрузка на долото" -> wob_tons
   - "Давление на стояке" -> spp_kpa
2. Handle Russian decimal commas (e.g., "10,5" -> 10.5).
3. Ignore headers, footers, and stamps. Focus ONLY on the data table.
4. Return the result as a STRICT JSON object with this exact structure:
   {
     "columns": ["col1", "col2", ...],
     "rows": [
       [val1, val2, ...],
       ...
     ],
     "confidence": 0.0 to 1.0
   }
5. If no table is found, return: {"columns": [], "rows": [], "confidence": 0.0}
DO NOT include any markdown formatting, explanations, or text outside the JSON."""

def extract_table_with_vision(
    image_bytes: bytes, 
    model: str = "claude-sonnet-4-5",
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Send a PDF page image to a Vision LLM and extract structured table data.
    """
    if not HAS_ANTHROPIC:
        logger.warning("Anthropic SDK not installed. Vision fallback disabled.")
        return {"columns": [], "rows": [], "confidence": 0.0}

    client = anthropic.Anthropic(api_key=api_key)
    
    # Encode image to base64
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
        )
        
        # Parse the JSON response
        raw_text = response.content[0].text.strip()
        # Clean up any accidental markdown code blocks
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        parsed = json.loads(raw_text.strip())
        return parsed
        
    except Exception as exc:
        logger.error(f"Vision LLM extraction failed: {exc}")
        return {"columns": [], "rows": [], "confidence": 0.0, "error": str(exc)}

def render_pdf_page_to_image(path: Path, page_index: int = 0) -> bytes | None:
    """Convert a specific PDF page to a PNG image in memory."""
    if not HAS_PDFIUM:
        return None
    try:
        pdf = pdfium.PdfDocument(str(path))
        page = pdf[page_index]
        # Render at 200 DPI for good OCR quality without massive file size
        bitmap = page.render(scale=200/72) 
        pil_image = bitmap.to_pil()
        
        import io
        img_byte_arr = io.BytesIO()
        pil_image.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
    except Exception as exc:
        logger.error(f"Failed to render PDF page {page_index} to image: {exc}")
        return None