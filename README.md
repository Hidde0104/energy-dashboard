# European Intraday Price Swing Dashboard

Interactive Streamlit dashboard for analysing daily peak-to-trough (intraday)
electricity price swings across European countries.

## What it shows

Four views, all driven by the same sidebar filters (date range + countries):

1. **Time series** — Smoothed line chart of daily swings per country, with an
   adjustable rolling-average window (1–30 days).
2. **Calendar heatmap** — Week-by-weekday grid of swings for any one country,
   making weekly patterns and outlier days visible at a glance.
3. **Country ranking** — Horizontal bar chart of countries ranked by mean,
   median, max, or 95th-percentile swing, plus a box plot of the full
   distribution.
4. **Data** — Filtered table of daily peak / trough / swing / mean prices,
   with a CSV download button.

The default date range is the most recent 12 months in the dataset.

## Setup

```bash
pip install -r requirements.txt
```

## Run

Place `all_countries.csv` in the same folder as `app.py`, then:

```bash
streamlit run app.py
```

The browser opens automatically. If `all_countries.csv` is missing from the
folder, the sidebar shows a file uploader as a fallback — useful for sharing.

## Expected CSV schema

| Column              | Example                |
|---------------------|------------------------|
| `Country`           | `Austria`              |
| `ISO3 Code`         | `AUT`                  |
| `Datetime (UTC)`    | `2015-01-01 00:00:00`  |
| `Datetime (Local)`  | `2015-01-01 01:00:00`  |
| `Price (EUR/MWhe)`  | `22.34`                |

The app uses `Datetime (Local)` for grouping, since intraday peaks and
troughs are local-clock phenomena.

## Sharing

Send the whole folder (`app.py`, `requirements.txt`, `README.md`,
`all_countries.csv`) to your friend. They install the requirements and run
the same command. Done.
