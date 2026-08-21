"""
Risk Management System
Complete risk registry and scoring engine for oil and gas operations.
Automatically detects, scores, and categorizes risks from all agent outputs.
Supports bilingual (EN/RU) risk descriptions for Gazprom Neft.
"""
from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class RiskCategory(str, Enum):
    """Risk categories aligned with oil & gas industry standards."""
    HSE = "hse"                        # Health, Safety, Environment
    OPERATIONAL = "operational"        # Drilling operations, NPT
    GEOLOGICAL = "geological"          # Formation, pay zones, reservoir
    TECHNICAL = "technical"            # Equipment, trajectory, surveys
    ENVIRONMENTAL = "environmental"    # Spills, emissions, regulations
    DATA_INTEGRITY = "data_integrity"  # Cross-domain mismatches


class RiskLevel(str, Enum):
    """Risk levels based on Probability × Impact matrix."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_score(cls, probability: int, impact: int) -> "RiskLevel":
        """Calculate risk level from 5x5 matrix."""
        score = probability * impact
        if score >= 16:
            return cls.CRITICAL
        if score >= 9:
            return cls.HIGH
        if score >= 4:
            return cls.MEDIUM
        return cls.LOW

    @property
    def color_hex(self) -> str:
        """Brand colors for risk levels."""
        return {
            RiskLevel.LOW: "#4CAF50",        # Green
            RiskLevel.MEDIUM: "#FFD700",     # Yellow
            RiskLevel.HIGH: "#FF6B00",       # Orange
            RiskLevel.CRITICAL: "#C00000",   # Red
        }[self]

    @property
    def display_name_en(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MEDIUM: "Medium",
            RiskLevel.HIGH: "High",
            RiskLevel.CRITICAL: "Critical",
        }[self]

    @property
    def display_name_ru(self) -> str:
        return {
            RiskLevel.LOW: "Низкий",
            RiskLevel.MEDIUM: "Средний",
            RiskLevel.HIGH: "Высокий",
            RiskLevel.CRITICAL: "Критический",
        }[self]


class RiskStatus(str, Enum):
    """Risk lifecycle status."""
    OPEN = "open"
    MONITORING = "monitoring"
    MITIGATED = "mitigated"
    CLOSED = "closed"
    ACCEPTED = "accepted"


# ---------------------------------------------------------------------------
# Risk Data Model
# ---------------------------------------------------------------------------
@dataclass
class Risk:
    """Single risk entry with bilingual descriptions."""
    risk_id: str = field(default_factory=lambda: f"RISK-{uuid.uuid4().hex[:8].upper()}")
    category: RiskCategory = RiskCategory.OPERATIONAL
    source_agent: str = ""
    title_en: str = ""
    title_ru: str = ""
    description_en: str = ""
    description_ru: str = ""
    probability: int = 3           # 1-5 scale
    impact: int = 3                # 1-5 scale
    risk_level: RiskLevel = RiskLevel.MEDIUM
    mitigation_en: list[str] = field(default_factory=list)
    mitigation_ru: list[str] = field(default_factory=list)
    status: RiskStatus = RiskStatus.OPEN
    linked_wells: list[str] = field(default_factory=list)
    linked_pads: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Auto-calculate risk level from probability × impact."""
        if self.probability and self.impact:
            self.risk_level = RiskLevel.from_score(self.probability, self.impact)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/DB storage."""
        d = asdict(self)
        d["category"] = self.category.value
        d["risk_level"] = self.risk_level.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Risk":
        """Deserialize from dict."""
        data = data.copy()
        data["category"] = RiskCategory(data.get("category", "operational"))
        data["risk_level"] = RiskLevel(data.get("risk_level", "medium"))
        data["status"] = RiskStatus(data.get("status", "open"))
        return cls(**data)


# ---------------------------------------------------------------------------
# Risk Registry
# ---------------------------------------------------------------------------
class RiskRegistry:
    """Centralized registry for all identified risks."""

    def __init__(self, well_name: Optional[str] = None, pad_name: Optional[str] = None):
        self.well_name = well_name
        self.pad_name = pad_name
        self.risks: list[Risk] = []
        self.created_at = datetime.utcnow().isoformat()

    def add_risk(self, risk: Risk) -> None:
        """Add a risk to the registry."""
        # Link to well/pad if not already set
        if self.well_name and not risk.linked_wells:
            risk.linked_wells = [self.well_name]
        if self.pad_name and not risk.linked_pads:
            risk.linked_pads = [self.pad_name]
        self.risks.append(risk)
        logger.debug(f"Added risk {risk.risk_id}: {risk.title_en} [{risk.risk_level.value}]")

    def add_risks(self, risks: list[Risk]) -> None:
        """Add multiple risks."""
        for risk in risks:
            self.add_risk(risk)

    def get_risks(
        self,
        category: Optional[RiskCategory] = None,
        level: Optional[RiskLevel] = None,
        status: Optional[RiskStatus] = None,
        min_probability: Optional[int] = None,
    ) -> list[Risk]:
        """Get filtered risks."""
        filtered = self.risks
        if category is not None:
            filtered = [r for r in filtered if r.category == category]
        if level is not None:
            filtered = [r for r in filtered if r.risk_level == level]
        if status is not None:
            filtered = [r for r in filtered if r.status == status]
        if min_probability is not None:
            filtered = [r for r in filtered if r.probability >= min_probability]
        return sorted(filtered, key=lambda r: (r.probability * r.impact), reverse=True)

    def get_critical_risks(self) -> list[Risk]:
        """Get all critical and high risks."""
        return self.get_risks(level=RiskLevel.CRITICAL) + self.get_risks(level=RiskLevel.HIGH)

    def get_risk_matrix(self) -> dict[int, dict[int, int]]:
        """
        Build 5x5 risk matrix (probability × impact).
        Returns dict[probability][impact] = count.
        """
        matrix: dict[int, dict[int, int]] = {p: {i: 0 for i in range(1, 6)} for p in range(1, 6)}
        for risk in self.risks:
            if 1 <= risk.probability <= 5 and 1 <= risk.impact <= 5:
                matrix[risk.probability][risk.impact] += 1
        return matrix

    def get_summary(self) -> dict[str, Any]:
        """Get aggregated risk statistics."""
        total = len(self.risks)
        if total == 0:
            return {
                "total_risks": 0,
                "by_level": {level.value: 0 for level in RiskLevel},
                "by_category": {cat.value: 0 for cat in RiskCategory},
                "risk_score": 0,
            }

        by_level = {level.value: 0 for level in RiskLevel}
        by_category = {cat.value: 0 for cat in RiskCategory}
        total_score = 0

        for risk in self.risks:
            by_level[risk.risk_level.value] += 1
            by_category[risk.category.value] += 1
            total_score += risk.probability * risk.impact

        return {
            "total_risks": total,
            "by_level": by_level,
            "by_category": by_category,
            "risk_score": round(total_score / total, 2),
            "max_risk_score": max(r.probability * r.impact for r in self.risks),
            "critical_count": by_level[RiskLevel.CRITICAL.value],
            "high_count": by_level[RiskLevel.HIGH.value],
        }

    def export_json(self, path: Path) -> None:
        """Export registry to JSON file."""
        data = {
            "well_name": self.well_name,
            "pad_name": self.pad_name,
            "created_at": self.created_at,
            "summary": self.get_summary(),
            "risks": [r.to_dict() for r in self.risks],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info(f"Risk registry exported to {path}")

    def export_csv(self, path: Path) -> None:
        """Export risks to CSV file."""
        import csv
        if not self.risks:
            return
        fieldnames = [
            "risk_id", "category", "title_en", "title_ru",
            "probability", "impact", "risk_level", "status",
            "source_agent", "linked_wells", "linked_pads",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for risk in self.risks:
                row = risk.to_dict()
                row["linked_wells"] = ";".join(risk.linked_wells)
                row["linked_pads"] = ";".join(risk.linked_pads)
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        logger.info(f"Risk registry exported to {path}")


# ---------------------------------------------------------------------------
# Risk Scoring Engine
# ---------------------------------------------------------------------------
class RiskScoringEngine:
    """
    Analyzes swarm results and generates risks based on domain-specific rules.
    Each analyze_* method returns a list of Risk objects.
    """

    def __init__(self, language: str = "ru"):
        """
        Args:
            language: Primary language for risk titles ("en" or "ru")
        """
        self.language = language

    def generate_all_risks(self, swarm_result: Any) -> list[Risk]:
        """
        Main entry point: analyze all agent results and generate comprehensive risk list.
        """
        all_risks: list[Risk] = []
        agent_results = getattr(swarm_result, "agent_results", {})

        # Analyze each domain
        if "drilling" in agent_results:
            all_risks.extend(self.analyze_drilling(agent_results["drilling"]))
        if "logs" in agent_results:
            all_risks.extend(self.analyze_logs(agent_results["logs"]))
        if "completions" in agent_results:
            all_risks.extend(self.analyze_completions(agent_results["completions"]))
        if "production" in agent_results:
            all_risks.extend(self.analyze_production(agent_results["production"]))
        if "directional" in agent_results:
            all_risks.extend(self.analyze_directional(agent_results["directional"]))
        if "hse" in agent_results:
            all_risks.extend(self.analyze_hse(agent_results["hse"]))

        # Cross-domain and quality flags
        all_risks.extend(self.analyze_quality_flags(swarm_result))

        # RAG predictive risks (if present in flags)
        all_risks.extend(self.analyze_rag_warnings(swarm_result))

        return all_risks

    # -----------------------------------------------------------------------
    # Domain-specific analyzers
    # -----------------------------------------------------------------------
    def analyze_drilling(self, result: dict) -> list[Risk]:
        """Analyze drilling agent results for operational risks."""
        risks = []
        data = result.get("extracted_data", {}).get("drilling", {})
        flags = result.get("quality_flags", [])

        # NPT analysis
        npt_hours = data.get("npt_hours") or 0
        npt_events = data.get("npt_events", [])

        if npt_hours > 10:
            risks.append(Risk(
                category=RiskCategory.OPERATIONAL,
                source_agent="DrillingAgent",
                title_en=f"High NPT: {npt_hours:.1f} hours recorded",
                title_ru=f"Высокое НПТ: зафиксировано {npt_hours:.1f} часов",
                description_en=f"Total non-productive time of {npt_hours:.1f} hours exceeds acceptable threshold (>10 hrs).",
                description_ru=f"Общее непроизводительное время {npt_hours:.1f} часов превышает допустимый порог (>10 ч).",
                probability=4, impact=3,
                mitigation_en=[
                    "Conduct NPT root cause analysis for top 3 events",
                    "Review BHA design and bit selection",
                    "Implement preventive maintenance schedule",
                ],
                mitigation_ru=[
                    "Провести анализ первопричин НПТ по топ-3 событиям",
                    "Пересмотреть конструкцию КПБТ и выбор долота",
                    "Внедрить график профилактического обслуживания",
                ],
                metadata={"npt_hours": npt_hours, "event_count": len(npt_events)},
            ))
        elif npt_hours > 5:
            risks.append(Risk(
                category=RiskCategory.OPERATIONAL,
                source_agent="DrillingAgent",
                title_en=f"Moderate NPT: {npt_hours:.1f} hours",
                title_ru=f"Умеренное НПТ: {npt_hours:.1f} часов",
                description_en=f"NPT of {npt_hours:.1f} hours requires monitoring.",
                description_ru=f"НПТ {npt_hours:.1f} часов требует мониторинга.",
                probability=3, impact=2,
                mitigation_en=["Monitor NPT trends over next 3 days", "Review mud properties"],
                mitigation_ru=["Мониторить тренд НПТ в ближайшие 3 дня", "Проверить свойства раствора"],
                metadata={"npt_hours": npt_hours},
            ))

        # Mud weight sanity failures
        mud_flags = [f for f in flags if "mud_weight" in f.lower() and "SANITY" in f]
        if mud_flags:
            risks.append(Risk(
                category=RiskCategory.TECHNICAL,
                source_agent="DrillingAgent",
                title_en="Mud weight outside expected range",
                title_ru="Плотность бурового раствора вне допустимого диапазона",
                description_en=f"Mud weight anomaly detected: {mud_flags[0]}",
                description_ru=f"Обнаружена аномалия плотности раствора: {mud_flags[0]}",
                probability=3, impact=4,
                mitigation_en=[
                    "Verify mud weight measurements",
                    "Check for fluid losses or influx",
                    "Review mud program and additives",
                ],
                mitigation_ru=[
                    "Проверить замеры плотности раствора",
                    "Проверить наличие поглощений или притоков",
                    "Пересмотреть программу бурового раствора",
                ],
                metadata={"flags": mud_flags},
            ))

        return risks

    def analyze_logs(self, result: dict) -> list[Risk]:
        """Analyze logs agent results for geological risks."""
        risks = []
        data = result.get("extracted_data", {}).get("logs", {})
        flags = result.get("quality_flags", [])

        # Pay zone analysis
        pay_count = data.get("pay_zone_count", 0)
        total_net_pay = data.get("total_net_pay", 0)

        if pay_count == 0 and data.get("curves"):
            risks.append(Risk(
                category=RiskCategory.GEOLOGICAL,
                source_agent="LogsAgent",
                title_en="No pay zones identified",
                title_ru="Не выявлено продуктивных интервалов",
                description_en="Log data present but no pay zones identified with current cutoffs. Review petrophysical model.",
                description_ru="Данные ГИС присутствуют, но не выявлено продуктивных интервалов при текущих отсечках. Пересмотреть петрофизическую модель.",
                probability=3, impact=4,
                mitigation_en=[
                    "Review GR and RT cutoffs for specific basin",
                    "Consider alternative pay indicators (porosity, sonic)",
                    "Consult with petrophysicist for field-specific model",
                ],
                mitigation_ru=[
                    "Пересмотреть отсечки ГК и ИС для конкретного бассейна",
                    "Рассмотреть альтернативные индикаторы (пористость, акустика)",
                    "Проконсультироваться с петрофизиком",
                ],
            ))

        # Missing key curves
        curves = data.get("curves", [])
        curve_mnemonics = {c.get("mnemonic", "").upper() for c in curves}
        missing_gr = not any(m in curve_mnemonics for m in ("GR", "GRC", "SGR"))
        missing_rt = not any(m in curve_mnemonics for m in ("RT", "RD", "RILD"))

        if missing_gr or missing_rt:
            missing = []
            if missing_gr: missing.append("GR")
            if missing_rt: missing.append("RT/RD")
            risks.append(Risk(
                category=RiskCategory.DATA_INTEGRITY,
                source_agent="LogsAgent",
                title_en=f"Missing key curves: {', '.join(missing)}",
                title_ru=f"Отсутствуют ключевые кривые: {', '.join(missing)}",
                description_en=f"Critical curves missing: {', '.join(missing)}. Pay zone identification may be unreliable.",
                description_ru=f"Отсутствуют критические кривые: {', '.join(missing)}. Оценка продуктивных интервалов может быть недостоверной.",
                probability=3, impact=3,
                mitigation_en=["Request complete log suite from service company", "Verify LAS file integrity"],
                mitigation_ru=["Запросить полный комплекс ГИС у сервисной компании", "Проверить целостность LAS-файла"],
            ))

        return risks

    def analyze_completions(self, result: dict) -> list[Risk]:
        """Analyze completions agent results."""
        risks = []
        data = result.get("extracted_data", {}).get("completions", {})
        flags = result.get("quality_flags", [])

        # ISIP out of range
        isip_flags = [f for f in flags if "ISIP" in f and "SANITY" in f]
        if isip_flags:
            risks.append(Risk(
                category=RiskCategory.TECHNICAL,
                source_agent="CompletionsAgent",
                title_en="ISIP values outside normal range",
                title_ru="Значения ISIP вне нормального диапазона",
                description_en=f"ISIP anomaly detected: {isip_flags[0]}",
                description_ru=f"Обнаружена аномалия ISIP: {isip_flags[0]}",
                probability=4, impact=3,
                mitigation_en=[
                    "Review frac design and treating pressure limits",
                    "Check for screen-out or near-screen-out events",
                    "Verify pressure gauge calibration",
                ],
                mitigation_ru=[
                    "Пересмотреть дизайн ГРП и ограничения по давлению",
                    "Проверить наличие песчаной пробки",
                    "Проверить калибровку манометров",
                ],
            ))

        # Stage count mismatch
        mismatch_flags = [f for f in flags if "MISMATCH" in f or "VOLUME" in f]
        if mismatch_flags:
            risks.append(Risk(
                category=RiskCategory.DATA_INTEGRITY,
                source_agent="CompletionsAgent",
                title_en="Completion data inconsistency",
                title_ru="Несоответствие данных по заканчиванию",
                description_en=f"Data mismatch: {mismatch_flags[0]}",
                description_ru=f"Несоответствие данных: {mismatch_flags[0]}",
                probability=3, impact=2,
                mitigation_en=["Verify stage count and volumes against field reports", "Cross-check with pump charts"],
                mitigation_ru=["Проверить количество стадий и объёмы по полевым отчётам", "Сверить с диаграммами закачки"],
            ))

        return risks

    def analyze_production(self, result: dict) -> list[Risk]:
        """Analyze production agent results."""
        risks = []
        data = result.get("extracted_data", {}).get("production", {})
        flags = result.get("quality_flags", [])

        # GOR breakthrough
        gor_flags = [f for f in flags if "GOR" in f and "BREAKTHROUGH" in f]
        if gor_flags:
            risks.append(Risk(
                category=RiskCategory.GEOLOGICAL,
                source_agent="ProductionAgent",
                title_en="Gas-oil ratio breakthrough detected",
                title_ru="Обнаружен прорыв газа (рост газового фактора)",
                description_en=f"GOR increased significantly: {gor_flags[0]}",
                description_ru=f"Значительный рост газового фактора: {gor_flags[0]}",
                probability=4, impact=4,
                mitigation_en=[
                    "Review choke size and production strategy",
                    "Consider gas coning mitigation",
                    "Evaluate reservoir pressure maintenance",
                ],
                mitigation_ru=[
                    "Пересмотреть размер штуцера и стратегию добычи",
                    "Рассмотреть меры по борьбе с конусообразованием",
                    "Оценить поддержание пластового давления",
                ],
            ))

        return risks

    def analyze_directional(self, result: dict) -> list[Risk]:
        """Analyze directional agent results for trajectory risks."""
        risks = []
        data = result.get("extracted_data", {}).get("directional", {})
        flags = result.get("quality_flags", [])

        # High DLS (stuck pipe risk)
        dls_flags = [f for f in flags if "HIGH_DLS" in f]
        if dls_flags:
            max_dls = data.get("max_dls", 0)
            risks.append(Risk(
                category=RiskCategory.TECHNICAL,
                source_agent="DirectionalAgent",
                title_en=f"High dogleg severity: {max_dls:.2f}°/100ft",
                title_ru=f"Высокая интенсивность искривления: {max_dls:.2f}°/100м",
                description_en=f"Maximum DLS of {max_dls:.2f}°/100ft exceeds safe threshold (>8°/100ft). High risk of stuck pipe and casing wear.",
                description_ru=f"Максимальная интенсивность {max_dls:.2f}°/100м превышает безопасный порог (>8°/100м). Высокий риск прихвата и износа обсадной колонны.",
                probability=4, impact=4,
                mitigation_en=[
                    "Implement rigorous hole cleaning program",
                    "Use lubricity additives in mud system",
                    "Consider reaming or back-reaming through high-DLS sections",
                    "Monitor torque and drag closely",
                ],
                mitigation_ru=[
                    "Внедрить строгую программу очистки забоя",
                    "Использовать смазывающие добавки в буровом растворе",
                    "Рассмотреть калибровку участков с высокой интенсивностью",
                    "Вести постоянный мониторинг момента и сопротивления",
                ],
                metadata={"max_dls": max_dls},
            ))

        # Inclination jumps
        inc_flags = [f for f in flags if "INC_JUMP" in f]
        if inc_flags:
            risks.append(Risk(
                category=RiskCategory.DATA_INTEGRITY,
                source_agent="DirectionalAgent",
                title_en="Survey inclination jumps detected",
                title_ru="Обнаружены скачки зенитного угла в инклинометрии",
                description_en=f"Sudden inclination changes: {inc_flags[0]}",
                description_ru=f"Резкие изменения зенитного угла: {inc_flags[0]}",
                probability=3, impact=3,
                mitigation_en=[
                    "Verify survey data quality",
                    "Check MWD/LWD tool calibration",
                    "Consider re-survey if trajectory uncertainty is high",
                ],
                mitigation_ru=[
                    "Проверить качество данных инклинометрии",
                    "Проверить калибровку телеметрии",
                    "Рассмотреть повторную съёмку при высокой неопределённости",
                ],
            ))

        # Survey gaps
        gap_flags = [f for f in flags if "SURVEY_GAP" in f]
        if gap_flags:
            risks.append(Risk(
                category=RiskCategory.DATA_INTEGRITY,
                source_agent="DirectionalAgent",
                title_en="Large gaps in survey data",
                title_ru="Большие пропуски в данных инклинометрии",
                description_en=f"Survey gaps detected: {gap_flags[0]}",
                description_ru=f"Обнаружены пропуски: {gap_flags[0]}",
                probability=2, impact=2,
                mitigation_en=["Request additional survey stations", "Use interpolation with caution"],
                mitigation_ru=["Запросить дополнительные станции съёмки", "Использовать интерполяцию с осторожностью"],
            ))

        return risks

    def analyze_hse(self, result: dict) -> list[Risk]:
        """Analyze HSE agent results for safety risks."""
        risks = []
        data = result.get("extracted_data", {}).get("hse", {})
        counts = data.get("incident_counts", {})
        incidents = data.get("incidents", [])

        # Fatalities
        if counts.get("fatality", 0) > 0:
            risks.append(Risk(
                category=RiskCategory.HSE,
                source_agent="HSEAgent",
                title_en=f"Fatalities recorded: {counts['fatality']}",
                title_ru=f"Зафиксированы смертельные случаи: {counts['fatality']}",
                description_en=f"{counts['fatality']} fatality(ies) recorded. Immediate investigation required.",
                description_ru=f"Зафиксировано {counts['fatality']} смертельных случаев. Требуется немедленное расследование.",
                probability=5, impact=5,
                mitigation_en=[
                    "IMMEDIATE: Halt operations and initiate investigation",
                    "Conduct comprehensive safety audit",
                    "Implement corrective actions before resuming",
                    "Report to regulatory authorities",
                ],
                mitigation_ru=[
                    "НЕМЕДЛЕННО: Остановить работы и начать расследование",
                    "Провести комплексный аудит безопасности",
                    "Внедрить корректирующие меры до возобновления работ",
                    "Сообщить в надзорные органы",
                ],
            ))

        # LTIs
        if counts.get("lti", 0) > 0:
            risks.append(Risk(
                category=RiskCategory.HSE,
                source_agent="HSEAgent",
                title_en=f"Lost Time Injuries: {counts['lti']}",
                title_ru=f"Травмы с потерей трудоспособности: {counts['lti']}",
                description_en=f"{counts['lti']} LTI(s) recorded. Review safety procedures.",
                description_ru=f"Зафиксировано {counts['lti']} травм с потерей трудоспособности. Пересмотреть процедуры безопасности.",
                probability=4, impact=5,
                mitigation_en=[
                    "Conduct LTI root cause analysis",
                    "Review JSA/JHA for high-risk activities",
                    "Enhance safety training and toolbox talks",
                    "Implement additional controls for identified hazards",
                ],
                mitigation_ru=[
                    "Провести анализ первопричин травм",
                    "Пересмотреть JSA/JHA для работ с высоким риском",
                    "Усилить обучение безопасности и производственные совещания",
                    "Внедрить дополнительные меры контроля",
                ],
            ))

        # SIF potentials
        sif_events = [e for e in incidents if e.get("sif_potential")]
        if sif_events:
            risks.append(Risk(
                category=RiskCategory.HSE,
                source_agent="HSEAgent",
                title_en=f"Serious Injury & Fatality (SIF) potentials: {len(sif_events)}",
                title_ru=f"Потенциал тяжёлых травм и смертельных случаев (SIF): {len(sif_events)}",
                description_en=f"{len(sif_events)} events with SIF potential identified. High-severity prevention required.",
                description_ru=f"Выявлено {len(sif_events)} событий с потенциалом SIF. Требуются меры по предотвращению тяжёлых последствий.",
                probability=3, impact=5,
                mitigation_en=[
                    "Implement SIF prevention protocols",
                    "Conduct SIF-specific safety observations",
                    "Review energy isolation procedures",
                    "Enhance dropped object prevention programs",
                ],
                mitigation_ru=[
                    "Внедрить протоколы предотвращения SIF",
                    "Провести целенаправленные наблюдения за безопасностью",
                    "Пересмотреть процедуры изоляции энергии",
                    "Усилить программы предотвращения падений предметов",
                ],
                metadata={"sif_count": len(sif_events)},
            ))

        # Recurring patterns
        patterns = data.get("recurring_patterns", [])
        if patterns:
            for pattern in patterns[:3]:  # Top 3 patterns
                risks.append(Risk(
                    category=RiskCategory.HSE,
                    source_agent="HSEAgent",
                    title_en=f"Recurring safety pattern: {pattern.get('pattern')}",
                    title_ru=f"Повторяющаяся проблема безопасности: {pattern.get('pattern')}",
                    description_en=f"Pattern '{pattern.get('pattern')}' occurred {pattern.get('occurrence_count')} times.",
                    description_ru=f"Проблема '{pattern.get('pattern')}' повторялась {pattern.get('occurrence_count')} раз.",
                    probability=4, impact=3,
                    mitigation_en=[pattern.get("recommendation", "Review procedures")],
                    mitigation_ru=[pattern.get("recommendation", "Пересмотреть процедуры")],
                    metadata=pattern,
                ))

        return risks

    def analyze_quality_flags(self, swarm_result: Any) -> list[Risk]:
        """Analyze cross-domain quality flags."""
        risks = []
        cross_flags = getattr(swarm_result, "cross_domain_flags", [])

        for flag in cross_flags:
            if "CROSS_DOMAIN" in flag:
                # Depth mismatch
                if "depth" in flag.lower() and "mismatch" in flag.lower():
                    risks.append(Risk(
                        category=RiskCategory.DATA_INTEGRITY,
                        source_agent="ReportAgent",
                        title_en="Cross-domain depth mismatch",
                        title_ru="Несоответствие глубин между источниками данных",
                        description_en=flag,
                        description_ru=flag,
                        probability=3, impact=3,
                        mitigation_en=[
                            "Verify depth reference (KB, DF, LAT) across all data sources",
                            "Reconcile drilling and log depth scales",
                        ],
                        mitigation_ru=[
                            "Проверить систему отсчёта глубин (РУ, забой, LAT) во всех источниках",
                            "Согласовать шкалы глубин бурения и ГИС",
                        ],
                    ))
                # Under-stimulation
                elif "under-stimulation" in flag.lower() or "stage" in flag.lower():
                    risks.append(Risk(
                        category=RiskCategory.GEOLOGICAL,
                        source_agent="ReportAgent",
                        title_en="Potential under-stimulation",
                        title_ru="Потенциальная неполная стимуляция",
                        description_en=flag,
                        description_ru=flag,
                        probability=3, impact=3,
                        mitigation_en=[
                            "Review completion design vs. log-identified pay zones",
                            "Consider adding stages to cover bypassed pay",
                        ],
                        mitigation_ru=[
                            "Пересмотреть дизайн заканчивания vs продуктивные интервалы по ГИС",
                            "Рассмотреть добавление стадий для охвата пропущенных интервалов",
                        ],
                    ))

        return risks

    def analyze_rag_warnings(self, swarm_result: Any) -> list[Risk]:
        """Analyze RAG predictive risk warnings from agents."""
        risks = []
        all_flags = getattr(swarm_result, "quality_flags", [])

        rag_flags = [f for f in all_flags if "PREDICTIVE_RISK" in f]
        for flag in rag_flags:
            risks.append(Risk(
                category=RiskCategory.GEOLOGICAL,
                source_agent="RAGAdvisor",
                title_en="Historical pad risk identified",
                title_ru="Выявлен исторический риск по кусту",
                description_en=flag,
                description_ru=flag,
                probability=4, impact=4,
                mitigation_en=[
                    "Review historical well data for this pad",
                    "Implement preventive measures based on offset well experience",
                    "Consider modified mud program or drilling parameters",
                    "Brief drilling team on known hazards",
                ],
                mitigation_ru=[
                    "Изучить исторические данные скважин этого куста",
                    "Внедрить превентивные меры на основе опыта соседних скважин",
                    "Рассмотреть корректировку программы бурового раствора",
                    "Провести инструктаж буровой бригады о известных рисках",
                ],
            ))

        return risks