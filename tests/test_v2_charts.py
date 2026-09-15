import numpy as np
import pandas as pd

from v2.analytics.charts import (
    _build_competency_risk_summary,
    _create_department_competency_heatmap,
    _create_readiness_status_chart,
    _create_personnel_priority_scatter,
)


def _summary():
    return pd.DataFrame([
        {"Name":"Alice","Department":"DPE","Staff Position":"Engineer","Current SG":"P1","Weighted Readiness %":90,"Strict Readiness %":80,"Assessment Coverage %":100,"Major Gaps":0,"Minor Gaps":0,"Gap Burden":0,"Readiness Status":"Ready","Years in Grade":2},
        {"Name":"Bob","Department":"PSR","Staff Position":"Engineer","Current SG":"P2","Weighted Readiness %":60,"Strict Readiness %":50,"Assessment Coverage %":80,"Major Gaps":2,"Minor Gaps":1,"Gap Burden":5,"Readiness Status":"Near Ready","Years in Grade":1},
    ])


def test_readiness_status_chart_returns_figure():
    figure = _create_readiness_status_chart(_summary())
    assert figure is not None
    assert len(figure.data) == 4


def test_personnel_priority_scatter_handles_valid_summary():
    figure = _create_personnel_priority_scatter(_summary())
    assert figure is not None
    assert len(figure.data) > 0


def test_risk_summary_and_department_heatmap():
    detail = pd.DataFrame([
        {"Name":"Alice","Department":"DPE","Staff Position":"Engineer","Competency Code":"B1","Competency Name":"B1","Category":"Base","Is Assessed":True,"Gap":0,"Gap Burden":0,"Is Major Gap":False},
        {"Name":"Bob","Department":"PSR","Staff Position":"Engineer","Competency Code":"B1","Competency Name":"B1","Category":"Base","Is Assessed":True,"Gap":-2,"Gap Burden":2,"Is Major Gap":True},
    ])
    risk = _build_competency_risk_summary(detail)
    assert risk.loc[0, "Affected Personnel"] == 1
    assert risk.loc[0, "Gap Prevalence %"] == 50.0
    figure = _create_department_competency_heatmap(detail, 10)
    assert figure is not None
