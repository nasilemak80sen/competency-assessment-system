"""OpenGlobus 3D Earth nationality intelligence component for Streamlit."""
from __future__ import annotations
import json
import pandas as pd
import streamlit.components.v1 as components
from config import NATIONALITY_ALIASES

OPEN_GLOBUS_VERSION = "0.28.7"
OPEN_GLOBUS_JS = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.es.js"
OPEN_GLOBUS_CSS = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.css"
OPEN_GLOBUS_RESOURCES = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res"
OPEN_GLOBUS_FONTS = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res/fonts"
PERSONNEL_FIELDS = ["Staff ID","Name","Staff Position","Department","SG","Employment Category","Section Name","Current Location:"]

def _normalise_nationality(value: object) -> str:
    value = "" if value is None or pd.isna(value) else str(value).strip()
    return NATIONALITY_ALIASES.get(value, value)

def _personnel_records(personnel_df: pd.DataFrame, valid_nationalities: set[str]) -> list[dict]:
    if personnel_df is None or personnel_df.empty or "Nationality" not in personnel_df.columns:
        return []
    records=[]
    for _,row in personnel_df.iterrows():
        raw=str(row.get("Nationality","") or "").strip()
        if not raw: continue
        for nationality in [_normalise_nationality(part) for part in raw.split("/")]:
            if nationality not in valid_nationalities: continue
            person={"nationality":nationality}
            for field in PERSONNEL_FIELDS:
                if field in personnel_df.columns:
                    value=row.get(field,"")
                    if pd.isna(value): value=""
                    person[field]=str(value)
            records.append(person)
    return records

def _records_from_map_df(map_df: pd.DataFrame, personnel_df: pd.DataFrame | None = None) -> list[dict]:
    if map_df is None or map_df.empty: return []
    required={"Nationality","Personnel Count","Latitude","Longitude"}
    missing=required.difference(map_df.columns)
    if missing: raise ValueError(f"OpenGlobus nationality data is missing columns: {sorted(missing)}")
    valid={_normalise_nationality(v) for v in map_df["Nationality"].tolist()}
    people=_personnel_records(personnel_df,valid)
    records=[]
    for _,row in map_df.iterrows():
        try:
            count=int(float(row["Personnel Count"])); lat=float(row["Latitude"]); lon=float(row["Longitude"])
        except (TypeError,ValueError): continue
        if count<=0: continue
        representation=row.get("Representation Display","")
        if pd.isna(representation): representation=""
        nationality=str(row["Nationality"])
        records.append({"nationality":nationality,"count":count,"latitude":lat,"longitude":lon,
                        "representation":str(representation),
                        "people":[p for p in people if p["nationality"]==nationality]})
    return records

def _build_openglobus_html(records: list[dict], height: int = 620) -> str:
    safe_height=max(520,int(height))
    payload=json.dumps(records,ensure_ascii=False).replace("</","<\\\\/")
    template=r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="__CSS__">
