"""Administration — native v2 CRUD and assessment entry page."""
from __future__ import annotations
from datetime import date, datetime
import pandas as pd
import streamlit as st
from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data, open_session
from models import Personnel
from services.personnel_service import update as update_personnel, delete as delete_personnel
from services.assessment_service import add_assessment, add_competency_scores
from config import SCORE_COLS, ASSESSMENT_LEVELS, CHAT_STATUS_OPTIONS, COMP_TYPES, DEPARTMENTS, POSITIONS, POSITION_TO_SG

render_navigation()
render_header("⚙️ Admin: Personnel Database Settings", "Maintain personnel records and enter competency assessments")

def _safe_int(value, default=0, minimum=None, maximum=None):
    try:
        if value is None or pd.isna(value): return default
    except (TypeError, ValueError): return default
    if isinstance(value,(pd.Timestamp,datetime,date)): n=int(value.year)
    else:
        x=pd.to_numeric(value,errors="coerce")
        if pd.notna(x): n=int(round(float(x)))
        else:
            d=pd.to_datetime(value,errors="coerce")
            if pd.isna(d): return default
            n=int(d.year)
    if minimum is not None and n<minimum: return default
    if maximum is not None and n>maximum: return default
    return n

def _safe_birth_year(value, default=1980):
    try:
        if value is None or pd.isna(value): return default
    except (TypeError,ValueError): return default
    if isinstance(value,(pd.Timestamp,datetime,date)):
        y=int(value.year); return y if 1950<=y<=2010 else default
    x=pd.to_numeric(value,errors="coerce")
    if pd.notna(x):
        x=float(x)
        if 1950<=x<=2010: return int(round(x))
        if 10000<=x<=60000:
            d=pd.to_datetime(x,unit="D",origin="1899-12-30",errors="coerce")
            if pd.notna(d) and 1950<=d.year<=2010: return int(d.year)
        if abs(x)>1_000_000_000:
            d=pd.to_datetime(int(x),unit="ns",errors="coerce")
            if pd.notna(d) and 1950<=d.year<=2010: return int(d.year)
    d=pd.to_datetime(value,errors="coerce")
    return int(d.year) if pd.notna(d) and 1950<=d.year<=2010 else default

def _text(row,key,default=""):
    v=row.get(key)
    try:
        if pd.isna(v): return default
    except (TypeError,ValueError): pass
    return str(v).strip()

def _num(value,default=0.0,lo=0.0,hi=600.0):
    x=pd.to_numeric(value,errors="coerce")
    return float(x) if pd.notna(x) and lo<=float(x)<=hi else float(default)

def _date(value):
    d=pd.to_datetime(value,errors="coerce")
    return date.today() if pd.isna(d) else d.date()

df=get_master_data()
if df is None or df.empty: st.info("No personnel available. Import data first."); st.stop()
names=sorted(df["Name"].dropna().astype(str).unique())
selected_name=st.selectbox("Select Personnel",names,key="personnel_db_selector")
row=df[df["Name"].astype(str)==selected_name].iloc[0]
pid=_safe_int(row.get("id"),0,1) if "id" in row.index and pd.notna(row.get("id")) else None
if pid is None:
    s=open_session()
    try:
        sid=row.get("Staff ID")
        p=s.query(Personnel).filter(Personnel.staff_id==str(sid)).first() if pd.notna(sid) else None
        if p is None: p=s.query(Personnel).filter(Personnel.name==selected_name).first()
        pid=p.id if p else None
    finally: s.close()
if pid is None: st.warning("No database personnel ID found for this person. Import data to enable editing."); st.stop()

st.caption(f"Editing: **{selected_name}**")
prefix=f"personnel_db_{pid}"
personnel_tab,assessment_tab,delete_tab=st.tabs(["✏️ Edit Personnel Info","🧾 Assessment Entry","🗑️ Delete Personnel"])

