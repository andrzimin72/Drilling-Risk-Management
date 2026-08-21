"""
Swarm Demo Script
Demonstrates all swarm patterns including the new Risk Management system.
Run: python -m swarms.demo
"""
from __future__ import annotations
import asyncio
import json
import logging
import sys
import tempfile
import textwrap
from pathlib import Path

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Pillar 3: Initialize OpenTelemetry
try:
    from skills.oil_and_gas_data_manager.telemetry import init_telemetry
    init_telemetry(service_name="oil_gas_swarm_demo", enable_console_exporter=False)
    logger.info("✓ OpenTelemetry initialized")
except ImportError:
    logger.warning("OpenTelemetry not installed. Tracing disabled.")


# ---------------------------------------------------------------------------
# Synthetic test file generators
# ---------------------------------------------------------------------------
def make_ddr(tmp_dir: Path, name: str = "DDR_Demo_Day01.txt") -> Path:
    f = tmp_dir / name
    f.write_text(textwrap.dedent("""
    DAILY DRILLING REPORT
    Operator: Demo Energy Corp
    Well Name: Demo Well A12H
    API Number: 42-888-77777-0000
    Rig Name: Demo Rig 5
    Report Date: March 1, 2025
    Current Depth: 12,450 ft MD
    True Vertical Depth: 9,820 ft TVD
    Rate of Penetration (ROP): 145 ft/hr
    Weight on Bit (WOB): 22 klbs
    Rotary Speed (RPM): 185 rpm
    Standpipe Pressure (SPP): 3,850 psi
    Mud Weight (In): 10.8 ppg
    Mud Weight (Out): 10.9 ppg
    NPT: Pump failure - liner replaced: 2.5 hrs
    NPT: Wellbore instability / tight hole: 1.2 hrs
    Total NPT: 3.7 hrs
    Near miss: Dropped 3-lb slip from rig floor (12 ft height). No injury.
    20 inch surface casing set at 2,400 ft
    13-3/8 inch intermediate casing set at 7,200 ft
    BHA: 8.5 PDC Bit / 9.5 NBS / 6.75 MWD / 6.75 Motor / 5 HWDP
    """))
    return f


def make_russian_ddr(tmp_dir: Path) -> Path:
    f = tmp_dir / "Ежсуточный_отчет_Скважина123.txt"
    f.write_text(textwrap.dedent("""
    ЕЖСУТОЧНЫЙ ОТЧЕТ БУРЕНИЯ
    Заказчик: Газпром нефть
    Скважина: 123
    Куст: 5
    Месторождение: Приобское
    Дата отчета: 31 июля 2026
    Текущая глубина: 3245,6 м
    Механическая скорость: 45 м/ч
    Нагрузка на долото: 18 т
    Плотность бурового раствора: 1,18 г/см3
    НПТ: 2.5 час - отказ насоса
    Инцидент: Микронепроизводство - падение инструмента. Пострадавших нет.
    """))
    return f


def make_survey(tmp_dir: Path) -> Path:
    f = tmp_dir / "survey_A12H.csv"
    f.write_text(
        "MD,INC,AZ\n"
        + "\n".join(
            f"{md},{inc},{az}"
            for md, inc, az in [
                (0, 0, 45), (500, 0.3, 45), (1000, 0.8, 46), (2000, 4.2, 47),
                (3000, 18.5, 48), (4000, 45.2, 49), (5000, 72.8, 50),
                (6000, 89.1, 51), (7000, 90.0, 51), (8000, 90.2, 52),
                (9000, 90.4, 52), (10000, 90.6, 53), (11000, 90.3, 53),
                (12450, 90.5, 53),
            ]
        )
    )
    return f


def make_high_dls_survey(tmp_dir: Path) -> Path:
    """Survey with high DLS to trigger trajectory risks."""
    f = tmp_dir / "survey_high_dls.csv"
    f.write_text(
        "MD,INC,AZ\n"
        + "\n".join(
            f"{md},{inc},{az}"
            for md, inc, az in [
                (0, 0, 45), (500, 0.5, 46), (1000, 15.0, 48),  # Big jump
                (1500, 45.0, 50), (2000, 85.0, 52), (2500, 90.0, 53),
            ]
        )
    )
    return f


