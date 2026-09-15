"""Individual Assessment & Talent Profile — native v2 page."""
from __future__ import annotations

from io import BytesIO
from datetime import datetime
import pandas as pd
import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data, get_ruler_data, open_session
from models import CVDocument, Personnel
from analytics.readiness import build_readiness_detail_dataframe, build_personnel_readiness_summary

render_navigation()
render_header("👤 Individual Assessment & Talent Profile", "Personnel profile, competency readiness, gaps and supporting documents")

df = get_master_data()
ruler_map, tech_labels = get_ruler_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

names = sorted(df["Name"].dropna().astype(str).unique())
selected_name = st.selectbox("Select Personnel", names, key="individual_personnel_select")
person_rows = df[df["Name"].astype(str) == selected_name]
if person_rows.empty:
    st.stop()
person = person_rows.iloc[0]

# Resolve database record for CV/assessment history.
session = open_session()
db_person = None
try:
    staff_id = person.get("Staff ID")
    if pd.notna(staff_id):
        db_person = session.query(Personnel).filter(Personnel.staff_id == str(staff_id)).first()
    if db_person is None:
        db_person = session.query(Personnel).filter(Personnel.name == selected_name).first()
    cv_rows = []
    if db_person is not None:
        cv_rows = session.query(CVDocument).filter(CVDocument.personnel_id == db_person.id, CVDocument.is_deleted == False).order_by(CVDocument.modified_date.desc()).all()
finally:
    session.close()

profile_cols = st.columns(5)
profile_cols[0].metric("Staff ID", str(person.get("Staff ID") or "N/A"))
profile_cols[1].metric("Position", str(person.get("Staff Position") or "N/A"))
profile_cols[2].metric("Salary Grade", str(person.get("SG") or "N/A"))
profile_cols[3].metric("Department", str(person.get("Department") or "N/A"))
profile_cols[4].metric("Assessment Level", str(person.get("Assessment Level") or "N/A"))

st.markdown("### 💪 Talent Profile")
talent_cols = st.columns(3)
talent_cols[0].markdown(f"**Strength**\n\n{person.get('Strength') or 'No strength information available.'}")
talent_cols[1].markdown(f"**Interest**\n\n{person.get('Interest') or 'No interest information available.'}")
talent_cols[2].markdown(f"**Background**\n\n{person.get('Background') or person.get('Sub-Disciplines') or 'No background information available.'}")

# Current-grade readiness detail.
detail = build_readiness_detail_dataframe(person_rows, ruler_map, "Current requirement")
summary = build_personnel_readiness_summary(detail)
if not summary.empty:
    row = summary.iloc[0]
    readiness_cols = st.columns(5)
    readiness_cols[0].metric("Weighted Readiness", f"{row['Weighted Readiness %']:.0f}%")
    readiness_cols[1].metric("Strict Readiness", f"{row['Strict Readiness %']:.0f}%")
    readiness_cols[2].metric("Coverage", f"{row['Assessment Coverage %']:.0f}%")
    readiness_cols[3].metric("Major Gaps", int(row['Major Gaps']))
    readiness_cols[4].metric("Status", row["Readiness Status"])

st.markdown("### 📊 Competency Profile")
if detail.empty:
    st.info("No competency requirements are available for this personnel's current ruler/grade.")
else:
    display = detail[["Category","Competency Code","Competency Name","Actual Score","Target Score","Gap","Gap Severity"]].copy()
    display.columns = ["Category","Code","Competency","Actual","Target","Gap","Status"]
    st.dataframe(display.sort_values(["Status","Code"]), width="stretch", hide_index=True)

# Supporting CV/documents.
st.markdown("### 📄 Curriculum Vitae & Supporting Documents")
if not cv_rows:
    st.info("No CV or supporting document is registered for this personnel.")
else:
    cv_data = pd.DataFrame([
        {"File Name": r.cv_file_name, "File Type": r.file_type or "N/A", "Modified Date": r.modified_date, "Status": r.cv_status or "N/A", "SharePoint URL": r.sharepoint_url or ""}
        for r in cv_rows
    ])
    st.dataframe(cv_data, width="stretch", hide_index=True, column_config={"SharePoint URL": st.column_config.LinkColumn("SharePoint URL")})

# Lightweight native report: no legacy runtime dependency.
def build_pdf_report(person_row, readiness_row, detail_df):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph("DPE Reservoir Engineering — Individual Competency Assessment", styles["Title"]), Spacer(1, 6*mm)]
    story.append(Paragraph(f"<b>Name:</b> {person_row.get('Name','N/A')} &nbsp;&nbsp; <b>Staff ID:</b> {person_row.get('Staff ID','N/A')}", styles["BodyText"]))
    story.append(Paragraph(f"<b>Position:</b> {person_row.get('Staff Position','N/A')} &nbsp;&nbsp; <b>Grade:</b> {person_row.get('SG','N/A')}", styles["BodyText"]))
    story.append(Spacer(1, 4*mm))
    if readiness_row is not None:
        story.append(Paragraph("Readiness Summary", styles["Heading2"]))
        data = [["Weighted", "Strict", "Coverage", "Major Gaps", "Status"], [f"{readiness_row['Weighted Readiness %']:.1f}%", f"{readiness_row['Strict Readiness %']:.1f}%", f"{readiness_row['Assessment Coverage %']:.1f}%", str(int(readiness_row['Major Gaps'])), str(readiness_row['Readiness Status'])]]
        table = Table(data)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#20419A")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CBD5E1")),("ALIGN",(0,0),(-1,-1),"CENTER")]))
        story.extend([table, Spacer(1, 4*mm)])
    story.append(Paragraph("Competency Gaps", styles["Heading2"]))
    rows = [["Code","Competency","Actual","Target","Gap","Status"]]
    for _, r in detail_df[detail_df["Gap"].notna() & (detail_df["Gap"] < 0)].iterrows():
        rows.append([str(r["Competency Code"]), str(r["Competency Name"]), f"{r['Actual Score']:.1f}", f"{r['Target Score']:.1f}", f"{r['Gap']:.1f}", str(r["Gap Severity"])])
    if len(rows) == 1:
        rows.append(["—","No assessed gaps","—","—","—","—"])
    gap_table = Table(rows, repeatRows=1, colWidths=[18*mm,75*mm,20*mm,20*mm,18*mm,28*mm])
    gap_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#20419A")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#CBD5E1")),("FONTSIZE",(0,0),(-1,-1),7)]))
    story.append(gap_table)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"Generated {datetime.now():%d %b %Y}", styles["BodyText"]))
    doc.build(story)
    buffer.seek(0)
    return buffer

if not summary.empty:
    pdf = build_pdf_report(person, summary.iloc[0], detail)
    st.download_button("⬇️ Download Individual Assessment Report (PDF)", pdf, f"{selected_name.replace(' ', '_')}_assessment_report.pdf", "application/pdf")
