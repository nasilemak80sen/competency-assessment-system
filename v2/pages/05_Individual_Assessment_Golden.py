"""Golden-parity implementation for Individual Assessment."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import html

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
from components.competency_charts import build_actual_target_figures, render_actual_target_charts
from components.navigation import render_header, render_navigation
from config import COMPETENCY_FULLNAMES, COMP_TYPES
from core.bootstrap import get_master_data, get_ruler_data, open_session
from models import CVDocument, Personnel, SummaryScore


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
                gap = float(actual) - float(target)
                status = "Met" if gap >= 0 else "Minor Gap" if gap >= -1 else "Major Gap"
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
            records.append(
                {
                    "Code": code,
                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                    "Score": float(score),
                    "Target": pd.to_numeric(person.get(f"R-{code}"), errors="coerce"),
                }
            )
    if not records:
        return pd.DataFrame(
            columns=["Rank", "Code", "Competency", "Score", "Target", "Gap", "Gap Status"]
        )

    frame = pd.DataFrame(records)
    frame["Gap"] = frame["Score"] - frame["Target"]
    frame["Gap Status"] = frame["Gap"].apply(
        lambda gap: (
            "Target unavailable"
            if pd.isna(gap)
            else "Above Target"
            if gap > 0
            else "Gap Closed"
            if gap == 0
            else "Gap Remaining"
        )
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
                st.info("Target unavailable")
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



def _pdf(person, gap, metrics, future_gap=None, target=None):
    """Generate the complete assessment report with chart and future-grade gaps."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 8
    story = [
        Paragraph("DPE Reservoir Engineering — Individual Competency Assessment", styles["Title"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"<b>Name:</b> {html.escape(_text(person.get('Name')))} &nbsp;&nbsp; "
            f"<b>Staff ID:</b> {html.escape(_text(person.get('Staff ID')))} &nbsp;&nbsp; "
            f"<b>Nationality:</b> {html.escape(_text(person.get('Nationality')))}",
            styles["BodyText"],
        ),
        Paragraph(
            f"<b>Position:</b> {html.escape(_text(person.get('Staff Position')))} &nbsp;&nbsp; "
            f"<b>Current Grade:</b> {html.escape(_text(person.get('SG')))} &nbsp;&nbsp; "
            f"<b>Department:</b> {html.escape(_text(person.get('Department')))} &nbsp;&nbsp; "
            f"<b>Section:</b> {html.escape(_text(person.get('Section Name')))}",
            styles["BodyText"],
        ),
        Spacer(1, 3 * mm),
        Paragraph("Assessment Summary", styles["Heading2"]),
    ]
    summary_rows = [
        ["Target SG", "Weighted Readiness", "Strict Readiness", "Met", "Minor Gaps", "Major Gaps", "Not Assessed"],
        [_text(target), f"{metrics['weighted_readiness']:.1f}%", f"{metrics['strict_readiness']:.1f}%",
         metrics["met"], metrics["minor"], metrics["major"], metrics["not_assessed"]],
    ]
    t = Table(summary_rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.extend([t, Spacer(1, 4 * mm)])

    # Export the same Plotly Actual-vs-Target chart used by the page.
    chart_gap = gap.dropna(subset=["Target"]).copy()
    if not chart_gap.empty:
        comparison, _radar = build_actual_target_figures(chart_gap)
        comparison.update_layout(height=330, margin={"l": 40, "r": 15, "t": 55, "b": 70})
        image_bytes = comparison.to_image(format="png", width=1200, height=420, scale=1)
        image_buffer = BytesIO(image_bytes)
        image_buffer.seek(0)
        story.extend([
            Image(image_buffer, width=250 * mm, height=82 * mm),
            Spacer(1, 3 * mm),
        ])

    story.append(Paragraph("Full Competency Breakdown", styles["Heading2"]))
    current_rows = [["Code", "Competency", "Current SG", "Target SG", "Actual", "Target", "Gap", "Status"]]
    for _, record in gap.iterrows():
        current_rows.append([
            record["Competency"], record["Competency Name"], _text(record["Current Grade"]),
            _text(record["Target Grade"]),
            "—" if pd.isna(record["Actual"]) else f"{float(record['Actual']):.1f}",
            "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
            "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
            record["Status"],
        ])
    current_table = Table(current_rows, repeatRows=1,
        colWidths=[18*mm, 67*mm, 22*mm, 22*mm, 18*mm, 18*mm, 18*mm, 35*mm])
    current_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.extend([current_table, PageBreak()])

    if future_gap is not None and not future_gap.empty:
        story.append(Paragraph(
            f"Forward-Looking Promotion Gap Matrix — Current {html.escape(_text(person.get('SG')))} to Higher Salary Grades",
            styles["Heading2"],
        ))
        story.append(Paragraph(
            "Actual scores are held constant and compared with each higher salary-grade requirement. "
            "All competency codes are retained so the promotion path is visible end-to-end.",
            styles["BodyText"],
        ))
        future_summary = _future_grade_summary(future_gap)
        if not future_summary.empty:
            matrix = [list(future_summary.columns)] + future_summary.fillna("—").astype(str).values.tolist()
            summary_table = Table(matrix, repeatRows=1)
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]))
            story.extend([summary_table, Spacer(1, 4 * mm)])

        future_rows = [["Target SG", "Code", "Competency", "Category", "Actual", "Target", "Gap", "Status"]]
        for _, record in future_gap.iterrows():
            future_rows.append([
                record["Target SG"], record["Competency"], record["Competency Name"], record["Category"],
                "—" if pd.isna(record["Actual"]) else f"{float(record['Actual']):.1f}",
                "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
                "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
                record["Status"],
            ])
        future_table = Table(future_rows, repeatRows=1,
            colWidths=[18*mm, 15*mm, 65*mm, 25*mm, 18*mm, 18*mm, 18*mm, 40*mm])
        future_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(future_table)

    document.build(story)
    buffer.seek(0)
    return buffer.getvalue()




