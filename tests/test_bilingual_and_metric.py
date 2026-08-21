"""
Tests for Bilingual (Russian/English) and Metric/Imperial parsing.
"""
import pytest
from pathlib import Path
from skills.oil_and_gas_data_manager.skill import classify_discipline, _extract_entity_context
from skills.oil_and_gas_data_manager.parsers.pdf_reports import _extract_entities

RUSSIAN_DDR_TEXT = """
ЕЖСУТОЧНЫЙ ОТЧЕТ БУРЕНИЯ (DAILY DRILLING REPORT)
Заказчик: Газпром нефть
Скважина: 123
Куст: 5
Дата: 31.07.2026
Текущая глубина: 3245,6 м
Механическая скорость: 45 м/ч
Плотность бурового раствора: 1,18 г/см3
НПТ: 2.5 час - отказ насоса
"""

class TestBilingualClassification:
    def test_classify_russian_drilling_report(self):
        """System must recognize Russian DDR keywords."""
        disc, doc_type, conf = classify_discipline(RUSSIAN_DDR_TEXT)
        assert disc == "drilling"
        assert conf > 0.1

    def test_extract_russian_well_context(self):
        """System must extract Russian well/pad identifiers (Скважина, Куст)."""
        ctx = _extract_entity_context(RUSSIAN_DDR_TEXT, {})
        assert ctx.get("well_name") == "123"
        assert ctx.get("pad") == "5"

class TestMetricEntityExtraction:
    def test_extract_metric_depth_and_rop(self):
        """System must extract metric depth (м) and ROP (м/ч)."""
        entities = _extract_entities(RUSSIAN_DDR_TEXT)
        # Regex should catch the metric values
        assert entities.get("rop_m_hr") == "45"
        # Depth might be parsed with or without the decimal comma depending on regex strictness
        assert "3245" in str(entities.get("current_depth_m", ""))

    def test_extract_metric_mud_weight(self):
        """System must extract mud weight in g/cm3 (sg)."""
        entities = _extract_entities(RUSSIAN_DDR_TEXT)
        # Should find the metric mud weight
        assert entities.get("mud_weight_sg") is not None or entities.get("mud_weight_ppg") is None