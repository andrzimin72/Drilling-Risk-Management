"""
Unit tests for the Risk Management core: Risk, RiskLevel, RiskRegistry.
"""
import pytest
import json
from pathlib import Path
from skills.oil_and_gas_data_manager.risk_manager import (
    Risk, RiskLevel, RiskCategory, RiskStatus, RiskRegistry
)


# ---------------------------------------------------------------------------
# RiskLevel tests
# ---------------------------------------------------------------------------
class TestRiskLevel:
    def test_from_score_critical(self):
        assert RiskLevel.from_score(5, 5) == RiskLevel.CRITICAL
        assert RiskLevel.from_score(4, 4) == RiskLevel.CRITICAL
        assert RiskLevel.from_score(5, 4) == RiskLevel.CRITICAL

    def test_from_score_high(self):
        assert RiskLevel.from_score(3, 4) == RiskLevel.HIGH
        assert RiskLevel.from_score(4, 3) == RiskLevel.HIGH
        assert RiskLevel.from_score(3, 3) == RiskLevel.HIGH

    def test_from_score_medium(self):
        assert RiskLevel.from_score(2, 3) == RiskLevel.MEDIUM
        assert RiskLevel.from_score(3, 2) == RiskLevel.MEDIUM
        assert RiskLevel.from_score(2, 2) == RiskLevel.MEDIUM

    def test_from_score_low(self):
        assert RiskLevel.from_score(1, 1) == RiskLevel.LOW
        assert RiskLevel.from_score(1, 3) == RiskLevel.LOW
        assert RiskLevel.from_score(2, 1) == RiskLevel.LOW

    def test_display_names_bilingual(self):
        assert RiskLevel.CRITICAL.display_name_en == "Critical"
        assert RiskLevel.CRITICAL.display_name_ru == "Критический"
        assert RiskLevel.HIGH.display_name_en == "High"
        assert RiskLevel.HIGH.display_name_ru == "Высокий"

    def test_color_hex_format(self):
        for level in RiskLevel:
            color = level.color_hex
            assert color.startswith("#")
            assert len(color) == 7


# ---------------------------------------------------------------------------
# Risk dataclass tests
# ---------------------------------------------------------------------------
class TestRisk:
    def test_risk_auto_calculates_level(self):
        risk = Risk(probability=4, impact=4)
        assert risk.risk_level == RiskLevel.CRITICAL

    def test_risk_default_values(self):
        risk = Risk()
        assert risk.status == RiskStatus.OPEN
        assert risk.probability == 3
        assert risk.impact == 3
        assert risk.risk_level == RiskLevel.MEDIUM  # 3×3 = 9
        assert risk.linked_wells == []
        assert risk.mitigation_en == []

    def test_risk_id_generated(self):
        risk = Risk()
        assert risk.risk_id.startswith("RISK-")
        assert len(risk.risk_id) > 5

    def test_risk_to_dict_serialization(self):
        risk = Risk(
            category=RiskCategory.HSE,
            title_en="Test risk",
            title_ru="Тестовый риск",
            probability=5,
            impact=5,
        )
        d = risk.to_dict()
        assert d["category"] == "hse"
        assert d["risk_level"] == "critical"
        assert d["status"] == "open"
        assert d["probability"] == 5

    def test_risk_from_dict_deserialization(self):
        data = {
            "category": "technical",
            "title_en": "High DLS",
            "probability": 4,
            "impact": 4,
            "risk_level": "critical",
            "status": "open",
        }
        risk = Risk.from_dict(data)
        assert risk.category == RiskCategory.TECHNICAL
        assert risk.risk_level == RiskLevel.CRITICAL

    def test_risk_bilingual_fields(self):
        risk = Risk(
            title_en="Stuck pipe risk",
            title_ru="Риск прихвата",
            description_en="High DLS detected",
            description_ru="Высокая интенсивность искривления",
            mitigation_en=["Use lubricity additives"],
            mitigation_ru=["Использовать смазывающие добавки"],
        )
        assert "Stuck" in risk.title_en
        assert "прихвата" in risk.title_ru