def make_metric_las(tmp_dir: Path) -> Path:
    f = tmp_dir / "gis_123.las"
    f.write_text(textwrap.dedent("""
    ~Version ---------------------------------------------------
    VERS.               2.0 : LAS, Version 2.0
    WRAP.               NO  : ONE LINE PER DEPTH STEP
    ~Well ------------------------------------------------------
    WELL.               СКВАЖИНА 123       : WELL NAME
    COMP.               ГАЗПРОМ НЕФТЬ      : COMPANY
    FLD.                PRIOBSKOYE         : FIELD
    STRT.  M            2000.0             : START DEPTH
    STOP.  M            2010.0             : STOP DEPTH
    STEP.  M            0.5                : STEP
    NULL.               -999.25            : NULL VALUE
    ~Curve -----------------------------------------------------
    DEPT.  M            : MEASURED DEPTH
    GR  .  GAPI         : GAMMA RAY
    RT  .  OHMM         : TRUE RESISTIVITY
    ~ASCII -----------------------------------------------------
    2000.0   80.0   5.0
    2001.0   70.0  15.0
    2002.0   50.0  25.0
    2003.0   85.0   4.0
    2004.0   40.0  30.0
    2005.0   65.0  12.0
    2006.0   55.0  20.0
    2007.0   72.0   8.0
    2008.0   48.0  28.0
    2009.0   60.0  18.0
    2010.0   75.0   6.0
    """))
    return f


def make_completion(tmp_dir: Path) -> Path:
    f = tmp_dir / "completion_A12H.csv"
    rows = ["Stage,Fluid_bbls,Proppant_lbs,ISIP_psi,Clusters"]
    for i in range(1, 9):
        rows.append(f"{i},{1800+i*50},{950000+i*20000},{6800+i*20},{4}")
    f.write_text("\n".join(rows))
    return f


def make_production(tmp_dir: Path) -> Path:
    f = tmp_dir / "production_A12H.csv"
    rows = ["Month,Oil_BOPD,Gas_MCFD,Water_BWPD"]
    for mo, oil, gas, water in [
        (1, 1050, 1800, 95), (2, 920, 1650, 110), (3, 800, 1500, 130),
        (4, 710, 1380, 145), (5, 640, 1250, 160), (6, 580, 1150, 175),
    ]:
        rows.append(f"Month_{mo},{oil},{gas},{water}")
    f.write_text("\n".join(rows))
    return f


# ---------------------------------------------------------------------------
# Demo 9: Risk Management Report (NEW!)
# ---------------------------------------------------------------------------
async def demo_risk_management(files: list[Path]) -> None:
    """Demo 9: Full risk management workflow with Word report generation."""
    from swarms.orchestrator import OrchestratorAgent, SwarmContext

    print("\n" + "=" * 60)
    print("DEMO 9: Risk Management & Word Report Generation (Pillar 4)")
    print("=" * 60)

    orchestrator = OrchestratorAgent(
        verbose=True,
        risk_management_enabled=True,
        report_language="ru",  # Russian for Gazprom Neft
    )
    ctx = SwarmContext(well_name="Demo Well A12H", api="42-888-77777-0000")

    # Run swarm with risk report generation
    result = await orchestrator.run(
        files,
        ctx,
        generate_risk_report=True,
        report_output_path="demo_risk_report.docx",
    )

    print("\n--- RISK ANALYSIS RESULTS ---")
    if result.risk_registry:
        summary = result.risk_registry.get_summary()
        print(f"Total risks identified: {summary['total_risks']}")
        print(f"  Critical: {summary['critical_count']}")
        print(f"  High: {summary['high_count']}")
        print(f"  Medium: {summary['by_level'].get('medium', 0)}")
        print(f"  Low: {summary['by_level'].get('low', 0)}")
        print(f"Average risk score: {summary['risk_score']}/25")

        # Show top 5 risks
        top_risks = result.risk_registry.get_risks()[:5]
        if top_risks:
            print("\n--- TOP 5 RISKS ---")
            for i, risk in enumerate(top_risks, 1):
                level_display = risk.risk_level.display_name_ru
                print(f"  {i}. [{risk.risk_id}] {risk.title_ru}")
                print(f"     Level: {level_display} | P={risk.probability} × I={risk.impact}")
                print(f"     Source: {risk.source_agent}")
    else:
        print("Risk registry not available.")

    if result.risk_report_path:
        print(f"\n✓ Word report generated: {result.risk_report_path}")
        print("  Open this file in Microsoft Word to view the full branded report.")
    else:
        print("\n✗ Word report generation failed or python-docx not installed.")

    # Also export JSON
    if result.risk_registry:
        json_path = Path("demo_risk_registry.json")
        result.risk_registry.export_json(json_path)
        print(f"✓ Risk registry exported to JSON: {json_path}")