with personnel_tab:
    with st.form("personnel_database_form"):
        st.markdown("### Personal")
        c1,c2,c3=st.columns(3)
        with c1:
            name=st.text_input("Name",_text(row,"Name"),key=f"{prefix}_name")
            staff_id=st.text_input("Staff ID",_text(row,"Staff ID"),key=f"{prefix}_staff_id")
            email=st.text_input("Email",_text(row,"Email Address"),key=f"{prefix}_email")
        with c2:
            gopts=["M","F","Other"]; gv=_text(row,"Gender","M")
            gender=st.selectbox("Gender",gopts,index=gopts.index(gv) if gv in gopts else 0,key=f"{prefix}_gender")
            age=st.number_input("Age",min_value=18,max_value=100,value=_safe_int(row.get("Age"),30,18,100),step=1,key=f"{prefix}_age")
            birth_year=st.number_input("Birth Year",min_value=1950,max_value=2010,value=_safe_birth_year(row.get("Birth Year")),step=1,key=f"{prefix}_birth_year")
            nationality=st.text_input("Nationality",_text(row,"Nationality","Malaysia"),key=f"{prefix}_nationality")
        with c3:
            employment_category=st.text_input("Employment Category",_text(row,"Employment Category"),key=f"{prefix}_employment_category")
            dopt=list(DEPARTMENTS[:-1]); dv=_text(row,"Department",dopt[0]); department=st.selectbox("Department",dopt,index=dopt.index(dv) if dv in dopt else 0,key=f"{prefix}_department")
            popt=list(POSITIONS[:-1]); pv=_text(row,"Staff Position",popt[0]); staff_position=st.selectbox("Staff Position",popt,index=popt.index(pv) if pv in popt else 0,key=f"{prefix}_position")
            sg=st.text_input("SG",_text(row,"SG") or POSITION_TO_SG.get(pv,""),key=f"{prefix}_sg")
        st.markdown("### Employment")
        e1,e2,e3=st.columns(3)
        with e1:
            section_name=st.text_input("Section Name",_text(row,"Section Name"),key=f"{prefix}_section")
            unit_name=st.text_input("Unit Name",_text(row,"Unit Name"),key=f"{prefix}_unit")
            sub_unit=st.text_input("Sub Unit",_text(row,"Sub Unit"),key=f"{prefix}_subunit")
            current_assignment=st.text_input("Current Assignment",_text(row,"Current Location:"),key=f"{prefix}_assignment")
        with e2:
            joining_date=st.date_input("Joining Date",_date(row.get("Joining Date")),key=f"{prefix}_joining")
            contract_expire_date=st.date_input("Contract Expire Date",_date(row.get("Contract Expire Date")),key=f"{prefix}_contract")
            assignment_date=st.date_input("Assignment Date",_date(row.get("Assignment Date") or row.get("Date in Position")),key=f"{prefix}_assignmentdate")
            sg_start_date=st.date_input("SG Start Date",_date(row.get("SG Start Date") or row.get("Date of Appointment to Current Grade")),key=f"{prefix}_sgstart")
        with e3:
            years_in_pet=st.number_input("Years in PET",0.0,60.0,_num(row.get("Years in PET")),0.5,key=f"{prefix}_pet")
            years_re_experience=st.number_input("Years of RE Experience",0.0,60.0,_num(row.get("Years of RE Experience")),0.5,key=f"{prefix}_re")
            sg_years=st.number_input("Years in Salary Grade",0.0,60.0,_num(row.get("Years in Salary Grade")),0.5,key=f"{prefix}_sgyears")
            age_promoted=st.number_input("Age Promoted",18.0,100.0,_num(row.get("Age Promoted to Staff or Principal"),30,18,100),1.0,key=f"{prefix}_ageprom")
            assignment_length=st.number_input("Length in Current Assignment",0.0,600.0,_num(row.get("Length in Current Assignment")),1.0,key=f"{prefix}_assignlen")
        st.markdown("### Tenure")
        t1,t2=st.columns(2)
        with t1:
            copts=list(CHAT_STATUS_OPTIONS); cv=_text(row,"Chat Status","No Need"); chat_status=st.selectbox("Chat Status",copts,index=copts.index(cv) if cv in copts else 0,key=f"{prefix}_chat")
            chat_date=st.date_input("Chat Date",_date(row.get("Chat Date")),key=f"{prefix}_chatdate")
            lv=list(ASSESSMENT_LEVELS); av=_text(row,"Assessment Level",lv[0]); assessment_level=st.selectbox("Assessment Level",lv,index=lv.index(av) if av in lv else 0,key=f"{prefix}_level")
            last_assessment_date=st.date_input("Last Assessment Date",_date(row.get("Last Assessment Date") or row.get("Last Assesment Date")),key=f"{prefix}_lastdate")
        with t2:
            sub_disciplines=st.text_input("Sub-disciplines",_text(row,"Sub-Disciplines"),key=f"{prefix}_subdisc")
            potential=st.text_input("Potential",_text(row,"Potential"),key=f"{prefix}_potential")
            resource_sme=st.text_input("Resource / SME",_text(row,"Resource/SME"),key=f"{prefix}_resource")
            interest=st.text_input("Interest",_text(row,"Interest"),key=f"{prefix}_interest")
        st.markdown("### Assessment")
        a1,a2=st.columns(2)
        with a1:
            strength=st.text_area("Strength",_text(row,"Strength"),height=140,key=f"{prefix}_strength")
            recommendation=st.text_area("Recommendation",_text(row,"Recommendation"),height=140,key=f"{prefix}_recommendation")
        with a2:
            preference=st.text_input("Preference",_text(row,"Preference"),key=f"{prefix}_preference")
            comment=st.text_area("Comment / Suggestion",_text(row,"Comment/Suggestion") or _text(row,"Comment"),height=140,key=f"{prefix}_comment")
            assessor1=st.text_input("Assessor 1",_text(row,"Assesor1") or _text(row,"Assessor1"),key=f"{prefix}_assessor1")
            assessor2=st.text_input("Assessor 2",_text(row,"Assessor2"),key=f"{prefix}_assessor2")
            supervisor=st.text_input("Supervisor",_text(row,"Supervisor"),key=f"{prefix}_supervisor")
            remarks=st.text_area("Remarks",_text(row,"Remarks"),height=120,key=f"{prefix}_remarks")
        submitted=st.form_submit_button("💾 Save Personnel Info",type="primary")
    if submitted:
        payload={"name":name.strip(),"staff_id":staff_id.strip(),"email":email.strip() or None,"gender":gender,"age":int(age),"birth_year":int(birth_year),"nationality":nationality.strip() or "Malaysia","employment_category":employment_category.strip() or None,"department":department,"section_name":section_name.strip() or None,"unit_name":unit_name.strip() or None,"sub_unit":sub_unit.strip() or None,"staff_position":str(staff_position),"sg":sg.strip() or POSITION_TO_SG.get(str(staff_position),""),"joining_date":joining_date,"contract_expire_date":contract_expire_date,"years_in_pet":float(years_in_pet),"years_re_experience":float(years_re_experience),"sg_years":float(sg_years),"sg_start_date":sg_start_date,"age_promoted":float(age_promoted),"current_assignment":current_assignment.strip() or None,"assignment_date":assignment_date,"assignment_length":float(assignment_length),"chat_status":chat_status,"chat_date":chat_date,"assessment_level":assessment_level,"last_assessment_date":last_assessment_date,"sub_disciplines":sub_disciplines.strip() or None,"potential":potential.strip() or None,"strength":strength.strip() or None,"recommendation":recommendation.strip() or None,"resource_sme":resource_sme.strip() or None,"interest":interest.strip() or None,"preference":preference.strip() or None,"comment":comment.strip() or None,"assessor1":assessor1.strip() or None,"assessor2":assessor2.strip() or None,"supervisor":supervisor.strip() or None,"remarks":remarks.strip() or None}
        s=open_session()
        try:
            ok,msg=update_personnel(s,pid,payload)
            if ok: st.success(msg); st.cache_data.clear(); st.rerun()
            else: st.error(msg)
        except Exception as exc: s.rollback(); st.error(f"Unable to update personnel: {exc}")
        finally: s.close()

