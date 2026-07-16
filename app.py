"""
Floor Inspection — Failure Analytics Dashboard
Production-plant floor inspection app data.

Every chart and every table has its OWN independent date-range slider,
so they can be filtered separately from one another.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_loader as dl

# Bridge Streamlit secrets -> env so data_loader can fetch the private data repo.
# (On Streamlit Cloud secrets live in st.secrets, not the environment.)
try:
    for _k in ("GH_TOKEN", "DATA_REPO"):
        if _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

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


try:
    FULL = get_data()
except Exception as exc:  # surface a clear, actionable message instead of a redacted trace
    st.error(
        "**Couldn't load the inspection data.**\n\n"
        f"{exc}\n\n"
        "This app reads its data from a private repository at runtime. If you are "
        "the owner, check that the **GH_TOKEN** secret is set on Streamlit Cloud "
        "(a fine-grained token with read-only **Contents** access to the private "
        "data repo) and reboot the app."
    )
    st.stop()

BIN_LABELS = list(dl.BIN_CHECKS.values())
# The four per-bin quality checks, named in full for use in formula explanations.
FOUR_CHECKS = ", ".join(BIN_LABELS[:-1]) + f", and {BIN_LABELS[-1]}"
# A "bin inspection" = one bin assessed in one inspection report; a bin checked on
# several days contributes one row per day. "passed_all" = that row passed all four.

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


def fx(text: str):
    """Render the underlying formula/derivation for a chart or table."""
    st.caption(f"**Formula:** {text}")


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
    c[0].metric("Inspection reports", reps["fi_reportid"].nunique(),
                help="Number of distinct inspection reports in the selected dates. "
                     "One report = one zone inspected on one occasion (counted by its "
                     "unique report id, fi_reportid).")
    c[1].metric("Zones covered", reps["zone"].nunique(),
                help="Number of distinct zones (e.g. Zone 1…Zone 13) that were "
                     "inspected in the selected dates.")
    c[2].metric("Bins inspected", f"{len(bins):,}",
                help="Total bin inspections = number of individual bins checked, counted "
                     "once per inspection. A bin checked on 2 days counts as 2.")
    c[3].metric("Bin pass rate",
                f"{100*bins['passed_all'].mean():.1f}%" if len(bins) else "—",
                help=f"100 × (bin inspections that passed ALL four checks — {FOUR_CHECKS} "
                     "— ÷ total bin inspections).")
    c = st.columns(4)
    c[0].metric("Bin-level defects", len(failed),
                help=f"Total number of failed checks across every bin. Each bin can "
                     f"contribute up to 4 (one per check: {FOUR_CHECKS}).")
    c[1].metric("Bins with ≥1 fail", int((~bins["passed_all"]).sum()) if len(bins) else 0,
                help=f"Number of bin inspections that failed at least one of the four "
                     f"checks ({FOUR_CHECKS}).")
    c[2].metric("Safety-check fails", int((safety["status"] == "Fail").sum()) if len(safety) else 0,
                help="Number of zone-level safety checks (e.g. Electrical Safety, Fire "
                     "Extinguisher, Emergency Lighting) marked Fail. Not the bin checks.")
    c[3].metric("Reports marked Fail", int((reps["result"] == "Fail").sum()) if len(reps) else 0,
                help="Number of inspection reports whose overall result was recorded as "
                     "Fail (the inspector's verdict for the whole zone visit).")

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
            fx("total bar height = number of failed checks in that zone. Each coloured "
               f"segment = how many of those were a given check ({FOUR_CHECKS}). "
               "Counted as: number of bin-inspection rows in the zone whose check = Fail. "
               "Zones inspected but with no failures show an empty (zero-height) bar.")

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
        fx(f"one bar per check ({FOUR_CHECKS}). Bar length = number of bin inspections, "
           "across all zones, where that particular check was marked Fail.")

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
            fx("each slice = number of inspection reports with that overall result "
               "(Pass / Fail) ÷ total number of reports in range. The result is the "
               "inspector's overall verdict per report, not the bin checks.")

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
        fx("one marker per inspection report. x = when the inspection happened (the "
           "timestamp encoded in its report id). y and bubble size = number of failed "
           f"bin checks ({FOUR_CHECKS}) found in that report. Colour = zone.")

    st.markdown("---")
    # ---- Pass rate trend by zone, filterable to a single check
    st.subheader("Bin pass-rate trend by zone")
    rng = date_range("ov_passrate")
    bins = clip(FULL["bins"], rng)
    if bins.empty:
        _empty_note(rng)
    else:
        zsel = st.multiselect(
            "Zones to plot (default: all)",
            options=sorted(bins["zone"].unique(), key=dl.zone_sort_key),
            default=[], key="ov_passrate_zones")
        zoned = bins if not zsel else bins[bins["zone"].isin(zsel)]
        # group the bin list by zone so it's clear which bin sits in which zone
        bin_to_zone = FULL["bin_to_zone"]
        bin_opts = sorted(zoned["bin"].unique(),
                          key=lambda b: (dl.zone_sort_key(bin_to_zone.get(b, "")), b))
        bin_multi = st.multiselect(
            "Bins (default: all bins) — grouped by zone",
            options=bin_opts, default=[], key="ov_passrate_bin",
            format_func=lambda b: f"{bin_to_zone.get(b, '?')} — {b}")
        check_multi = st.multiselect("Checks (default: all four)",
                                     options=BIN_LABELS, default=[],
                                     key="ov_passrate_check")
        sel_checks = check_multi if check_multi else BIN_LABELS
        label = ("passing all four checks" if len(sel_checks) == 4
                 else "passing " + ", ".join(sel_checks))
        check_word = ("all four checks" if len(sel_checks) == 4
                      else ", ".join(sel_checks))

        def _pass_col(df):
            return df[sel_checks].eq("Pass").all(axis=1)

        work = zoned if not bin_multi else zoned[zoned["bin"].isin(bin_multi)]

        if len(bin_multi) == 1:
            # -------- Single-bin drill-down (two views of the same data) --------
            bin_one = bin_multi[0]
            one = work.copy()
            one["_pass"] = _pass_col(one)
            one = one.sort_values("date")
            zlabel = one["zone"].iloc[0] if len(one) else "—"
            st.caption(f"Bin **{bin_one}** ({zlabel}) — {label}. "
                       "Two views of the same data:")

            # View 1 — per inspection (pass = 100, fail = 0), stepped
            st.markdown("**1. Per inspection — passed / failed each time (shows WHEN it failed)**")
            v1 = one.copy()
            v1["result"] = v1["_pass"].map({True: 100, False: 0})
            v1["outcome"] = v1["_pass"].map({True: "Pass", False: "Fail"})
            fig1 = px.line(v1, x="date", y="result", markers=True,
                           hover_data={"outcome": True, "result": False, "date": False})
            fig1.update_traces(marker=dict(size=11), line=dict(shape="hv", color=MUTED))
            fig1.update_yaxes(range=[-8, 108], tickvals=[0, 100], ticktext=["Fail", "Pass"])
            fig1.update_layout(xaxis_title="", yaxis_title="", height=300,
                               margin=dict(t=10, b=0))
            st.plotly_chart(fig1, width="stretch")
            fx(f"one marker per inspection of {bin_one}: 100 = it passed {check_word} that "
               "day, 0 = it failed. The step line shows exactly which inspections failed.")

            # View 2 — monthly pass rate (%)
            st.markdown("**2. Monthly pass rate — how often it passed per month (shows the TREND)**")
            v2 = one.copy()
            v2["month"] = v2["date"].dt.to_period("M").dt.to_timestamp()
            mg = (v2.groupby("month").agg(passed=("_pass", "sum"),
                                          insp=("_pass", "size")).reset_index())
            mg["pass_rate"] = 100 * mg["passed"] / mg["insp"]
            fig2 = px.line(mg, x="month", y="pass_rate", markers=True,
                           hover_data={"passed": True, "insp": True,
                                       "pass_rate": ":.1f", "month": False})
            fig2.update_traces(marker=dict(size=9), line=dict(color=PASS))
            fig2.update_layout(xaxis_title="", yaxis_title="Pass rate (%)",
                               yaxis_range=[0, 105], height=300, margin=dict(t=10, b=0))
            st.plotly_chart(fig2, width="stretch")
            fx(f"each point = 100 × (inspections that month where {bin_one} passed "
               f"{check_word} ÷ its inspections that month). Smooths into a real % once "
               "the bin has several inspections in a month.")
            st.caption("Early on (≤1 inspection per month) both look binary; as "
                       "inspections accumulate, view 2 becomes a smooth trend while "
                       "view 1 keeps the exact pass/fail history. Select exactly one bin "
                       "for this view.")
        else:
            # -------- Zone-aggregate view (one line per zone) --------
            plot_bins = work.copy()
            plot_bins["_pass"] = _pass_col(plot_bins)
            trend = (plot_bins.groupby(["zone", "fi_reportid", "date"])
                     .agg(insp=("bin", "size"), passed=("_pass", "sum")).reset_index())
            trend["pass_rate"] = 100 * trend["passed"] / trend["insp"]
            trend["fails"] = trend["insp"] - trend["passed"]
            trend = trend.sort_values("date")
            fig = px.line(
                trend, x="date", y="pass_rate", color="zone", markers=True,
                hover_data={"insp": True, "fails": True, "pass_rate": ":.1f",
                            "date": False, "zone": False},
                category_orders={"zone": sorted(trend["zone"].unique(), key=dl.zone_sort_key)},
                color_discrete_sequence=px.colors.qualitative.Dark24)
            fig.update_traces(marker=dict(size=8))
            fig.update_layout(xaxis_title="", yaxis_title=f"% bins {label}",
                              yaxis_range=[0, 105], legend_title="Zone", height=440,
                              margin=dict(t=10, b=0))
            st.plotly_chart(fig, width="stretch")
            scope = "" if not bin_multi else f" (limited to {len(bin_multi)} selected bins)"
            fx(f"each point = a zone's pass rate in one inspection = 100 × (bins {label} "
               f"÷ bins inspected in that report{scope}). x = inspection date; a line "
               "joins the zone's repeat inspections.")
            st.caption("One marker per inspection; lines connect a zone's repeat "
                       "inspections. Bins and Checks accept multiple selections — pick "
                       "exactly one Bin to drill into its pass/fail history.")

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
        m[0].metric("Zone", sub["zone"].iloc[0] if not sub.empty else "—",
                    help="The zone this bin belongs to, taken from the Zone Config "
                         "workbook's authoritative bin→zone mapping.")
        m[1].metric("Times inspected", len(sub),
                    help="How many times this bin was inspected in the selected dates "
                         "(one count per inspection report it appears in).")
        m[2].metric("Inspections with a fail", int((~sub["passed_all"]).sum()),
                    help=f"How many of this bin's inspections failed at least one of the "
                         f"four checks ({FOUR_CHECKS}).")
        m[3].metric("Total failures", len(sel_fails),
                    help="Total failed checks for this bin, added up over all its "
                         "inspections (a single inspection can contribute up to 4).")
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
        fx(f"one bar per check ({FOUR_CHECKS}). Bar height = how many times THIS bin "
           "failed that specific check, added up over all its inspections in range.")
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
            fx("one row for each check this bin failed, on each date it was inspected. "
               "'inspector notes' = the free-text explanation the inspector wrote for "
               "that whole inspection (the report's observed-issues field, or the "
               "comments field if that's blank), matched to the row by report id.")
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
        c[i].metric(chk, n, f"{100*n/total:.1f}% of inspections",
                    help=f"Number of bin inspections where the '{chk}' check was marked "
                         "Fail. The % below = that number ÷ total bin inspections in range.")

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
        fx("one bar per zone. Height = 100 × (bin inspections in the zone that failed "
           f"at least one of the four checks ({FOUR_CHECKS}) ÷ all bin inspections in "
           "the zone). Colour (green→red) tracks the same rate.")

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
        fx(f"rows = zones, columns = the four checks ({FOUR_CHECKS}). Each cell = number "
           "of bin inspections in that zone where that check failed; darker = more. "
           "0 (blank) means no failures of that check in that zone.")

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
        fx("one bar per safety check this zone must do (from the Zone Config Y/N "
           "matrix — e.g. Electrical, Fire Extinguisher, Emergency Lighting, Dock, "
           "Moisture, Eyewash, 5S). Bar height = number of this zone's inspections; "
           "coloured segments split that by outcome (Pass / Fail / Recorded / Not "
           "recorded). 'Not recorded' = the check was required but left blank.")
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
        fx("one row for each required safety check, on each date the zone was "
           "inspected. 'status' is the recorded outcome of that check; 'inspector "
           "notes' = the free-text explanation for that inspection (the report's "
           "observed-issues field, or comments if blank), matched by report id.")
        st.caption("Inspector notes are recorded per inspection (whole-zone).")

    # ---- Zone safety-check pass-rate trend (mirrors the bin pass-rate trend)
    st.markdown("---")
    st.subheader("Zone safety-check pass-rate trend")
    st.caption("Pass rate = % of a zone's required safety checks (Electrical Safety, "
               "Fire Extinguisher, Emergency Lighting, Dock Security, Moisture Control, "
               "Eyewash, 5S Board) that passed in each inspection. One line per zone; "
               "designed to become a real trend as inspections accumulate.")
    rng = date_range("ba_safetytrend")
    safety_t = clip(FULL["safety"], rng)

    # keep only rows for checks that the row's own zone is required to perform
    sdf_t = safety_t[safety_t["check"].isin(dl.SAFETY_CHECKS)].copy() if len(safety_t) else safety_t
    if len(sdf_t):
        sdf_t = sdf_t[[(z in required.index and bool(required.loc[z, c]))
                       for z, c in zip(sdf_t["zone"], sdf_t["check"])]]

    if sdf_t.empty:
        _empty_note(rng)
    else:
        zones_avail = sorted(sdf_t["zone"].unique(), key=dl.zone_sort_key)
        zsel = st.multiselect("Zones to plot (default: all)", options=zones_avail,
                              default=[], key="ba_safetytrend_zones")
        chk_multi = st.multiselect("Safety checks (default: all required)",
                                   options=dl.SAFETY_CHECKS, default=[],
                                   key="ba_safetytrend_check")
        work = sdf_t if not zsel else sdf_t[sdf_t["zone"].isin(zsel)]
        if chk_multi:
            work = work[work["check"].isin(chk_multi)]
        if work.empty:
            _empty_note(rng)
        elif len(zsel) == 1 and len(chk_multi) == 1:
            # -------- Single zone + single safety check: two-view drill --------
            zone_one = zsel[0]
            chk_s = chk_multi[0]
            s1 = work.sort_values("date").copy()
            s1["_pass"] = s1["status"] == "Pass"
            st.caption(f"Zone **{zone_one}** — '{chk_s}'. Two views of the same data:")

            # View 1 — per inspection (pass = 100, fail/not-recorded = 0), stepped
            st.markdown("**1. Per inspection — passed / failed each time (shows WHEN it failed)**")
            v1 = s1.copy()
            v1["result"] = v1["_pass"].map({True: 100, False: 0})
            fig1 = px.line(v1, x="date", y="result", markers=True,
                           hover_data={"status": True, "result": False, "date": False})
            fig1.update_traces(marker=dict(size=11), line=dict(shape="hv", color=MUTED))
            fig1.update_yaxes(range=[-8, 108], tickvals=[0, 100], ticktext=["Fail", "Pass"])
            fig1.update_layout(xaxis_title="", yaxis_title="", height=300,
                               margin=dict(t=10, b=0))
            st.plotly_chart(fig1, width="stretch")
            fx(f"one marker per inspection of {zone_one}: 100 = '{chk_s}' passed that "
               "inspection, 0 = it failed or was not recorded. The step line shows "
               "exactly which inspections failed.")

            # View 2 — monthly pass rate (%)
            st.markdown("**2. Monthly pass rate — how often it passed per month (shows the TREND)**")
            v2 = s1.copy()
            v2["month"] = v2["date"].dt.to_period("M").dt.to_timestamp()
            mg = (v2.groupby("month").agg(passed=("_pass", "sum"),
                                          insp=("_pass", "size")).reset_index())
            mg["pass_rate"] = 100 * mg["passed"] / mg["insp"]
            fig2 = px.line(mg, x="month", y="pass_rate", markers=True,
                           hover_data={"passed": True, "insp": True,
                                       "pass_rate": ":.1f", "month": False})
            fig2.update_traces(marker=dict(size=9), line=dict(color=PASS))
            fig2.update_layout(xaxis_title="", yaxis_title="Pass rate (%)",
                               yaxis_range=[0, 105], height=300, margin=dict(t=10, b=0))
            st.plotly_chart(fig2, width="stretch")
            fx(f"each point = 100 × (inspections that month where '{chk_s}' passed ÷ "
               f"{zone_one}'s inspections that month). Smooths into a real % once the "
               "zone has several inspections in a month.")
            st.caption("Early on (≤1 inspection per month) both look binary; as "
                       "inspections accumulate, view 2 becomes a smooth trend while view 1 "
                       "keeps the exact pass/fail history. Pick multiple zones or 'Overall' "
                       "for the comparison line instead.")
        else:
            # -------- Comparison view: one line per zone --------
            grp = (work.groupby(["zone", "fi_reportid", "date"])
                   .agg(passed=("status", lambda s: int((s == "Pass").sum())),
                        required=("status", "size")).reset_index())
            grp["pass_rate"] = 100 * grp["passed"] / grp["required"]
            grp = grp.sort_values("date")
            fig = px.line(
                grp, x="date", y="pass_rate", color="zone", markers=True,
                hover_data={"passed": True, "required": True, "pass_rate": ":.1f",
                            "date": False, "zone": False},
                category_orders={"zone": zones_avail},
                color_discrete_sequence=px.colors.qualitative.Dark24)
            fig.update_traces(marker=dict(size=8))
            ytitle = (f"'{chk_multi[0]}' pass rate (%)" if len(chk_multi) == 1
                      else "Safety pass rate (%)")
            fig.update_layout(xaxis_title="", yaxis_title=ytitle, yaxis_range=[0, 105],
                              legend_title="Zone", height=440, margin=dict(t=10, b=0))
            st.plotly_chart(fig, width="stretch")
            scope = ("all required safety checks" if not chk_multi
                     else ", ".join(chk_multi))
            fx(f"each point = 100 × (selected safety checks marked Pass ÷ selected "
               "safety checks recorded) for that zone in one inspection. A required "
               f"check left blank counts as not passed. Selected: {scope}. x = "
               "inspection date; a line joins the zone's repeat inspections.")
            st.caption("Only zones that require the selected checks appear. Safety "
                       "checks accept multiple selections — select a single zone AND a "
                       "single safety check to drill into its per-inspection history.")


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
    st.metric("Bins failing more than once", len(repeat),
              help="Number of distinct bins that failed on 2 or more separate "
                   "inspections in range (a failed inspection = ≥1 of the four checks "
                   "failed). These are the bins where fixes aren't sticking.")
    if repeat.empty:
        st.info("No bin failed on more than one inspection in this range.")
        return
    disp = repeat.copy()
    disp["Dates failed"] = disp["dates"].map(lambda ds: ", ".join(d.strftime("%b %d") for d in ds))
    disp["Failed checks"] = disp["checks"].map(", ".join)
    disp = disp.rename(columns={"bin": "Bin", "zone": "Zone", "times_failed": "Times failed"})
    st.dataframe(disp[["Bin", "Zone", "Times failed", "Dates failed", "Failed checks"]],
                 width="stretch", hide_index=True)
    fx("for each bin, 'Times failed' = number of its inspections that failed at least "
       f"one of the four checks ({FOUR_CHECKS}); only bins with more than one such "
       "inspection are listed. 'Dates failed' = those inspection dates; 'Failed checks' "
       "= every distinct check the bin failed across them.")


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
        c[0].metric("Reports analysed", len(comp),
                    help="Number of inspection reports in the selected dates.")
        c[1].metric("Fully complete", int((comp["completed"] == comp["required"]).sum()),
                    help="Reports that recorded every check their zone is required to do "
                         "(per the Zone Config): completed = required.")
        c[2].metric("Missing ≥1 required check", len(incomplete),
                    help="Reports that skipped at least one check their zone was required "
                         "to do (per the Zone Config): completed < required.")
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
        fx("one pair of bars per report. Required (grey) = how many checks the zone's "
           "Zone Config marks as needed (Y). Completed (green) = how many of those were "
           "actually filled in on that inspection. A green bar shorter than grey = a gap.")

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
        fx("rows = zones, columns = every check type. For each zone×check: '–' if the "
           "Zone Config doesn't require it for that zone; otherwise Fail if any "
           "inspection failed it (for Bin Quality, any bin defect in the zone), else "
           "Pass if it was recorded as passing, else Recorded (captured but no explicit "
           "pass/fail), else Missing (required but never recorded).")
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
        fx("lists only reports that skipped a required check (completed < required). "
           "'missing_checks' = the checks the zone was required to do (Zone Config Y) "
           "but which have no record in that report.")

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
    fx("read directly from the Zone Config workbook (Sheet 1): True = the zone is "
       "required to perform that check (Y in the source), False = not required.")


# --------------------------------------------------------------------------- #
PAGES = {
    "Overview": page_overview,
    "Bin Failure Analysis": page_bin_analysis,
    "Repeat Offenders": page_repeat,
    "Data Quality": page_quality,
}
PAGES[page]()
