"""API-backed Streamlit dashboard for synthetic research exploration."""

import os
from datetime import date

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
st.sidebar.caption("This date affects age calculations only; charts include all loaded records.")
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()


@st.cache_data(ttl=30)
def fetch(url: str) -> dict | list:
    """Fetch computed aggregates; never substitute mock values after an error."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


try:
    summary = fetch(f"{base_url}/cohort/summary?as_of={as_of.isoformat()}")
    monthly = fetch(f"{base_url}/encounters/monthly")
    conditions = fetch(f"{base_url}/conditions/common")
except (requests.RequestException, ValueError):
    st.error("Cannot retrieve research data. Check the API, database, and import status.")
    st.stop()

st.header("Patient cohort overview")
for column, (name, count) in zip(st.columns(4), summary["counts"].items(), strict=True):
    column.metric(name.title(), count)
if summary["counts"]["patients"] == 0:
    st.info("No patients loaded. Run the documented synthetic CSV import.")
st.caption("Counts reflect currently loaded records, not real populations or scientific findings.")
st.write("Age summary (at reference date, or death if earlier)", summary["age"])
dimension = st.selectbox("Demographic dimension", ["gender", "race", "ethnicity"])
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

st.header("Data quality")
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
