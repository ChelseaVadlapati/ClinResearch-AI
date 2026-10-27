"""API-backed Streamlit dashboard for synthetic research exploration."""

import json
import os
from datetime import date
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="ClinResearch AI", layout="wide")
st.title("ClinResearch AI")
st.warning(
    "Synthetic EHR research demonstration only. Not clinically validated or for patient care."
)
base_url = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
as_of = st.sidebar.date_input(
    "Age reference date",
    value=date.today(),
    min_value=date(1900, 1, 1),
    max_value=date(2100, 12, 31),
)
st.sidebar.caption("Age is measured at this date, or at death if earlier.")
filters = {"as_of": as_of.isoformat()}
if st.sidebar.checkbox("Enable cohort filters", key="enable_filters"):
    filters["minimum_age"] = st.sidebar.number_input("Minimum age", 0, 120, 0)
    filters["maximum_age"] = st.sidebar.number_input("Maximum age", 0, 120, 120)
    gender = st.sidebar.selectbox(
        "Recorded gender", ["All", "F", "M", "other", "unknown"], key="gender_filter"
    )
    kind = st.sidebar.selectbox(
        "Required encounter class",
        ["All", "inpatient", "ambulatory", "emergency", "wellness"],
        key="class_filter",
    )
    if gender != "All":
        filters["gender"] = gender
    if kind != "All":
        filters["encounter_class"] = kind
    if st.sidebar.checkbox("Limit matching encounter dates"):
        filters["encounter_start"] = st.sidebar.date_input(
            "Encounter start (inclusive)", value=date(2024, 1, 1)
        ).isoformat()
        filters["encounter_end"] = st.sidebar.date_input(
            "Encounter end (exclusive)", value=date(2025, 1, 1)
        ).isoformat()
    st.sidebar.caption(
        "Selects patients with a matching encounter. Charts include their full recorded history."
    )
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()


