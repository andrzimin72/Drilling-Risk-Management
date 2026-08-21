"""
Localization and Unit Configuration
Allows the swarm to switch between US/Imperial and Russian/Metric standards.
"""
from dataclasses import dataclass, field

@dataclass
class LocalizationProfile:
    name: str
    language: str  # "en" or "ru"
    unit_system: str  # "imperial" or "metric"
    
    # Keyword dictionaries for discipline classification
    drilling_keywords: set[str] = field(default_factory=set)
    completion_keywords: set[str] = field(default_factory=set)
    production_keywords: set[str] = field(default_factory=set)
    survey_keywords: set[str] = field(default_factory=set)
    hse_keywords: set[str] = field(default_factory=set)

    # Sanity check limits (mapped to canonical internal units)
    sanity_limits: dict[str, tuple[float, float]] = field(default_factory=dict)

# --- US / Imperial Profile ---
US_ENGLISH_PROFILE = LocalizationProfile(
    name="US_ENGLISH",
    language="en",
    unit_system="imperial",
    drilling_keywords={
        "daily drilling report", "ddr", "morning report", "operations summary",
        "bit record", "npt", "weight on bit", "standpipe pressure",
        "mud weight", "rate of penetration", "rop", "bha",
    },
    completion_keywords={
        "frac", "stage", "cluster", "perforation", "proppant",
        "plug and perf", "toe sleeve", "stimulation", "pump schedule",
        "slurry rate", "isip", "treating pressure",
    },
    production_keywords={
        "oil rate", "gas rate", "water rate", "production test",
        "allocation", "separator test", "choke", "gor", "water cut",
        "tubing pressure", "casing pressure", "bopd", "mcfd",
    },
    survey_keywords={
        "survey station", "inclination", "azimuth", "dogleg",
        "measured depth", "true vertical depth", "northing", "easting",
        "trajectory", "minimum curvature",
    },
    hse_keywords={
        "incident", "near miss", "injury", "h2s", "safety stop", "lti",
    },
    sanity_limits={
        "mud_weight_ppg": (6.0, 22.0),
        "rop_ft_hr": (0.0, 1000.0),
        "depth_ft": (0.0, 50000.0),
    }
)

# --- Russian / Metric Profile (Gazprom Neft Standard) ---
RU_METRIC_PROFILE = LocalizationProfile(
    name="RU_METRIC",
    language="ru",
    unit_system="metric",
    drilling_keywords={
        "ежсуточный отчет", "еср", "утренний отчет", "отчет о бурении",
        "долото", "нпт", "нагрузка на крюке", "вес на крюке", "осевая нагрузка",
        "давление на стояке", "плотность бурового раствора", "механическая скорость",
        "рейс", "кпбт", "забой", "бурильная колонна",
    },
    completion_keywords={
        "грп", "гидроразрыв", "стадия", "кластер", "перфорация", "проппант",
        "цементирование", "стимуляция", "закачка", "устьевое давление",
        "мгнт", "давление остановки", "агент", "жидкость",
    },
    production_keywords={
        "дебит нефти", "дебит газа", "дебит воды", "испытание",
        "газовый фактор", "обводненность", "буферное давление",
        "затрубное давление", "т/сут", "тыс. м3/сут", "м3/сут",
    },
    survey_keywords={
        "инклинометрия", "зенитный угол", "азимут", "интенсивность",
        "искривление", "глубина по стволу", "истинная вертикальная глубина",
        "отход", "траектория", "минимальная кривизна", "твг", "мд",
    },
    hse_keywords={
        "инцидент", "микронепроизводство", "травма", "сероводород", "h2s",
        "остановка работ", "потеря времени", "охрана труда", "промышленная безопасность",
    },
    sanity_limits={
        "mud_weight_sg": (1.0, 2.8),      # Specific Gravity (g/cm3)
        "rop_m_hr": (0.0, 100.0),         # Meters per hour
        "depth_m": (0.0, 15000.0),        # Meters
    }
)

# --- Unit Conversion Utilities ---
def convert_depth(value: float, from_unit: str, to_unit: str = "m") -> float:
    """Convert depth values."""
    if from_unit == to_unit:
        return value
    if from_unit == "ft" and to_unit == "m":
        return value * 0.3048
    if from_unit == "m" and to_unit == "ft":
        return value / 0.3048
    return value

def convert_mud_weight(value: float, from_unit: str, to_unit: str = "sg") -> float:
    """Convert mud weight between ppg, sg, and kg/m3."""
    if from_unit == to_unit:
        return value
    # PPG to SG (Specific Gravity)
    if from_unit == "ppg" and to_unit == "sg":
        return value * 0.1198
    if from_unit == "sg" and to_unit == "ppg":
        return value / 0.1198
    return value

# Global active profile (can be changed at runtime via SwarmContext)
ACTIVE_PROFILE = US_ENGLISH_PROFILE 

def set_active_profile(profile_name: str):
    global ACTIVE_PROFILE
    if profile_name == "RU_METRIC":
        ACTIVE_PROFILE = RU_METRIC_PROFILE
    else:
        ACTIVE_PROFILE = US_ENGLISH_PROFILE