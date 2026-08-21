"""
Configuration - RE Fraternity Competency Assessment System v3.0
All constants derived from actual Excel data structure.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = (BASE_DIR / "re_competency.db").resolve()
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


def resolve_excel_path() -> str:
    """Resolve the workbook path from an environment variable or local project paths."""
    env_path = os.getenv("COMPETENCY_EXCEL_PATH") or os.getenv("RE_EXCEL_PATH")
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return str(path.resolve())

    candidates = [
        BASE_DIR / "RE Fraternity Jul2026_Master.xlsm",
        BASE_DIR / "RE_Fraternity_Jul2026_Master.xlsm",
        Path(r"C:\Users\mnabielizzuddin.radz\OneDrive - PETRONAS\Reservoir Engineering\Programming_Python_Projects\Competency Assessment System\RE Fraternity Jul2026_Master.xlsm"),
        BASE_DIR / "RE Fraternity Jul2026_Master.xlsm",
        BASE_DIR / "RE_Fraternity_Jul2026_Master.xlsm",
        Path(r"C:\Users\mnabielizzuddin.radz\OneDrive - PETRONAS\Reservoir Engineering\Programming_Python_Projects\Competency Assessment System\RE Fraternity Jul2026_Master.xlsm"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())

    return str((BASE_DIR / "RE Fraternity Jul2026_Master.xlsx").resolve())


EXCEL_PATH = resolve_excel_path()
USE_LIVE_EXCEL_SOURCE = True

# ── Salary Grade Hierarchy ───────────────────────────────────────────────────
# Single source of truth for the RE competency hierarchy.
#
# IMPORTANT:
# The order of this dictionary defines the official hierarchy:
#
# UPTREX
# P1  Junior Executive
# P2  Executive
# P3  Senior Executive
# P4  Senior Reservoir Engineer
# P5  Staff
# P6  Specialist
# P7  Principal
# P8  Senior Principal
# P9  Custodian
# P10 Senior Custodian
#
# ── Salary Grade Hierarchy ───────────────────────────────────────────────────
# Single source of truth for the RE competency hierarchy.
#
# IMPORTANT:
# The order of this dictionary defines the official hierarchy:
#
# UPTREX
# P1  Junior Executive
# P2  Executive
# P3  Senior Executive
# P4  Senior Reservoir Engineer
# P5  Staff
# P6  Specialist
# P7  Principal
# P8  Senior Principal
# P9  Custodian
# P10 Senior Custodian
#
GRADE_LABELS = {
    "UPTREX": "UPTREX",
    "P1": "Junior Executive",
    "P2": "Executive",
    "P1": "Junior Executive",
    "P2": "Executive",
    "P3": "Senior Executive",
    "P4": "Senior Reservoir Engineer",
    "P5": "Staff",
    "P6": "Specialist",
    "P7": "Principal",
    "P8": "Senior Principal",
    "P9": "Custodian",
    "P10": "Senior Custodian",
    "P9": "Custodian",
    "P10": "Senior Custodian",
}



# ── Position → Salary Grade mapping ──────────────────────────────────────────
# All recognised position names are normalised to the official SG hierarchy.
#
# Multiple position aliases can point to the same SG.
# This prevents differences such as "Snr RE" vs "Senior Reservoir Engineer"
# from breaking filtering, grouping, or chart generation.

# ── Position → Salary Grade mapping ──────────────────────────────────────────
# All recognised position names are normalised to the official SG hierarchy.
#
# Multiple position aliases can point to the same SG.
# This prevents differences such as "Snr RE" vs "Senior Reservoir Engineer"
# from breaking filtering, grouping, or chart generation.

POSITION_TO_SG = {
    # UPTREX
    "UPTREX": "UPTREX",

    # P1
    "Junior Executive": "P1",

    # P2
    "Executive": "P2",
    # P3
    "Senior Executive" : "P3",
    
    # P4
    "Senior RE" : "P4",

    # P5
    "Staff": "P5",

    # P6

    # P6
    "Specialist": "P6",

    # P7
    "Principal": "P7",

    # P8
    "Senior Principal": "P8",

    # P9
    "Custodian": "P9",

    # P10
    "Senior Custodian": "P10",

}


# ── Official Position Hierarchy ──────────────────────────────────────────────
# Used for dropdowns, filters, charts and ordered displays.
#
# Do NOT derive this from the order of rows in Excel.
# The order here is intentional and follows GRADE_LABELS.

POSITIONS = [
    GRADE_LABELS["UPTREX"],
    GRADE_LABELS["P1"],
    GRADE_LABELS["P2"],
    GRADE_LABELS["P3"],
    GRADE_LABELS["P4"],
    GRADE_LABELS["P5"],
    GRADE_LABELS["P6"],
    GRADE_LABELS["P7"],
    GRADE_LABELS["P8"],
    GRADE_LABELS["P9"],
    GRADE_LABELS["P10"],
    "All",
]


# ── Salary Grade Hierarchy ───────────────────────────────────────────────────
# Useful when a chart/table needs to sort by SG rather than alphabetically.

SG_HIERARCHY = [
    "UPTREX",
    "P1",
    "P2",
    "P3",
    "P4",
    "P5",
    "P6",
    "P7",
    "P8",
    "P9",
    "P10",
]


# ── Salary Grade Rank ────────────────────────────────────────────────────────
# Numeric ranking makes sorting reliable.
#
# Lower number = lower position in the hierarchy.

SG_RANK = {
    sg: rank
    for rank, sg in enumerate(SG_HIERARCHY, start=0)
}


# ── Position Rank ────────────────────────────────────────────────────────────
# Allows the application to sort using the official hierarchy.

POSITION_RANK = {
    GRADE_LABELS[sg]: SG_RANK[sg]
    for sg in SG_HIERARCHY
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
    "Current Location:","Date in Position","Length in Current Assignment",
    "Current Location:","Date in Position","Length in Current Assignment",
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

RULER_SHEET = "Ruler"
TAB_SEPARATOR_SHEET = "tab separator"

COMPETENCY_FULLNAMES = {
    "B1": "Fluid characterisation*",
    "B2": "Rock Properties*",
    "B3": "Integrated Reservoir Characterisation",
    "B4": "Oil & Gas Resource Estimation",
    "B5": "Reservoir Performance Analysis",
    "B6": "Numerical Simulation*",
    "B7": "Depletion Strategy and Drive Mechanism",
    "B8": "Well performance and prediction",
    "B9": "Pressure Transient Analysis",
    "B10": "Production Operations",
    "B11": "Subsurface Development Planning and Execution*",
    "B12": "Integrated Reservoir Management Principles and Practices*",
    "K1": "Petroleum Economics, Risk and Uncertainty Management",
    "K2": "Integrated Field Development Planning",
    "K3": "EOR",
    "K4": "Advanced Reservoir Data Acquisition and Monitoring",
    "K5": "CO2 Sequestration and Disposal",
    "P1": "Complex Fluid System",
    "P2": "Complex Reservoir System",
    "P3": "Advanced Reservoir Modeling",
    "P4": "Smart Fields reservoir development",
    "P5": "Unconventional Hydrocarbon Energy Sources (CBM, heavy oil, shale oil/gas, Tar Sands)",
    "E1": "Unconventional Hydrocarbon Energy Sources (methane hydrates)",
    "E2": "Advanced Technologies and Novel Solutions",
}

# =============================================================================
# NATIONALITY MAP CONFIGURATION
# =============================================================================

COUNTRY_COORDINATES = {
    "Argentina": {
        "latitude": -38.4161,
        "longitude": -63.6167,
    },
    "Australia": {
        "latitude": -25.2744,
        "longitude": 133.7751,
    },
    "Canada": {
        "latitude": 56.1304,
        "longitude": -106.3468,
    },
    "Denmark": {
        "latitude": 56.2639,
        "longitude": 9.5018,
    },
    "Egypt": {
        "latitude": 26.8206,
        "longitude": 30.8025,
    },
    "France": {
        "latitude": 46.2276,
        "longitude": 2.2137,
    },
    "India": {
        "latitude": 20.5937,
        "longitude": 78.9629,
    },
    "Indonesia": {
        "latitude": -0.7893,
        "longitude": 113.9213,
    },
    "Iran": {
        "latitude": 32.4279,
        "longitude": 53.6880,
    },
    "Malaysia": {
        "latitude": 4.2105,
        "longitude": 101.9758,
    },
    "Nigeria": {
        "latitude": 9.0820,
        "longitude": 8.6753,
    },
    "Russia": {
        "latitude": 61.5240,
        "longitude": 105.3188,
    },
    "Sudan": {
        "latitude": 12.8628,
        "longitude": 30.2176,
    },
    "Turkmenistan": {
        "latitude": 38.9697,
        "longitude": 59.5563,
    },
    "United Kingdom": {
        "latitude": 55.3781,
        "longitude": -3.4360,
    },
    "Venezuela": {
        "latitude": 6.4238,
        "longitude": -66.5897,
    },
    "Vietnam": {
        "latitude": 14.0583,
        "longitude": 108.2772,
    },
}

NATIONALITY_ALIASES = {
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "England": "United Kingdom",
    "United Kingdom/India": "United Kingdom/India",
    "Viet Nam": "Vietnam",
    "Russian Federation": "Russia",
    "Iran, Islamic Republic of": "Iran",
    "Venezuela, Bolivarian Republic of": "Venezuela",
    "USA": "United States",
    "US": "United States",
    "U.S.": "United States",
}
# ─────────────────────────────────────────────────────────────────────────
# CV DOCUMENT SETTINGS
# ─────────────────────────────────────────────────────────────────────────

CV_LIST_SHEET = "CV list"  # Sheet name in Excel workbook

CV_COLUMNS_MAP = {
    "Name": "name",
    "Staff ID": "staff_id",
    "Staff Position": "staff_position",
    "CV Status": "cv_status",
    "CV File Name": "cv_file_name",
    "File Type": "file_type",
    "Local File Path": "local_file_path",
    "SharePoint URL": "sharepoint_url",
    "Modified Date": "modified_date",
    "Match Method": "match_method",
    "Notes": "notes",
}

VALID_URL_PREFIXES = ("https://", "http://", "file://")

CV_ALLOWED_FILE_TYPES = {
    "PDF",
    "DOC",
    "DOCX",
}

SHAREPOINT_CV_ROOT_URL = (
    "https://petronas.sharepoint.com/"
    "teams/ts_coe_dpereservoirengineer/"
    "Shared%20Documents/General/"
    "RE%20Leadership%20Teams/SKG10/"
)

# =============================================================================
# CV DOCUMENT CONFIGURATION
# =============================================================================

CV_LIST_SHEET = "CV list"

CV_LIST_COLUMNS = [
    "Name",
    "Staff ID",
    "Staff Position",
    "CV Status",
    "CV File Name",
    "File Type",
    "Local File Path",
    "Local File Link",
    "SharePoint URL",
    "Modified Date",
    "Match Method",
    "Notes",
]

CV_ALLOWED_FILE_TYPES = {
    "PDF",
    "DOC",
    "DOCX",
}




# ── PETRONAS Colors ──────────────────────────────────────────────────────────
PRIMARY   = "#00a19c"
SECONDARY = "#20419a"
SUCCESS   = "#763f98"
WARNING   = "#fdb924"
DANGER    = "#C62828"
INFO      = "#bfd730"
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
