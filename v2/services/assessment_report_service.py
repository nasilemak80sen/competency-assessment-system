"""Shared individual-assessment report calculations and PDF rendering."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import html
import math
from typing import Any, Mapping, Sequence

import pandas as pd
from v2.analytics.readiness import (
    _rg_determine_target_sg,
    _rg_get_person_ruler,
    _rg_grade_rank,
    _rg_sort_salary_grades,
    build_target_gap_dataframe,
    calculate_readiness_metrics,
)
from config import COMPETENCY_FULLNAMES, COMP_TYPES, SCORE_COLS


def _get(record: Any, key: str, fallback: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, fallback)
    getter = getattr(record, "get", None)
    return getter(key, fallback) if callable(getter) else getattr(record, key, fallback)


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _display(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.casefold() not in {"nan", "none", "nat"} else fallback


def _safe_markup(value: Any) -> str:
    return html.escape(_display(value)).replace("\n", "<br/>")


def build_future_grade_gap_dataframe(person: Any, requirements: Mapping[str, Any]) -> pd.DataFrame:
    """Compare actual scores with every higher-grade requirement."""
    current_rank = _rg_grade_rank(_get(person, "SG"))
    if current_rank is None:
        return pd.DataFrame()
    grades = [
        grade for grade in _rg_sort_salary_grades(requirements.keys())
        if _rg_grade_rank(grade) is not None and _rg_grade_rank(grade) > current_rank
    ]
    records = []
    for grade in grades:
        grade_requirements = requirements.get(grade, {}) or {}
        for code in SCORE_COLS:
            actual = pd.to_numeric(_get(person, code), errors="coerce")
            target = pd.to_numeric(grade_requirements.get(code), errors="coerce")
            if pd.isna(target):
                gap, status = pd.NA, "Requirement Unavailable"
            elif pd.isna(actual):
                gap, status = pd.NA, "Not Assessed"
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


def build_future_grade_summary(future_gap: pd.DataFrame) -> pd.DataFrame:
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


def build_assessment_report_data(
    person: Any,
    ruler_map: Mapping[str, Any],
    *,
    history: Sequence[Mapping[str, Any]] | pd.DataFrame | None = None,
    summary: Any = None,
    target_mode: str = "Next salary grade",
    selected_target_sg: str | None = None,
) -> dict[str, Any]:
    """Use the same career-ruler, target-gap and readiness logic as Individual Assessment."""
    career_ruler = _rg_get_person_ruler(person, ruler_map) if ruler_map else None
    requirements = ruler_map.get(career_ruler, {}) if career_ruler else {}
    target = _rg_determine_target_sg(
        _get(person, "SG"), requirements, target_mode, selected_target_sg
    ) if requirements else None
    gap = (
        build_target_gap_dataframe(
            person,
            requirements.get(target, {}),
            _get(person, "SG"),
            target,
            _get(person, "Staff Position"),
            career_ruler,
            COMPETENCY_FULLNAMES,
        )
        if target in requirements
        else pd.DataFrame()
    )
    metrics = calculate_readiness_metrics(gap)
    future_gap = build_future_grade_gap_dataframe(person, requirements) if requirements else pd.DataFrame()
    if isinstance(history, pd.DataFrame):
        history_frame = history.copy()
    else:
        history_frame = pd.DataFrame(list(history) if history is not None else [])
    if not history_frame.empty:
        if "date" in history_frame.columns:
            history_frame["date"] = pd.to_datetime(history_frame["date"], errors="coerce")
        if "actual" in history_frame.columns:
            history_frame["actual"] = pd.to_numeric(history_frame["actual"], errors="coerce")
    return {
        "person": person,
        "career_ruler": career_ruler,
        "target_mode": target_mode,
        "target": target,
        "requirements": requirements,
        "gap": gap,
        "metrics": metrics,
        "future_gap": future_gap,
        "future_summary": build_future_grade_summary(future_gap),
        "history": history_frame,
        "summary": summary,
    }


def _strength_frame(person: Any, competency_type: str) -> pd.DataFrame:
    records = []
    for code in COMP_TYPES.get(competency_type, {}).get("cols", []):
        score = pd.to_numeric(_get(person, code), errors="coerce")
        if pd.isna(score):
            continue
        target = pd.to_numeric(_get(person, f"R-{code}"), errors="coerce")
        raw_gap = _get(person, f"G--{code}")
        if raw_gap is None:
            raw_gap = _get(person, f"G-{code}")
        gap = pd.to_numeric(raw_gap, errors="coerce")
        if pd.isna(gap) and pd.notna(target):
            gap = float(target) - float(score)
        records.append({
            "Code": code,
            "Competency": COMPETENCY_FULLNAMES.get(code, code),
            "Score": float(score),
            "Target": target,
            "Gap": gap,
        })
    if not records:
        return pd.DataFrame(columns=["Code", "Competency", "Score", "Target", "Gap", "Status"])
    frame = pd.DataFrame(records).sort_values(
        ["Score", "Competency"], ascending=[False, True]
    ).reset_index(drop=True)
    frame["Status"] = frame["Gap"].map(
        lambda value: "Not recorded" if pd.isna(value)
        else "Above target" if value < 0
        else "Met target" if value == 0
        else "Gap remaining"
    )
    return frame


def _history_summary(history: pd.DataFrame) -> pd.DataFrame:
    columns = ["Assessment Date", "Assessment Type", "Average Score", "Scored Records"]
    if history is None or history.empty or not {"date", "type", "actual"}.issubset(history.columns):
        return pd.DataFrame(columns=columns)
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["actual"] = pd.to_numeric(frame["actual"], errors="coerce")
    frame = frame.dropna(subset=["date", "actual"])
    if frame.empty:
        return pd.DataFrame(columns=columns)
    grouped = frame.groupby(["date", "type"], dropna=False)["actual"].agg(["mean", "count"]).reset_index()
    grouped = grouped.sort_values(["date", "type"])
    grouped["Assessment Date"] = grouped["date"].dt.strftime("%d %b %Y")
    grouped["Assessment Type"] = grouped["type"].fillna("Unspecified").astype(str)
    grouped["Average Score"] = grouped["mean"].round(2)
    grouped["Scored Records"] = grouped["count"].astype(int)
    return grouped[columns]


def generate_assessment_pdf(
    person: Any,
    gap: pd.DataFrame,
    metrics: Mapping[str, Any],
    *,
    target: str | None = None,
    career_ruler: str | None = None,
    future_gap: pd.DataFrame | None = None,
    history: Sequence[Mapping[str, Any]] | pd.DataFrame | None = None,
    summary: Any = None,
) -> bytes:
    """Render the individual assessment with vector charts and detailed tables."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Flowable, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    class ActualTargetChart(Flowable):
        """Vector rendering of the same actual-versus-target chart data as the page."""
        def __init__(self, data: pd.DataFrame, width: float, height: float = 185):
            super().__init__()
            self.data = data.copy()
            self.width = width
            self.height = height

        def wrap(self, avail_width, avail_height):
            self.width = min(self.width, avail_width)
            return self.width, self.height

        def draw(self):
            canvas = self.canv
            data = self.data.reset_index(drop=True)
            if data.empty:
                canvas.setFont("Helvetica-Oblique", 9)
                canvas.drawString(8, self.height / 2, "No competency target data is available.")
                return
            left, right, bottom, top = 34, 12, 46, self.height - 23
            plot_width = max(1, self.width - left - right)
            plot_height = max(1, top - bottom)
            group_width = plot_width / len(data)
            canvas.setFont("Helvetica", 6)
            for tick in range(6):
                y = bottom + plot_height * tick / 5
                canvas.setStrokeColor(colors.HexColor("#D9DEE7"))
                canvas.setLineWidth(0.35)
                canvas.line(left, y, left + plot_width, y)
                canvas.setFillColor(colors.HexColor("#465166"))
                canvas.drawRightString(left - 5, y - 2, str(tick))
            target_points = []
            for index, row in data.iterrows():
                center = left + group_width * (index + 0.5)
                actual = _number(row.get("Actual"))
                target_value = _number(row.get("Target"))
                if actual is not None:
                    bar_height = plot_height * max(0, min(actual, 5)) / 5
                    bar_width = min(10, group_width * 0.48)
                    canvas.setFillColor(colors.HexColor("#00A651"))
                    canvas.rect(center - bar_width / 2, bottom, bar_width, bar_height, fill=1, stroke=0)
                if target_value is None:
                    target_points.append(None)
                else:
                    y_target = bottom + plot_height * max(0, min(target_value, 5)) / 5
                    target_points.append((center, y_target))
                canvas.saveState()
                canvas.translate(center - 2, bottom - 5)
                canvas.rotate(55)
                canvas.setFillColor(colors.HexColor("#263447"))
                canvas.setFont("Helvetica", 5.2)
                canvas.drawString(0, 0, str(row.get("Competency", "")))
                canvas.restoreState()
            canvas.setStrokeColor(colors.HexColor("#D62728"))
            canvas.setFillColor(colors.HexColor("#D62728"))
            canvas.setLineWidth(1.5)
            previous = None
            for point in target_points:
                if point is None:
                    previous = None
                    continue
                if previous is not None:
                    canvas.line(previous[0], previous[1], point[0], point[1])
                canvas.circle(point[0], point[1], 2.1, fill=1, stroke=0)
                previous = point
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(colors.HexColor("#263447"))
            canvas.drawString(left, self.height - 12, "Actual vs Target Competency Scores")
            canvas.setFillColor(colors.HexColor("#00A651"))
            canvas.rect(self.width - 130, self.height - 16, 7, 7, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#263447"))
            canvas.setFont("Helvetica", 7)
            canvas.drawString(self.width - 119, self.height - 14, "Actual")
            canvas.setFillColor(colors.HexColor("#D62728"))
            canvas.line(self.width - 65, self.height - 12, self.width - 53, self.height - 12)
            canvas.circle(self.width - 59, self.height - 12, 2, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#263447"))
            canvas.drawString(self.width - 47, self.height - 14, "Target")

    class CompetencyRadarChart(Flowable):
        """Vector rendering of the same competency radar chart data as the page."""
        def __init__(self, data: pd.DataFrame, width: float, height: float = 190):
            super().__init__()
            self.data = data.copy()
            self.width = width
            self.height = height

        def wrap(self, avail_width, avail_height):
            self.width = min(self.width, avail_width)
            return self.width, self.height

        def draw(self):
            canvas = self.canv
            data = self.data.reset_index(drop=True)
            if data.empty:
                canvas.setFont("Helvetica-Oblique", 9)
                canvas.drawString(8, self.height / 2, "No competency data is available for radar chart.")
                return
            cx, cy = self.width / 2, self.height / 2 - 5
            radius = min(self.width * 0.31, self.height * 0.34)
            count = len(data)
            angles = [math.pi / 2 - 2 * math.pi * i / count for i in range(count)]
            canvas.setStrokeColor(colors.HexColor("#D9DEE7"))
            canvas.setLineWidth(0.45)
            for level in range(1, 6):
                ring = radius * level / 5
                points = [(cx + ring * math.cos(a), cy + ring * math.sin(a)) for a in angles]
                path = canvas.beginPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                path.close()
                canvas.drawPath(path, stroke=1, fill=0)
                canvas.setFont("Helvetica", 5)
                canvas.setFillColor(colors.HexColor("#586174"))
                canvas.drawString(cx + 2, cy + ring + 1, str(level))
            for angle in angles:
                canvas.line(cx, cy, cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            canvas.setFont("Helvetica", 4.8)
            canvas.setFillColor(colors.HexColor("#263447"))
            for index, angle in enumerate(angles):
                label_radius = radius + 10
                canvas.drawCentredString(
                    cx + label_radius * math.cos(angle),
                    cy + label_radius * math.sin(angle),
                    str(data.iloc[index].get("Competency", "")),
                )
            for field, stroke in [
                ("Target", colors.HexColor("#D62728")),
                ("Actual", colors.HexColor("#00A651")),
            ]:
                values = pd.to_numeric(data[field], errors="coerce").fillna(0).clip(0, 5)
                points = [
                    (
                        cx + radius * float(values.iloc[i]) / 5 * math.cos(angles[i]),
                        cy + radius * float(values.iloc[i]) / 5 * math.sin(angles[i]),
                    )
                    for i in range(count)
                ]
                path = canvas.beginPath()
                path.moveTo(*points[0])
                for point in points[1:]:
                    path.lineTo(*point)
                path.close()
                canvas.setStrokeColor(stroke)
                canvas.setLineWidth(1.4)
                canvas.drawPath(path, stroke=1, fill=0)
                canvas.setFillColor(stroke)
                for x, y in points:
                    canvas.circle(x, y, 1.7, fill=1, stroke=0)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(colors.HexColor("#263447"))
            canvas.drawString(8, self.height - 12, "Competency Radar")
            canvas.setFont("Helvetica", 6.5)
            canvas.setFillColor(colors.HexColor("#00A651"))
            canvas.drawString(8, 8, "Actual")
            canvas.setFillColor(colors.HexColor("#D62728"))
            canvas.drawString(46, 8, "Target")

    class AssessmentHistoryChart(Flowable):
        """Vector rendering of the assessment-history line chart from the page."""
        palette = ["#20419A", "#00A19C", "#F28E2B", "#763F98", "#4E79A7"]

        def __init__(self, data: pd.DataFrame, width: float, height: float = 155):
            super().__init__()
            self.data = data.copy()
            self.width = width
            self.height = height

        def wrap(self, avail_width, avail_height):
            self.width = min(self.width, avail_width)
            return self.width, self.height

        def draw(self):
            canvas = self.canv
            data = self.data.copy()
            required = {"date", "type", "actual"}
            if data.empty or not required.issubset(data.columns):
                canvas.setFont("Helvetica-Oblique", 9)
                canvas.drawString(8, self.height / 2, "No assessment history is available.")
                return
            data["date"] = pd.to_datetime(data["date"], errors="coerce")
            data["actual"] = pd.to_numeric(data["actual"], errors="coerce")
            data = data.dropna(subset=["date", "actual"])
            if data.empty:
                canvas.setFont("Helvetica-Oblique", 9)
                canvas.drawString(8, self.height / 2, "No dated assessment history is available.")
                return
            grouped = data.groupby(["date", "type"], dropna=False)["actual"].mean().reset_index()
            dates = sorted(grouped["date"].dropna().unique())
            if not dates:
                return
            left, right, bottom, top = 38, 18, 30, self.height - 28
            plot_width = max(1, self.width - left - right)
            plot_height = max(1, top - bottom)
            ordinals = [pd.Timestamp(value).toordinal() for value in dates]
            min_date, max_date = min(ordinals), max(ordinals)
            span = max(max_date - min_date, 1)
            for tick in range(6):
                y = bottom + plot_height * tick / 5
                canvas.setStrokeColor(colors.HexColor("#E1E5EB"))
                canvas.setLineWidth(0.35)
                canvas.line(left, y, left + plot_width, y)
                canvas.setFont("Helvetica", 6)
                canvas.setFillColor(colors.HexColor("#586174"))
                canvas.drawRightString(left - 4, y - 2, str(tick))
            for tick_index in range(min(4, len(dates))):
                date_index = round(tick_index * (len(dates) - 1) / max(min(4, len(dates)) - 1, 1))
                current_date = pd.Timestamp(dates[date_index])
                x = left + (current_date.toordinal() - min_date) / span * plot_width
                canvas.setFont("Helvetica", 5.8)
                canvas.setFillColor(colors.HexColor("#586174"))
                canvas.drawCentredString(x, 15, current_date.strftime("%b %Y"))
            assessment_types = grouped["type"].drop_duplicates().tolist()
            for type_index, assessment_type in enumerate(assessment_types):
                subset = grouped[grouped["type"] == assessment_type].sort_values("date")
                color = colors.HexColor(self.palette[type_index % len(self.palette)])
                points = [
                    (
                        left + (pd.Timestamp(row["date"]).toordinal() - min_date) / span * plot_width,
                        bottom + plot_height * max(0, min(float(row["actual"]), 5)) / 5,
                    )
                    for _, row in subset.iterrows()
                ]
                canvas.setStrokeColor(color)
                canvas.setFillColor(color)
                canvas.setLineWidth(1.5)
                for previous, current in zip(points, points[1:]):
                    canvas.line(previous[0], previous[1], current[0], current[1])
                for x, y in points:
                    canvas.circle(x, y, 2.4, fill=1, stroke=0)
                legend_x = left + (type_index % 4) * (plot_width / 4)
                legend_y = self.height - 10 - (type_index // 4) * 9
                canvas.setFont("Helvetica", 5.8)
                canvas.drawString(legend_x, legend_y, str(assessment_type or "Unspecified")[:18])
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(colors.HexColor("#263447"))
            canvas.drawString(left, self.height - 12, "Average Competency Score by Assessment Date")

    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Competency Assessment - {_display(_get(person, 'Name'))}",
        author="RE Fraternity Competency Assessment System",
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 7.5
    styles["BodyText"].leading = 10
    small = ParagraphStyle("SmallCell", parent=styles["BodyText"], fontSize=6.5, leading=8)
    story = []

    def para(value: Any) -> Paragraph:
        return Paragraph(_safe_markup(value), small)

    def make_table(rows, widths=None, font_size=6.5):
        table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C1CE")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD2DC"))
        canvas.line(doc.leftMargin, 8 * mm, landscape(A4)[0] - doc.rightMargin, 8 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5B6573"))
        canvas.drawString(doc.leftMargin, 5 * mm, "DPE Reservoir Engineering · Confidential personnel assessment")
        canvas.drawRightString(landscape(A4)[0] - doc.rightMargin, 5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    # 1. Profile and talent information.
    story.extend([
        Paragraph("DPE Reservoir Engineering", styles["Title"]),
        Paragraph("Individual Competency Assessment & Talent Profile", styles["Heading2"]),
        Spacer(1, 2 * mm),
    ])
    profile_rows = [
        ["Name", _display(_get(person, "Name")), "Staff ID", _display(_get(person, "Staff ID"))],
        ["Position", _display(_get(person, "Staff Position")), "Salary Grade", _display(_get(person, "SG"))],
        ["Department", _display(_get(person, "Department")), "Section", _display(_get(person, "Section Name"))],
        ["Sub-Department", _display(_get(person, "Unit Name")), "Sub-Unit", _display(_get(person, "Sub Unit"))],
        ["Nationality", _display(_get(person, "Nationality")), "Employment Type", _display(_get(person, "Employment Category"))],
        ["Assessment Level", _display(_get(person, "Assessment Level")), "Last Assessment", _display(_get(person, "Last Assesment Date"))],
        ["Current Assignment", _display(_get(person, "Current Location:")), "Contract Expiry", _display(_get(person, "Contract Expire Date"))],
        ["Career Ruler", _display(career_ruler or _get(person, "Ruler Type")), "Report Target SG", _display(target)],
    ]
    profile_table = Table(profile_rows, colWidths=[29*mm, 105*mm, 31*mm, 105*mm])
    profile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF6")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#E8EEF6")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C1CE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([profile_table, Spacer(1, 3 * mm)])

    story.append(Paragraph("Talent Profile", styles["Heading2"]))
    talent_rows = [
        ["Strength", _display(_get(person, "Strength"))],
        ["Interest", _display(_get(person, "Interest"))],
        ["Background / Sub-Disciplines", _display(_get(person, "Background") or _get(person, "Sub-Disciplines"))],
        ["Potential", _display(_get(person, "Potential"))],
        ["Recommendation", _display(_get(person, "Recommendation"))],
    ]
    talent_table = Table(talent_rows, colWidths=[48*mm, 222*mm])
    talent_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF6")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C1CE")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([talent_table, Spacer(1, 3 * mm)])

    # 2. Target readiness and the three charts used by the assessment view.
    story.append(Paragraph(f"Assessment Summary vs Target ({_display(target)})", styles["Heading2"]))
    metric_rows = [[
        "Target SG", "Career Ruler", "Weighted Readiness", "Strict Readiness",
        "Total", "Assessed", "Met", "Minor Gaps", "Major Gaps", "Not Assessed",
    ], [
        _display(target), _display(career_ruler or _get(person, "Ruler Type")),
        f"{float(metrics.get('weighted_readiness', 0)):.1f}%",
        f"{float(metrics.get('strict_readiness', 0)):.1f}%",
        int(metrics.get("total", 0)), int(metrics.get("assessed", 0)),
        int(metrics.get("met", 0)), int(metrics.get("minor", 0)),
        int(metrics.get("major", 0)), int(metrics.get("not_assessed", 0)),
    ]]
    story.extend([make_table(metric_rows, font_size=6), Spacer(1, 3 * mm)])

    story.append(Paragraph("Gap Analysis Visualizations", styles["Heading2"]))
    chart_data = (
        gap.dropna(subset=["Target"]).copy()
        if gap is not None and not gap.empty and "Target" in gap.columns
        else pd.DataFrame()
    )
    inner_width = landscape(A4)[0] - document.leftMargin - document.rightMargin
    if not chart_data.empty:
        story.extend([
            ActualTargetChart(chart_data, inner_width, 185),
            Spacer(1, 2 * mm),
            CompetencyRadarChart(chart_data, inner_width, 190),
            Spacer(1, 3 * mm),
        ])
    else:
        story.append(Paragraph("No target-matched competency data is available for the selected target.", styles["BodyText"]))

    # 3. Strength ranking, priority development areas and full target matrix.
    story.append(Paragraph("Assessment-Based Competency Strength", styles["Heading2"]))
    for code, category in [("B", "Base"), ("K", "Key"), ("P", "Pacing"), ("E", "Emerging")]:
        strength = _strength_frame(person, code)
        if strength.empty:
            continue
        rows = [[f"{category} Competency", "Competency Name", "Score", "Target", "Gap", "Status"]]
        for _, record in strength.iterrows():
            rows.append([
                record["Code"], para(record["Competency"]),
                f"{float(record['Score']):.1f}",
                "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
                "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
                record["Status"],
            ])
        story.extend([make_table(rows, font_size=6), Spacer(1, 2 * mm)])

    if gap is None or gap.empty:
        story.append(Paragraph("No competency target-gap breakdown is available for this personnel and target.", styles["BodyText"]))
    else:
        priority = gap[gap["Status"].isin(["Major Gap", "Minor Gap"])].copy()
        story.append(Paragraph("Priority Development Areas", styles["Heading2"]))
        if priority.empty:
            story.append(Paragraph("No competency gaps were identified for the selected target grade.", styles["BodyText"]))
        else:
            priority_rows = [["Code", "Competency", "Actual", "Target", "Gap", "Status"]]
            for _, record in priority.iterrows():
                priority_rows.append([
                    record["Competency"], para(record["Competency Name"]),
                    "—" if pd.isna(record["Actual"]) else f"{float(record['Actual']):.1f}",
                    "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
                    "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
                    record["Status"],
                ])
            story.append(make_table(priority_rows, font_size=6))

        story.append(Paragraph("Full Competency Breakdown", styles["Heading2"]))
        current_rows = [[
            "Code", "Competency", "Current SG", "Target SG", "Actual", "Target", "Gap", "Status",
        ]]
        for _, record in gap.iterrows():
            current_rows.append([
                record["Competency"], para(record["Competency Name"]),
                _display(record.get("Current Grade")), _display(record.get("Target Grade")),
                "—" if pd.isna(record["Actual"]) else f"{float(record['Actual']):.1f}",
                "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
                "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
                record["Status"],
            ])
        story.extend([make_table(current_rows, font_size=5.8), PageBreak()])

    # 4. Forward-looking promotion gaps.
    if future_gap is not None and not future_gap.empty:
        story.append(Paragraph("Forward-Looking Promotion Gap Matrix", styles["Heading2"]))
        story.append(Paragraph(
            "Current assessment scores are held constant and compared with each higher salary-grade requirement.",
            styles["BodyText"],
        ))
        future_summary = build_future_grade_summary(future_gap)
        if not future_summary.empty:
            rows = [list(future_summary.columns)] + future_summary.fillna("—").astype(str).values.tolist()
            story.extend([make_table(rows, font_size=6), Spacer(1, 3 * mm)])
        future_rows = [[
            "Target SG", "Code", "Competency", "Category", "Actual", "Target", "Gap", "Status",
        ]]
        for _, record in future_gap.iterrows():
            future_rows.append([
                record["Target SG"], record["Competency"], para(record["Competency Name"]),
                record["Category"],
                "—" if pd.isna(record["Actual"]) else f"{float(record['Actual']):.1f}",
                "—" if pd.isna(record["Target"]) else f"{float(record['Target']):.1f}",
                "—" if pd.isna(record["Gap"]) else f"{float(record['Gap']):.1f}",
                record["Status"],
            ])
        story.append(make_table(future_rows, font_size=5.6))
    else:
        story.append(Paragraph("No higher salary-grade requirements are available for forward-looking analysis.", styles["BodyText"]))

    # 5. Imported summary scorecards and the assessment-history trend chart.
    if summary is not None:
        summary_fields = {
            "Next Grade": ["next_grade_base", "next_grade_keys", "next_grade_pacing", "next_grade_emerging", "next_grade_cti"],
            "Staff": ["staff_base", "staff_keys", "staff_pacing", "staff_emerging", "staff_cti"],
            "Principal": ["principal_base", "principal_keys", "principal_pacing", "principal_emerging", "principal_cti"],
            "Custodian": ["custodian_base", "custodian_keys", "custodian_pacing", "custodian_emerging", "custodian_cti"],
        }
        story.extend([PageBreak(), Paragraph("Summary Personnel Scores and Competencies", styles["Heading2"])])
        rows = [["Summary Group", "Base", "Keys", "Pacing", "Emerging", "CTI"]]
        for group, fields in summary_fields.items():
            values = []
            for field in fields:
                number = _number(_get(summary, field))
                values.append("—" if number is None else f"{number:.1f}%")
            rows.append([group] + values)
        story.append(make_table(rows, font_size=6.5))

    history_frame = (
        history.copy()
        if isinstance(history, pd.DataFrame)
        else pd.DataFrame(list(history) if history is not None else [])
    )
    story.extend([Spacer(1, 4 * mm), Paragraph("Assessment History", styles["Heading2"])])
    story.append(AssessmentHistoryChart(history_frame, inner_width, 155))
    history_summary = _history_summary(history_frame)
    if not history_summary.empty:
        story.append(make_table(
            [list(history_summary.columns)] + history_summary.astype(str).values.tolist(),
            font_size=6.5,
        ))
    else:
        story.append(Paragraph("No dated assessment history is available for this personnel.", styles["BodyText"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD2DC"))
        canvas.line(doc.leftMargin, 8 * mm, landscape(A4)[0] - doc.rightMargin, 8 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5B6573"))
        canvas.drawString(doc.leftMargin, 5 * mm, "DPE Reservoir Engineering · Confidential personnel assessment")
        canvas.drawRightString(landscape(A4)[0] - doc.rightMargin, 5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()


def build_personnel_assessment_pdf(
    person: Any,
    ruler_map: Mapping[str, Any],
    *,
    history: Sequence[Mapping[str, Any]] | pd.DataFrame | None = None,
    summary: Any = None,
    target_mode: str = "Next salary grade",
    selected_target_sg: str | None = None,
) -> bytes:
    """Create the PDF using the Individual Assessment page's default target mode."""
    report = build_assessment_report_data(
        person, ruler_map, history=history, summary=summary,
        target_mode=target_mode, selected_target_sg=selected_target_sg,
    )
    person_for_pdf = person.copy() if hasattr(person, "copy") else dict(person)
    try:
        person_for_pdf["Ruler Type"] = report["career_ruler"]
    except (TypeError, KeyError):
        pass
    return generate_assessment_pdf(
        person_for_pdf,
        report["gap"],
        report["metrics"],
        target=report["target"],
        career_ruler=report["career_ruler"],
        future_gap=report["future_gap"],
        history=report["history"],
        summary=report["summary"],
    )