@st.cache_data(ttl=30)
def fetch(url: str) -> dict | list:
    """Fetch computed aggregates; never substitute mock values after an error."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


try:
    exploration = fetch(f"{base_url}/cohort/explore?{urlencode(filters)}")
    summary, monthly, conditions = (
        exploration["summary"],
        exploration["monthly"],
        exploration["conditions"],
    )
except (requests.RequestException, ValueError):
    st.error("Cannot retrieve research data. Check the API, database, and import status.")
    st.stop()

st.caption(exploration["scope"])
st.caption(
    f"Software {exploration['source']['software_version']} · latest dataset: "
    f"{exploration['source']['latest_dataset_version']} · imported "
    f"{exploration['source']['latest_import_at']}"
)
st.caption(exploration["source"]["scope"])
st.download_button(
    "Download aggregate research summary (JSON)",
    json.dumps(exploration, indent=2, default=str),
    "cohort-summary.json",
    "application/json",
)
aggregate_rows = [{"measure": k, "count": v} for k, v in summary["counts"].items()]
st.download_button(
    "Download aggregate counts (CSV)",
    pd.DataFrame(aggregate_rows).to_csv(index=False),
    "cohort-counts.csv",
    "text/csv",
)
st.header("Patient cohort overview")
for column, (name, count) in zip(st.columns(4), summary["counts"].items(), strict=True):
    column.metric(name.title(), count)
if summary["counts"]["patients"] == 0:
    st.info("No patients match the selection. Clear filters or check the synthetic import.")
st.caption("Counts reflect currently loaded records, not real populations or scientific findings.")
st.write("Age summary (at reference date, or death if earlier)", summary["age"])
dimension = st.selectbox("Demographic dimension", ["gender", "race", "ethnicity"], key="dimension")
frame = pd.DataFrame(summary["demographics"][dimension].items(), columns=[dimension, "patients"])
if not frame.empty:
    st.plotly_chart(px.bar(frame, x=dimension, y="patients"), width="stretch")

st.header("Encounter trends")
if monthly:
    st.plotly_chart(
        px.line(pd.DataFrame(monthly), x="month", y="encounters", markers=True), width="stretch"
    )
else:
    st.info("No encounters loaded.")
st.header("Common conditions")
if conditions:
    frame = pd.DataFrame(conditions)
    frame["label"] = frame["description"] + " [" + frame["system"] + ":" + frame["code"] + "]"
    st.plotly_chart(
        px.bar(frame, x="occurrences", y="label", orientation="h", hover_data=["patients"]),
        width="stretch",
    )
    st.dataframe(frame.drop(columns="label"), hide_index=True)
else:
    st.info("No conditions loaded.")
st.caption(
    "Condition occurrences can repeat per patient. These counts are not prevalence estimates."
)

with st.expander("Chart data tables (accessible alternative)"):
    st.dataframe(
        pd.DataFrame(summary["demographics"][dimension].items(), columns=[dimension, "patients"]),
        hide_index=True,
    )
    st.dataframe(pd.DataFrame(monthly), hide_index=True)

st.header("Data quality")
st.caption("Missingness reflects selected patients; import audit below covers the whole database.")
quality = summary["data_quality"]
st.write("Missing demographic values", quality["missing_demographics"])
st.metric("Import runs", quality["import_runs"])
if quality["latest_import"]:
    report = quality["latest_import"]
    st.caption(f"Latest import: {report['run_id']}. Accepted includes previously loaded records.")
    st.dataframe(pd.DataFrame(report["tables"]).T, width="stretch")
    st.write("Changes in latest import", report["changes"])
    if any(table["rejected"] for table in report["tables"].values()):
        st.warning("Latest import rejected rows. Inspect its JSON report or rejected_rows table.")
else:
    st.info("No import audit is available.")

st.header("NLP and readmission research")
st.caption(
    "Saved analysis of synthetic data. Results are a snapshot "
    "and do not refresh when data is imported or dashboard filters change."
)
try:
    research = fetch(f"{base_url}/research/report")
except (requests.RequestException, ValueError):
    st.warning(
        "Research report could not be loaded. The clinical data dashboard remains available."
    )
else:
    if research["status"] == "not_run":
        st.info("No research run yet. Run the documented clinresearch analyze command.")
    else:
        report = research["report"]
        st.caption(
            f"Generated {report['generated_at']} · "
            f"Observation end (exclusive): {report['observation_end_exclusive']}"
        )
        st.download_button(
            "Download saved aggregate study report",
            json.dumps(report, indent=2),
            "study-report.json",
            "application/json",
        )
        if report.get("study_config"):
            with st.expander("Saved study configuration (independent of dashboard filters)"):
                st.json(report["study_config"])
                st.caption(f"Configuration SHA-256: {report['config_sha256']}")
        st.write("Cohort eligibility audit", report["cohort_audit"])
        if report.get("cohort_flow"):
            st.dataframe(pd.DataFrame(report["cohort_flow"]), hide_index=True)
        st.write("Simulated notes", report["notes"])
        descriptive = report.get("descriptive")
        if descriptive and descriptive["patients"]:
            st.subheader("Observed outcome classes")
            st.bar_chart(
                pd.DataFrame(
                    {"patients": [descriptive["negatives"], descriptive["positives"]]},
                    index=["No observed return", "Observed return"],
                )
            )
            feature = st.selectbox(
                "Feature distribution", list(descriptive["features"]), key="feature_distribution"
            )
            st.dataframe(
                pd.DataFrame(descriptive["features"][feature]["histogram"]), hide_index=True
            )
            st.bar_chart(
                pd.DataFrame(descriptive["features"][feature]["histogram"]), x="lower", y="count"
            )
            if descriptive["outcome_wilson_95"]:
                st.write(
                    "Descriptive synthetic-sample Wilson interval", descriptive["outcome_wilson_95"]
                )
            else:
                st.caption(descriptive["interval_withheld_reason"])
        evaluation = report["evaluation"]
        st.write("Temporal split", evaluation["split"])
        if evaluation["status"] == "insufficient_data":
            st.info("Model not trained: " + evaluation["reason"])
        else:
            st.warning(
                "Synthetic holdout scores are not evidence of clinical prediction performance."
            )
            st.write("Logistic regression holdout metrics", evaluation["metrics"])
            st.write("Training-prevalence constant baseline", evaluation["constant_baseline"])
            st.write("95% bootstrap intervals", evaluation["bootstrap_95_percent_intervals"])
            calibration = pd.DataFrame(evaluation["calibration"])
            st.dataframe(calibration, hide_index=True)
            st.line_chart(
                calibration.dropna(subset=["mean_prediction", "observed_fraction"]),
                x="mean_prediction",
                y="observed_fraction",
            )
        with st.expander("Research definitions and limitations"):
            st.write("Features", evaluation["features"])
            for limitation in evaluation["limitations"]:
                st.write("• " + limitation)


st.header("Experimental synthetic NLP benchmark")
st.caption("Separate fixed text benchmark; not filtered by the patient cohort controls.")
try:
    nlp = fetch(f"{base_url}/nlp/report")
except (requests.RequestException, ValueError):
    st.warning("NLP report unavailable. Other dashboard sections remain available.")
else:
    if nlp["status"] == "not_run":
        st.info("No NLP benchmark report configured. Run the documented optional experiment.")
    else:
        nlp_report = nlp["report"]
        st.warning(
            "Assistant-authored synthetic annotations without independent clinical review. "
            "Not clinical NLP accuracy."
        )
        st.caption(
            f"Dataset {nlp_report['dataset_version']} · "
            f"train {nlp_report['train_examples']}, holdout {nlp_report['test_examples']} · "
            f"transformer: {nlp_report['transformer_status']}"
        )
        table = [
            {"method": method, **result["classification"]["macro avg"]}
            for method, result in nlp_report["results"].items()
        ]
        st.dataframe(pd.DataFrame(table), hide_index=True)
        st.download_button(
            "Download aggregate NLP results",
            json.dumps(nlp_report, indent=2),
            "nlp-summary.json",
            "application/json",
        )
