"""Golden-parity implementation for Individual Assessment."""
from __future__ import annotations
from datetime import datetime
from io import BytesIO
import html
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data, get_ruler_data, open_session
from models import CVDocument, Personnel, SummaryScore
from config import COMP_TYPES, COMPETENCY_FULLNAMES
from analytics.readiness import _rg_get_person_ruler,_rg_determine_target_sg,_rg_sort_salary_grades,build_target_gap_dataframe,calculate_readiness_metrics

def _text(v, fallback="Not Applicable"):
    if v is None:return fallback
    try:
        if pd.isna(v):return fallback
    except (TypeError,ValueError):pass
    s=str(v).strip();return s if s and s.lower() not in {"nan","none","nat"} else fallback

def _int(v,fallback="Not Applicable"):
    n=pd.to_numeric(v,errors="coerce");return fallback if pd.isna(n) else int(round(float(n)))

def _date(v,fallback="Not Applicable"):
    d=pd.to_datetime(v,errors="coerce");return fallback if pd.isna(d) else d.strftime("%d %b %Y")

def _pct(v):
    n=pd.to_numeric(v,errors="coerce");return "N/A" if pd.isna(n) else f"{float(n):.0f}%"

def _safe_name(v):return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(v)).strip("_") or "personnel"

def _strength(person,ctype):
    records=[]
    for code in COMP_TYPES.get(ctype,{}).get("cols",[]):
        n=pd.to_numeric(person.get(code),errors="coerce")
        if pd.notna(n):records.append({"Code":code,"Competency":COMPETENCY_FULLNAMES.get(code,code),"Score":float(n)})
    if records:st.dataframe(pd.DataFrame(records).sort_values("Score",ascending=False),width="stretch",hide_index=True)
    else:st.info("No assessed competency scores are available for this competency class.")

def _pdf(person,gap,metrics):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    b=BytesIO();d=SimpleDocTemplate(b,pagesize=A4,leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm);s=getSampleStyleSheet();story=[Paragraph("DPE Reservoir Engineering — Individual Competency Assessment",s["Title"]),Spacer(1,5*mm),Paragraph(f"<b>Name:</b> {html.escape(_text(person.get('Name')))} &nbsp;&nbsp; <b>Staff ID:</b> {html.escape(_text(person.get('Staff ID')))}",s["BodyText"]),Paragraph(f"<b>Position:</b> {html.escape(_text(person.get('Staff Position')))} &nbsp;&nbsp; <b>Grade:</b> {html.escape(_text(person.get('SG')))}",s["BodyText"])]
    story += [Spacer(1,4*mm),Paragraph("Assessment Summary",s["Heading2"]),Table([["Weighted","Strict","Met","Minor","Major"],[f"{metrics['weighted_readiness']:.1f}%",f"{metrics['strict_readiness']:.1f}%",metrics['met'],metrics['minor'],metrics['major']]])]
    rows=[["Code","Competency","Actual","Target","Gap","Status"]]
    for _,r in gap[gap["Status"].isin(["Major Gap","Minor Gap"])].iterrows():rows.append([r["Competency"],r["Competency Name"],"—" if pd.isna(r["Actual"]) else f"{r['Actual']:.1f}",f"{r['Target']:.1f}","—" if pd.isna(r["Gap"]) else f"{r['Gap']:.1f}",r["Status"]])
    if len(rows)==1:rows.append(["—","No assessed gaps","—","—","—","—"])
    t=Table(rows,repeatRows=1);t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#20419A")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.grey)]));story += [Spacer(1,4*mm),Paragraph("Competency Gaps",s["Heading2"]),t];d.build(story);b.seek(0);return b.getvalue()

