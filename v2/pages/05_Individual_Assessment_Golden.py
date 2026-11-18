"""Golden-parity implementation for Individual Assessment."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.readiness import (
    _rg_determine_target_sg,
    _rg_grade_rank,
    _rg_get_person_ruler,
    _rg_sort_salary_grades,
    build_target_gap_dataframe,
    calculate_readiness_metrics,
)
from components.competency_charts import render_actual_target_charts
from components.competency_charts import build_actual_target_figures
from components.navigation import render_header, render_navigation
from config import COMPETENCY_FULLNAMES, COMP_TYPES, EXCEL_PATH
from core.bootstrap import get_master_data, get_ruler_data, open_session
from models import CVDocument, Personnel, SummaryScore
from services.assessment_report_service import generate_assessment_pdf


def _text(value, fallback="Not Applicable"):
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "nat"} else fallback


def _int(value, fallback="Not Applicable"):
    number = pd.to_numeric(value, errors="coerce")
    return fallback if pd.isna(number) else int(round(float(number)))


def _date(value, fallback="Not Applicable"):
    parsed = pd.to_datetime(value, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def _pct(value):
    number = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(number) else f"{float(number):.0f}%"


def _safe_name(value):
    return "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(value)
    ).strip("_") or "personnel"

def _normalise_staff_id(value):
    """Normalise workbook Staff IDs for stable matching to SQLite records."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    key = str(value).strip()
    if not key or key.casefold() in {"nan", "none", "nat"}:
        return None
    if key.endswith(".0") and key[:-2].isdigit():
        key = key[:-2]
    return key.casefold()



def _all_competency_codes():
    codes = []
    for config in COMP_TYPES.values():
        for code in config.get("cols", []):
            if code not in codes:
                codes.append(code)
    return codes


def _build_future_grade_gap_dataframe(person, requirements, current_sg):
    """Build a complete forward-looking gap matrix for every higher P-grade."""
    current_rank = _rg_grade_rank(current_sg)
    if current_rank is None:
        return pd.DataFrame()
    grades = [
        grade for grade in _rg_sort_salary_grades(requirements.keys())
        if _rg_grade_rank(grade) is not None and _rg_grade_rank(grade) > current_rank
    ]
    records = []
    for grade in grades:
        grade_requirements = requirements.get(grade, {}) or {}
        for code in _all_competency_codes():
            actual = pd.to_numeric(person.get(code), errors="coerce")
            target = pd.to_numeric(grade_requirements.get(code), errors="coerce")
            if pd.isna(target):
                gap = pd.NA
                status = "Requirement Unavailable"
            elif pd.isna(actual):
                gap = pd.NA
                status = "Not Assessed"
            else:
                gap = float(target) - float(actual)
                status = "Met" if gap <= 0 else "Minor Gap" if gap <= 1 else "Major Gap"
            records.append({
                "Target SG": grade,
                "Competency": code,
                "Competency Name": COMPETENCY_FULLNAMES.get(code, code),
                "Category": next(
                    (config.get("label", key) for key, config in COMP_TYPES.items()
                     if code in config.get("cols", [])),
                    "Other",
                ),
                "Actual": actual,
                "Target": target,
                "Gap": gap,
                "Status": status,
            })
    return pd.DataFrame(records)


def _future_grade_summary(future_gap):
    if future_gap is None or future_gap.empty:
        return pd.DataFrame()
    rows = []
    for grade, part in future_gap.groupby("Target SG", sort=False):
        rows.append({
            "Target SG": grade,
            "Met": int((part["Status"] == "Met").sum()),
            "Minor Gaps": int((part["Status"] == "Minor Gap").sum()),
            "Major Gaps": int((part["Status"] == "Major Gap").sum()),
            "Not Assessed": int((part["Status"] == "Not Assessed").sum()),
            "Requirement Unavailable": int((part["Status"] == "Requirement Unavailable").sum()),
        })
    return pd.DataFrame(rows)