with assessment_tab:
    st.markdown(f"### Assessment Entry for **{selected_name}**")
    st.markdown(f"**{_text(row,'Staff Position')}** • **{_text(row,'Department')}** • **{_text(row,'SG')}**")
    with st.form("assessment_entry_form"):
        c1,c2=st.columns(2)
        with c1:
            adate=st.date_input("Assessment Date",date.today(),key="admin_assessment_date")
            level=st.selectbox("Assessment Level",list(ASSESSMENT_LEVELS),key="admin_assessment_level")
        with c2:
            assessor1_entry=st.text_input("Assessor 1",key="admin_assessor1")
            supervisor_entry=st.text_input("Supervisor",key="admin_supervisor")
        st.markdown("### Competency Scores")
        st.caption("Actual / Target — leave target as the previous value if unsure.")
        score_inputs={}
        for ctype,info in COMP_TYPES.items():
            with st.expander(f"{info['label']} ({ctype})",expanded=(ctype=="B")):
                for code in info["cols"]:
                    actual_prev=pd.to_numeric(row.get(code),errors="coerce"); req_prev=pd.to_numeric(row.get(f"R-{code}"),errors="coerce")
                    left,right=st.columns(2)
                    with left: actual=st.number_input(f"{code} Actual",min_value=0.0,max_value=5.0,value=float(actual_prev) if pd.notna(actual_prev) else 0.0,step=0.5,key=f"admin_act_{code}_{pid}")
                    with right: requirement=st.number_input(f"{code} Target",min_value=0.0,max_value=5.0,value=float(req_prev) if pd.notna(req_prev) else 3.0,step=0.5,key=f"admin_req_{code}_{pid}")
                    score_inputs[code]={"actual":actual,"req":requirement,"gap":round(max(requirement-actual,0),2)}
        save_assessment=st.form_submit_button("💾 Save Assessment",type="primary")
    if save_assessment:
        s=open_session()
        try:
            ok,msg,aid=add_assessment(s,pid,{"assessment_date":adate,"assessment_level":level,"assessor1":assessor1_entry.strip() or None,"supervisor":supervisor_entry.strip() or None})
            if ok:
                ok2,msg2=add_competency_scores(s,aid,pid,score_inputs)
                if ok2: st.success(f"✅ Assessment saved for {selected_name} on {adate}"); st.cache_data.clear()
                else: st.error(msg2)
            else: st.error(msg)
        except Exception as exc: s.rollback(); st.error(f"Unable to save assessment: {exc}")
        finally: s.close()

with delete_tab:
    st.warning(f"⚠️ This will soft-delete **{selected_name}** (Staff ID: {_text(row,'Staff ID','N/A')}).")
    confirm_name=st.text_input("Type the person name to confirm deletion",key="personnel_delete_confirm")
    if st.button("Confirm Soft Delete",type="primary",disabled=(confirm_name.strip()!=selected_name.strip())):
        s=open_session()
        try:
            ok,msg=delete_personnel(s,pid)
            if ok: st.success(msg); st.cache_data.clear(); st.rerun()
            else: st.error(msg)
        except Exception as exc: s.rollback(); st.error(f"Unable to delete personnel: {exc}")
        finally: s.close()
