# Floor Inspection — Failure Analytics Dashboard

A Streamlit dashboard for analysing production-plant floor & safety inspection
data exported from a Microsoft Dataverse / Power Apps inspection app.

## What it shows

- **Overview** — KPIs, defects by zone & check, report outcomes, inspection
  timeline, bin pass-rate by zone, and a per-bin failure breakdown with an
  inspector-notes ledger.
- **Bin Failure Analysis** — per-check defect counts, failure rate by zone,
  a zone × check heatmap, and a per-zone safety-check view (stacked status bar
  + notes ledger).
- **Repeat Offenders** — bins that failed on more than one inspection.
- **Data Quality** — checklist completeness vs the config's required checks,
  a required-check status grid by zone, and known data-quality notes.

Every chart and table has its **own independent date-range slider**.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Data

The inspection data (the `fi_*.csv` exports and the `Zone Config` workbook) is
**not** stored in this repository — it contains plant data and lives in a
separate **private** repo. To run locally, place those files alongside `app.py`
(the same folder). `data_loader.py` reads them from the working directory.

Expected data files:

- `fi_binqualityinspections.csv`
- `fi_floorinspectionmasters.csv`
- `fi_electricalsafeties.csv`, `fi_fireextinguisherinspections.csv`,
  `fi_emergencyexitlightingchecks.csv`, `fi_eyewashstationinspections.csv`,
  `fi_docksecurityandsafetyinspections.csv`, `fi_moisturecontrols.csv`,
  `fi_sboards.csv`
- `Zone Config Table-new (1).xlsx` — authoritative bin→zone mapping and
  per-zone required-check matrix.

## Notes on the data model

- Bin→Zone mapping is sourced from the Zone Config workbook (authoritative).
- Pass/Fail is read from the Dataverse `*text` fields; the `fi_passed` booleans
  are unreliable and are ignored.
