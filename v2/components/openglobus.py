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
#hovercard{position:absolute;left:16px;top:76px;z-index:32;display:none;min-width:190px;max-width:min(290px,calc(100% - 32px));box-sizing:border-box;padding:10px 12px;border:1px solid rgba(0,161,156,.2);border-radius:10px;background:rgba(255,255,255,.94);backdrop-filter:blur(10px);box-shadow:0 7px 22px rgba(18,47,53,.13);color:#183238;pointer-events:none}
#hovercard.visible{display:block}#hovercard strong{display:block;font-size:12px}#hovercard .meta{display:block;margin-top:3px;font-size:10px;color:#52676b}#hovercard .hint{display:block;margin-top:5px;font-size:9px;color:#00a19c;font-weight:700}
#toolbar{position:absolute;left:16px;bottom:16px;z-index:40;width:min(430px,calc(100% - 32px));padding:10px;border-radius:12px;background:rgba(255,255,255,.93);backdrop-filter:blur(10px);box-shadow:0 8px 28px rgba(18,47,53,.16)}
#toolbar .row{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:7px}
#toolbar .row:last-of-type{margin-bottom:5px}#toolbar .row .wide{grid-column:1/-1}
#toolbar select,#toolbar button{width:100%;box-sizing:border-box;border:1px solid #d4e0e2;border-radius:8px;padding:7px 8px;background:#fff;color:#183238;font-size:11px}
#toolbar button{cursor:pointer;font-weight:700}#toolbar button:hover{border-color:#00a19c}
#stats{font-size:10px;color:#52676b;padding:2px 2px 0}
#details{position:absolute;right:16px;top:16px;z-index:40;width:min(330px,calc(100% - 32px));max-height:calc(100% - 32px);overflow:auto;box-sizing:border-box;padding:14px;border-radius:12px;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);box-shadow:0 10px 30px rgba(18,47,53,.18);color:#183238;display:none}
#details.visible{display:block}#details .close{float:right;border:0;background:transparent;cursor:pointer;font-size:18px}
#details h3{margin:0 28px 3px 0;font-size:16px}.muted{font-size:10px;color:#63767a}
#details .kpi{display:flex;gap:22px;margin:13px 0;padding:10px 0;border-top:1px solid #edf1f1;border-bottom:1px solid #edf1f1}.kpi strong{display:block;font-size:19px;letter-spacing:-.02em;color:#20419a}
.people-head{display:flex;align-items:center;justify-content:space-between;margin-top:10px;font-size:11px;color:#183238}.people-head span{font-size:9px;color:#63767a}
.person{padding:8px 0;border-top:1px solid #e7eeee;font-size:10px;line-height:1.45}.person strong{font-size:11px;color:#183238}#people{margin-top:5px}
#status{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:50;padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.94);box-shadow:0 8px 28px rgba(18,47,53,.15);color:#183238;font-size:13px}.hidden{display:none}
#legend{position:absolute;right:16px;bottom:16px;z-index:30;padding:8px 10px;border-radius:9px;background:rgba(255,255,255,.86);backdrop-filter:blur(8px);color:#52676b;font-size:9px;box-shadow:0 4px 14px rgba(18,47,53,.08)}
.legend-dot{display:inline-block;border-radius:50%;background:#00a19c;vertical-align:middle;margin:0 4px;border:1px solid rgba(255,255,255,.9)}
#attribution{position:absolute;right:12px;top:8px;z-index:30;padding:4px 7px;border-radius:6px;background:rgba(255,255,255,.72);color:#4a6065;font-size:8px}#attribution a{color:#34666c;text-decoration:none}
@media(max-width:700px){#details{width:calc(100% - 32px);max-height:46%;top:auto;bottom:112px}#hovercard{left:12px;top:72px;max-width:calc(100% - 24px)}#legend,#attribution{display:none}}
</style></head>
<body><div id="shell"><div id="globus"></div>
<div id="hud"><div class="title">🌍 RE Workforce Geography</div><div class="subtitle">Nationality distribution · Select a marker to explore</div></div>
<div id="hovercard" aria-live="polite"><strong id="hoverTitle"></strong><span class="meta" id="hoverMeta"></span><span class="hint">Click marker to view workforce profile</span></div>
<div id="status">Loading 3D Earth…</div>
<div id="details"><button class="close" id="closeDetails">×</button><h3 id="detailNationality">Nationality</h3><div class="muted" id="detailRepresentation"></div>
<div class="kpi"><div><strong id="detailCount">0</strong><span class="muted">personnel</span></div><div><strong id="detailSections">0</strong><span class="muted">sections</span></div></div>
<button id="flyTo" style="width:100%;padding:8px;border:0;border-radius:8px;background:#00a19c;color:white;font-weight:700;cursor:pointer">📍 Fly to nationality</button><div class="people-head"><strong>Personnel directory</strong><span id="peopleMeta"></span></div><div id="people"></div></div>
<div id="toolbar"><div class="row"><select id="employmentFilter"><option value="">All Employment Categories</option></select><select id="sgFilter"><option value="">All Salary Grades</option></select></div>
<div class="row"><select id="sectionFilter"><option value="">All Sections</option></select><select id="labelMode" aria-label="Country label visibility"><option value="selected">Labels: selected only</option><option value="top">Labels: top 5</option><option value="all">Labels: all</option><option value="none">Labels: off</option></select></div><div class="row"><button class="wide" id="resetFilters">↺ Reset Filters</button></div><div id="stats"></div></div>
<div id="legend"><span class="legend-dot" style="width:7px;height:7px"></span> Lower <span class="legend-dot" style="width:12px;height:12px"></span> Medium <span class="legend-dot" style="width:17px;height:17px"></span> Higher <span style="margin-left:5px">· Bubble size = personnel</span></div>
<div id="attribution">OpenGlobus · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a></div></div>
<script type="module">
import {Globe,GlobusRgbTerrain,OpenStreetMap,control,Vector,Entity,LonLat} from "__JS__";

const records=__PAYLOAD__;
const status=document.getElementById("status");
const details=document.getElementById("details");
const stats=document.getElementById("stats");
const employmentFilter=document.getElementById("employmentFilter");
const sgFilter=document.getElementById("sgFilter");
const sectionFilter=document.getElementById("sectionFilter");
const labelMode=document.getElementById("labelMode");
const hoverCard=document.getElementById("hovercard");
const hoverTitle=document.getElementById("hoverTitle");
const hoverMeta=document.getElementById("hoverMeta");

let globe=null;
let nationalityLayer=null;
let selectedRecord=null;
let hoveredNationality=null;

const uniqueValues=field=>[...new Set(records.flatMap(r=>r.people||[]).map(p=>p[field]).filter(Boolean))].sort();
const addOptions=(select,values)=>values.forEach(value=>{
  const option=document.createElement("option");
  option.value=value;
  option.textContent=value;
  select.appendChild(option);
});

addOptions(employmentFilter,uniqueValues("Employment Category"));
addOptions(sgFilter,uniqueValues("SG"));
addOptions(sectionFilter,uniqueValues("Section Name"));

function visiblePeople(record){
  const people=record.people||[];
  if(!people.length)return null;
  return people.filter(person=>
    (!employmentFilter.value||person["Employment Category"]===employmentFilter.value)&&
    (!sgFilter.value||person["SG"]===sgFilter.value)&&
    (!sectionFilter.value||person["Section Name"]===sectionFilter.value)
  );
}

function visibleCount(record){
  const people=visiblePeople(record);
  return people===null?Number(record.count||0):people.length;
}

// Focus the initial camera and marker on the largest nationality. With the
// default filters empty, visibleCount reflects the full workforce count.
const defaultFocusRecord=records.reduce((largest,record)=>
  visibleCount(record)>visibleCount(largest)?record:largest,
  records[0]
);
selectedRecord=defaultFocusRecord;

function markerSvg(proportion,selected=false){
  const radius=7+Math.max(0,Math.min(1,proportion))*8;
  const center=22;
  const fill=selected?"#20419A":"#00A19C";
  const ring=selected?"#BFD730":"#FFFFFF";
  const svg=
    '<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">'+
    '<circle cx="'+center+'" cy="'+center+'" r="'+(radius+4)+'" fill="#00A19C" fill-opacity=".13"/>'+
    '<circle cx="'+center+'" cy="'+center+'" r="'+radius+'" fill="'+fill+'" fill-opacity=".97" stroke="'+ring+'" stroke-width="'+(selected?3.2:2.5)+'"/>'+
    '<circle cx="'+center+'" cy="'+center+'" r="'+Math.max(2.5,radius*.24)+'" fill="#FFFFFF" fill-opacity=".96"/>'+
    '</svg>';
  return "data:image/svg+xml;charset=utf-8,"+encodeURIComponent(svg);
}

function renderLayer(){
  const ranked=records.map(record=>({record,count:visibleCount(record)}))
    .filter(item=>item.count>0);
  const maxCount=Math.max(...ranked.map(item=>item.count),1);
  const topFive=new Set(
    [...ranked].sort((a,b)=>b.count-a.count).slice(0,5).map(item=>item.record.nationality)
  );

  const entities=ranked.map(({record,count})=>{
    const selected=Boolean(selectedRecord&&selectedRecord.nationality===record.nationality);
    const showLabel=
      labelMode.value==="all"||
      (labelMode.value==="top"&&topFive.has(record.nationality))||
      (labelMode.value==="selected"&&selected);

    const entityOptions={
      name:record.nationality,
      lonlat:[record.longitude,record.latitude],
      billboard:{
        src:markerSvg(Math.sqrt(count/maxCount),selected),
        size:[48,48],
        offset:[0,20]
      },
      properties:{
        nationality:record.nationality,
        personnel:count,
        representation:record.representation,
        latitude:record.latitude,
        longitude:record.longitude
      }
    };

    if(showLabel){
      entityOptions.label={
        text:record.nationality,
        size:selected?15:11,
        offset:[0,34,0],
        color:selected?"rgba(32,65,154,.98)":"rgba(35,62,67,.94)",
        outlineColor:"rgba(255,255,255,.98)",
        outline:3
      };
    }
    return new Entity(entityOptions);
  });

  nationalityLayer.setEntities(entities);
  const total=ranked.reduce((sum,item)=>sum+item.count,0);
  stats.textContent=total.toLocaleString()+" visible personnel · "+entities.length+
    " nationalities · Hover for summary, click for details";
}

function escapeHtml(value){
  return String(value).replace(/[&<>"']/g,char=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[char]));
}

function showHover(record){
  if(hoveredNationality===record.nationality)return;
  hoveredNationality=record.nationality;
  const people=visiblePeople(record);
  const count=people===null?Number(record.count||0):people.length;
  hoverTitle.textContent=record.nationality;
  hoverMeta.textContent=count.toLocaleString()+" personnel · "+
    (record.representation||"—")+" workforce representation";
  hoverCard.classList.add("visible");
}

function hideHover(){
  hoveredNationality=null;
  hoverCard.classList.remove("visible");
}

function showDetails(record){
  selectedRecord=record;
  hideHover();

  const people=visiblePeople(record);
  const detailPeople=people===null?(record.people||[]):people;
  const detailCount=people===null?Number(record.count||0):detailPeople.length;

  document.getElementById("detailNationality").textContent="🌐 "+record.nationality;
  document.getElementById("detailRepresentation").textContent=
    "Representation: "+(record.representation||"—");
  document.getElementById("detailCount").textContent=detailCount.toLocaleString();
  document.getElementById("detailSections").textContent=
    new Set(detailPeople.map(person=>person["Section Name"]).filter(Boolean)).size;

  const directory=document.getElementById("people");
  const peopleMeta=document.getElementById("peopleMeta");
  if(people===null){
    peopleMeta.textContent="Summary only";
    directory.innerHTML='<div class="muted">Individual personnel details are not available for this nationality.</div>';
  }else if(!detailPeople.length){
    peopleMeta.textContent="0 matching";
    directory.innerHTML='<div class="muted">No personnel match the current filters.</div>';
  }else{
    peopleMeta.textContent=detailPeople.length.toLocaleString()+" matching";
    directory.innerHTML=detailPeople.slice(0,60).map(person=>
      '<div class="person"><strong>'+escapeHtml(person["Name"]||"Unnamed")+
      '</strong><br>'+escapeHtml(person["Staff Position"]||"Position not specified")+
      " · "+escapeHtml(person["SG"]||"SG —")+
      '<br><span class="muted">'+escapeHtml(person["Department"]||"Department —")+
      " · "+escapeHtml(person["Section Name"]||"Section —")+"</span></div>"
    ).join("");
    if(detailPeople.length>60){
      directory.innerHTML+='<div class="muted" style="padding:8px 0">Showing first 60 of '+
        detailPeople.length.toLocaleString()+" matching personnel.</div>";
    }
  }

  details.classList.add("visible");
  renderLayer();
}

function flyToRecord(record){
  if(!globe||!globe.planet?.camera)return;
  globe.planet.camera.flyLonLat(
    new LonLat(record.longitude,record.latitude,3500000),
    {duration:900}
  );
}

function clearSelection(){
  selectedRecord=null;
  details.classList.remove("visible");
  hideHover();
  renderLayer();
}

[employmentFilter,sgFilter,sectionFilter].forEach(element=>
  element.addEventListener("change",clearSelection)
);
labelMode.addEventListener("change",renderLayer);

document.getElementById("resetFilters").addEventListener("click",()=>{
  employmentFilter.value="";
  sgFilter.value="";
  sectionFilter.value="";
  labelMode.value="selected";
  clearSelection();
});
document.getElementById("closeDetails").addEventListener("click",clearSelection);
document.getElementById("flyTo").addEventListener("click",()=>{
  if(selectedRecord)flyToRecord(selectedRecord);
});

const osm=new OpenStreetMap("OpenStreetMap",{
  isBaseLayer:true,
  visibility:true,
  attribution:"© OpenStreetMap contributors, ODbL"
});

try{
  globe=new Globe({
    target:"globus",
    name:"RE Workforce Geography",
    terrain:new GlobusRgbTerrain(),
    layers:[osm],
    atmosphereEnabled:true,
    resourcesSrc:"__RESOURCES__",
    fontsSrc:"__FONTS__",
    msaa:4,
    idleMode:false,
    navigation:{mode:"lockNorth",inertia:.18,zoomSpeed:1.15}
  });

  nationalityLayer=new Vector("Nationalities",{
    entities:[],
    pickingEnabled:true,
    async:true
  });
  nationalityLayer.addTo(globe.planet);

  if(control.KeyboardNavigation){
    globe.renderer.addControl(new control.KeyboardNavigation());
  }

  // Start on the nationality with the largest workforce representation.
  // 4.5 Mm is a country-level view; 12 Mm showed nearly the whole globe.
  if(globe.planet?.camera){
    globe.planet.camera.setLonLat(new LonLat(
      defaultFocusRecord.longitude,
      defaultFocusRecord.latitude,
      4500000
    ));
  }

  globe.renderer.events.on("mousemove",event=>{
    const picked=event?.pickingObject;
    const nationality=picked?.properties?.nationality;
    const record=nationality?records.find(item=>item.nationality===nationality):null;
    if(record)showHover(record);
    else hideHover();
  });

  // Clicking continues to open the existing workforce detail experience.
  globe.renderer.events.on("lclick",event=>{
    const picked=event.pickingObject;
    if(!picked||!picked.properties||!picked.properties.nationality)return;
    const record=records.find(item=>item.nationality===picked.properties.nationality);
    if(record){
      showDetails(record);
      flyToRecord(record);
    }
  });

  nationalityLayer.events.on("mouseleave",hideHover);
  renderLayer();

  if(nationalityLayer.getEntities().length!==records.length){
    throw new Error(
      "Nationality vector layer entity count mismatch: "+
      nationalityLayer.getEntities().length+" vs "+records.length
    );
  }

  status.classList.add("hidden");
  window.setTimeout(()=>window.dispatchEvent(new Event("resize")),250);
}catch(error){
  console.error("OpenGlobus Phase 2 initialization failed:",error);
  status.textContent="3D Earth could not be initialized. Check WebGL/network access.";
}
</script></body></html>'''
    return (template.replace("__CSS__",OPEN_GLOBUS_CSS).replace("__JS__",OPEN_GLOBUS_JS)
            .replace("__RESOURCES__",OPEN_GLOBUS_RESOURCES).replace("__FONTS__",OPEN_GLOBUS_FONTS)
            .replace("__HEIGHT__",str(safe_height)).replace("__PAYLOAD__",payload))

def render_nationality_globe(map_df: pd.DataFrame, *, personnel_df: pd.DataFrame | None = None, height: int = 620) -> None:
    records=_records_from_map_df(map_df,personnel_df)
    if not records: raise ValueError("Nationality globe data cannot be empty.")
    components.html(_build_openglobus_html(records,height=height),height=max(520,int(height)),scrolling=False)

__all__=["OPEN_GLOBUS_VERSION","render_nationality_globe","_build_openglobus_html","_records_from_map_df"]