def _strength_frame(person, competency_type):
    records = []
    for code in COMP_TYPES.get(competency_type, {}).get("cols", []):
        score = pd.to_numeric(person.get(code), errors="coerce")
        if pd.notna(score):
            target = pd.to_numeric(person.get(f"R-{code}"), errors="coerce")
            gap_column = (
                f"G--{code}" if f"G--{code}" in person.index
                else f"G-{code}" if f"G-{code}" in person.index
                else None
            )
            # Raw assessment gaps should match the source workbook, including
            # blank cells. Only derive a gap when no source gap column exists.
            if gap_column is not None:
                gap = pd.to_numeric(person.get(gap_column), errors="coerce")
            else:
                gap = target - float(score) if pd.notna(target) else float("nan")
            records.append(
                {
                    "Code": code,
                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                    "Score": float(score),
                    "Target": target,
                    "Gap": gap,
                }
            )
    if not records:
        return pd.DataFrame(
            columns=["Rank", "Code", "Competency", "Score", "Target", "Gap", "Gap Status"]
        )

    frame = pd.DataFrame(records)
    frame["Gap Status"] = frame.apply(
        lambda row: (
            ("Target unavailable" if pd.isna(row["Target"]) else "Gap not recorded")
            if pd.isna(row["Gap"])
            else "Gap Remaining"
            if row["Gap"] > 0
            else "Gap Closed"
            if row["Gap"] == 0
            else "Above Target"
        ),
        axis=1,
    )
    frame = frame.sort_values(
        ["Score", "Competency"], ascending=[False, True]
    ).reset_index(drop=True)
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    return frame


def _render_competency_strength_class(person, competency_type):
    class_config = COMP_TYPES.get(competency_type, {})
    class_label = class_config.get("label", competency_type)
    strength_df = _strength_frame(person, competency_type)

    if strength_df.empty:
        st.info(f"No assessed {class_label.lower()} scores are available for this personnel.")
        return

    top3 = strength_df.head(3)
    medals = ["🥇", "🥈", "🥉"]
    cards = st.columns(len(top3))

    for index, (_, record) in enumerate(top3.iterrows()):
        with cards[index]:
            st.markdown(f"### {medals[index]}")
            st.markdown(f"**{record['Competency']}**")
            st.metric("Score", f"{record['Score']:.0f}")
            if pd.notna(record["Target"]):
                st.caption(f"Target: **{float(record['Target']):.0f}**")
            else:
                st.caption("Target: **Not Available**")

            gap = record["Gap"]
            if pd.isna(gap):
                st.info("Gap not recorded in workbook" if pd.notna(record["Target"]) else "Target unavailable")
            elif gap > 0:
                st.success(f"Gap: +{gap:.0f} · Above Target")
            elif gap == 0:
                st.success("Gap: 0 · Gap Closed")
            else:
                st.warning(f"Gap: {gap:.0f} · Gap Remaining")

    with st.expander(f"📋 Full {class_label} competency ranking"):
        st.dataframe(
            strength_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Score": st.column_config.NumberColumn("Score", format="%.1f"),
                "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                "Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
            },
        )



def _pdf(person, gap, metrics, future_gap=None, target=None, history=None, summary=None, career_ruler=None):
    """Compatibility wrapper around the shared assessment PDF generator."""
    return generate_assessment_pdf(
        person,
        gap,
        metrics,
        future_gap=future_gap,
        target=target,
        career_ruler=career_ruler,
        history=history,
        summary=summary,
    )