# ---------------------------------------------------------------------------
# RiskRegistry tests
# ---------------------------------------------------------------------------
class TestRiskRegistry:
    def test_empty_registry(self):
        registry = RiskRegistry(well_name="Test Well")
        assert len(registry.risks) == 0
        summary = registry.get_summary()
        assert summary["total_risks"] == 0
        assert summary["risk_score"] == 0

    def test_add_risk(self):
        registry = RiskRegistry(well_name="Well 123", pad_name="Pad 5")
        risk = Risk(title_en="Test", probability=4, impact=3)
        registry.add_risk(risk)
        assert len(registry.risks) == 1
        assert risk.linked_wells == ["Well 123"]
        assert risk.linked_pads == ["Pad 5"]

    def test_get_risks_filtered_by_level(self):
        registry = RiskRegistry()
        registry.add_risk(Risk(probability=5, impact=5))  # Critical
        registry.add_risk(Risk(probability=3, impact=3))  # High
        registry.add_risk(Risk(probability=2, impact=2))  # Medium
        registry.add_risk(Risk(probability=1, impact=1))  # Low

        critical = registry.get_risks(level=RiskLevel.CRITICAL)
        assert len(critical) == 1
        high = registry.get_risks(level=RiskLevel.HIGH)
        assert len(high) == 1

    def test_get_risks_filtered_by_category(self):
        registry = RiskRegistry()
        registry.add_risk(Risk(category=RiskCategory.HSE, probability=3, impact=3))
        registry.add_risk(Risk(category=RiskCategory.TECHNICAL, probability=3, impact=3))
        registry.add_risk(Risk(category=RiskCategory.HSE, probability=3, impact=3))

        hse = registry.get_risks(category=RiskCategory.HSE)
        assert len(hse) == 2

    def test_get_critical_risks(self):
        registry = RiskRegistry()
        registry.add_risk(Risk(probability=5, impact=5))   # Critical
        registry.add_risk(Risk(probability=4, impact=4))   # Critical
        registry.add_risk(Risk(probability=3, impact=3))   # High
        registry.add_risk(Risk(probability=1, impact=1))   # Low

        critical = registry.get_critical_risks()
        assert len(critical) == 3  # 2 critical + 1 high

    def test_risk_matrix_5x5(self):
        registry = RiskRegistry()
        registry.add_risk(Risk(probability=5, impact=5))
        registry.add_risk(Risk(probability=5, impact=5))
        registry.add_risk(Risk(probability=1, impact=1))

        matrix = registry.get_risk_matrix()
        assert matrix[5][5] == 2
        assert matrix[1][1] == 1
        assert matrix[3][3] == 0

    def test_summary_statistics(self):
        registry = RiskRegistry()
        registry.add_risk(Risk(category=RiskCategory.HSE, probability=5, impact=5))
        registry.add_risk(Risk(category=RiskCategory.TECHNICAL, probability=3, impact=3))
        registry.add_risk(Risk(category=RiskCategory.GEOLOGICAL, probability=2, impact=2))

        summary = registry.get_summary()
        assert summary["total_risks"] == 3
        assert summary["critical_count"] == 1
        assert summary["high_count"] == 1
        assert summary["by_category"]["hse"] == 1
        assert summary["risk_score"] > 0

    def test_export_json(self, tmp_path):
        registry = RiskRegistry(well_name="Well 123")
        registry.add_risk(Risk(title_en="Test risk", probability=4, impact=3))

        json_path = tmp_path / "risks.json"
        registry.export_json(json_path)

        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["well_name"] == "Well 123"
        assert len(data["risks"]) == 1

    def test_export_csv(self, tmp_path):
        registry = RiskRegistry()
        registry.add_risk(Risk(title_en="Risk 1", probability=4, impact=3))
        registry.add_risk(Risk(title_en="Risk 2", probability=2, impact=2))

        csv_path = tmp_path / "risks.csv"
        registry.export_csv(csv_path)

        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "risk_id" in content
        assert "Risk 1" in content or "risk_1" in content.lower()