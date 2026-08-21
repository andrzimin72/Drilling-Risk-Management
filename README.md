# Drilling-Risk-Management
This software is an Enterprise-Grade, Multi-Agent AI Data Extraction and Risk Analysis Platform specifically tailored for the Oil and Gas Industry.

## 1. What was it created for?
It was created to solve one of the most expensive and time-consuming bottlenecks in upstream oil and gas operations: the manual ingestion, normalization, and analysis of unstructured and semi-structured engineering data (Daily Drilling Reports, LAS well logs, completion spreadsheets, HSE incident logs). Instead of engineers spending hundreds of hours copying data from PDFs into Excel to find trends, this system uses a swarm of specialized AI agents to read, understand, cross-reference, and score the data automatically.

## 2. Main Purpose and Tasks Solved
Main Purpose: To transform raw, messy, multi-format field data into structured, actionable engineering intelligence and automated risk assessments.
Main Tasks it Solves:

a) Automated Data Extraction: Pulling KPIs (ROP, WOB, Mud Weight, NPT) from unstructured PDFs and DOCX files;

b) Petrophysical Interpretation: Reading LAS/DLIS binary files, identifying pay zones using configurable cutoffs, and computing net pay;

c) Trajectory Computation: Calculating Minimum Curvature, TVD, and Dogleg Severity (DLS) from survey data;

d) Cross-Domain QA/QC: Automatically flagging inconsistencies (e.g., the depth reported in the Drilling Agent doesn't match the depth range in the LAS logs);

e) Risk Identification: Scanning HSE reports for fatalities, LTIs, and SIF potentials, and scoring them on a 5x5 matrix;

f) Historical Pattern Recognition: Using RAG (Vector Database) to warn engineers if a specific depth on a specific pad has caused stuck pipe or mud losses in previous wells.

## 3. Main Functions
a) Intelligent Routing: The DataManagerAgent inspects files and routes them to the correct specialist agent without human intervention;

b) Bilingual & Unit-Agnostic Processing: Seamlessly handles both US Imperial (ft, ppg, bbls) and Russian Metric (m, g/cm³, m³) data, including Cyrillic text;

c) Vision LLM Fallback: When standard PDF parsers fail on scanned or poorly formatted tables, it converts the page to an image and uses a Vision LLM to extract the data;

d) Automated Risk Scoring Engine: Evaluates extracted data against industry heuristics (e.g., DLS > 8°/100ft = Critical Stuck Pipe Risk) and generates a 5x5 Risk Matrix;

e) Interactive Dashboard & Reporting: Provides a Streamlit web UI for trend analysis (Pareto charts, DLS profiles) and exports branded Word/PDF reports;

f) Enterprise Resilience: Features SQLite caching, crash-recovery checkpointing, and OpenTelemetry tracing for IT observability.

## 4. What Opportunities Does it Open Up for Engineers?
a) Shift from Data Gathering to Decision Making: Engineers stop being "data entry clerks" and become "data reviewers." They can spend their time analyzing why NPT happened, rather than spending 3 days compiling the report that it happened;

b) Pad-Level Intelligence: By using the PadAnalysisSwarm and RAG system, a drilling supervisor can look at a new well and instantly see the historical "personality" of that specific pad (e.g., "Wells 1, 2, and 3 all experienced shale swelling at 3,100m");

c) Standardization Across Global Assets: A multinational operator can use the exact same software to analyze a well in the Permian Basin (US) and a well in Western Siberia (Russia), getting a unified, standardized risk scorecard for both.

## 5. Where Will This Software Be Most Effective?
a) End-of-Well (EoW) Reporting: Generating comprehensive EoW reports in minutes instead of weeks;

b) Data QA/QC and Auditing: Finding missing data, mismatched depths, or impossible geometries (TVD > MD) before they cause engineering errors;

c) HSE Trend Analysis: Aggregating near-misses and incidents across hundreds of DDRs to identify systemic safety culture issues;

d) Offset Well Analysis: Rapidly comparing the performance of 10 wells on the same pad to optimize the design of the 11th well.

## 6. Where Should This Software NOT Be Used?
a) Real-Time Rig Floor Control: This is a post-event or near-real-time analytical tool. It must never be connected to the rig's SCADA systems to automatically adjust drilling parameters (like closing a BOP or changing WOB). It is an advisory system, not a control system;

b) Official Financial / Reserve Auditing: The petrophysical calculations (Net Pay, Porosity estimates) are based on simplified cutoffs. This software should not be used to calculate official EUR (Estimated Ultimate Recovery) or book reserves for SEC/government reporting without rigorous validation by a certified human petrophysicist;

c) Legal or Regulatory Submissions: The generated Word/PDF reports are for internal engineering decision support. They should not be submitted directly to regulatory bodies (like Rostekhnadzor in Russia or the EPA in the US) as official legal documents without human review and sign-off;

d) Environments with Zero IT Support: If the end-user is a small, independent operator with no IT department, the enterprise features (Docker, OpenTelemetry, Vector DBs) will become a burden. This software is designed for mid-to-large enterprise environments.

## 7. Quick Start Checklist
- install Python 3.10+;
- clone/download the project;
- Create virtual environment;
- install dependencies (pip install -r requirements.txt);
- copy .env.example to .env and configure;
- run tests (pytest tests/ -v);
- start dashboard (streamlit run dashboard.py);
- upload your first files and analyze.
For more questions or issues, please refer to the Troubleshooting section or Engineer's User Guide.

## 8. Resume
This is a Tier-1, Enterprise-Ready Decision Support System. Most companies in the Oil & Gas sector are still using manual copy-paste workflows or basic, rigid database tools that break the moment a file format changes. By combining Multi-Agent AI orchestration, bilingual/unit-agnostic parsing, vector-based historical memory, and automated risk scoring, we have a product that is genuinely ahead of the curve.

It is robust, it is resilient, and it is deeply respectful of the domain-specific realities of drilling engineering. If delivered with the clear understanding that it is an engineer's co-pilot rather than an autopilot, it will provide immense value to any drilling, completions, or HSE department.
