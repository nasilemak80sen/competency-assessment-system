# Competency Assessment System — v2 Modular Build

This directory is a migration-safe parallel build of the RE Fraternity Competency Assessment System.

## Why v2 exists

The current root `app.py` is intentionally left untouched. It contains the proven v3 application and remains the rollback/reference implementation.

V2 replaces the monolithic Streamlit navigation pattern with native Streamlit pages and a shared application context. Pages do not import one another. They communicate through shared services/context and `st.session_state`.

## Current structure

```text
v2/
├── app.py
├── core/
│   ├── __init__.py
│   └── bootstrap.py
├── components/
│   ├── __init__.py
│   └── navigation.py
└── pages/
    ├── 02_Personnel.py
    ├── 03_Competency_Heatmap.py
    ├── 04_Readiness_and_Gaps.py
    ├── 05_Individual_Assessment.py
    ├── 06_Chart_Builder.py
    └── 07_Admin.py
```

## Run

From the repository root:

```bash
streamlit run v2/app.py
```

## Migration rule

Do not delete or rewrite the root v3 application during migration. Move one responsibility at a time, add regression coverage, and only switch the production entry point after the v2 workflow matches the v3 behaviour.

## Next extraction phases

1. Move shared data-access helpers into services/repositories.
2. Extract assessment write workflows and CRUD behind services.
3. Extract PDF/CV/reporting workflows.
4. Add regression tests around gap/readiness calculations.
5. Add authentication and authorization before enterprise deployment.
6. Switch the production entry point only after parity testing.