def render_page():
    render_navigation()
    render_header(
        "👤 Individual Assessment & Talent Profile",
        "Personnel profile, competency readiness, gaps and supporting documents",
    )

    df = get_master_data()
    ruler_map, _tech_labels = get_ruler_data()
    if df is None or df.empty:
        st.info("No personnel data is available. Import the master workbook first.")
        st.stop()

    if "Name" not in df.columns:
        st.error("The personnel dataset does not contain the required Name column.")
        st.stop()

    names = sorted(
        df["Name"].dropna().astype(str).str.strip().loc[lambda s: s.ne("")].unique()
    )
    if not names:
        st.error("No valid personnel names are available.")
        st.stop()

    selection_col, refresh_col = st.columns([5, 1], vertical_alignment="bottom")
    with selection_col:
        selected_name = st.selectbox("Select Personnel", names, key="personnel_select")
    with refresh_col:
        if st.button("🔄 Refresh", type="secondary", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    selected_rows = df[df["Name"].astype(str).str.strip() == str(selected_name).strip()]
    if selected_rows.empty:
        st.error("The selected personnel record could not be found.")
        st.stop()
    if len(selected_rows) > 1:
        st.warning(
            "More than one record has the selected name. The first record is being displayed. "
            "Use Staff ID as the selector in a future update to eliminate name ambiguity."
        )
    person = selected_rows.iloc[0]

    session = open_session()
    db = None
    docs = []
    summary = None
    history = []
    retrieval_error = None
    try:
        staff_id = person.get("Staff ID")
        if pd.notna(staff_id):
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

        second_row = st.columns(5)
        second_row[0].metric("Age", _int(person.get("Age"), "N/A"))
        second_row[1].metric("Years in PETRONAS", _int(person.get("Years in PET")))
        second_row[2].metric("Years of RE Experiences", _int(person.get("Years of RE Experience")))
        second_row[3].metric("Contract Expiry Date", _date(person.get("Contract Expire Date")))
        second_row[4].metric("Length in Grade", _int(person.get("Years in Salary Grade")))

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
            _pdf(person, gap, metrics, future_gap=future_gap, target=target),
            f"Assessment_{_safe_name(selected_name)}_{target or 'target'}_{datetime.now():%Y%m%d}.pdf",
            "application/pdf",
            width="stretch",
        )


render_page()
