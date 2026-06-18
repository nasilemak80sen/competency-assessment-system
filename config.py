"""
Configuration - RE Fraternity Competency Assessment System v3.0
All constants derived from actual Excel data structure.
"""

DATABASE_URL = "sqlite:///re_competency.db"

# ── Salary Grades (SG column in Excel) ──────────────────────────────────────
GRADE_LABELS = {
    "P1": "Executive Level 1",
    "P2": "Executive Level 2",
    "P3": "Senior Executive",
    "P4": "Senior Reservoir Engineer",
    "P5": "Staff",
    "P6": "Specialist",
    "P7": "Principal",
    "P8": "Senior Principal",
    "CDH": "Custodian / Head",
    "UPTREX": "UPTREX",
}

# Staff Position → SG mapping (from data)
POSITION_TO_SG = {
    "Executive": "P3",
    "Snr RE": "P4",
    "Staff": "P5",
    "Principal": "P7",
    "Specialist": "P6",
    "UPTREX": "UPTREX",
    "Manager": "CDH",
    "Custodian": "CDH",
}

# ── Competency Columns ───────────────────────────────────────────────────────
SCORE_COLS = (
    [f"B{i}" for i in range(1, 13)] +   # B1-B12
    [f"K{i}" for i in range(1, 6)] +    # K1-K5  (K6 not in file)
    [f"P{i}" for i in range(1, 6)] +    # P1-P5
    ["E1", "E2"]                         # E1-E2  (E3 not in file)
)

REQ_COLS  = [f"R-{c}" for c in SCORE_COLS]
GAP_COLS  = [f"G--{c}" for c in SCORE_COLS]

COMP_TYPES = {
    "B": {"label": "Base Competency",  "cols": [f"B{i}" for i in range(1,13)]},
    "K": {"label": "Knowledge",         "cols": [f"K{i}" for i in range(1,6)]},
    "P": {"label": "Pacing",            "cols": [f"P{i}" for i in range(1,6)]},
    "E": {"label": "Emerging",          "cols": ["E1","E2"]},
}

# Summary score columns present in Excel
SUMMARY_GROUPS = {
    "Staff":      ["Staff Base","Staff Keys","Staff Pacing","Staff Emerging","Staff CTI"],
    "Principal":  ["Principal Base","Principal Keys","Principal Pacing","Principal Emerging","Principal CTI"],
    "Custodian":  ["Custodian Base","Custodian Keys","Custodian Pacing","Custodian Emerging","Custodian CTI"],
}

# ── Personnel meta columns ───────────────────────────────────────────────────
PERSONAL_COLS = [
    "Name","Staff ID","Age","Birth Year","Gender","Nationality",
    "Email Address","Employment Category","Contract Expire Date",
]
EMPLOYMENT_COLS = [
    "Department","Section Name","Unit Name","Sub Unit","Staff Position","SG",
    "Joining Date","Years in PET","Years of RE Experience",
    "Age Promoted to Staff or Principal","Years in Salary Grade",
    "Date of Appointment to Current Grade",
    "Current Assignment / Loc:","Date in Position","Length in Current Assignment",
]
ASSESSMENT_COLS = [
    "Chat Status","Chat Date","Assessment Level","Last Assesment Date",
    "Sub-Disciplines","Potential","Strength","Recommendation",
    "Resource/SME","Interest","Preference","Comment/Suggestion",
    "Assesor1","Assessor2","Supervisor","Remarks",
]

# ── Departments (from data) ──────────────────────────────────────────────────
DEPARTMENTS = ["DPE","PSR","MPM","PCINO","IRQ","TURK","DUC","UAE","AUS","PECL","ANGOLA","All"]

# ── Positions (from data) ────────────────────────────────────────────────────
POSITIONS = ["Executive","Snr RE","Staff","Principal","Specialist","UPTREX","Manager","All"]

# ── Chat Status ──────────────────────────────────────────────────────────────
CHAT_STATUS_OPTIONS = ["Yes","No","No Need"]

# ── Assessment Levels (from data) ────────────────────────────────────────────
ASSESSMENT_LEVELS = ["Staff","SMA","Principal","UPE","Not yet","Not done","Research"]

# ── PETRONAS Colors ──────────────────────────────────────────────────────────
PRIMARY   = "#003D5C"
SECONDARY = "#00A3A3"
SUCCESS   = "#2E7D32"
WARNING   = "#F57C00"
DANGER    = "#C62828"
INFO      = "#1565C0"
LIGHT_BG  = "#F0F4F8"

# Score color scale for heatmaps
HEATMAP_COLORSCALE = [
    [0.0, "#C62828"],   # red  – 0
    [0.4, "#F57C00"],   # orange
    [0.6, "#FDD835"],   # yellow
    [0.8, "#81C784"],   # light green
    [1.0, "#2E7D32"],   # dark green – 5
]

APP_TITLE = "RE Fraternity Competency Assessment System"
EXCEL_PATH = "RE_Fraternity_Jun2026_Master.xlsx"
