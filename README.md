# DPE | Reservoir Engineering Talent Profile Dashboard

### PCSB / DPE Reservoir Engineering Fraternity

### Competency, Readiness & Talent Intelligence Platform

![Status](https://img.shields.io/badge/Release-Beta%20v3.0-orange)
![Development](https://img.shields.io/badge/Development-Agile%20%7C%20Incremental-blue)
![Framework](https://img.shields.io/badge/Competencies-24-green)
![Personnel](https://img.shields.io/badge/Personnel-229-green)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20SQLAlchemy-lightgrey)

> **A continuously evolving competency and talent intelligence platform for Reservoir Engineering — transforming assessment data into actionable insights on competency gaps, readiness, career progression and workforce development.**

---

## 📌 Overview

The **RE Fraternity Competency Assessment System** is a web-based competency intelligence platform developed for the Reservoir Engineering fraternity within **PCSB / DPE**.

The system was developed to progressively move the competency assessment process away from fragmented spreadsheet-based analysis towards a centralized application that can:

* Manage personnel and competency information
* Conduct and store competency assessments
* Compare actual competency against career-ruler requirements
* Identify competency gaps
* Measure individual and workforce readiness
* Analyse competency risk across departments
* Prioritise personnel for development
* Track historical assessment performance
* Maintain individual talent profiles
* Link supporting CV/document information
* Provide interactive workforce analytics
* Generate assessment reports
* Support future development and talent-management capabilities

The current **v3.0 Beta** represents the foundation of this platform.

It is intentionally designed as an **agile, incremental product**: each development phase builds upon the previous release, introduces validated functionality, and creates the foundation for subsequent capabilities.

---

# 🎯 Why This System Exists

Traditional competency assessment processes often rely heavily on spreadsheets, manual calculations and disconnected analysis.

This creates several challenges:

* Repetitive manual processing
* Difficulty maintaining assessment history
* Inconsistent competency calculations
* Limited visibility of competency gaps
* Difficult workforce-level analysis
* Limited connection between competency and career progression
* Time-consuming preparation of management reports
* Difficulty identifying development priorities

The system addresses these challenges by introducing a structured application and database layer between the source data and the analytical interface.

### From:

```text
Excel
   ↓
Manual Filtering
   ↓
Manual Calculation
   ↓
Manual Charts
   ↓
Manual Reporting
```

### Towards:

```text
Master Data
     ↓
Data Validation & Normalisation
     ↓
Structured Database
     ↓
Competency Engine
     ↓
Readiness & Gap Analytics
     ↓
Talent Intelligence
     ↓
Management Decision Support
```

---

# 🚀 Current Release — Beta v3.0

**Beta v3.0** establishes the core platform architecture and competency intelligence layer.

The current release supports a competency framework covering:

* **12 Base competencies — B1–B12**
* **5 Knowledge competencies — K1–K5**
* **5 Pacing competencies — P1–P5**
* **2 Emerging competencies — E1–E2**

### Total: 24 competency dimensions

The current master dataset contains **229 personnel records**.

The system uses the Excel master workbook as the initial master-data source while progressively transitioning operational analysis and assessment history into a structured SQLAlchemy-backed database.

---

# ⭐ Key Capabilities

## 1. Workforce Intelligence

The system provides a centralised personnel profile containing information such as:

* Staff ID
* Name
* Department
* Section
* Unit / Sub-unit
* Position
* Salary Grade
* Employment category
* Age
* Nationality
* Years in PETRONAS
* Reservoir Engineering experience
* Years in current grade
* Current assignment
* Assignment duration
* Contract information
* Assessment information
* Strengths
* Interests
* Potential
* Recommendations
* SME / resource information
* Supervisor / assessor information

This provides the foundation for workforce-level competency and talent analysis.

---

## 2. Competency Intelligence

The platform evaluates personnel against the established Reservoir Engineering competency framework.

Each assessment can contain competency-level information including:

* Actual competency score
* Required competency level
* Gap
* Achievement percentage
* Competency category
* Assessment date

Rather than storing only an overall employee score, the system maintains competency-level records that allow detailed analysis.

### Assessment structure

```text
Personnel
   │
   └── Assessment
          │
          ├── B1
          ├── B2
          ├── ...
          ├── B12
          │
          ├── K1
          ├── ...
          ├── K5
          │
          ├── P1
          ├── ...
          ├── P5
          │
          ├── E1
          └── E2
```

This structure also provides the foundation for future longitudinal competency tracking.

---

# 3. Career Ruler & Target Grade Analysis

One of the core capabilities of the system is the ability to evaluate personnel against career-ruler requirements.

The platform can compare:

```text
Current Grade
      ↓
Career Ruler
      ↓
Target Grade
      ↓
Required Competencies
      ↓
Actual Competencies
      ↓
Gap
      ↓
Readiness
```

This changes the assessment question from:

> **"What is this person's current competency level?"**

to:

> **"How ready is this person for the next career level?"**

This creates a direct connection between competency assessment and career progression.

---

# 4. Individual Assessment & Talent Profile

The **Individual Assessment** module provides a consolidated view of an individual's:

* Personnel profile
* Current position
* Salary grade
* Career target
* Competency scores
* Required competency levels
* Competency gaps
* Achievement
* Readiness
* Assessment history
* Talent information
* Supporting documents

Visual analysis includes:

* Actual vs Target competency charts
* Competency category radar analysis
* Gap tables
* Historical assessment trends

The objective is to provide a **360° individual competency view** rather than a single assessment score.

---

# 5. Readiness Intelligence

The platform provides multiple readiness perspectives rather than relying on a single score.

### Weighted Readiness

Measures the degree to which actual competency achievement contributes towards the required competency target.

### Strict Readiness

Measures the proportion of competencies that meet or exceed the required target.

### Category Readiness

Readiness can also be viewed across competency groups:

* Base
* Knowledge
* Pacing
* Emerging

This distinction helps prevent misleading interpretations such as:

> "92% ready"

when several critical competencies may still remain below the required level.

---

# 6. Competency Gap Analysis

Competency gaps are classified into meaningful categories.

| Status         | Meaning                                        |
| -------------- | ---------------------------------------------- |
| 🟢 Met         | Actual competency meets or exceeds requirement |
| 🟡 Minor Gap   | Competency is slightly below requirement       |
| 🔴 Major Gap   | Significant competency gap identified          |
| ⚪ Not Assessed | No valid assessment available                  |

The system can analyse gaps at both:

### Individual level

> Which competencies does this person need to develop?

and

### Workforce level

> Which competencies represent the largest risk across the fraternity?

---

# 7. Competency Risk Intelligence

The platform aggregates competency gaps across organisational structures to identify areas of concentrated competency risk.

Analysis can include:

* Department
* Section
* Position
* Salary Grade
* Competency
* Competency category

This allows management to identify patterns such as:

```text
Department A
   ↓
High B3 Gap
   ↓
High number of affected personnel
   ↓
Potential development priority
```

The purpose is to move from **individual assessment reporting** towards **workforce competency risk management**.

---

# 8. Personnel Development Prioritisation

The Readiness & Gaps analytics layer can identify personnel who may require development attention based on factors including:

* Weighted readiness
* Strict readiness
* Major competency gaps
* Minor competency gaps
* Gap burden
* Years in grade
* Top competency gap
* Overall readiness status

The system can provide indicative actions such as:

* Leadership Review Required
* Targeted Technical Development
* Focused Development Plan
* Close Minor Gaps
* Complete Assessment
* Ready for Assessment

These recommendations are intended as **decision-support indicators**, not automated HR decisions.

---

# 9. Competency Heatmap

The competency heatmap provides a workforce-level view of competency performance.

Users can analyse competency performance across:

* Personnel
* Departments
* Positions
* Competency categories
* Individual competencies

The heatmap also provides supporting metrics such as:

* Average score
* Assessment coverage
* High-score cells
* Low-score cells
* Personnel represented

This enables rapid identification of competency concentration and weakness.

---

# 10. Workforce & Demographic Analytics

The platform provides workforce-level analytical views covering areas such as:

* Headcount
* Department distribution
* Section distribution
* Position distribution
* Salary-grade distribution
* Gender distribution
* Chat / engagement status
* Assessment completion
* Age vs Salary Grade
* Experience vs Competency Performance

These analytics provide contextual information around competency results.

---

# 11. Historical Assessment Tracking

The database architecture supports multiple assessments for the same individual.

This allows the system to evolve from:

```text
Assessment Snapshot
```

towards:

```text
Assessment 1
      ↓
Assessment 2
      ↓
Assessment 3
      ↓
Competency Trajectory
```

Historical assessment information can be used to analyse competency movement over time.

This capability forms the foundation for future **competency growth and development tracking**.

---

# 12. Talent Profile & Supporting Documents

The individual talent profile provides additional contextual information such as:

* Strength
* Interest
* Background
* Potential
* Recommendation
* SME / resource information

The system also provides a structured relationship for CV and supporting document information.

CV records can be associated with personnel through controlled matching mechanisms including:

1. Staff ID
2. Normalised name
3. Controlled partial-name matching

This creates the foundation for combining:

```text
Competency
+
Experience
+
Career Information
+
Talent Profile
+
Supporting Documents
```

---

# 13. Assessment Reporting

Individual assessment information can be exported into a PDF assessment report.

This enables assessment outputs to be shared outside the application while maintaining a structured representation of:

* Personnel information
* Assessment results
* Competency performance
* Target requirements
* Gap information
* Readiness information

---

# 14. Dynamic Analytics & Chart Builder

The platform includes a configurable **Chart Builder** designed to support exploratory analysis.

The engine can inspect dataset characteristics and identify data types such as:

* Numeric
* Categorical
* Datetime
* Mixed
* Unknown

Based on the available data, compatible visualisation types can be suggested, including:

* Bar charts
* Stacked bar charts
* Line charts
* Scatter plots
* Histograms
* Box plots
* Pie charts
* Bubble charts

The Chart Builder is intended to provide a lightweight **self-service analytics capability** without requiring users to modify the application's source code.

---

# 🗄️ Data & Application Architecture

The current system uses a layered architecture:

```text
┌─────────────────────────────────────────────┐
│              Excel Master Data              │
│      Personnel • Assessment • Ruler Data    │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│          Data Loading & Validation           │
│ Cleaning • Normalisation • Mapping • Checks  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│            SQLAlchemy Database Layer         │
│ Personnel • Assessments • Scores • Documents │
│ Audit Records                                │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              Analytics Engine               │
│ Gaps • Readiness • Risk • Workforce Trends  │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│                Streamlit UI                 │
│ Dashboard • Assessment • Readiness • Admin  │
└─────────────────────────────────────────────┘
```

The database architecture separates personnel records, assessment records, competency scores, summary information, CV/document records and audit information.

This allows the application to retain assessment history rather than treating Excel as the permanent operational database.

---

# 📥 Data Import & Synchronisation

The Excel master workbook remains the initial source for master personnel and competency information.

The import pipeline performs validation and normalisation before data enters the application database.

The pipeline handles issues including:

* Missing dates
* Non-standard Staff IDs
* Missing Staff IDs
* Position normalisation
* Salary-grade normalisation
* Competency mapping
* Career-ruler mapping
* Gap recalculation

### Gap convention

The application internally uses:

```text
Gap = Actual − Requirement
```

Therefore:

```text
Positive Gap  → Above requirement
Zero Gap      → Meets requirement
Negative Gap  → Below requirement
```

This differs from the raw Excel `G--` convention, which uses:

```text
Requirement − Actual
```

The importer recalculates the application gap rather than blindly copying the spreadsheet value.

---

# 🛠️ Administrative Capabilities

The current Beta release provides administrative workflows for:

### Import Data

* Upload master Excel data
* Validate/import data
* Monitor database status
* Reset database when required

### Personnel Management

* Add personnel
* Edit personnel
* Soft-delete personnel
* Search personnel

### Assessment Entry

* Create a new assessment
* Enter all 24 competency scores
* Record assessment information
* Store assessment history

---

# 🔐 Data Governance & Audit Foundation

The database includes audit-log infrastructure capable of recording:

* Entity type
* Entity ID
* Action
* User / actor
* Previous values
* New values
* Timestamp

This provides a foundation for stronger governance as authentication, role-based access and enterprise deployment capabilities are introduced in future releases.

> **Important:** Authentication and role-based access control are not yet implemented in the current Beta release.

---

# 📊 Current Application Modules

| Module                     | Purpose                                                       |
| -------------------------- | ------------------------------------------------------------- |
| 🏠 Dashboard Home          | Workforce overview and management-level analytics             |
| 👥 Personnel Directory     | Search, filter and export personnel information               |
| 🌡️ Competency Heatmap     | Workforce competency performance and coverage                 |
| 🔍 Individual Assessment   | Individual competency, target, gap and history analysis       |
| 🎯 Readiness & Gaps        | Readiness, gap analysis and development prioritisation        |
| 📈 Trends                  | Workforce experience, age, grade and competency relationships |
| 📊 Chart Builder           | Exploratory/self-service visual analytics                     |
| ⚙️ Admin: Import Data      | Master-data ingestion and database management                 |
| ⚙️ Admin: Personnel CRUD   | Personnel administration                                      |
| ⚙️ Admin: Assessment Entry | Manual assessment creation                                    |

---

# 🧩 Technology Stack

| Layer                 | Technology        |
| --------------------- | ----------------- |
| Programming Language  | Python            |
| Application Framework | Streamlit         |
| ORM                   | SQLAlchemy        |
| Database              | SQLite            |
| Analytics             | Pandas / Python   |
| Visualisation         | Plotly            |
| Excel Processing      | OpenPyXL          |
| Reporting             | PDF generation    |
| Testing               | Python test suite |
| Source Control        | Git / GitHub      |

The architecture is designed so that the database layer can be extended beyond SQLite for future deployment scenarios.

---

# 📁 Project Structure

```text
competency-assessment-system/
│
├── app.py
├── config.py
├── data_loader.py
├── db_ops.py
├── models.py
├── analytics.py
├── chart_builder.py
├── navigation.py
├── requirements.txt
│
├── assets/
│
├── competency_v3_final/
│
├── scripts/
│
├── tests/
│
├── .github/
│   └── workflows/
│
├── .devcontainer/
│
├── CHART_BUILDER_GUIDE.md
├── CHART_BUILDER_IMPLEMENTATION.md
├── CHART_BUILDER_REFERENCE.md
├── CHART_BUILDER_SUMMARY.md
│
└── README.md
```

---

# 🚀 Agile Development & Release Strategy

The system follows an **incremental Agile development approach**.

Rather than attempting to build a complete enterprise talent-management platform in one release, functionality is introduced progressively through validated Beta phases.

Each phase aims to:

1. Deliver usable functionality
2. Validate against real assessment data
3. Collect user feedback
4. Identify technical and business gaps
5. Improve the existing workflow
6. Establish the foundation for the next capability

### Product evolution

```text
                     ┌──────────────────┐
                     │   Beta v3.0      │
                     │ Core Foundation   │
                     └────────┬─────────┘
                              │
                              ▼
                  ┌──────────────────────┐
                  │   Beta Phase 2       │
                  │ Analytics & Usability│
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   Beta Phase 3       │
                  │ Development Planning │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   Beta Phase 4       │
                  │ Talent Intelligence  │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   Beta Phase 5       │
                  │ Enterprise Readiness │
                  └──────────────────────┘
```

The phases are **not intended to be rigid or sequential feature locks**.

New requirements, user feedback and operational priorities may result in features being moved, expanded or reprioritised between releases.

---

# 🛣️ Product Roadmap

## 🟢 Phase 1 — Core Competency Foundation

**Status: Completed / Beta v3.0**

Current capabilities include:

* Personnel database
* Excel ingestion
* Data cleaning and normalisation
* 24-competency framework
* Career-ruler mapping
* Individual assessment
* Competency gap analysis
* Readiness calculation
* Workforce heatmap
* Historical assessments
* Personnel administration
* Assessment entry
* PDF reporting
* Talent profile foundation
* CV/document linkage
* Dynamic Chart Builder
* Audit-log foundation

---

## 🔵 Phase 2 — Analytics & Operational Maturity

**Status: In active evolution**

Potential enhancements include:

* Improved dashboard UX
* Advanced filtering
* Enhanced workforce risk analytics
* Improved assessment-cycle management
* Better bulk data operations
* Enhanced reporting
* Improved data-quality monitoring
* Assessment calibration support
* Performance optimisation
* Stronger testing coverage

---

## 🟣 Phase 3 — Development Intelligence

**Target direction**

Transform identified competency gaps into trackable development actions.

Potential capabilities:

```text
Competency Gap
      ↓
Development Recommendation
      ↓
Development Plan
      ↓
Owner
      ↓
Target Date
      ↓
Progress
      ↓
Completion
      ↓
Reassessment
```

Potential features include:

* Individual Development Plans
* Competency action tracker
* Development status
* Development deadlines
* Follow-up assessment
* Competency improvement tracking

---

## 🟠 Phase 4 — Talent Intelligence

**Target direction**

Expand the system from competency assessment into broader talent intelligence.

Potential capabilities include:

* Talent segmentation
* High-potential identification
* Succession readiness
* Bench-strength analysis
* Career mobility analysis
* SME / technical authority mapping
* Workforce capability planning
* Talent profile enrichment

---

## 🔴 Phase 5 — Enterprise Readiness

**Target direction**

Prepare the platform for broader operational deployment.

Potential capabilities include:

* Authentication
* Role-based access control
* User permissions
* Secure database deployment
* PostgreSQL production support
* Assessment approval workflow
* Assessment calibration
* Change tracking
* Notification workflows
* Enterprise reporting
* Deployment automation
* Backup and recovery
* Security hardening

---

# 🔄 Agile Release Philosophy

The system is deliberately designed to evolve.

Each release should answer three questions:

### 1. What problem are we solving?

A feature should have a clear operational or business purpose.

### 2. What evidence validates the solution?

Features should be tested against real assessment data and actual user workflows where possible.

### 3. What foundation does this create for the next release?

The objective is not simply to add features, but to progressively build a more integrated competency and talent intelligence platform.

---

# ⚠️ Current Beta Limitations

The current release should be considered a **Beta operational platform** rather than a fully productionised enterprise application.

Known limitations include:

* Authentication is not currently implemented.
* Role-based access control is not currently implemented.
* The readiness threshold is currently configured around an 80% achievement rule.
* Manual assessment entry is available but may become cumbersome for large-scale bulk updates.
* Excel remains an important master-data input.
* SQLite is currently the default database.
* Some enterprise security and governance capabilities remain part of future development.
* Development-plan and succession workflows are not yet implemented.

These limitations are intentionally tracked as part of the Agile product roadmap.

---

# 🧪 Testing & Validation

The data pipeline has been tested against the real personnel dataset used for the Beta release.

Testing has included:

* Excel ingestion
* Data cleaning
* Missing-date handling
* Staff ID normalisation
* Duplicate/non-standard ID handling
* Competency mapping
* Career-ruler mapping
* Gap calculation
* Readiness calculation
* Database import
* Assessment data handling

Several data-integrity issues discovered during development were corrected, including:

1. Missing/invalid dates causing database insertion failures
2. Non-numeric Staff IDs
3. Duplicate literal `UPTREX` identifiers
4. Missing Staff IDs
5. Gap-sign convention mismatch between Excel and application logic

The application continues to undergo iterative testing as new Beta capabilities are introduced.

---

# ▶️ Installation

## 1. Clone the repository

```bash
git clone https://github.com/nasilemak80sen/competency-assessment-system.git
cd competency-assessment-system
```

## 2. Create a virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Run the application

```bash
streamlit run app.py
```

The application will normally be available at:

```text
http://localhost:8501
```

---

# 📥 First-Time Data Setup

After launching the application:

1. Navigate to **Admin → Import Data**
2. Upload the appropriate Reservoir Engineering master workbook
3. Review the import status
4. Confirm the import
5. Verify personnel and competency records
6. Proceed to the Dashboard

The import process is designed to update existing personnel by Staff ID and retain assessment snapshots when assessment dates change.

---

# 📌 Important Data Principle

The Excel workbook should be treated as the **master-data input**, not as the application's long-term analytical database.

The intended architecture is:

```text
Excel Master Data
       ↓
Validated Import
       ↓
Application Database
       ↓
Assessment History
       ↓
Analytics
       ↓
Reporting
```

This separation is important for future scalability.

---

# 🔭 Long-Term Vision

The long-term objective is to evolve the system from a competency assessment application into an integrated **Reservoir Engineering Capability & Talent Intelligence Platform**.

The intended progression is:

```text
ASSESS
   ↓
UNDERSTAND
   ↓
IDENTIFY GAPS
   ↓
MEASURE READINESS
   ↓
PRIORITISE
   ↓
DEVELOP
   ↓
TRACK
   ↓
RE-ASSESS
   ↓
PLAN CAREER
   ↓
STRENGTHEN THE FRATERNITY
```

The system is therefore not intended to remain a static dashboard.

It is being developed as an **iterative digital product**, where each Beta release adds another layer of intelligence to the competency lifecycle.

---

# 📜 Release Philosophy

### Beta does not mean incomplete.

For this project, **Beta represents controlled evolution**.

The system is already capable of supporting meaningful competency assessment and workforce analysis, while its architecture allows additional capabilities to be introduced progressively.

Future releases will be driven by:

* User feedback
* Assessment-cycle requirements
* Data-quality findings
* Business priorities
* Operational experience
* Technical improvements
* New competency-management requirements

> **Build → Validate → Learn → Improve → Release → Repeat**

This is the development philosophy behind the platform.

---

# 🤝 Contribution & Development

The repository is maintained as an evolving internal development project.

Changes should ideally follow the Agile cycle:

```text
Requirement
    ↓
Design
    ↓
Development
    ↓
Testing
    ↓
User Validation
    ↓
Release
    ↓
Feedback
    ↓
Next Iteration
```

New functionality should preserve compatibility with existing personnel, assessment and competency data wherever practical.

---

# 📍 Current Release

**Current Release:** `v3.0 Beta`

**Development Model:** Agile / Incremental

**Primary Domain:** Reservoir Engineering Competency & Talent Management

**Current Dataset:** 229 personnel

**Competency Framework:** 24 competencies

**Primary Application:** Streamlit

**Database:** SQLAlchemy / SQLite

**Status:** Active Development

---

## Built for continuous improvement.

**RE Fraternity Competency Assessment System**
*From competency assessment → to readiness intelligence → to talent intelligence.*

