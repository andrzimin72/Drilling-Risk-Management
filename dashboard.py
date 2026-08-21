"""
Drilling Risk Management Dashboard — Enterprise Edition
Features:
  • Interactive analysis with drag-and-drop upload
  • Live 5×5 risk matrix (Plotly heatmap)
  • Trend charts (NPT Pareto, DLS by depth)
  • Well comparison (up to 3 wells side-by-side)
  • Analysis history (SQLite persistent storage)
  • Export: Word / PDF / JSON / CSV

Run:
  streamlit run dashboard.py
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("dashboard")

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    from skills.oil_and_gas_data_manager.telemetry import init_telemetry
    init_telemetry(service_name="oil_gas_dashboard", enable_console_exporter=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
I18N = {
    "en": {
        "title": "🛢️ Drilling Risk Management System",
        "subtitle": "Multi-agent platform for automated drilling risk analysis",
        "settings": "⚙️ Settings",
        "language": "Language / Язык",
        "well_name": "Well Name",
        "pad_name": "Pad / Cluster",
        "gr_cutoff": "GR Cutoff (API)",
        "rt_cutoff": "RT Cutoff (ohm·m)",
        "tab_analysis": "📊 Analysis",
        "tab_trends": "📈 Trends",
        "tab_comparison": "🔄 Well Comparison",
        "tab_history": "📚 History",
        "upload": "📁 Upload Files",
        "upload_hint": "Drag & drop PDF, LAS, CSV, XLSX, DOCX files here",
        "analyze": "🚀 Analyze Files",
        "analyzing": "Analyzing...",
        "processing_file": "Processing files through agent swarm...",
        "results": "📊 Analysis Results",
        "risk_matrix": "🎯 Risk Matrix (5×5)",
        "identified_risks": "⚠️ Identified Risks",
        "no_risks": "✅ No significant risks identified",
        "filter_level": "Filter by risk level",
        "filter_category": "Filter by category",
        "export": "📥 Export Report",
        "export_word": "Word (.docx)",
        "export_pdf": "PDF (.pdf)",
        "export_json": "JSON",
        "export_csv": "CSV",
        "agent_progress": "🔧 Agent Progress",
        "critical": "Critical", "high": "High", "medium": "Medium", "low": "Low",
        "probability": "Probability", "impact": "Impact",
        "total_risks": "Total Risks",
        "risk_score": "Risk Score",
        "files_processed": "Files Processed",
        "elapsed_time": "Analysis Time",
        "no_files": "Please upload files to begin analysis.",
        "analysis_complete": "✅ Analysis complete",
        "error": "❌ Error during analysis",
        # Trends
        "trends_title": "📈 Trend Charts",
        "npt_pareto": "NPT Pareto Analysis",
        "npt_pareto_hint": "Non-productive time by event category (sorted by duration)",
        "dls_by_depth": "Dogleg Severity by Depth",
        "dls_by_depth_hint": "DLS profile along the wellbore — high values indicate stuck pipe risk",
        "npt_by_category": "NPT Distribution",
        "no_trend_data": "No trend data available. Run an analysis first.",
        "dls_safe": "Safe zone (< 5°/100ft)",
        "dls_caution": "Caution (5-8°/100ft)",
        "dls_danger": "Danger (> 8°/100ft)",
        "depth_m": "Depth (MD)",
        "dls_label": "DLS (°/100ft)",
        "npt_hours_label": "NPT (hours)",
        "cumulative_pct": "Cumulative %",
        # Comparison
        "comparison_title": "🔄 Well Comparison",
        "select_wells": "Select wells to compare (up to 3)",
        "no_history": "No analysis history available. Run analyses first to enable comparison.",
        "compare_btn": "Compare Wells",
        "metric": "Metric",
        "comparison_chart": "Risk Level Comparison",
        "comparison_table": "Metrics Comparison",
        # History
        "history_title": "📚 Analysis History",
        "history_empty": "No analyses saved yet.",
        "load_analysis": "Load",
        "delete_analysis": "Delete",
        "saved_to_history": "💾 Analysis saved to history",
        "date": "Date",
        "well": "Well",
        "pad": "Pad",
        "files": "Files",
        "risks": "Risks",
        "actions": "Actions",
        "about": "ℹ️ About",
        "about_text": (
            "This system uses a multi-agent AI swarm to analyze oil & gas "
            "engineering data and automatically identify, score, and visualize "
            "drilling risks. Supports bilingual (EN/RU) operation."
        ),
    },
    "ru": {
        "title": "🛢️ Система управления рисками бурения",
        "subtitle": "Мультиагентная платформа для автоматического анализа рисков",
        "settings": "⚙️ Настройки",
        "language": "Язык / Language",
        "well_name": "Скважина",
        "pad_name": "Куст",
        "gr_cutoff": "Отсечка ГК (API)",
        "rt_cutoff": "Отсечка ИС (Ом·м)",
        "tab_analysis": "📊 Анализ",
        "tab_trends": "📈 Тренды",
        "tab_comparison": "🔄 Сравнение скважин",
        "tab_history": "📚 История",
        "upload": "📁 Загрузить файлы",
        "upload_hint": "Перетащите PDF, LAS, CSV, XLSX, DOCX файлы сюда",
        "analyze": "🚀 Анализировать",
        "analyzing": "Анализ...",
        "processing_file": "Обработка файлов агентным роем...",
        "results": "📊 Результаты анализа",
        "risk_matrix": "🎯 Матрица рисков (5×5)",
        "identified_risks": "⚠️ Выявленные риски",
        "no_risks": "✅ Существенных рисков не выявлено",
        "filter_level": "Фильтр по уровню риска",
        "filter_category": "Фильтр по категории",
        "export": "📥 Экспорт отчёта",
        "export_word": "Word (.docx)",
        "export_pdf": "PDF (.pdf)",
        "export_json": "JSON",
        "export_csv": "CSV",
        "agent_progress": "🔧 Прогресс агентов",
        "critical": "Критический", "high": "Высокий", "medium": "Средний", "low": "Низкий",
        "probability": "Вероятность", "impact": "Влияние",
        "total_risks": "Всего рисков",
        "risk_score": "Оценка риска",
        "files_processed": "Обработано файлов",
        "elapsed_time": "Время анализа",
        "no_files": "Загрузите файлы для начала анализа.",
        "analysis_complete": "✅ Анализ завершён",
        "error": "❌ Ошибка при анализе",
        # Trends
        "trends_title": "📈 Графики трендов",
        "npt_pareto": "Парето-анализ НПТ",
        "npt_pareto_hint": "Непроизводительное время по категориям событий (по убыванию длительности)",
        "dls_by_depth": "Интенсивность искривления по глубине",
        "dls_by_depth_hint": "Профиль DLS вдоль ствола — высокие значения указывают на риск прихвата",
        "npt_by_category": "Распределение НПТ",
        "no_trend_data": "Нет данных для трендов. Сначала выполните анализ.",
        "dls_safe": "Безопасная зона (< 5°/100м)",
        "dls_caution": "Внимание (5-8°/100м)",
        "dls_danger": "Опасно (> 8°/100м)",
        "depth_m": "Глубина (МД)",
        "dls_label": "DLS (°/100м)",
        "npt_hours_label": "НПТ (часы)",
        "cumulative_pct": "Накопленный %",
        # Comparison
        "comparison_title": "🔄 Сравнение скважин",
        "select_wells": "Выберите скважины для сравнения (до 3)",
        "no_history": "Нет истории анализов. Выполните анализы для активации сравнения.",
        "compare_btn": "Сравнить скважины",
        "metric": "Показатель",
        "comparison_chart": "Сравнение уровней рисков",
        "comparison_table": "Сравнение показателей",
        # History
        "history_title": "📚 История анализов",
        "history_empty": "Сохранённых анализов пока нет.",
        "load_analysis": "Загрузить",
        "delete_analysis": "Удалить",
        "saved_to_history": "💾 Анализ сохранён в историю",
        "date": "Дата",
        "well": "Скважина",
        "pad": "Куст",
        "files": "Файлы",
        "risks": "Риски",
        "actions": "Действия",
        "about": "ℹ️ О системе",
        "about_text": (
            "Система использует мультиагентный ИИ для анализа инженерных "
            "данных скважин и автоматического выявления, оценки и визуализации "
            "рисков бурения. Поддерживает двуязычный режим (RU/EN)."
        ),
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("language", "ru")
    return I18N.get(lang, I18N["ru"]).get(key, key)


# ---------------------------------------------------------------------------
# Page config & branding
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Oil & Gas Risk Dashboard",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #004C97; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #666; margin-bottom: 1.5rem; }
    .stButton>button {
        background-color: #0072CE; color: white; font-weight: 600;
        border-radius: 8px; padding: 0.5rem 1.5rem;
    }
    .stButton>button:hover { background-color: #004C97; }
    .metric-highlight {
        background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
        padding: 1rem; border-radius: 10px; border-left: 4px solid #0072CE;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
defaults = {
    "language": "ru",
    "analysis_result": None,
    "risk_registry": None,
    "metrics": None,
    "uploaded_files": [],
    "analysis_in_progress": False,
    "history": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# Initialize history manager
try:
    from analysis_history import AnalysisHistory, extract_metrics_from_result
    if st.session_state.history is None:
        st.session_state.history = AnalysisHistory()
    HAS_HISTORY = True
except ImportError:
    HAS_HISTORY = False

try:
    from pdf_export import export_to_pdf, generate_html_report
    HAS_PDF_EXPORT = True
except ImportError:
    HAS_PDF_EXPORT = False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### {t('settings')}")

    lang_options = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
    selected_lang = st.selectbox(
        t("language"),
        options=list(lang_options.keys()),
        format_func=lambda x: lang_options[x],
        index=0 if st.session_state.language == "ru" else 1,
    )
    st.session_state.language = selected_lang

    st.divider()
    well_name = st.text_input(t("well_name"), value="", placeholder="123")
    pad_name = st.text_input(t("pad_name"), value="", placeholder="5")

    st.divider()
    st.markdown("**Petrophysics**")
    gr_cutoff = st.slider(t("gr_cutoff"), 30, 150, 75, step=5)
    rt_cutoff = st.slider(t("rt_cutoff"), 1, 50, 10, step=1)

    st.divider()
    with st.expander(t("about")):
        st.info(t("about_text"))
        st.caption("v2.0.0 | Enterprise Edition")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(f'<div class="main-header">{t("title")}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">{t("subtitle")}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_analysis, tab_trends, tab_comparison, tab_history = st.tabs([
    t("tab_analysis"),
    t("tab_trends"),
    t("tab_comparison"),
    t("tab_history"),
])


# ===========================================================================
# TAB 1: ANALYSIS
# ===========================================================================
with tab_analysis:
    # File upload
    st.markdown(f"### {t('upload')}")
    uploaded_files = st.file_uploader(
        t("upload_hint"),
        type=["pdf", "las", "csv", "xlsx", "xls", "docx", "txt", "dlis", "lis"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        st.success(f"✅ {len(uploaded_files)} file(s) ready")
        with st.expander(f"📄 {len(uploaded_files)} files"):
            for f in uploaded_files:
                st.caption(f"• {f.name} ({f.size / 1024:.1f} KB)")
    else:
        st.info(t("no_files"))

    # Analyze button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_clicked = st.button(
            t("analyze"),
            disabled=not uploaded_files or st.session_state.analysis_in_progress,
            use_container_width=True,
        )

    # Run analysis
    if analyze_clicked and uploaded_files:
        st.session_state.analysis_in_progress = True
        progress_bar = st.progress(0, text=t("processing_file"))

        try:
            # Save files to temp dir
            tmp_dir = tempfile.mkdtemp(prefix="og_dash_")
            saved_paths = []
            for f in uploaded_files:
                p = Path(tmp_dir) / f.name
                p.write_bytes(f.getvalue())
                saved_paths.append(p)

            for i in range(5):
                time.sleep(0.05)
                progress_bar.progress((i + 1) / 10)

            # Import and run swarm
            from swarms.orchestrator import OrchestratorAgent, SwarmContext

            ctx = SwarmContext(
                well_name=well_name or None,
                pad=pad_name or None,
                gr_cutoff=gr_cutoff,
                rt_cutoff=rt_cutoff,
            )
            orchestrator = OrchestratorAgent(
                verbose=False,
                risk_management_enabled=True,
                report_language=st.session_state.language,
            )

            progress_bar.progress(0.6, text="Running agent swarm...")
            result = asyncio.run(orchestrator.run(saved_paths, ctx))

            progress_bar.progress(0.8, text="Extracting metrics...")
            metrics = extract_metrics_from_result(result, result.risk_registry)

            st.session_state.analysis_result = result
            st.session_state.risk_registry = result.risk_registry
            st.session_state.metrics = metrics

            # Save to history
            if HAS_HISTORY and st.session_state.history:
                risk_data = []
                if result.risk_registry:
                    risk_data = [r.to_dict() for r in result.risk_registry.risks]
                    risk_summary = result.risk_registry.get_summary()
                else:
                    risk_summary = {}

                st.session_state.history.save_analysis(
                    task_id=result.task_id,
                    well_name=well_name,
                    pad_name=pad_name,
                    operator=None,
                    files_processed=result.files_processed,
                    elapsed_seconds=result.elapsed_seconds,
                    agents_succeeded=result.agents_succeeded,
                    agents_failed=result.agents_failed,
                    risk_summary=risk_summary,
                    risk_registry_data=risk_data,
                    metrics=metrics,
                    report_path=None,
                )
                st.toast(t("saved_to_history"), icon="💾")

            progress_bar.progress(1.0, text=t("analysis_complete"))
            st.success(t("analysis_complete"))

        except Exception as exc:
            logger.exception("Analysis failed")
            st.error(f"{t('error')}: {exc}")
        finally:
            st.session_state.analysis_in_progress = False

    # Display results
    if st.session_state.analysis_result is not None:
        result = st.session_state.analysis_result
        registry = st.session_state.risk_registry
        metrics = st.session_state.metrics or {}

        st.divider()
        st.markdown(f"## {t('results')}")

        # Summary metrics
        if registry:
            summary = registry.get_summary()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("total_risks"), summary["total_risks"])
            c2.metric(t("critical"), summary["critical_count"])
            c3.metric(t("high"), summary["high_count"])
            c4.metric(t("risk_score"), f"{summary['risk_score']}/25")

        # Risk matrix
        st.markdown(f"### {t('risk_matrix')}")
        if registry and HAS_PLOTLY:
            matrix = registry.get_risk_matrix()
            z = [[matrix.get(p, {}).get(i, 0) for i in range(1, 6)] for p in range(5, 0, -1)]
            fig = go.Figure(go.Heatmap(
                z=z, x=[1, 2, 3, 4, 5], y=[5, 4, 3, 2, 1],
                colorscale=[[0, "#E8F5E9"], [0.3, "#FFF59D"], [0.6, "#FFB74D"], [1, "#C62828"]],
                showscale=False,
                text=[[str(v) if v else "" for v in row] for row in z],
                texttemplate="%{text}", textfont={"size": 20},
            ))
            fig.update_layout(
                xaxis_title=t("impact"), yaxis_title=t("probability"),
                height=400, xaxis=dict(dtick=1), yaxis=dict(dtick=1),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Risks list
        st.markdown(f"### {t('identified_risks')}")
        if registry and registry.risks:
            from skills.oil_and_gas_data_manager.risk_manager import RiskLevel, RiskCategory
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                sel_level = st.selectbox(t("filter_level"), ["All", "Critical", "High", "Medium", "Low"])
            with col_f2:
                sel_cat = st.selectbox(t("filter_category"), ["All"] + [c.value for c in RiskCategory])

            risks = registry.risks
            if sel_level != "All":
                lm = {"Critical": RiskLevel.CRITICAL, "High": RiskLevel.HIGH,
                      "Medium": RiskLevel.MEDIUM, "Low": RiskLevel.LOW}
                risks = [r for r in risks if r.risk_level == lm[sel_level]]
            if sel_cat != "All":
                risks = [r for r in risks if r.category.value == sel_cat]

            icons = {RiskLevel.CRITICAL: "🔴", RiskLevel.HIGH: "🟠",
                     RiskLevel.MEDIUM: "🟡", RiskLevel.LOW: "🟢"}
            for risk in risks:
                title = risk.title_ru if st.session_state.language == "ru" else risk.title_en
                desc = risk.description_ru if st.session_state.language == "ru" else risk.description_en
                mits = risk.mitigation_ru if st.session_state.language == "ru" else risk.mitigation_en
                icon = icons.get(risk.risk_level, "⚪")
                with st.expander(
                    f"{icon} **{risk.risk_id}** — {title} (P={risk.probability} × I={risk.impact})"
                ):
                    st.markdown(desc)
                    st.caption(f"Source: `{risk.source_agent}` | {risk.category.value}")
                    if mits:
                        st.markdown("**" + t("mitigations") + ":**")
                        for m in mits:
                            st.markdown(f"- {m}")
        else:
            st.success(t("no_risks"))

        # Export section
        st.divider()
        st.markdown(f"### {t('export')}")
        ec1, ec2, ec3, ec4 = st.columns(4)

        with ec1:
            try:
                from skills.oil_and_gas_data_manager.report_generator import ReportGenerator
                tmp_docx = Path(tempfile.gettempdir()) / f"risk_{result.task_id}.docx"
                ReportGenerator(language=st.session_state.language).generate(
                    result, registry, tmp_docx
                )
                st.download_button(
                    t("export_word"),
                    data=tmp_docx.read_bytes(),
                    file_name=f"Risk_Report_{datetime.now():%Y%m%d}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as exc:
                st.warning(f"Word: {exc}")

        with ec2:
            if HAS_PDF_EXPORT and registry:
                try:
                    tmp_pdf = Path(tempfile.gettempdir()) / f"risk_{result.task_id}.pdf"
                    # Try docx first, fallback to HTML
                    tmp_docx_for_pdf = Path(tempfile.gettempdir()) / f"risk_pdf_{result.task_id}.docx"
                    try:
                        from skills.oil_and_gas_data_manager.report_generator import ReportGenerator
                        ReportGenerator(language=st.session_state.language).generate(
                            result, registry, tmp_docx_for_pdf
                        )
                    except Exception:
                        tmp_docx_for_pdf = None

                    html_content = generate_html_report(
                        risk_summary=registry.get_summary(),
                        risks=[r.to_dict() for r in registry.risks],
                        well_name=well_name,
                        pad_name=pad_name,
                        language=st.session_state.language,
                    )

                    if tmp_docx_for_pdf and tmp_docx_for_pdf.exists():
                        ok, msg = export_to_pdf(tmp_docx_for_pdf, tmp_pdf, html_content)
                    else:
                        ok, msg = export_to_pdf(
                            Path("nonexistent.docx"), tmp_pdf, html_content
                        )

                    if ok and tmp_pdf.exists():
                        st.download_button(
                            t("export_pdf"),
                            data=tmp_pdf.read_bytes(),
                            file_name=f"Risk_Report_{datetime.now():%Y%m%d}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    else:
                        st.warning(msg)
                except Exception as exc:
                    st.warning(f"PDF: {exc}")
            else:
                st.warning("PDF: install docx2pdf or weasyprint")

        with ec3:
            if registry:
                json_data = json.dumps(
                    {
                        "task_id": result.task_id,
                        "well_name": well_name,
                        "summary": registry.get_summary(),
                        "risks": [r.to_dict() for r in registry.risks],
                    },
                    indent=2, ensure_ascii=False, default=str,
                ).encode("utf-8")
                st.download_button(
                    t("export_json"), data=json_data,
                    file_name=f"risks_{datetime.now():%Y%m%d}.json",
                    mime="application/json", use_container_width=True,
                )

        with ec4:
            if registry and registry.risks:
                import csv as csv_mod
                buf = io.StringIO()
                w = csv_mod.writer(buf)
                w.writerow(["risk_id", "category", "title_en", "title_ru",
                            "probability", "impact", "risk_level", "source_agent"])
                for r in registry.risks:
                    w.writerow([r.risk_id, r.category.value, r.title_en, r.title_ru,
                                r.probability, r.impact, r.risk_level.value, r.source_agent])
                st.download_button(
                    t("export_csv"), data=buf.getvalue().encode("utf-8"),
                    file_name=f"risks_{datetime.now():%Y%m%d}.csv",
                    mime="text/csv", use_container_width=True,
                )


# ===========================================================================
# TAB 2: TRENDS
# ===========================================================================
with tab_trends:
    st.markdown(f"## {t('trends_title')}")

    metrics = st.session_state.metrics or {}

    if not metrics:
        st.info(t("no_trend_data"))
    else:
        # -------------------------------------------------------------------
        # Chart 1: NPT Pareto
        # -------------------------------------------------------------------
        st.markdown(f"### {t('npt_pareto')}")
        st.caption(t("npt_pareto_hint"))

        npt_details = metrics.get("npt_event_details", [])
        if npt_details and HAS_PLOTLY:
            # Group by description and sum durations
            npt_grouped: dict[str, float] = {}
            for ev in npt_details:
                desc = ev.get("description", "Unknown")[:50]
                npt_grouped[desc] = npt_grouped.get(desc, 0) + (ev.get("duration") or 0)

            # Sort descending
            sorted_items = sorted(npt_grouped.items(), key=lambda x: x[1], reverse=True)
            labels = [item[0] for item in sorted_items]
            values = [item[1] for item in sorted_items]
            total_npt = sum(values)
            cumulative = []
            running = 0
            for v in values:
                running += v
                cumulative.append(running / total_npt * 100 if total_npt > 0 else 0)

            fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
            fig_pareto.add_trace(
                go.Bar(
                    x=labels, y=values, name=t("npt_hours_label"),
                    marker_color="#FF6B00",
                ),
                secondary_y=False,
            )
            fig_pareto.add_trace(
                go.Scatter(
                    x=labels, y=cumulative, name=t("cumulative_pct"),
                    mode="lines+markers", line=dict(color="#004C97", width=2),
                ),
                secondary_y=True,
            )
            fig_pareto.update_layout(
                height=400,
                xaxis_tickangle=-30,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            fig_pareto.update_yaxes(title_text=t("npt_hours_label"), secondary_y=False)
            fig_pareto.update_yaxes(
                title_text=t("cumulative_pct"), secondary_y=True, range=[0, 110]
            )
            st.plotly_chart(fig_pareto, use_container_width=True)
        elif not HAS_PLOTLY:
            st.warning("Install plotly for interactive charts: pip install plotly")
        else:
            st.info("No NPT events in this analysis.")

        # -------------------------------------------------------------------
        # Chart 2: DLS by Depth
        # -------------------------------------------------------------------
        st.markdown(f"### {t('dls_by_depth')}")
        st.caption(t("dls_by_depth_hint"))

        dls_stations = metrics.get("dls_stations", [])
        if dls_stations and HAS_PLOTLY:
            mds = [s["md"] for s in dls_stations]
            dls_vals = [s["dls"] for s in dls_stations]

            # Color by severity
            colors = []
            for d in dls_vals:
                if d > 8:
                    colors.append("#C62828")   # Danger
                elif d > 5:
                    colors.append("#FF6B00")   # Caution
                else:
                    colors.append("#4CAF50")   # Safe

            fig_dls = go.Figure()
            fig_dls.add_trace(go.Scatter(
                x=dls_vals, y=mds,
                mode="lines+markers",
                line=dict(color="#004C97", width=2),
                marker=dict(color=colors, size=8),
                name="DLS",
            ))
            # Add threshold lines
            fig_dls.add_vline(x=5, line_dash="dash", line_color="#FF6B00",
                              annotation_text=t("dls_caution"))
            fig_dls.add_vline(x=8, line_dash="dash", line_color="#C62828",
                              annotation_text=t("dls_danger"))

            fig_dls.update_layout(
                height=500,
                xaxis_title=t("dls_label"),
                yaxis_title=t("depth_m"),
                yaxis=dict(autorange="reversed"),  # Depth increases downward
            )
            st.plotly_chart(fig_dls, use_container_width=True)
        else:
            st.info("No directional data available for DLS chart.")

        # -------------------------------------------------------------------
        # Chart 3: NPT Distribution Pie
        # -------------------------------------------------------------------
        st.markdown(f"### {t('npt_by_category')}")
        if npt_details and HAS_PLOTLY:
            fig_pie = go.Figure(data=[go.Pie(
                labels=labels[:8],  # Top 8 categories
                values=values[:8],
                hole=0.4,
                marker_colors=[
                    "#C62828", "#FF6B00", "#FFB74D", "#FFF59D",
                    "#C8E6C9", "#90CAF9", "#CE93D8", "#B0BEC5",
                ],
            )])
            fig_pie.update_layout(height=350)
            st.plotly_chart(fig_pie, use_container_width=True)


# ===========================================================================
# TAB 3: WELL COMPARISON
# ===========================================================================
with tab_comparison:
    st.markdown(f"## {t('comparison_title')}")

    if not HAS_HISTORY or not st.session_state.history:
        st.warning("History module not available.")
    else:
        well_names = st.session_state.history.get_well_names()

        if not well_names:
            st.info(t("no_history"))
        else:
            selected_wells = st.multiselect(
                t("select_wells"),
                options=well_names,
                max_selections=3,
            )

            if selected_wells:
                compare_clicked = st.button(t("compare_btn"), use_container_width=False)

                if compare_clicked:
                    analyses = st.session_state.history.get_latest_for_wells(selected_wells)

                    if len(analyses) < 2:
                        st.warning("Need at least 2 wells with analysis history.")
                    else:
                        # -------------------------------------------------------
                        # Comparison table
                        # -------------------------------------------------------
                        st.markdown(f"### {t('comparison_table')}")

                        # Define metrics to compare
                        metric_defs = [
                            ("total_risks", t("total_risks"), ""),
                            ("critical_risks", t("critical"), ""),
                            ("high_risks", t("high"), ""),
                            ("risk_score", t("risk_score"), "/25"),
                            ("npt_hours", "NPT", "hrs"),
                            ("max_dls", "Max DLS", "°/100ft"),
                            ("max_inclination", "Max Inc", "°"),
                            ("total_md", "Total MD", "m"),
                            ("total_net_pay", "Net Pay", "m"),
                            ("pay_zone_count", "Pay Zones", ""),
                            ("stage_count", "Frac Stages", ""),
                            ("ip30", "IP30", ""),
                            ("hse_incidents", "HSE Incidents", ""),
                        ]

                        # Build comparison dataframe
                        import pandas as pd
                        comp_data = {t("metric"): [md[1] + (f" ({md[2]})" if md[2] else "") for md in metric_defs]}
                        for analysis in analyses:
                            well_label = analysis.get("well_name", "Unknown")
                            m = analysis.get("metrics", {})
                            col_vals = []
                            for key, _, _ in metric_defs:
                                val = m.get(key, "—")
                                if isinstance(val, float):
                                    val = round(val, 2)
                                col_vals.append(val)
                            comp_data[well_label] = col_vals

                        df_comp = pd.DataFrame(comp_data)
                        st.dataframe(df_comp, use_container_width=True, hide_index=True)

                        # -------------------------------------------------------
                        # Risk level comparison chart
                        # -------------------------------------------------------
                        if HAS_PLOTLY:
                            st.markdown(f"### {t('comparison_chart')}")

                            well_labels = [a.get("well_name", "?") for a in analyses]
                            risk_levels = ["critical_risks", "high_risks", "medium_risks", "low_risks"]
                            level_names = [t("critical"), t("high"), t("medium"), t("low")]
                            level_colors = ["#C62828", "#FF6B00", "#FFB74D", "#4CAF50"]

                            fig_comp = go.Figure()
                            for i, (rkey, rname, rcolor) in enumerate(
                                zip(risk_levels, level_names, level_colors)
                            ):
                                fig_comp.add_trace(go.Bar(
                                    name=rname,
                                    x=well_labels,
                                    y=[a.get("metrics", {}).get(rkey, 0) for a in analyses],
                                    marker_color=rcolor,
                                ))

                            fig_comp.update_layout(
                                barmode="group",
                                height=400,
                                yaxis_title=t("total_risks"),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                            )
                            st.plotly_chart(fig_comp, use_container_width=True)

                            # -------------------------------------------------------
                            # Radar / spider chart for multi-dimensional comparison
                            # -------------------------------------------------------
                            st.markdown("### 🕸️ Radar Comparison")
                            radar_metrics = [
                                ("npt_hours", "NPT"),
                                ("max_dls", "DLS"),
                                ("risk_score", "Risk"),
                                ("hse_incidents", "HSE"),
                                ("total_risks", "Risks"),
                            ]

                            # Normalize to 0-1 scale for radar
                            fig_radar = go.Figure()
                            for analysis in analyses:
                                m = analysis.get("metrics", {})
                                vals = []
                                for key, _ in radar_metrics:
                                    v = m.get(key, 0) or 0
                                    # Simple normalization (cap at reasonable max)
                                    caps = {"npt_hours": 50, "max_dls": 15,
                                            "risk_score": 25, "hse_incidents": 10,
                                            "total_risks": 30}
                                    norm = min(v / caps.get(key, 10), 1.0)
                                    vals.append(round(norm * 100, 1))
                                vals.append(vals[0])  # Close the polygon

                                categories = [rm[1] for rm in radar_metrics]
                                categories.append(categories[0])

                                fig_radar.add_trace(go.Scatterpolar(
                                    r=vals,
                                    theta=categories,
                                    fill="toself",
                                    name=analysis.get("well_name", "?"),
                                    opacity=0.6,
                                ))

                            fig_radar.update_layout(
                                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                                height=400,
                            )
                            st.plotly_chart(fig_radar, use_container_width=True)


# ===========================================================================
# TAB 4: HISTORY
# ===========================================================================
with tab_history:
    st.markdown(f"## {t('history_title')}")

    if not HAS_HISTORY or not st.session_state.history:
        st.warning("History module not available.")
    else:
        analyses_list = st.session_state.history.list_analyses(limit=50)

        if not analyses_list:
            st.info(t("history_empty"))
        else:
            # Summary metrics
            st.metric("Total analyses in history", len(analyses_list))
            st.divider()

            # Display as interactive table
            for analysis in analyses_list:
                task_id = analysis["task_id"]
                well = analysis.get("well_name") or "—"
                pad = analysis.get("pad_name") or "—"
                created = analysis.get("created_at", "")
                files = analysis.get("files_processed", 0)

                col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 2])
                col1.write(f"**{well}** (Куст {pad})")
                col2.write(f"📄 {files}")
                col3.write(f"⏱ {analysis.get('elapsed_seconds', 0):.1f}s")
                col4.write(f"📅 {created[:10] if created else '—'}")

                with col5:
                    if st.button(t("load_analysis"), key=f"load_{task_id}"):
                        full = st.session_state.history.load_analysis(task_id)
                        if full:
                            st.session_state.metrics = full.get("metrics", {})
                            st.toast(f"Loaded analysis for well {well}", icon="📂")
                            st.rerun()

                with col6:
                    if st.button(t("delete_analysis"), key=f"del_{task_id}"):
                        st.session_state.history.delete_analysis(task_id)
                        st.toast("Analysis deleted", icon="🗑️")
                        st.rerun()

                st.divider()


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "🛢️ Drilling Risk Management System v1.0 | "
    "Multi-Agent Swarm | Enterprise Edition | "
    f"© {datetime.now().year}"
)