# ---------------------------------------------------------------------------
# Existing demos (abbreviated for space)
# ---------------------------------------------------------------------------
async def demo_file_analysis(files: list[Path]) -> None:
    from swarms.patterns.file_analysis_swarm import FileAnalysisSwarm
    print("\n" + "=" * 60)
    print("DEMO 1: File Analysis Swarm")
    print("=" * 60)
    swarm = FileAnalysisSwarm(verbose=True)
    result = await swarm.run(files, well_name="Demo Well A12H", api="42-888-77777-0000")
    print("\n--- REPORT ---")
    print(result.unified_report[:1500])


async def demo_russian_metric(files: list[Path]) -> None:
    from swarms.patterns.file_analysis_swarm import FileAnalysisSwarm
    print("\n" + "=" * 60)
    print("DEMO 2: File Analysis Swarm (Russian/Metric — Gazprom Neft)")
    print("=" * 60)
    swarm = FileAnalysisSwarm(verbose=True)
    result = await swarm.run(files, well_name="123", pad="5")
    print("\n--- REPORT ---")
    print(result.unified_report[:1500])


async def demo_well_performance(files: list[Path]) -> None:
    from swarms.patterns.well_performance_swarm import WellPerformanceSwarm
    print("\n" + "=" * 60)
    print("DEMO 3: Well Performance Swarm")
    print("=" * 60)
    swarm = WellPerformanceSwarm(
        well_name="Demo Well A12H", api="42-888-77777-0000",
        lateral_length_ft=5250, total_manhours=8760, verbose=True,
    )
    result = await swarm.run(files)
    print("\n--- PERFORMANCE REPORT ---")
    print(result.unified_report[:2000])


async def demo_qa_swarm(files: list[Path]) -> None:
    from swarms.patterns.qa_swarm import QASwarm
    print("\n" + "=" * 60)
    print("DEMO 4: QA Swarm")
    print("=" * 60)
    swarm = QASwarm(verbose=False)
    result = await swarm.run(files)
    print(result.unified_report[:2000])


async def demo_pad_analysis(files_per_well: dict[str, list[Path]]) -> None:
    from swarms.patterns.pad_analysis_swarm import PadAnalysisSwarm
    print("\n" + "=" * 60)
    print("DEMO 5: Pad Analysis Swarm (parallel wells)")
    print("=" * 60)
    swarm = PadAnalysisSwarm(pad_name="South Pad A", operator="Demo Energy Corp", verbose=True)
    result = await swarm.run({k: [str(p) for p in v] for k, v in files_per_well.items()})
    print(f"\nPad: {result['pad_name']}")
    print(f"Wells analyzed: {result['well_count']}")
    print("Pad summary: ", json.dumps(result.get("pad_summary", {}), indent=2))


async def demo_eow_report(files: list[Path]) -> None:
    from swarms.patterns.end_of_well_swarm import EndOfWellSwarm
    print("\n" + "=" * 60)
    print("DEMO 6: End-of-Well Report Swarm")
    print("=" * 60)
    swarm = EndOfWellSwarm(
        well_name="Demo Well A12H", api="42-888-77777-0000",
        operator="Demo Energy Corp", lateral_length_ft=5250, verbose=False,
    )
    result = await swarm.run(files)
    print(result.unified_report[:3000])