def render_page():
    render_navigation();render_header("👤 Individual Assessment & Talent Profile","Personnel profile, competency readiness, gaps and supporting documents")
    df=get_master_data();ruler_map,_=get_ruler_data()
    if df is None or df.empty:st.info("No personnel data is available. Import the master workbook first.");st.stop()
    names=sorted(df["Name"].dropna().astype(str).str.strip().unique());sel,ref=st.columns([5,1],vertical_alignment="bottom")
    with sel:selected=st.selectbox("Select Personnel",names,key="personnel_select")
    with ref:
        if st.button("🔄 Refresh",type="secondary",width="stretch"):st.cache_data.clear();st.rerun()
    person_rows=df[df["Name"].astype(str).str.strip()==selected]
    if person_rows.empty:st.error("The selected personnel record could not be found.");st.stop()
    person=person_rows.iloc[0];session=open_session();db=None;docs=[];summary=None;history=[]
    try:
        sid=person.get("Staff ID")
        if pd.notna(sid):db=session.query(Personnel).filter(Personnel.staff_id==str(sid)).first()
        if db is None:db=session.query(Personnel).filter(Personnel.name==selected).first()
        if db:
            docs=session.query(CVDocument).filter(CVDocument.personnel_id==db.id,CVDocument.is_deleted==False).order_by(CVDocument.modified_date.desc()).all();summary=session.query(SummaryScore).filter(SummaryScore.personnel_id==db.id).first()
            for a in sorted(db.assessments,key=lambda x:x.assessment_date or datetime.min):
                for score in a.scores:history.append({"date":a.assessment_date,"type":score.competency_type,"actual":score.actual_score})
    finally:session.close()
    overview,documents=st.tabs(["👤 Personnel Overview","📄 CV & Documents"])
    with overview:
        st.subheader("📋 Personnel Profile");c=st.columns(5);c[0].metric("Position / Grade",f"{_text(person.get('Staff Position'))} ({_text(person.get('SG'))})");c[1].metric("Department / Section",f"{_text(person.get('Department'))} ({_text(person.get('Section Name'))})");c[2].metric("Current Assignment",_text(person.get("Current Location:"),"Not available"));c[3].metric("Years in PETRONAS",_int(person.get("Years in PET")));c[4].metric("Years of RE Experiences",_int(person.get("Years of RE Experience")))
        c=st.columns(5);c[0].metric("Age",_int(person.get("Age"),"N/A"));c[1].metric("Employment Type",_text(person.get("Employment Category")));c[2].metric("Contract Expiry Date",_date(person.get("Contract Expire Date")));c[3].metric("Length in Grade",_int(person.get("Years in Salary Grade")));c[4].metric("Assessment Type",_text(person.get("Assessment Level")))
        st.markdown("### 💪 Talent Profile");c=st.columns(3);c[0].markdown("#### 💪 Strength\n\n"+_text(person.get("Strength"),"No strength information available."));c[1].markdown("#### ❤️ Interest\n\n"+_text(person.get("Interest"),"No interest information available."));c[2].markdown("#### 🎓 Background\n\n"+_text(person.get("Background") or person.get("Sub-Disciplines"),"No background information available."))
        st.markdown("---");st.markdown("### 📊 Assessment-Based Competency Strength");st.caption("Automatically derived from the selected personnel's assessed competency scores. The strongest competencies are ranked within each competency class.")
        for tab,code in zip(st.tabs(["🟢 Base","🔵 Key","🟠 Pace","🟣 Emerging"]),["B","K","P","E"]):
            with tab:_strength(person,code)
    with documents:
        st.subheader("📄 Curriculum Vitae & Supporting Documents")
        if db is None:st.warning("The selected personnel could not be matched to a database record.")
        elif not docs:st.info("No CV or supporting document is registered for this personnel.")
        else:
            data=pd.DataFrame([{"CV File Name":x.cv_file_name or "Document","File Type":x.file_type or "N/A","Modified Date":x.modified_date,"Status":x.cv_status or "N/A","SharePoint URL":(x.sharepoint_url or "").strip()} for x in docs]);data["Valid"]=data["SharePoint URL"].str.lower().str.startswith(("https://","http://"));valid=data[data["Valid"]].copy();invalid=data[~data["Valid"]].copy()
            if not valid.empty:
                valid["Modified Date"]=pd.to_datetime(valid["Modified Date"],errors="coerce");valid=valid.sort_values("Modified Date",ascending=False,na_position="last");latest=valid.iloc[0];c=st.columns([2,1,1]);c[0].metric("Latest Document",latest["CV File Name"]);c[1].metric("File Type",latest["File Type"]);c[2].metric("Last Modified",_date(latest["Modified Date"],"Date unavailable"));st.link_button("📄 Open Latest Document in SharePoint",latest["SharePoint URL"],width="stretch");st.caption(f"{len(valid)} valid document link(s) available.")
                with st.expander(f"🗂️ View all documents ({len(valid)})",expanded=len(valid)<=3):
                    for _,x in valid.iterrows():a,b=st.columns([4,1]);a.markdown(f"**{x['CV File Name']}**  \n`{x['File Type']}` • Modified {_date(x['Modified Date'],'Date unavailable')}");b.link_button("Open",x["SharePoint URL"],width="stretch");st.divider()
            else:st.warning("Document records exist, but none has a valid SharePoint HTTPS link.")
            if not invalid.empty:
                with st.expander(f"⚠️ Documents without valid links ({len(invalid)})"):st.dataframe(invalid.drop(columns=["Valid"],errors="ignore"),width="stretch",hide_index=True)
    st.markdown("---");st.subheader("🎯 Target Definition & Career Progression")
    rulers=list(ruler_map.keys());career=_rg_get_person_ruler(person,ruler_map) if rulers else None;c=st.columns([1.4,1.4,1])
    with c[0]:ruler=st.selectbox("Career Ruler",rulers,index=rulers.index(career) if career in rulers else 0,key="individual_target_ruler") if rulers else None
    req=ruler_map.get(ruler,{}) if ruler else {};grades=_rg_sort_salary_grades(req.keys())
    with c[1]:mode=st.selectbox("Target Requirement",["Next salary grade","Current requirement","Selected target grade"],key="individual_target_mode")
    with c[2]:target=st.selectbox("Selected Target SG",grades,key="individual_target_sg") if mode=="Selected target grade" and grades else _rg_determine_target_sg(person.get("SG"),req,mode);st.caption(f"Target SG: **{target or 'Not available'}**")
    gap=build_target_gap_dataframe(person,req.get(target,{}),person.get("SG"),target,person.get("Staff Position"),ruler,COMPETENCY_FULLNAMES) if target in req else pd.DataFrame();metrics=calculate_readiness_metrics(gap)
    if not gap.empty:
        st.subheader("Assessment Summary vs Target");c=st.columns(4);c[0].metric("Total Competencies",metrics["total"]);c[1].metric("Weighted Readiness",f"{metrics['weighted_readiness']:.0f}%");c[2].metric("Strict Readiness",f"{metrics['strict_readiness']:.0f}%");c[3].metric("Overall Status","Ready ✅" if metrics["weighted_readiness"]>=80 else ("On Track 🟡" if metrics["weighted_readiness"]>=60 else "Needs Work 🔴"));c=st.columns(4);c[0].metric("Met",metrics["met"]);c[1].metric("Minor Gaps",metrics["minor"]);c[2].metric("Major Gaps",metrics["major"]);c[3].metric("Not Assessed",metrics["not_assessed"])
        st.markdown("#### 🔥 Priority Development Areas");priority=gap[gap["Status"].isin(["Major Gap","Minor Gap"])];st.success("🎉 No competency gaps were identified for the selected Target SG.") if priority.empty else st.dataframe(priority[["Competency","Competency Name","Actual","Target","Gap","Status"]],width="stretch",hide_index=True);st.markdown("#### Full Competency Breakdown");st.dataframe(gap[["Competency","Competency Name","Current Grade","Target Grade","Actual","Target","Gap","Status"]],width="stretch",hide_index=True)
        st.markdown("### 📈 Gap Analysis Visualizations");a,b=st.columns([3,2]);f=go.Figure([go.Bar(x=gap["Competency"],y=gap["Target"],name="Target"),go.Bar(x=gap["Competency"],y=gap["Actual"],name="Actual")]);f.update_layout(title="Actual vs Target Competency Scores",height=500,yaxis={"range":[0,5],"dtick":1},barmode="group");a.plotly_chart(f,width="stretch",config={"displaylogo":False});r=go.Figure([go.Scatterpolar(r=gap["Actual"].fillna(0),theta=gap["Competency"],fill="toself",name="Actual"),go.Scatterpolar(r=gap["Target"],theta=gap["Competency"],name="Target")]);r.update_layout(title="Competency Radar",height=500,polar={"radialaxis":{"range":[0,5],"dtick":1}});b.plotly_chart(r,width="stretch",config={"displaylogo":False})
    else:st.warning("No target requirements could be matched to the selected personnel and target mode.")
    if summary:
        with st.expander("📊 Summary Personnel Scores and Competencies",expanded=True):
            groups={"Next Grade":["next_grade_base","next_grade_keys","next_grade_pacing","next_grade_emerging","next_grade_cti"],"Staff":["staff_base","staff_keys","staff_pacing","staff_emerging","staff_cti"],"Principal":["principal_base","principal_keys","principal_pacing","principal_emerging","principal_cti"],"Custodian":["custodian_base","custodian_keys","custodian_pacing","custodian_emerging","custodian_cti"]}
            for tab,(group,fields) in zip(st.tabs(["🎯 Next Grade","👤 Staff","⭐ Principal","🏆 Custodian"]),groups.items()):
                with tab:
                    c=st.columns(5)
                    for col,label,field in zip(c,["Base","Keys","Pacing","Emerging","CTI"],fields):col.metric(label,_pct(getattr(summary,field,None)))
    if history:
        h=pd.DataFrame(history);h["date"]=pd.to_datetime(h["date"],errors="coerce");hs=h.groupby(["date","type"],as_index=False)["actual"].mean();f=go.Figure()
        for typ in hs["type"].dropna().unique():x=hs[hs["type"]==typ];f.add_trace(go.Scatter(x=x["date"],y=x["actual"],mode="lines+markers",name=str(typ)))
        f.update_layout(title="Average Competency Score by Assessment Date",height=350,yaxis={"range":[0,5],"dtick":1});st.subheader("📅 Assessment History");st.plotly_chart(f,width="stretch",config={"displaylogo":False})
    if not gap.empty:st.download_button("📥 Download PDF Report",_pdf(person,gap,metrics),f"Assessment_{_safe_name(selected_name)}_{target or 'target'}_{datetime.now():%Y%m%d}.pdf","application/pdf",width="stretch")

render_page()