<style>
html,body{width:100%;height:100%;margin:0;padding:0;overflow:hidden;background:transparent;font-family:Arial,sans-serif}
#shell{position:relative;width:100%;height:__HEIGHT__px;min-height:520px;overflow:hidden;border-radius:14px;background:radial-gradient(circle at 50% 45%,#fff 0%,#eef4f5 62%,#dfeaec 100%);box-shadow:inset 0 0 0 1px rgba(22,58,64,.08)}
#globus{position:absolute;inset:0;width:100%;height:100%}
#hud{position:absolute;left:16px;top:14px;z-index:30;pointer-events:none;padding:9px 12px;border-radius:10px;background:rgba(255,255,255,.88);backdrop-filter:blur(8px);box-shadow:0 5px 18px rgba(18,47,53,.10);color:#183238}
#hud .title{font-size:13px;font-weight:700}.subtitle{margin-top:2px;font-size:10px;opacity:.68}
#toolbar{position:absolute;left:16px;bottom:16px;z-index:40;width:min(430px,calc(100% - 32px));padding:10px;border-radius:12px;background:rgba(255,255,255,.93);backdrop-filter:blur(10px);box-shadow:0 8px 28px rgba(18,47,53,.16)}
#toolbar .row{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:7px}
#toolbar select,#toolbar button{width:100%;box-sizing:border-box;border:1px solid #d4e0e2;border-radius:8px;padding:7px 8px;background:#fff;color:#183238;font-size:11px}
#toolbar button{cursor:pointer;font-weight:700}#toolbar button:hover{border-color:#00a19c}
#stats{font-size:10px;color:#52676b;padding:2px 2px 0}
#details{position:absolute;right:16px;top:16px;z-index:40;width:min(330px,calc(100% - 32px));max-height:calc(100% - 32px);overflow:auto;box-sizing:border-box;padding:14px;border-radius:12px;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);box-shadow:0 10px 30px rgba(18,47,53,.18);color:#183238;display:none}
#details.visible{display:block}#details .close{float:right;border:0;background:transparent;cursor:pointer;font-size:18px}
#details h3{margin:0 28px 3px 0;font-size:16px}.muted{font-size:10px;color:#63767a}
#details .kpi{display:flex;gap:16px;margin:12px 0}.kpi strong{display:block;font-size:18px}
.person{padding:7px 0;border-top:1px solid #e7eeee;font-size:10px}.person strong{font-size:11px}#people{margin-top:10px}
#status{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:50;padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.94);box-shadow:0 8px 28px rgba(18,47,53,.15);color:#183238;font-size:13px}.hidden{display:none}
#legend{position:absolute;right:16px;bottom:16px;z-index:30;padding:8px 10px;border-radius:9px;background:rgba(255,255,255,.84);color:#52676b;font-size:9px}
.legend-dot{display:inline-block;border-radius:50%;background:#00a19c;vertical-align:middle;margin:0 4px}
#attribution{position:absolute;right:12px;top:8px;z-index:30;padding:4px 7px;border-radius:6px;background:rgba(255,255,255,.72);color:#4a6065;font-size:8px}#attribution a{color:#34666c;text-decoration:none}
@media(max-width:700px){#details{width:calc(100% - 32px);max-height:46%;top:auto;bottom:112px}#legend,#attribution{display:none}}
</style></head>
<body><div id="shell"><div id="globus"></div>
<div id="hud"><div class="title">🌍 RE Nationality Intelligence Globe</div><div class="subtitle">Explore personnel distribution by nationality and workforce attributes</div></div>
<div id="status">Loading 3D Earth…</div>
<div id="details"><button class="close" id="closeDetails">×</button><h3 id="detailNationality">Nationality</h3><div class="muted" id="detailRepresentation"></div>
<div class="kpi"><div><strong id="detailCount">0</strong><span class="muted">personnel</span></div><div><strong id="detailSections">0</strong><span class="muted">sections</span></div></div>
<button id="flyTo" style="width:100%;padding:7px;border:1px solid #d4e0e2;border-radius:8px;background:#00a19c;color:white;font-weight:700;cursor:pointer">📍 Fly to nationality</button><div id="people"></div></div>
<div id="toolbar"><div class="row"><select id="employmentFilter"><option value="">All Employment Categories</option></select><select id="sgFilter"><option value="">All Salary Grades</option></select></div>
<div class="row"><select id="sectionFilter"><option value="">All Sections</option></select><button id="resetFilters">↺ Reset Filters</button></div><div id="stats"></div></div>
<div id="legend"><span class="legend-dot" style="width:8px;height:8px"></span> lower <span class="legend-dot" style="width:13px;height:13px"></span> medium <span class="legend-dot" style="width:19px;height:19px"></span> higher concentration</div>
<div id="attribution">OpenGlobus · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a></div></div>
<script type="module">
import {Globe,GlobusRgbTerrain,OpenStreetMap,control,Vector,Entity,LonLat} from "__JS__";
const records=__PAYLOAD__,status=document.getElementById("status"),details=document.getElementById("details"),stats=document.getElementById("stats"),employmentFilter=document.getElementById("employmentFilter"),sgFilter=document.getElementById("sgFilter"),sectionFilter=document.getElementById("sectionFilter");
let globe=null,nationalityLayer=null,selectedRecord=null;
const uniqueValues=field=>[...new Set(records.flatMap(r=>r.people||[]).map(p=>p[field]).filter(Boolean))].sort();
const addOptions=(select,values)=>values.forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;select.appendChild(o)});
addOptions(employmentFilter,uniqueValues("Employment Category"));addOptions(sgFilter,uniqueValues("SG"));addOptions(sectionFilter,uniqueValues("Section Name"));
function visiblePeople(record){const people=record.people||[];if(!people.length)return null;return people.filter(p=>(!employmentFilter.value||p["Employment Category"]===employmentFilter.value)&&(!sgFilter.value||p["SG"]===sgFilter.value)&&(!sectionFilter.value||p["Section Name"]===sectionFilter.value));}
function markerSvg(count,selected=false){const maxCount=Math.max(...records.map(r=>{const p=visiblePeople(r);return p===null?r.count:p.length}),1);const n=Math.sqrt(Math.max(count,1))/Math.sqrt(maxCount),radius=9+n*11,h=Math.ceil(radius*2+8),fill=selected?"#20419A":"#00A19C";const cx=h/2,cy=radius+4;const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+h+'" height="'+h+'" viewBox="0 0 '+h+' '+h+'"><circle cx="'+cx+'" cy="'+cy+'" r="'+radius+'" fill="'+fill+'" fill-opacity=".94" stroke="#fff" stroke-width="3"/><circle cx="'+cx+'" cy="'+cy+'" r="'+Math.max(3,radius*.28)+'" fill="#fff"/></svg>';return"data:image/svg+xml;charset=utf-8,"+encodeURIComponent(svg);}
function renderLayer(){const entities=records.map(record=>{const people=visiblePeople(record);const count=people===null?record.count:people.length;if(!count)return null;const selected=selectedRecord&&selectedRecord.nationality===record.nationality;return new Entity({name:record.nationality,lonlat:[record.longitude,record.latitude],billboard:{src:markerSvg(count,selected),size:[44,44],offset:[0,20]},label:{text:record.nationality+" · "+count,size:selected?16:12,offset:[0,30,0],color:selected?"rgba(32,65,154,.98)":"rgba(24,50,56,.94)",outlineColor:"rgba(255,255,255,.96)",outline:2},properties:{nationality:record.nationality,personnel:count,representation:record.representation,latitude:record.latitude,longitude:record.longitude}})}).filter(Boolean);nationalityLayer.setEntities(entities);const total=entities.reduce((sum,e)=>sum+Number(e.properties?.personnel||0),0);stats.textContent=total+" visible personnel · "+entities.length+" nationalities · Click a pin for details";}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));}
function showDetails(record){selectedRecord=record;const people=visiblePeople(record);const detailPeople=people===null?record.people||[]:people;document.getElementById("detailNationality").textContent="🌐 "+record.nationality;document.getElementById("detailRepresentation").textContent="Representation: "+(record.representation||"—");document.getElementById("detailCount").textContent=detailPeople.length||record.count;document.getElementById("detailSections").textContent=new Set(detailPeople.map(p=>p["Section Name"]).filter(Boolean)).size;document.getElementById("people").innerHTML=detailPeople.length?detailPeople.slice(0,60).map(p=>'<div class="person"><strong>'+escapeHtml(p["Name"]||"Unnamed")+'</strong><br>'+escapeHtml(p["Staff Position"]||"Position not specified")+" · "+escapeHtml(p["SG"]||"SG —")+'<br><span class="muted">'+escapeHtml(p["Department"]||"Department —")+" · "+escapeHtml(p["Section Name"]||"Section —")+"</span></div>").join(""):'<div class="muted">No personnel match the current filters.</div>';details.classList.add("visible");renderLayer();}
function flyToRecord(record){if(!globe||!globe.planet?.camera)return;globe.planet.camera.flyLonLat(new LonLat(record.longitude,record.latitude,3500000),{duration:900});}
function clearSelection(){selectedRecord=null;details.classList.remove("visible");renderLayer();}
[employmentFilter,sgFilter,sectionFilter].forEach(el=>el.addEventListener("change",clearSelection));
document.getElementById("resetFilters").addEventListener("click",()=>{employmentFilter.value="";sgFilter.value="";sectionFilter.value="";clearSelection()});
document.getElementById("closeDetails").addEventListener("click",clearSelection);
document.getElementById("flyTo").addEventListener("click",()=>{if(selectedRecord)flyToRecord(selectedRecord)});
const osm=new OpenStreetMap("OpenStreetMap",{isBaseLayer:true,visibility:true,attribution:"© OpenStreetMap contributors, ODbL"});
try{globe=new Globe({target:"globus",name:"RE Nationality Intelligence Globe",terrain:new GlobusRgbTerrain(),layers:[osm],atmosphereEnabled:true,resourcesSrc:"__RESOURCES__",fontsSrc:"__FONTS__",msaa:4,idleMode:false,navigation:{mode:"north",inertia:.18,zoomSpeed:1.15}});nationalityLayer=new Vector("Nationalities",{entities:[],pickingEnabled:true,async:true});nationalityLayer.addTo(globe.planet);if(control.KeyboardNavigation)globe.renderer.addControl(new control.KeyboardNavigation());
// Start over Southeast Asia so the RE workforce markers are immediately visible.
if(globe.planet?.camera)globe.planet.camera.setLonLat(new LonLat(101.9758,4.2105,12000000));globe.renderer.events.on("lclick",e=>{const picked=e.pickingObject;if(!picked||!picked.properties||!picked.properties.nationality)return;const record=records.find(r=>r.nationality===picked.properties.nationality);if(record){showDetails(record);flyToRecord(record)}});renderLayer();if(nationalityLayer.getEntities().length!==records.length)throw new Error("Nationality vector layer entity count mismatch: "+nationalityLayer.getEntities().length+" vs "+records.length);status.classList.add("hidden");window.setTimeout(()=>window.dispatchEvent(new Event("resize")),250)}catch(error){console.error("OpenGlobus Phase 2 initialization failed:",error);status.textContent="3D Earth could not be initialized. Check WebGL/network access.";}
</script></body></html>'''
    return (template.replace("__CSS__",OPEN_GLOBUS_CSS).replace("__JS__",OPEN_GLOBUS_JS)
            .replace("__RESOURCES__",OPEN_GLOBUS_RESOURCES).replace("__FONTS__",OPEN_GLOBUS_FONTS)
            .replace("__HEIGHT__",str(safe_height)).replace("__PAYLOAD__",payload))

def render_nationality_globe(map_df: pd.DataFrame, *, personnel_df: pd.DataFrame | None = None, height: int = 620) -> None:
    records=_records_from_map_df(map_df,personnel_df)
    if not records: raise ValueError("Nationality globe data cannot be empty.")
    components.html(_build_openglobus_html(records,height=height),height=max(520,int(height)),scrolling=False)

__all__=["OPEN_GLOBUS_VERSION","render_nationality_globe","_build_openglobus_html","_records_from_map_df"]
