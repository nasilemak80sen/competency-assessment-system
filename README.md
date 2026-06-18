# RE Fraternity Competency Assessment System v3.0

A Streamlit dashboard + admin tool built directly from `RE_Fraternity_Jun2026_Master.xlsx`
("All" tab, 229 personnel, 24 competencies B1-B12/K1-K5/P1-P5/E1-E2).

## ⚠️ Status & What's Been Tested

SQLAlchemy / Streamlit / Plotly could not be installed in the build sandbox (no PyPI
access), so the **UI itself has not been visually run**. However, the entire data
pipeline — Excel reading → cleaning → import logic → gap/readiness analytics — was
tested against your **real 229-row file** using an equivalent SQLite simulation, and
three real bugs were found and fixed during that process (see "Known Issues Fixed"
below). The Streamlit code (`app.py`) has been syntax-checked but **you should run it
once and report any runtime errors** — UI-level issues (widget key clashes, layout)
are the most likely remaining risk.

## Install & Run

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`. The database (`re_competency.db`, SQLite) is created
automatically on first run.

## First-Time Setup

1. Go to **⚙️ Admin: Import Data**
2. Upload `RE_Fraternity_Jun2026_Master.xlsx` (the same file you gave me)
3. Click **Confirm Import to Database**

This loads all 229 personnel, their latest competency scores (B1-E2), targets, gaps,
and summary scores (Staff/Principal/Custodian Base/Keys/Pacing/Emerging/CTI).

Re-uploading the same (or updated) file later **updates existing records** by Staff ID
and adds a new assessment snapshot if the "Last Assessment Date" differs.

## Pages

| Page | What it shows |
|---|---|
| 🏠 Dashboard Home | Headcounts, position/department/SG distribution, chat status, completion % by department |
| 👥 Personnel Directory | Searchable/filterable table, CSV export |
| 🌡️ Competency Heatmap | B/K/P/E score heatmap, filterable by dept/position/type |
| 🔍 Individual Assessment | Per-person actual vs target bars, radar by category, gap table, history trend |
| 🎯 Readiness & Gaps | Readiness tiers (P1–P4 style: <50/50-80/80-99/≥100%), gap status (No/1/>1 gaps) |
| 📈 Trends (Age vs Grade) | Scatter: Age vs SG (colored by overall score), Years in PET vs score |
| ⚙️ Admin: Import Data | Excel import, DB status, reset |
| ⚙️ Admin: Personnel CRUD | Add / edit / soft-delete personnel |
| ⚙️ Admin: Assessment Entry | Record a new assessment with all 24 competency scores |

## Data Model

- **Grades (SG)**: P1–P8, CDH (Custodian), UPTREX, UNK (unmapped) — taken directly from
  the Excel `SG` column; falls back to a Position→SG map in `config.py` if blank.
- **Competencies**: B1-B12 (Base), K1-K5 (Knowledge — note: only 5 in your file, not 6),
  P1-P5 (Pacing), E1-E2 (Emerging — only 2 in your file, not 3).
- **Gap convention**: stored internally as `Actual − Requirement` (negative = below
  target). Note this is the **opposite sign** of the Excel's `G--` columns
  (`Requirement − Actual`) — the importer recomputes it correctly, don't be confused
  if you compare against the raw spreadsheet.

## Known Issues Fixed During Testing

1. **NaT dates crashed every insert with a missing date** (~52% of rows) — fixed in
   `db_ops._safe()`.
2. **Non-numeric Staff IDs** (`"UPTREX"`) crashed the ID-cleaning step — fixed in
   `data_loader.py`.
3. **20 people share the literal Staff ID "UPTREX"** and **20 more have no Staff ID
   at all** — both groups were being silently dropped on import (17% data loss).
   Fixed: the importer now generates a stable synthetic ID (`UPTREX-<row>` /
   `NOID-<name>-<row>`) so every one of the 229 people is retained.
4. **Gap sign convention mismatch** — Excel's `G--` columns are `Requirement − Actual`;
   the app's gap logic assumes `Actual − Requirement`. Fixed by recomputing gaps on
   import rather than copying the Excel value.

## Known Limitations / Next Steps

- "Ready" threshold in Readiness tab is fixed at 80% achievement — adjust in
  `analytics.readiness_table()` if your business rule differs.
- `Admin: Assessment Entry` lets you record a brand-new assessment date with all 24
  scores manually — useful for the *next* assessment cycle, but tedious for bulk
  corrections (use re-import for that).
- No authentication — anyone with the URL can use Admin pages.
- PostgreSQL: change `DATABASE_URL` in `config.py`.

## Files

```
app.py          – Streamlit UI (9 pages)
config.py       – grades, competency lists, colors (verified against actual Excel headers)
data_loader.py  – reads 'All' sheet (header row 3, data row 4+), cleans types
models.py       – SQLAlchemy schema (5 tables)
db_ops.py       – CRUD + bulk import + analytics queries
analytics.py    – heatmap/gap/readiness/scatter calculations
requirements.txt
```
# RE Fraternity Competency Assessment System v3.0

A Streamlit dashboard for managing and analyzing competency assessments across 229 personnel with 24 competencies.

## Features

- 📊 Dashboard with position, department, and grade distribution
- 🌡️ Competency heatmaps with filtering
- 🔍 Individual assessment profiles with gap analysis
- 🎯 Readiness tiers and gap status analysis
- 📈 Age vs Grade and Length in Position trends
- ⚙️ Admin tools for data import and personnel management

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/competency-assessment-system.git
cd competency-assessment-system
pip install -r requirements.txt
streamlit run app.py
```

## File Structure

- `app.py` - Main Streamlit application (9 pages)
- `config.py` - Configuration (grades, competencies, colors)
- `models.py` - SQLAlchemy ORM models
- `db_ops.py` - Database operations
- `data_loader.py` - Excel data loading
- `analytics.py` - Analytics calculations

## Deployment

Deploy free on [Streamlit Cloud](https://streamlit.io/cloud)

## Data

Upload the RE Fraternity Master Excel file via the Admin Import page.

## Author

Built for PETRONAS RE Fraternity