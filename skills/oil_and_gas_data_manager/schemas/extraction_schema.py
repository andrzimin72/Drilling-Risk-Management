"""
Extraction Output Schema
Defines the canonical output structure for all oil and gas data extractions.
Added strict domain-specific models to enforce data integrity.
"""
from __future__ import annotations
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    class BaseModel: pass
    def Field(*args, **kwargs): return None

# ---------------------------------------------------------------------------
# Phase 3: Domain-Specific Sub-Models
# ---------------------------------------------------------------------------
if HAS_PYDANTIC:
    class PayIntervalSchema(BaseModel):
        top: float
        base: float
        net_pay: float
        depth_unit: str = "ft"
        criteria: str = ""
        confidence: float = 0.6

    class NPTEventSchema(BaseModel):
        description: str
        duration_hrs: Optional[float] = None
        raw_text: Optional[str] = None
        severity: Optional[str] = None

    class SurveyStationSchema(BaseModel):
        md: float
        inc_deg: float
        az_deg: float
        tvd: Optional[float] = None
        north: Optional[float] = None
        east: Optional[float] = None
        dls: Optional[float] = None

    class HSEIncidentSchema(BaseModel):
        severity: str
        description: str
        npt_hrs: Optional[float] = None
        sif_potential: bool = False
        source_file: str = ""

    class DrillingDataSchema(BaseModel):
        well_name: Optional[str] = None
        api: Optional[str] = None
        rig_name: Optional[str] = None
        operator: Optional[str] = None
        field: Optional[str] = None
        current_depth_ft: Optional[float] = None
        current_depth_m: Optional[float] = None
        measured_depth_ft: Optional[float] = None
        measured_depth_m: Optional[float] = None
        rop_ft_hr: Optional[float] = None
        rop_m_hr: Optional[float] = None
        wob_klbs: Optional[float] = None
        wob_tons: Optional[float] = None
        rpm: Optional[float] = None
        mud_weight_ppg: Optional[float] = None
        mud_weight_sg: Optional[float] = None
        npt_events: list[NPTEventSchema] = Field(default_factory=list)
        npt_hours: Optional[float] = None

    class LogsDataSchema(BaseModel):
        well_name: Optional[str] = None
        api: Optional[str] = None
        curve_count: int = 0
        depth_unit: str = "ft"
        total_net_pay: float = 0.0
        pay_zone_count: int = 0
        pay_intervals: list[PayIntervalSchema] = Field(default_factory=list)
        depth_ranges: list[dict[str, Any]] = Field(default_factory=list)

    class CompletionsDataSchema(BaseModel):
        stage_count: Optional[float] = None
        stage_count_actual: Optional[int] = None
        total_fluid_bbls: Optional[float] = None
        total_fluid_m3: Optional[float] = None
        total_proppant_lbs: Optional[float] = None
        total_proppant_tons: Optional[float] = None
        isip_psi: Optional[float] = None
        isip_kpa: Optional[float] = None

    class ProductionDataSchema(BaseModel):
        oil_rate_bopd: Optional[float] = None
        oil_rate_t_day: Optional[float] = None
        gas_rate_mcfd: Optional[float] = None
        gas_rate_m3_day: Optional[float] = None
        ip_metrics: dict[str, float] = Field(default_factory=dict)

    class DirectionalDataSchema(BaseModel):
        total_md: Optional[float] = None
        total_tvd: Optional[float] = None
        max_inc_deg: Optional[float] = None
        max_dls: Optional[float] = None
        raw_stations: list[SurveyStationSchema] = Field(default_factory=list)

    class HSEDataSchema(BaseModel):
        incident_counts: dict[str, int] = Field(default_factory=dict)
        total_npt_hse_hrs: float = 0.0
        trir: Optional[float] = None
        incidents: list[HSEIncidentSchema] = Field(default_factory=list)

# ---------------------------------------------------------------------------
# Core Output Models
# ---------------------------------------------------------------------------
if HAS_PYDANTIC:
    class FileInfoSchema(BaseModel):
        filename: str
        file_type: str = "unknown"
        mime_type: str = "application/octet-stream"
        discipline: str = "unknown"
        document_type: str = "unknown"

    class EntityContextSchema(BaseModel):
        operator: Optional[str] = None
        field: Optional[str] = None
        basin: Optional[str] = None
        pad: Optional[str] = None
        well_name: Optional[str] = None
        api: Optional[str] = None
        report_date: Optional[str] = None

    class TableSchema(BaseModel):
        name: str
        columns: list[str] = Field(default_factory=list)
        rows: list[list[Any]] = Field(default_factory=list)
        note: Optional[str] = None
        total_rows: Optional[int] = None

    class ReferenceSchema(BaseModel):
        source_section: str
        page_or_depth_range: str = ""
        confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    class ExtractionOutput(BaseModel):
        """Full extraction output for one file."""
        project_match: dict[str, Any] = Field(default_factory=dict)
        file_info: dict[str, Any] = Field(default_factory=dict)
        entity_context: dict[str, Any] = Field(default_factory=dict)
        extracted_data: dict[str, Any] = Field(default_factory=dict)
        tables: list[dict[str, Any]] = Field(default_factory=list)
        references: list[dict[str, Any]] = Field(default_factory=list)
        quality_flags: list[str] = Field(default_factory=list)

        @classmethod
        def empty(cls, filename: str = "") -> "ExtractionOutput":
            return cls(file_info={"filename": filename}, quality_flags=["EMPTY_EXTRACTION"])
else:
    class ExtractionOutput:
        def __init__(self, **kwargs: Any) -> None:
            self.project_match = kwargs.get("project_match", {})
            self.file_info = kwargs.get("file_info", {})
            self.entity_context = kwargs.get("entity_context", {})
            self.extracted_data = kwargs.get("extracted_data", {})
            self.tables = kwargs.get("tables", [])
            self.references = kwargs.get("references", [])
            self.quality_flags = kwargs.get("quality_flags", [])

        def model_dump(self) -> dict[str, Any]:
            return {k: v for k, v in self.__dict__.items()}

        @classmethod
        def empty(cls, filename: str = "") -> "ExtractionOutput":
            return cls(file_info={"filename": filename}, quality_flags=["EMPTY_EXTRACTION"])
