"""
Floor Inspection — Failure Analytics Dashboard
Production-plant floor inspection app data.

Every chart and every table has its OWN independent date-range slider,
so they can be filtered separately from one another.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_loader as dl

st.set_page_config(page_title="Floor Inspection — Failure Analytics",
                   layout="wide")

# --------------------------------------------------------------------------- #
# Palette (colour-blind-safe, consistent across the app)
# --------------------------------------------------------------------------- #
PASS = "#2E9E7B"
FAIL = "#E4572E"
WARN = "#E8A93E"
MUTED = "#8A94A6"
CHECK_COLORS = {
    "Aisle Clean": "#E4572E",
    "QR Code Readable": "#4C6EF5",
    "Lane Organisation": "#E8A93E",
    "Boundary Check": "#9B5DE5",
}
STATUS_COLORS = {"Pass": PASS, "Fail": FAIL, "Recorded": "#4C6EF5", "Not recorded": MUTED}
SHORT_CHECK = {
    dl.CHECK_BIN: "Bin Quality", dl.CHECK_EMERG: "Emerg. Lighting",
    dl.CHECK_FIRE: "Fire Ext.", dl.CHECK_EYEWASH: "Eyewash",
    dl.CHECK_DOCK: "Dock Security", dl.CHECK_ELEC: "Electrical",
    dl.CHECK_MOISTURE: "Moisture", dl.CHECK_5S: "5S Board",
}


@st.cache_data
def get_data():
    bin_to_zone, zone_to_bins, required = dl.load_config()
    safety = dl.load_safety_status().copy()
    safety["date"] = safety["fi_reportid"].map(dl.report_id_to_dt)  # for filtering
    return {
        "bin_to_zone": bin_to_zone,
        "zone_to_bins": zone_to_bins,
        "required": required,
        "reports": dl.load_reports(),
        "bins": dl.load_bin_inspections(),
        "failed_long": dl.failed_bins_long(),
        "safety": safety,
        "completeness": dl.completeness_by_report(),
    }


FULL = get_data()
BIN_LABELS = list(dl.BIN_CHECKS.values())

# Full inspection window (bounds for every slider)
_all_dates = pd.concat([FULL["reports"]["date"], FULL["bins"]["date"]]).dropna()
FULL_MIN = _all_dates.min().date()
FULL_MAX = _all_dates.max().date()


# --------------------------------------------------------------------------- #
# Per-element date-filter helpers
# --------------------------------------------------------------------------- #
def date_range(key: str, label: str = "Date range"):
    """Render an independent date-range slider (unique `key`) and return (start, end)."""
    if FULL_MIN == FULL_MAX:
        st.caption(f"{FULL_MIN:%b %d, %Y}")
        return FULL_MIN, FULL_MAX
    return st.slider(label, min_value=FULL_MIN, max_value=FULL_MAX,
                     value=(FULL_MIN, FULL_MAX), format="MMM DD", key=key)


def clip(df: pd.DataFrame, rng) -> pd.DataFrame:
    """Filter a date-bearing dataframe to the inclusive [start, end] day range."""
    if df is None or df.empty or "date" not in df.columns:
        return df
    s, e = rng
    d = df["date"]
    return df[d.notna() & (d.dt.date >= s) & (d.dt.date <= e)].copy()


def zone_options(zones):
    return sorted(set(zones), key=dl.zone_sort_key)


def zone_check_status(rng) -> pd.DataFrame:
    """Grid of zones × checks showing the status of every check the config
    REQUIRES for that zone (aggregated over reports in the date range)."""
    required = FULL["required"].set_index("Zone")
    reps = clip(FULL["reports"], rng)
    safety = clip(FULL["safety"], rng)
    bins = clip(FULL["bins"], rng)
    checks = [c for c in required.columns]

    def cell(zone, chk):
        if not bool(required.loc[zone, chk]):
            return "–"                      # not required for this zone
        if chk == dl.CHECK_BIN:
            zb = bins[bins["zone"] == zone] if len(bins) else bins
            if len(zb) == 0:
                return "Missing"
            return "Fail" if zb["n_fail"].sum() > 0 else "Pass"
        zrep = reps.loc[reps["zone"] == zone, "fi_reportid"].tolist() if len(reps) else []
        s = set(safety[(safety["fi_reportid"].isin(zrep)) &
                       (safety["check"] == chk)]["status"]) if len(safety) else set()
        if "Fail" in s:
            return "Fail"
        if "Pass" in s:
            return "Pass"
        if "Recorded" in s:
            return "Recorded"
        return "Missing"

    grid = {z: {c: cell(z, c) for c in checks} for z in required.index}
    df = pd.DataFrame(grid).T.reindex(sorted(grid, key=dl.zone_sort_key))
    # shorten column headers for display
    short = {
        dl.CHECK_BIN: "Bin Quality", dl.CHECK_EMERG: "Emerg. Lighting",
        dl.CHECK_FIRE: "Fire Ext.", dl.CHECK_EYEWASH: "Eyewash",
        dl.CHECK_DOCK: "Dock", dl.CHECK_ELEC: "Electrical",
        dl.CHECK_MOISTURE: "Moisture", dl.CHECK_5S: "5S Board",
    }
    df = df.rename(columns=short)
    return df


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("Floor Inspection")
st.sidebar.caption("Production-plant floor & safety inspection analytics")

page = st.sidebar.radio(
    "View",
    ["Overview", "Bin Failure Analysis",
     "Repeat Offenders", "Data Quality"],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "Each chart and table below has its **own** date-range slider — "
    "filter them independently of one another."
)
st.sidebar.caption(
    "Bin→Zone mapping is sourced from the uploaded **Zone Config** workbook "
    "(authoritative). Pass/Fail is read from the Dataverse `*text` fields; "
    "the unreliable `fi_passed` booleans are ignored."
)


def _empty_note(rng):
    st.info(f"No inspections between {rng[0]:%b %d} and {rng[1]:%b %d}. "
            "Widen this chart's date range.")


# --------------------------------------------------------------------------- #
# Page: Overview
# --------------------------------------------------------------------------- #
def page_overview():
    st.title("Floor Inspection — Failure Overview")
    st.caption("Every element has its own date slider.")

    # ---- KPI block
    st.subheader("Key metrics")
    rng = date_range("ov_kpi")
    reps = clip(FULL["reports"], rng)
    bins = clip(FULL["bins"], rng)
    failed = clip(FULL["failed_long"], rng)
    safety = clip(FULL["safety"], rng)

    c = st.columns(4)
    c[0].metric("Inspection reports", reps["fi_reportid"].nunique())
    c[1].metric("Zones covered", reps["zone"].nunique())
    c[2].metric("Bins inspected", f"{len(bins):,}")
    c[3].metric("Bin pass rate",
                f"{100*bins['passed_all'].mean():.1f}%" if len(bins) else "—")
    c = st.columns(4)
    c[0].metric("Bin-level defects", len(failed))
    c[1].metric("Bins with ≥1 fail", int((~bins["passed_all"]).sum()) if len(bins) else 0)
    c[2].metric("Safety-check fails", int((safety["status"] == "Fail").sum()) if len(safety) else 0)
    c[3].metric("Reports marked Fail", int((reps["result"] == "Fail").sum()) if len(reps) else 0)

    st.markdown("---")
    left, right = st.columns([3, 2])

    # ---- Defects by zone & check
    with left:
        st.subheader("Where failures happen — defects by zone & check")
        rng = date_range("ov_zonecheck")
        fl = clip(FULL["failed_long"], rng)
        bn = clip(FULL["bins"], rng)
        if fl.empty:
            _empty_note(rng)
        else:
            g = fl.groupby(["zone", "check"]).size().reset_index(name="fails")
            all_zones = sorted(bn["zone"].unique(), key=dl.zone_sort_key)
            order = fl.groupby("zone").size().sort_values(ascending=False).index.tolist()
            order += [z for z in all_zones if z not in order]
            fig = px.bar(g, x="zone", y="fails", color="check",
                         category_orders={"zone": order, "check": BIN_LABELS},
                         color_discrete_map=CHECK_COLORS)
            fig.update_xaxes(categoryorder="array", categoryarray=order, type="category")
            fig.update_layout(barmode="stack", xaxis_title="", yaxis_title="Failed checks",
                              legend_title="Check", height=430, margin=dict(t=10, b=0))
            st.plotly_chart(fig, width="stretch")

    with right:
        # ---- Defects by check type
        st.subheader("Bin defects by check type")
        rng = date_range("ov_checktype")
        fl = clip(FULL["failed_long"], rng)
        counts = (fl["check"].value_counts().reindex(BIN_LABELS).fillna(0)
                  if not fl.empty else pd.Series(0, index=BIN_LABELS))
        cdf = counts.reset_index(); cdf.columns = ["check", "fails"]
        fig = px.bar(cdf, x="fails", y="check", orientation="h",
                     color="check", color_discrete_map=CHECK_COLORS)
        fig.update_layout(showlegend=False, yaxis_title="", xaxis_title="Failed checks",
                          height=250, margin=dict(t=10, b=0))
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig, width="stretch")

        # ---- Report outcomes
        st.subheader("Report outcomes")
        rng = date_range("ov_outcomes")
        reps = clip(FULL["reports"], rng)
        if reps.empty:
            _empty_note(rng)
        else:
            rc = reps["result"].replace("", "—").value_counts().reset_index()
            rc.columns = ["result", "n"]
            fig = px.pie(rc, names="result", values="n", hole=0.55, color="result",
                         color_discrete_map={"Pass": PASS, "Fail": FAIL, "—": MUTED})
            fig.update_layout(height=250, margin=dict(t=10, b=0))
            st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    # ---- Timeline
    st.subheader("Inspection timeline — defects found per report")
    rng = date_range("ov_timeline")
    fl = clip(FULL["failed_long"], rng)
    if fl.empty:
        _empty_note(rng)
    else:
        per_report = (fl.groupby(["fi_reportid", "date", "zone"]).size()
                      .reset_index(name="defects").sort_values("date"))
        fig = px.scatter(per_report, x="date", y="defects", size="defects",
                         color="zone", hover_data=["fi_reportid"])
        fig.update_layout(height=320, xaxis_title="", yaxis_title="Defects in report",
                          margin=dict(t=10, b=0))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    # ---- Pass rate by zone
    st.subheader("Bin pass rate by zone")
    rng = date_range("ov_passrate")
    bins = clip(FULL["bins"], rng)
    if bins.empty:
        _empty_note(rng)
    else:
        pr = bins.groupby("zone").agg(insp=("bin", "size"),
                                      passed=("passed_all", "sum")).reset_index()
        pr["pass_rate"] = 100 * pr["passed"] / pr["insp"]
        pr["fails"] = pr["insp"] - pr["passed"]
        pr = pr.sort_values("pass_rate")
        fig = px.bar(pr, x="pass_rate", y="zone", orientation="h",
                     text=pr["pass_rate"].map(lambda v: f"{v:.1f}%"),
                     hover_data={"insp": True, "fails": True, "pass_rate": ":.1f"},
                     color="pass_rate", range_color=(80, 100),
                     color_continuous_scale=[FAIL, WARN, PASS])
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(coloraxis_showscale=False, xaxis_title="Pass rate (%)",
                          yaxis_title="", xaxis_range=[0, 108], height=430,
                          margin=dict(t=10, b=0))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    # ---- Per-bin failure breakdown
    st.subheader("Failures for a specific bin — by reason")
    rng = date_range("ov_binpick")
    bins = clip(FULL["bins"], rng)
    fl = clip(FULL["failed_long"], rng)
    bin_fail_totals = (fl.groupby("bin").size().sort_values(ascending=False)
                       if not fl.empty else pd.Series(dtype=int))
    failing_bins = bin_fail_totals.index.tolist()
    other_bins = sorted(set(bins["bin"]) - set(failing_bins), key=str) if len(bins) else []
    bin_options = failing_bins + other_bins
    if not bin_options:
        _empty_note(rng)
    else:
        sel_bin = st.selectbox(
            "Bin Location", bin_options,
            format_func=lambda b: f"{b}  —  {int(bin_fail_totals.get(b, 0))} failure(s)",
            key="ov_binpick_sel")
        sub = bins[bins["bin"] == sel_bin]
        sel_fails = fl[fl["bin"] == sel_bin] if not fl.empty else fl
        m = st.columns(4)
        m[0].metric("Zone", sub["zone"].iloc[0] if not sub.empty else "—")
        m[1].metric("Times inspected", len(sub))
        m[2].metric("Inspections with a fail", int((~sub["passed_all"]).sum()))
        m[3].metric("Total failures", len(sel_fails))
        counts = (sel_fails["check"].value_counts().reindex(BIN_LABELS).fillna(0)
                  if not sel_fails.empty else pd.Series(0, index=BIN_LABELS))
        cdf = counts.reset_index(); cdf.columns = ["check", "failures"]
        fig = px.bar(cdf, x="check", y="failures", color="check",
                     category_orders={"check": BIN_LABELS},
                     color_discrete_map=CHECK_COLORS, text="failures")
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_yaxes(dtick=1, rangemode="tozero")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Failures",
                          height=360, margin=dict(t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        if sel_fails.empty:
            st.caption(f"{sel_bin} passed every check on all {len(sub)} inspection(s).")

        # ---- Failing-check ledger for the SELECTED bin only (with inspector notes)
        st.markdown(f"##### Failing-check records for {sel_bin}")
        if sel_fails.empty:
            st.caption("No failing-check records for this bin in the selected date range.")
        else:
            # inspector's free-text explanation, recorded per inspection (master table)
            notes_src = FULL["reports"]["issues"].where(
                FULL["reports"]["issues"].str.strip() != "", FULL["reports"]["comments"])
            notes_map = dict(zip(FULL["reports"]["fi_reportid"], notes_src))
            led = sel_fails.sort_values("date").copy()
            led["date"] = led["date"].dt.strftime("%Y-%m-%d %H:%M")
            led["inspector notes"] = led["fi_reportid"].map(notes_map).fillna("")
            st.dataframe(led[["date", "zone", "bin", "check", "inspector notes"]],
                         width="stretch", hide_index=True)
            st.caption("Inspector notes are recorded per inspection (whole-zone), "
                       "so they may describe issues beyond this single bin.")


# --------------------------------------------------------------------------- #
# Page: Bin failure analysis
# --------------------------------------------------------------------------- #
def page_bin_analysis():
    st.title("Bin Failure Analysis")

    # ---- Per-check KPIs
    st.subheader("Defect counts by check")
    rng = date_range("ba_kpi")
    fl = clip(FULL["failed_long"], rng)
    bins = clip(FULL["bins"], rng)
    total = max(len(bins), 1)
    c = st.columns(4)
    for i, chk in enumerate(BIN_LABELS):
        n = int((fl["check"] == chk).sum()) if len(fl) else 0
        c[i].metric(chk, n, f"{100*n/total:.1f}% of inspections")

    st.markdown("---")
    st.subheader("Failure rate by zone")
    rng = date_range("ba_zonerate")
    bins = clip(FULL["bins"], rng)
    if bins.empty:
        _empty_note(rng)
    else:
        bz = bins.groupby("zone").agg(insp=("bin", "size"),
                                      fails=("passed_all", lambda s: int((~s).sum()))).reset_index()
        bz["rate"] = 100 * bz["fails"] / bz["insp"]
        bz = bz.sort_values("rate", ascending=False)
        fig = px.bar(bz, x="zone", y="rate", hover_data=["insp", "fails"],
                     color="rate", color_continuous_scale=[PASS, WARN, FAIL])
        fig.update_layout(coloraxis_showscale=False, xaxis_title="",
                          yaxis_title="% bins failing", height=340, margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    st.subheader("Zone × Check heatmap (defect counts)")
    rng = date_range("ba_heatmap")
    fl = clip(FULL["failed_long"], rng)
    if fl.empty:
        _empty_note(rng)
    else:
        pivot = (fl.groupby(["zone", "check"]).size().reset_index(name="n")
                 .pivot(index="zone", columns="check", values="n").fillna(0))
        pivot = pivot.reindex(columns=[c for c in BIN_LABELS if c in pivot.columns])
        pivot = pivot.reindex(sorted(pivot.index, key=dl.zone_sort_key))
        fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index,
                                   colorscale="OrRd", text=pivot.values.astype(int),
                                   texttemplate="%{text}", showscale=True))
        fig.update_layout(height=430, margin=dict(t=10), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, width="stretch")

    # ---- Zone safety checks (select a zone -> stacked status bar + ledger)
    st.markdown("---")
    st.subheader("Zone safety checks — status by check type")
    st.caption("Select a zone to see its required safety checks (Emergency Lighting, "
               "Fire Extinguisher, Dock Security, Electrical, Moisture, Eyewash, 5S).")
    zones = zone_options(FULL["zone_to_bins"].keys())
    sel_zone = st.selectbox("Zone", zones, key="ba_safety_zone")
    rng = date_range("ba_safetyzone")

    required = FULL["required"].set_index("Zone")
    req_checks = [c for c in dl.SAFETY_CHECKS
                  if sel_zone in required.index and bool(required.loc[sel_zone, c])]
    reps_z = clip(FULL["reports"], rng)
    safety_z = clip(FULL["safety"], rng)
    zrep = reps_z.loc[reps_z["zone"] == sel_zone, "fi_reportid"].tolist() if len(reps_z) else []
    sdf = (safety_z[(safety_z["fi_reportid"].isin(zrep)) & (safety_z["check"].isin(req_checks))]
           if len(safety_z) else safety_z)

    if not req_checks:
        st.info(f"{sel_zone} has no zone-level safety checks required in the config "
                "(it is bin-quality only).")
    elif sdf.empty:
        _empty_note(rng)
    else:
        order = ["Pass", "Fail", "Recorded", "Not recorded"]
        g = sdf.groupby(["check", "status"]).size().reset_index(name="n")
        g["check"] = g["check"].map(SHORT_CHECK).fillna(g["check"])
        cat = [SHORT_CHECK.get(c, c) for c in req_checks]
        fig = px.bar(g, x="check", y="n", color="status",
                     category_orders={"status": order, "check": cat},
                     color_discrete_map=STATUS_COLORS)
        fig.update_layout(barmode="stack", xaxis_title="", yaxis_title="Inspections",
                          legend_title="Status", height=400, margin=dict(t=10),
                          xaxis_tickangle=-15)
        st.plotly_chart(fig, width="stretch")
        st.caption("Only the checks this zone is required to perform (per Zone Config) "
                   "are shown. 'Not recorded' = required but left blank in that inspection.")

        # ledger with inspector notes
        st.markdown(f"##### Safety-check records for {sel_zone}")
        notes_src = FULL["reports"]["issues"].where(
            FULL["reports"]["issues"].str.strip() != "", FULL["reports"]["comments"])
        notes_map = dict(zip(FULL["reports"]["fi_reportid"], notes_src))
        led = sdf.sort_values(["date", "check"]).copy()
        led["date"] = led["date"].dt.strftime("%Y-%m-%d %H:%M")
        led["inspector notes"] = led["fi_reportid"].map(notes_map).fillna("")
        st.dataframe(led[["date", "zone", "check", "status", "inspector notes"]],
                     width="stretch", hide_index=True)
        st.caption("Inspector notes are recorded per inspection (whole-zone).")


# --------------------------------------------------------------------------- #
# Page: Repeat offenders
# --------------------------------------------------------------------------- #
def page_repeat():
    st.title("Repeat Offenders")
    st.caption("Bins that failed on more than one inspection within the chosen range.")
    rng = date_range("ro_table")
    bins = clip(FULL["bins"], rng)
    fails = bins[~bins["passed_all"]].copy() if len(bins) else bins
    if fails.empty:
        _empty_note(rng)
        return
    agg = fails.groupby("bin").agg(
        times_failed=("bin", "size"), zone=("zone", "first"),
        dates=("date", lambda s: sorted(s.dropna())),
        checks=("failed_checks", lambda s: sorted({c for lst in s for c in lst})),
    ).reset_index()
    repeat = agg[agg["times_failed"] > 1].sort_values("times_failed", ascending=False)
    st.metric("Bins failing more than once", len(repeat))
    if repeat.empty:
        st.info("No bin failed on more than one inspection in this range.")
        return
    disp = repeat.copy()
    disp["Dates failed"] = disp["dates"].map(lambda ds: ", ".join(d.strftime("%b %d") for d in ds))
    disp["Failed checks"] = disp["checks"].map(", ".join)
    disp = disp.rename(columns={"bin": "Bin", "zone": "Zone", "times_failed": "Times failed"})
    st.dataframe(disp[["Bin", "Zone", "Times failed", "Dates failed", "Failed checks"]],
                 width="stretch", hide_index=True)


# --------------------------------------------------------------------------- #
# Page: Data quality
# --------------------------------------------------------------------------- #
def page_quality():
    st.title("Data Quality & Checklist Completeness")

    st.subheader("Required vs completed checks per report")
    rng = date_range("dq_comp")
    comp = clip(FULL["completeness"], rng)
    if comp.empty:
        _empty_note(rng)
    else:
        incomplete = comp[comp["completed"] < comp["required"]]
        c = st.columns(3)
        c[0].metric("Reports analysed", len(comp))
        c[1].metric("Fully complete", int((comp["completed"] == comp["required"]).sum()))
        c[2].metric("Missing ≥1 required check", len(incomplete))
        comp2 = comp.sort_values("date").copy()
        comp2["label"] = comp2["zone"] + " · " + comp2["date"].dt.strftime("%b %d %H:%M")
        fig = go.Figure()
        fig.add_bar(x=comp2["label"], y=comp2["required"], name="Required",
                    marker_color=MUTED, opacity=0.5)
        fig.add_bar(x=comp2["label"], y=comp2["completed"], name="Completed",
                    marker_color=PASS)
        fig.update_layout(barmode="overlay", height=420, xaxis_tickangle=-40,
                          yaxis_title="# checks", margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    st.subheader("Required-check status by zone")
    st.caption("For every zone, the status of each check the Zone Config requires. "
               "“–” = not required for that zone.")
    rng = date_range("dq_zonestatus")
    grid = zone_check_status(rng)
    if grid.empty:
        _empty_note(rng)
    else:
        st.dataframe(grid, width="stretch")
        st.caption("Pass · Fail · Recorded (no explicit pass/fail) · "
                   "Missing (required but not recorded) · – not required")

    st.markdown("---")
    st.subheader("Reports missing required checks")
    rng = date_range("dq_missing")
    comp = clip(FULL["completeness"], rng)
    inc = comp[comp["completed"] < comp["required"]].copy() if len(comp) else comp
    if inc.empty:
        st.success("No reports are missing required checks in this range.")
    else:
        inc["date"] = inc["date"].dt.strftime("%Y-%m-%d %H:%M")
        inc["missing_checks"] = inc["missing_checks"].map(", ".join)
        st.dataframe(inc[["zone", "date", "required", "completed", "missing_checks"]],
                     width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("Known data-quality notes")
    st.markdown(
        "- **Orphan report** `QA20260709134623` (Jul 9 13:46) has bin rows but no "
        "master record; its bins match Zone 9.\n"
        "- **`fi_passed` booleans are unreliable** — electrical reads `fi_passed = True` "
        "on the same row whose text field says **Fail**. This dashboard trusts the "
        "`*text` fields.\n"
        "- **`fi_remediationstatus` is blank on every report** — no closed-loop "
        "remediation tracking is captured.\n"
        "- **1 configured bin never inspected**: `STL-D-BL49`.\n"
        "- Emergency-lighting brightness and fire-extinguisher quantity are **counts**, "
        "not Pass/Fail — not treated as compliance signals."
    )
    st.subheader("Required-checks matrix (from config — not date-dependent)")
    st.dataframe(FULL["required"], width="stretch", hide_index=True)


# --------------------------------------------------------------------------- #
PAGES = {
    "Overview": page_overview,
    "Bin Failure Analysis": page_bin_analysis,
    "Repeat Offenders": page_repeat,
    "Data Quality": page_quality,
}
PAGES[page]()