async def demo_checkpoint_recovery(files: list[Path]) -> None:
    from swarms.orchestrator import OrchestratorAgent, SwarmContext
    print("\n" + "=" * 60)
    print("DEMO 7: Checkpoint Recovery (Pillar 3)")
    print("=" * 60)

    print("\n--- First run ---")
    orchestrator = OrchestratorAgent(verbose=True, checkpoint_enabled=True)
    ctx = SwarmContext(well_name="Demo Well A12H")
    result1 = await orchestrator.run(files, ctx)
    print(f"Task ID: {result1.task_id}, Elapsed: {result1.elapsed_seconds}s")

    print("\n--- Second run (should restore from checkpoint) ---")
    orchestrator2 = OrchestratorAgent(verbose=True, checkpoint_enabled=True)
    ctx2 = SwarmContext(well_name="Demo Well A12H")
    result2 = await orchestrator2.run(files, ctx2)
    print(f"Task ID: {result2.task_id}, Elapsed: {result2.elapsed_seconds}s")


async def demo_rag_risk_advisor(files: list[Path]) -> None:
    print("\n" + "=" * 60)
    print("DEMO 8: RAG Predictive Risk Advisor (Pillar 2)")
    print("=" * 60)

    try:
        from skills.oil_and_gas_data_manager.rag_risk_advisor import PadRiskAdvisor
        advisor = PadRiskAdvisor()

        print("\n--- Ingesting historical NPT from Well 122 ---")
        historical_npt = [
            {"description": "Stuck pipe due to shale swelling at 3100m", "duration_hrs": 24.0, "severity": "lti"},
            {"description": "Mud losses at 3150m, lost 50 m3", "duration_hrs": 12.0, "severity": "mtc"},
        ]
        ingested = advisor.ingest_well_npt("Куст 5", "122", historical_npt, current_depth_m=3200.0)
        print(f"Ingested {ingested} NPT events.")

        print("\n--- Querying risks for Well 123 at 3150m ---")
        risks = advisor.query_risks("Куст 5", current_depth_m=3150.0, depth_tolerance_m=200.0)
        if risks:
            print(f"Found {len(risks)} historical risk(s):")
            for risk in risks:
                print(f"  • Well {risk['historical_well']} at {risk['historical_depth_m']}m: "
                      f"{risk['description'][:80]}... (similarity: {risk['similarity_score']})")
        else:
            print("No historical risks found.")
    except ImportError:
        print("ChromaDB not installed. RAG features disabled.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Oil and Gas Agent Swarm — Enterprise Demo")
    print("Featuring: Bilingual, Unit-Agnostic, Telemetry, Checkpointing,")
    print("           Vision LLM, RAG, and Risk Management (Pillar 4)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Generate test files
        ddr = make_ddr(tmp_path)
        ru_ddr = make_russian_ddr(tmp_path)
        survey = make_survey(tmp_path)
        high_dls_survey = make_high_dls_survey(tmp_path)
        las = make_metric_las(tmp_path)
        completion = make_completion(tmp_path)
        production = make_production(tmp_path)

        all_files = [ddr, survey, completion, production]
        ru_files = [ru_ddr, las]
        risk_files = [ddr, high_dls_survey, las, completion, production]

        print(f"\n✓ Created {len(all_files)} English/Imperial test files")
        print(f"✓ Created {len(ru_files)} Russian/Metric test files")
        print(f"✓ Created {len(risk_files)} files for risk demo (incl. high DLS)")

        mode = sys.argv[1] if len(sys.argv) > 1 else "all"

        if mode in ("all", "1", "file"):
            await demo_file_analysis(all_files)
        if mode in ("all", "2", "russian"):
            await demo_russian_metric(ru_files)
        if mode in ("all", "3", "well"):
            await demo_well_performance(all_files)
        if mode in ("all", "4", "qa"):
            await demo_qa_swarm(all_files)
        if mode in ("all", "5", "pad"):
            ddr2 = make_ddr(tmp_path, "DDR_Demo_A13H.txt")
            await demo_pad_analysis({
                "A12H": [ddr, survey, completion, production],
                "A13H": [ddr2],
            })
        if mode in ("all", "6", "eow"):
            await demo_eow_report(all_files)
        if mode in ("all", "7", "checkpoint"):
            await demo_checkpoint_recovery(all_files)
        if mode in ("all", "8", "rag"):
            await demo_rag_risk_advisor(ru_files)
        if mode in ("all", "9", "risk"):
            await demo_risk_management(risk_files)

    print("\n" + "=" * 60)
    print("Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())