def render_page():
    render_navigation()
    render_header(
        "👤 Individual Assessment & Talent Profile",
        "Personnel profile, competency readiness, gaps and supporting documents",
    )
    st.caption(f"Master workbook source: {EXCEL_PATH}")

    df = get_master_data()
    ruler_map, _tech_labels = get_ruler_data()
    if df is None or df.empty:
        st.info("No personnel data is available. Import the master workbook first.")
        st.stop()

    if "Name" not in df.columns:
        st.error("The personnel dataset does not contain the required Name column.")
        st.stop()

    # OpenGlobus profile links pass the stable SQLite Personnel primary key.
    # Resolve that ID to its Staff ID first, then preselect the matching workbook
    # row. Names remain visible in the selector, but Staff ID removes ambiguity.
    requested_personnel_id = None
    requested_staff_id = None
    requested_person_name = None

    # The OpenGlobus component selects a profile through Streamlit's active
    # session. Consume that ID first; retain the query-parameter fallback for
    # older bookmarks and manually shared assessment links.
    requested_id_value = st.session_state.pop("requested_personnel_id", None)
    if requested_id_value is None:
        requested_id_value = st.query_params.get("personnel_id")

    if requested_id_value:
        try:
            requested_personnel_id = int(requested_id_value)
            lookup_session = open_session()
            try:
                requested_person = (
                    lookup_session.query(Personnel.id, Personnel.staff_id, Personnel.name)
                    .filter(
                        Personnel.id == requested_personnel_id,
                        Personnel.is_deleted.is_not(True),
                    )
                    .first()
                )
            finally:
                lookup_session.close()
            if requested_person is not None:
                requested_staff_id = requested_person.staff_id
                requested_person_name = requested_person.name
            else:
                st.warning(
                    "The linked personnel profile is unavailable or archived. "
                    "Please select a current personnel record."
                )
                requested_personnel_id = None
        except (TypeError, ValueError):
            st.warning("The personnel profile link contains an invalid database ID.")
            requested_personnel_id = None

    profile_df = df.reset_index(drop=True).copy()
    profile_df = profile_df[
        profile_df["Name"].notna()
        & profile_df["Name"].astype(str).str.strip().ne("")
    ].copy()
    if profile_df.empty:
        st.error("No valid personnel names are available.")
        st.stop()

    base_labels = []
    for _, row in profile_df.iterrows():
        name = str(row.get("Name", "")).strip()
        staff_value = row.get("Staff ID")
        staff_id = (
            ""
            if staff_value is None or pd.isna(staff_value)
            else str(staff_value).strip()
        )
        if staff_id.casefold() in {"nan", "none", "nat"}:
            staff_id = ""
        base_labels.append(f"{name} · {staff_id}" if staff_id else name)

    label_counts = {}
    for label in base_labels:
        label_counts[label] = label_counts.get(label, 0) + 1
    labels = [
        label if label_counts[label] == 1 else f"{label} · record {index + 1}"
        for index, label in enumerate(base_labels)
    ]

    default_index = 0
    requested_staff_key = _normalise_staff_id(requested_staff_id)
    if requested_staff_key:
        matching_indexes = [
            index for index, (_, row) in enumerate(profile_df.iterrows())
            if _normalise_staff_id(row.get("Staff ID")) == requested_staff_key
        ]
        if len(matching_indexes) == 1:
            default_index = matching_indexes[0]
        elif requested_person_name:
            name_matches = [
                index for index, name in enumerate(profile_df["Name"].astype(str))
                if name.strip().casefold() == str(requested_person_name).strip().casefold()
            ]
            if len(name_matches) == 1:
                default_index = name_matches[0]
            else:
                st.warning(
                    "The linked database record could not be matched uniquely to "
                    "the master workbook. Please verify its Staff ID."
                )

    # A map selection may target a different person from the previous page
    # visit. Clear the prior widget choice so the database ID drives this run.
    if requested_personnel_id is not None:
        st.session_state.pop("personnel_profile_select", None)

    selection_col, refresh_col = st.columns([5, 1], vertical_alignment="bottom")
    with selection_col:
        selected_label = st.selectbox(
            "Select Personnel",
            labels,
            index=default_index,
            key="personnel_profile_select",
        )
    with refresh_col:
        if st.button("🔄 Refresh", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    selected_index = labels.index(selected_label)
    person = profile_df.iloc[selected_index]
    selected_name = str(person.get("Name", "")).strip()

    session = open_session()
    db = None
    docs = []
    summary = None
    history = []
    retrieval_error = None
    try:
        staff_id = person.get("Staff ID")
        selected_staff_key = _normalise_staff_id(staff_id)
        if (
            requested_personnel_id is not None
            and requested_staff_key
            and selected_staff_key == requested_staff_key
        ):
            db = (
                session.query(Personnel)
                .filter(
                    Personnel.id == requested_personnel_id,
                    Personnel.is_deleted.is_not(True),
                )
                .first()
            )
        if db is None and pd.notna(staff_id):
            db = (
                session.query(Personnel)
                .filter(Personnel.staff_id == str(staff_id))
                .first()
            )
        if db is None:
            db = session.query(Personnel).filter(Personnel.name == selected_name).first()
        if db:
            docs = (
                session.query(CVDocument)
                .filter(CVDocument.personnel_id == db.id, CVDocument.is_deleted == False)
                .order_by(CVDocument.modified_date.desc())
                .all()
            )
            summary = (
                session.query(SummaryScore)
                .filter(SummaryScore.personnel_id == db.id)
                .first()
            )
            for assessment in sorted(
                db.assessments,
                key=lambda value: value.assessment_date or datetime.min,
            ):
                for score in assessment.scores:
                    history.append(
                        {
                            "date": assessment.assessment_date,
                            "type": score.competency_type,
                            "actual": score.actual_score,
                        }
                    )
    except Exception as exc:
        retrieval_error = str(exc)
    finally:
        session.close()

    overview, documents = st.tabs(["👤 Personnel Overview", "📄 CV & Documents"])

    with overview:
        st.subheader("📋 Personnel Profile")
        st.caption("Core identity and employment profile")
        first_row = st.columns(5)
        first_row[0].metric("Position / Grade", f"{_text(person.get('Staff Position'))} ({_text(person.get('SG'))})")
        first_row[1].metric("Department / Section", f"{_text(person.get('Department'))} ({_text(person.get('Section Name'))})")
        first_row[2].metric("Nationality", _text(person.get("Nationality")))
        first_row[3].metric("Current Assignment", _text(person.get("Current Location:"), "Not available"))
        first_row[4].metric("Employment Type", _text(person.get("Employment Category")))

        second_row = st.columns(6)
        second_row[0].metric("Age", _int(person.get("Age"), "N/A"))
        second_row[1].metric("Years in PETRONAS", _int(person.get("Years in PET")))
        second_row[2].metric("Years of RE Experiences", _int(person.get("Years of RE Experience")))
        second_row[3].metric("Contract Expiry Date", _date(person.get("Contract Expire Date")))
        second_row[4].metric("Length in Grade", _int(person.get("Years in Salary Grade")))
        second_row[5].metric("Assessment Type", _text(person.get("Assessment Level")))

        st.markdown("### 💪 Talent Profile")
        talent_cols = st.columns(3)
        talent_cols[0].markdown(
            "#### 💪 Strength\n\n" + _text(person.get("Strength"), "No strength information available.")
        )
        talent_cols[1].markdown(
            "#### ❤️ Interest\n\n" + _text(person.get("Interest"), "No interest information available.")
        )
        talent_cols[2].markdown(
            "#### 🎓 Background\n\n"
            + _text(
                person.get("Background") or person.get("Sub-Disciplines"),
                "No background information available.",
            )
        )

        st.markdown("---")
        st.markdown("### 📊 Assessment-Based Competency Strength")
        st.caption(
            "Automatically derived from the selected personnel's assessed competency scores. "
            "The strongest competencies are ranked within each competency class."
        )
        strength_tabs = st.tabs(["🟢 Base", "🔵 Key", "🟠 Pace", "🟣 Emerging"])
        for tab, code in zip(strength_tabs, ["B", "K", "P", "E"]):
            with tab:
                _render_competency_strength_class(person, code)

    with documents:
        st.subheader("📄 Curriculum Vitae & Supporting Documents")
        if retrieval_error:
            st.error(f"Unable to retrieve document records: {retrieval_error}")
        elif db is None:
            st.warning("The selected personnel could not be matched to a database record.")
            with st.expander("Personnel matching diagnostics"):
                st.write(
                    {
                        "Name": person.get("Name"),
                        "Staff ID": person.get("Staff ID"),
                        "DataFrame ID": person.get("id"),
                        "DataFrame has ID column": "id" in df.columns,
                    }
                )
        elif not docs:
            st.info("No CV or supporting document is registered for this personnel.")
            st.caption(f"Database personnel ID: {db.id}")
        else:
            data = pd.DataFrame(
                [
                    {
                        "CV File Name": item.cv_file_name or "Document",
                        "File Type": item.file_type or "N/A",
                        "Modified Date": item.modified_date,
                        "Status": item.cv_status or "N/A",
                        "SharePoint URL": (item.sharepoint_url or "").strip(),
                        "Match Method": getattr(item, "match_method", None) or "Database personnel match",
                        "Notes": getattr(item, "notes", None) or "",
                        "id": getattr(item, "id", None),
                    }
                    for item in docs
                ]
            )
            data["Valid SharePoint URL"] = data["SharePoint URL"].str.lower().str.startswith(
                ("https://", "http://")
            )
            valid = data[data["Valid SharePoint URL"]].copy()
            invalid = data[~data["Valid SharePoint URL"]].copy()

            valid["Modified Date"] = pd.to_datetime(valid["Modified Date"], errors="coerce")
            sort_columns = [column for column in ["Modified Date", "id"] if column in valid.columns]
            if sort_columns:
                valid = valid.sort_values(
                    sort_columns,
                    ascending=[False] * len(sort_columns),
                    na_position="last",
                )

            if valid.empty:
                st.warning("Document records exist, but none has a valid SharePoint HTTPS link.")
                diagnostic_columns = [
                    column
                    for column in ["CV File Name", "File Type", "SharePoint URL", "Match Method", "Notes"]
                    if column in invalid.columns
                ]
                with st.expander("Document import diagnostics", expanded=True):
                    st.dataframe(invalid[diagnostic_columns], width="stretch", hide_index=True)
            else:
                latest = valid.iloc[0]
                latest_col, type_col, modified_col = st.columns([2, 1, 1])
                latest_col.metric("Latest Document", latest["CV File Name"])
                type_col.metric("File Type", latest["File Type"])
                modified_col.metric(
                    "Last Modified",
                    _date(latest["Modified Date"], "Date unavailable"),
                )
                st.link_button(
                    "📄 Open Latest Document in SharePoint",
                    latest["SharePoint URL"],
                    width="stretch",
                )
                st.caption(f"{len(valid)} valid document link(s) available.")

                with st.expander(
                    f"🗂️ View all documents ({len(valid)})",
                    expanded=len(valid) <= 3,
                ):
                    for _, document in valid.iterrows():
                        info_col, action_col = st.columns([4, 1], vertical_alignment="center")
                        info_col.markdown(
                            f"**{document['CV File Name']}**  \n"
                            f"`{document['File Type']}` • Modified "
                            f"{_date(document['Modified Date'], 'Date unavailable')}"
                        )
                        action_col.link_button("Open", document["SharePoint URL"], width="stretch")
                        st.divider()

                if not invalid.empty:
                    diagnostic_columns = [
                        column
                        for column in ["CV File Name", "File Type", "SharePoint URL", "Match Method", "Notes"]
                        if column in invalid.columns
                    ]
                    with st.expander(
                        f"⚠️ Documents without valid links ({len(invalid)})"
                    ):
                        st.dataframe(invalid[diagnostic_columns], width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("🎯 Target Definition & Career Progression")
    st.caption(
        "The workbook's recorded assessment gaps are shown above. This section "
        "recalculates gaps against the selected career-ruler target, so values "
        "can differ when a different ruler or target grade is selected."
    )
    rulers = list(ruler_map.keys())
    career = _rg_get_person_ruler(person, ruler_map) if rulers else None
    target_cols = st.columns([1.4, 1.4, 1])

    with target_cols[0]:
        ruler = (
            st.selectbox(
                "Career Ruler",
                rulers,
                index=rulers.index(career) if career in rulers else 0,
                key="individual_target_ruler",
            )
            if rulers
            else None
        )
    requirements = ruler_map.get(ruler, {}) if ruler else {}
    grades = _rg_sort_salary_grades(requirements.keys())

    with target_cols[1]:
        mode = st.selectbox(
            "Target Requirement",
            ["Next salary grade", "Current requirement", "Selected target grade"],
            key="individual_target_mode",
        )
    with target_cols[2]:
        target = (
            st.selectbox("Selected Target SG", grades, key="individual_target_sg")
            if mode == "Selected target grade" and grades
            else _rg_determine_target_sg(person.get("SG"), requirements, mode)
        )
        st.caption(f"Target SG: **{target or 'Not available'}**")

    gap = (
        build_target_gap_dataframe(
            person,
            requirements.get(target, {}),
            person.get("SG"),
            target,
            person.get("Staff Position"),
            ruler,
            COMPETENCY_FULLNAMES,
        )
        if target in requirements
        else pd.DataFrame()
    )
    metrics = calculate_readiness_metrics(gap)

    if gap.empty:
        st.warning("No competency requirements could be matched to the selected personnel and target mode.")
    else:
        st.subheader(f"📊 Assessment Summary vs Target ({target})")
        status_cols = st.columns(4)
        status_cols[0].metric("Total Competencies", metrics["total"])
        status_cols[1].metric("Weighted Readiness", f"{metrics['weighted_readiness']:.0f}%")
        status_cols[2].metric("Strict Readiness", f"{metrics['strict_readiness']:.0f}%")
        overall_status = (
            "Ready ✅"
            if metrics["weighted_readiness"] >= 80
            else "On Track 🟡"
            if metrics["weighted_readiness"] >= 60
            else "Needs Work 🔴"
        )
        status_cols[3].metric("Overall Status", overall_status)

        counts = st.columns(4)
        counts[0].metric("Met", metrics["met"])
        counts[1].metric("Minor Gaps", metrics["minor"])
        counts[2].metric("Major Gaps", metrics["major"])
        counts[3].metric("Not Assessed", metrics["not_assessed"])

        st.markdown("#### 🔥 Priority Development Areas")
        priority = gap[gap["Status"].isin(["Major Gap", "Minor Gap"])].copy()
        if priority.empty:
            st.success("🎉 No competency gaps were identified for the selected Target SG.")
        else:
            st.dataframe(
                priority[["Competency", "Competency Name", "Actual", "Target", "Gap", "Status"]],
                width="stretch",
                hide_index=True,
            )

        st.markdown("#### Full Competency Breakdown")
        st.dataframe(
            gap[
                [
                    "Competency",
                    "Competency Name",
                    "Current Grade",
                    "Target Grade",
                    "Actual",
                    "Target",
                    "Gap",
                    "Status",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        st.markdown("### 📈 Gap Analysis Visualizations")
        render_actual_target_charts(gap)

        future_gap = _build_future_grade_gap_dataframe(person, requirements, person.get("SG"))
        if not future_gap.empty:
            st.markdown("### 🚀 Forward-Looking Promotion Gap Matrix")
            st.caption(
                "Current assessment scores are compared against every higher salary grade. "
                "For example, a P3 personnel will see the complete P4–P10 competency path."
            )
            st.dataframe(_future_grade_summary(future_gap), width="stretch", hide_index=True)
            with st.expander("📋 Full competency gaps for all future salary grades", expanded=True):
                st.dataframe(
                    future_gap[[
                        "Target SG", "Competency", "Competency Name",
                        "Category", "Actual", "Target", "Gap", "Status"
                    ]],
                    width="stretch",
                    hide_index=True,
                )
        else:
            future_gap = pd.DataFrame()
            st.info("No higher P-grade requirements are available for this personnel's current grade/ruler.")

    if summary:
        with st.expander("📊 Summary Personnel Scores and Competencies", expanded=True):
            groups = {
                "Next Grade": ["next_grade_base", "next_grade_keys", "next_grade_pacing", "next_grade_emerging", "next_grade_cti"],
                "Staff": ["staff_base", "staff_keys", "staff_pacing", "staff_emerging", "staff_cti"],
                "Principal": ["principal_base", "principal_keys", "principal_pacing", "principal_emerging", "principal_cti"],
                "Custodian": ["custodian_base", "custodian_keys", "custodian_pacing", "custodian_emerging", "custodian_cti"],
            }
            summary_tabs = st.tabs(["🎯 Next Grade", "👤 Staff", "⭐ Principal", "🏆 Custodian"])
            for tab, (_group_name, fields) in zip(summary_tabs, groups.items()):
                with tab:
                    columns = st.columns(5)
                    for column, label, field in zip(
                        columns,
                        ["Base", "Keys", "Pacing", "Emerging", "CTI"],
                        fields,
                    ):
                        column.metric(label, _pct(getattr(summary, field, None)))

    if history:
        history_df = pd.DataFrame(history)
        history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
        history_summary = (
            history_df.groupby(["date", "type"], as_index=False)["actual"].mean()
        )
        history_fig = go.Figure()
        for assessment_type in history_summary["type"].dropna().unique():
            subset = history_summary[history_summary["type"] == assessment_type]
            history_fig.add_trace(
                go.Scatter(
                    x=subset["date"],
                    y=subset["actual"],
                    mode="lines+markers",
                    name=str(assessment_type),
                )
            )
        history_fig.update_layout(
            title="Average Competency Score by Assessment Date",
            height=350,
            yaxis={"range": [0, 5], "dtick": 1},
        )
        st.subheader("📅 Assessment History")
        st.plotly_chart(history_fig, width="stretch", config={"displaylogo": False})
    else:
        st.info("No assessment history is available for this personnel.")

    if not gap.empty:
        st.download_button(
            "📥 Download PDF Report",
            _pdf(
                person,
                gap,
                metrics,
                future_gap=future_gap,
                target=target,
                history=history,
                summary=summary,
                career_ruler=ruler,
            ),
            f"Assessment_{_safe_name(selected_name)}_{target or 'target'}_{datetime.now():%Y%m%d}.pdf",
            "application/pdf",
            width="stretch",
        )


render_page()
