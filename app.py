"""
European Intraday Energy Price Swing Dashboard
==============================================
Interactive Streamlit app analysing intraday (peak-to-trough) price swings
across European countries over the past 12 months.

Run:
    pip install -r requirements.txt
    streamlit run app.py

The app looks for `all_countries.csv` in the same folder as this script.
If not found, it offers a file uploader fallback.
"""

from __future__ import annotations

import base64
import io
import zipfile
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen, Request

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# File paths (defined before page config because set_page_config needs LOGO_PATH)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent if "__file__" in globals() else Path.cwd()
GUIDA_PATH = SCRIPT_DIR / "fonts" / "guida-bold.otf"
LOGO_PATH = SCRIPT_DIR / "logo.png"

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="European Intraday Price Swings",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Typography — load Guida Bold from local file, Inter from Google Fonts
# ---------------------------------------------------------------------------


@st.cache_data
def _font_face_rule() -> str:
    """Build a @font-face CSS rule with the Guida Bold file embedded as base64.

    Returns an empty string (and warns) if the file is missing, so the rest of
    the app still works — the title just falls back to the next font.
    """
    if not GUIDA_PATH.exists():
        return ""
    encoded = base64.b64encode(GUIDA_PATH.read_bytes()).decode("ascii")
    return f"""
    @font-face {{
        font-family: 'Guida';
        font-style: normal;
        font-weight: 700;
        font-display: swap;
        src: url(data:font/otf;base64,{encoded}) format('opentype');
    }}
    """


_guida_rule = _font_face_rule()
if not _guida_rule:
    st.sidebar.warning(
        "⚠️ `fonts/guida-bold.otf` not found — the title will use a fallback font."
    )

# Theme colors (kept in sync with .streamlit/config.toml)
COLOR_BG = "#1F2739"
COLOR_SURFACE = "#363D4D"
COLOR_ACCENT = "#00C490"
COLOR_TEXT = "#E8ECF2"
COLOR_MUTED = "#8B92A3"

# Custom CSS for a cleaner, more editorial look on dark theme
st.markdown(
    f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        {_guida_rule}

        /* Base body text — Inter Light everywhere by default */
        html, body, [class*="css"], .stMarkdown, .stMarkdown p, .stMarkdown li,
        .stCaption, label, .stRadio, .stSelectbox, .stMultiSelect, .stSlider,
        div[data-testid="stSidebar"] *, .stTabs, .stDataFrame,
        .stExpander, .stAlert {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 300;
        }}

        /* Section sub-headers stay Inter but a touch heavier for hierarchy */
        h2, h3, h4, h5, h6 {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 500;
            letter-spacing: -0.01em;
        }}

        /* Main title — Guida Bold in accent teal */
        h1 {{
            font-family: 'Guida', Georgia, serif !important;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: {COLOR_ACCENT} !important;
        }}

        .main .block-container {{ padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }}

        /* Metric numbers — Inter Medium (500), accent green.
           Streamlit's internal CSS forces bold; we override with maximum
           specificity by targeting the test-id AND every nested element type. */
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] div,
        div[data-testid="stMetricValue"] p,
        div[data-testid="stMetricValue"] span,
        div[data-testid="stMetricValue"] > * {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            color: {COLOR_ACCENT} !important;
            font-synthesis-weight: none !important;
            -webkit-font-smoothing: antialiased;
        }}
        div[data-testid="stMetricValue"] {{
            font-size: 1.6rem !important;
        }}
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] div,
        div[data-testid="stMetricLabel"] p,
        div[data-testid="stMetricLabel"] span,
        div[data-testid="stMetricLabel"] > * {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 300 !important;
        }}
        [data-testid="stMetric"] {{
            background: {COLOR_SURFACE};
            padding: 1rem 1.25rem;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.04);
        }}

        .stPlotlyChart {{
            background: {COLOR_SURFACE};
            border-radius: 10px;
            padding: 0.75rem;
            border: 1px solid rgba(255,255,255,0.04);
        }}
        div[data-testid="stSidebarUserContent"] {{ padding-top: 1rem; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
        .stTabs [data-baseweb="tab"] {{
            background: {COLOR_SURFACE};
            border-radius: 8px 8px 0 0;
            padding: 0.5rem 1rem;
            font-weight: 400;
        }}
        .stTabs [aria-selected="true"] {{
            background: {COLOR_ACCENT} !important;
            color: {COLOR_BG} !important;
            font-weight: 500;
        }}
        div[data-testid="stDataFrame"] {{
            background: {COLOR_SURFACE};
            border-radius: 10px;
            padding: 0.5rem;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# Shared Plotly layout — applied to every chart so theming stays consistent
def apply_dark_theme(fig, height=None):
    fig.update_layout(
        paper_bgcolor=COLOR_SURFACE,
        plot_bgcolor=COLOR_SURFACE,
        font=dict(color=COLOR_TEXT, family="Inter, sans-serif", size=12),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.1)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.1)"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig


# Color sequence built around the accent — used for multi-country line charts
ACCENT_SEQUENCE = [
    "#00C490", "#7DD3C0", "#F5C76A", "#E68C7C", "#A78BFA",
    "#60A5FA", "#FB923C", "#F472B6", "#34D399", "#FBBF24",
    "#94A3B8", "#22D3EE",
]

# Monochrome scale built from the accent — used for heatmap & bar gradients
ACCENT_SCALE = [
    [0.0, "#1F2739"],
    [0.25, "#1E4A45"],
    [0.5, "#1A6E5A"],
    [0.75, "#069672"],
    [1.0, "#00C490"],
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS = {
    "Country",
    "ISO3 Code",
    "Datetime (UTC)",
    "Datetime (Local)",
    "Price (EUR/MWhe)",
}


@st.cache_data(show_spinner="Loading and aggregating price data…")
def load_and_aggregate(source) -> tuple[pd.DataFrame, dict]:
    """Stream the hourly CSV in chunks and aggregate to daily swings on the fly.

    This avoids holding the full hourly dataset (often hundreds of MB) in memory.
    For each chunk we accumulate per-(country, date) min, max, sum, and count,
    then combine across chunks at the end.

    Returns a tuple of (daily_swings_df, metadata_dict).
    """
    CHUNK_SIZE = 200_000  # rows per chunk — keeps peak memory low

    # Per-key accumulators: keyed by (country, iso, date)
    peak: dict = {}
    trough: dict = {}
    price_sum: dict = {}
    hours: dict = {}

    total_rows = 0
    countries_seen: set = set()
    header_checked = False

    # Note: BytesIO needs to be rewound between reads, but pd.read_csv with
    # chunksize handles it via a single iterator.
    reader = pd.read_csv(
        source,
        chunksize=CHUNK_SIZE,
        usecols=list(EXPECTED_COLUMNS),  # skip any extra columns Ember might add
    )

    for chunk in reader:
        if not header_checked:
            missing = EXPECTED_COLUMNS - set(chunk.columns)
            if missing:
                raise ValueError(
                    f"Missing expected columns: {missing}. Found: {list(chunk.columns)}"
                )
            header_checked = True

        # Parse + clean this chunk
        chunk["Datetime"] = pd.to_datetime(chunk["Datetime (Local)"], errors="coerce")
        chunk["Price"] = pd.to_numeric(chunk["Price (EUR/MWhe)"], errors="coerce")
        chunk = chunk.dropna(subset=["Datetime", "Price"])
        if chunk.empty:
            continue

        chunk["Date"] = chunk["Datetime"].dt.date
        countries_seen.update(chunk["Country"].unique())
        total_rows += len(chunk)

        # Aggregate within this chunk first — turns ~200k rows into ~ N_countries * N_days_in_chunk rows
        agg = chunk.groupby(
            ["Country", "ISO3 Code", "Date"], sort=False
        )["Price"].agg(["max", "min", "sum", "count"])

        # Merge chunk aggregates into running accumulators
        for (country, iso, date), row in agg.iterrows():
            key = (country, iso, date)
            row_max = row["max"]
            row_min = row["min"]
            row_sum = row["sum"]
            row_count = row["count"]

            if key in peak:
                if row_max > peak[key]:
                    peak[key] = row_max
                if row_min < trough[key]:
                    trough[key] = row_min
                price_sum[key] += row_sum
                hours[key] += row_count
            else:
                peak[key] = row_max
                trough[key] = row_min
                price_sum[key] = row_sum
                hours[key] = row_count

        # Free the chunk explicitly so memory drops between iterations
        del chunk, agg

    if not peak:
        raise ValueError("No usable rows found in the data.")

    # Materialize accumulators into a DataFrame
    keys = list(peak.keys())
    swings = pd.DataFrame(
        {
            "Country": [k[0] for k in keys],
            "ISO3 Code": [k[1] for k in keys],
            "Date": pd.to_datetime([k[2] for k in keys]),
            "Peak": [peak[k] for k in keys],
            "Trough": [trough[k] for k in keys],
            "Hours": [hours[k] for k in keys],
        }
    )
    swings["Mean"] = [price_sum[k] / hours[k] for k in keys]
    swings["Swing"] = swings["Peak"] - swings["Trough"]

    # Only keep days with reasonable coverage (≥ 20 hours of 24)
    swings = swings[swings["Hours"] >= 20].reset_index(drop=True)

    metadata = {
        "total_rows": total_rows,
        "countries": len(countries_seen),
    }
    return swings, metadata


@st.cache_data(show_spinner="Downloading data from Ember (one-time, ~60s)…", ttl=24 * 3600)
def download_and_extract_zip(url: str) -> bytes:
    """Download a zip file from a URL and return the bytes of the first CSV inside.

    Cached for 24 hours, so the download only happens once per server lifetime
    (or sooner if the cache is invalidated).
    """
    req = Request(url, headers={"User-Agent": "energy-dashboard/1.0"})
    with urlopen(req, timeout=120) as resp:
        zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Find the first CSV file inside the archive
        csv_members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_members:
            raise ValueError(
                f"No CSV file found inside the zip. Contents: {zf.namelist()}"
            )
        with zf.open(csv_members[0]) as f:
            return f.read()


# ---------------------------------------------------------------------------
# Data source resolution
# ---------------------------------------------------------------------------
DEFAULT_CSV = SCRIPT_DIR / "all_countries.csv"
EMBER_ZIP_URL = (
    "https://files.ember-energy.org/public-downloads/price/outputs/"
    "european_wholesale_electricity_price_data_hourly.zip"
)


def resolve_data_source():
    """Resolve the data source in priority order:
    1. Local `all_countries.csv` next to the script (fastest, used in dev)
    2. Ember's public zip download (used in production / on Streamlit Cloud)
    3. Manual file uploader (final fallback)
    """
    # Priority 1: local CSV — fastest, no network round trip
    if DEFAULT_CSV.exists():
        st.sidebar.success(f"📂 Loaded `{DEFAULT_CSV.name}` from script folder")
        return DEFAULT_CSV

    # Priority 2: Ember's public zip
    try:
        csv_bytes = download_and_extract_zip(EMBER_ZIP_URL)
        st.sidebar.success("📥 Loaded latest data from Ember")
        return io.BytesIO(csv_bytes)
    except (URLError, zipfile.BadZipFile, ValueError, TimeoutError) as e:
        st.sidebar.warning(
            f"Could not fetch from Ember ({type(e).__name__}). "
            "Upload the CSV manually below."
        )

    # Priority 3: uploader fallback
    uploaded = st.sidebar.file_uploader(
        "Upload your CSV",
        type=["csv", "zip"],
        help=(
            "Expected columns: Country, ISO3 Code, Datetime (UTC), "
            "Datetime (Local), Price (EUR/MWhe). A zip containing the CSV is also accepted."
        ),
    )
    if uploaded is not None and uploaded.name.lower().endswith(".zip"):
        # Unzip the uploaded archive
        with zipfile.ZipFile(uploaded) as zf:
            csv_members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_members:
                st.sidebar.error("No CSV found in the uploaded zip.")
                return None
            return io.BytesIO(zf.read(csv_members[0]))
    return uploaded


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
if LOGO_PATH.exists():
    logo_col, title_col = st.columns([1, 9], vertical_alignment="center")
    with logo_col:
        st.image(str(LOGO_PATH), width=72)
    with title_col:
        st.title("European Intraday Price Swings")
else:
    st.title("European Intraday Price Swings")
st.caption(
    "Daily peak-to-trough spreads in day-ahead electricity markets · EUR/MWh · local time"
)

source = resolve_data_source()
if source is None:
    st.info(
        "👈 No data source available. The app tried to download from Ember "
        "automatically — if that failed, please upload the CSV (or zip) in "
        "the sidebar."
    )
    st.stop()

try:
    swings, data_meta = load_and_aggregate(source)
except Exception as e:
    st.error(f"Could not read the CSV: {e}")
    st.stop()

if swings.empty:
    st.error("No usable rows after cleaning. Check the input file.")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar controls — past 12 months window
# ---------------------------------------------------------------------------
data_max_date = swings["Date"].max()
default_start = data_max_date - pd.DateOffset(months=12) + pd.Timedelta(days=1)
data_min_date = swings["Date"].min()

st.sidebar.header("Filters")

# Data source attribution — Ember requires credit + link under CC BY 4.0
with st.sidebar.expander("ℹ️ About the data", expanded=False):
    st.markdown(
        """
        **Source:** [Ember](https://ember-energy.org/) — European
        Wholesale Electricity Price Data.

        Ember is an independent energy think tank. Their data is published
        under a [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
        licence, which allows reuse with attribution.

        **Suggested citation:**
        Ember (2025). *European Wholesale Electricity Price Data.*
        Accessed from ember-energy.org.
        """
    )

date_range = st.sidebar.date_input(
    "Date range",
    value=(max(default_start.date(), data_min_date.date()), data_max_date.date()),
    min_value=data_min_date.date(),
    max_value=data_max_date.date(),
    help="Defaults to the most recent 12 months in the dataset.",
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    # User is mid-selection
    st.sidebar.info("Pick a start and end date to continue.")
    st.stop()

start_ts = pd.Timestamp(start_date)
end_ts = pd.Timestamp(end_date)

countries_all = sorted(swings["Country"].unique())

# Default: top 10 by mean swing in window for a sensible starting view
window_mask = (swings["Date"] >= start_ts) & (swings["Date"] <= end_ts)
default_top = (
    swings[window_mask]
    .groupby("Country")["Swing"]
    .mean()
    .sort_values(ascending=False)
    .head(10)
    .index.tolist()
)

selected_countries = st.sidebar.multiselect(
    "Countries",
    options=countries_all,
    default=default_top if default_top else countries_all[:10],
    help="Select one or more countries to compare.",
)

if not selected_countries:
    st.warning("Select at least one country in the sidebar.")
    st.stop()

filtered = swings[
    (swings["Country"].isin(selected_countries)) & window_mask
].copy()

if filtered.empty:
    st.warning("No data in the selected range. Widen the filters.")
    st.stop()


# ---------------------------------------------------------------------------
# Top-line metrics
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Countries", f"{filtered['Country'].nunique()}")
col2.metric("Days observed", f"{filtered['Date'].nunique():,}")
col3.metric("Avg daily swing", f"€{filtered['Swing'].mean():,.1f}")
col4.metric("Largest single swing", f"€{filtered['Swing'].max():,.1f}")

st.divider()


# ---------------------------------------------------------------------------
# Tabs for the four views
# ---------------------------------------------------------------------------
tab_ts, tab_heat, tab_rank, tab_data = st.tabs(
    ["📈 Time series", "🗓️ Calendar heatmap", "🏆 Country ranking", "📋 Data"]
)


# --- Time series ------------------------------------------------------------
with tab_ts:
    st.subheader("Daily intraday swing over time")

    smoothing = st.slider(
        "Rolling average (days)",
        min_value=1,
        max_value=30,
        value=7,
        help="Smooth the line to see the trend through daily noise.",
    )

    ts = filtered.sort_values("Date").copy()
    ts["Smoothed"] = (
        ts.groupby("Country")["Swing"]
        .transform(lambda s: s.rolling(smoothing, min_periods=1).mean())
    )

    fig_ts = px.line(
        ts,
        x="Date",
        y="Smoothed",
        color="Country",
        labels={"Smoothed": f"Swing (€/MWh, {smoothing}-day avg)", "Date": ""},
        color_discrete_sequence=ACCENT_SEQUENCE,
    )
    fig_ts.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    apply_dark_theme(fig_ts, height=500)
    st.plotly_chart(fig_ts, width="stretch")

    with st.expander("ℹ️ How to read this"):
        st.markdown(
            "Each line shows the rolling mean of the daily peak-to-trough spread "
            "for one country. Higher values = bigger intraday price differences = "
            "more value for flexibility (batteries, demand response, etc.)."
        )


# --- Calendar heatmap -------------------------------------------------------
with tab_heat:
    st.subheader("Calendar heatmap of daily swings")

    heat_country = st.selectbox(
        "Country",
        options=selected_countries,
        index=0,
    )

    sub = filtered[filtered["Country"] == heat_country].copy()
    if sub.empty:
        st.info("No data for this country in the selected window.")
    else:
        sub["Year"] = sub["Date"].dt.year
        sub["Week"] = sub["Date"].dt.isocalendar().week.astype(int)
        sub["DayOfWeek"] = sub["Date"].dt.dayofweek  # 0 = Monday
        sub["YearWeek"] = (
            sub["Date"].dt.strftime("%G-W%V")  # ISO year + ISO week
        )

        # Order by actual chronology, not lexicographically
        order = (
            sub.sort_values("Date")
            .drop_duplicates("YearWeek")["YearWeek"]
            .tolist()
        )

        pivot = sub.pivot_table(
            index="DayOfWeek",
            columns="YearWeek",
            values="Swing",
            aggfunc="mean",
        ).reindex(index=range(7), columns=order)

        weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        fig_heat = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=pivot.columns,
                y=weekday_labels,
                colorscale=ACCENT_SCALE,
                colorbar=dict(title="€/MWh", tickfont=dict(color=COLOR_TEXT)),
                hovertemplate="Week %{x}<br>%{y}<br>Swing: €%{z:.1f}<extra></extra>",
            )
        )
        fig_heat.update_layout(
            xaxis=dict(title="", tickangle=-45, nticks=20),
            yaxis=dict(title="", autorange="reversed"),
        )
        apply_dark_theme(fig_heat, height=320)
        st.plotly_chart(fig_heat, width="stretch")

        c1, c2, c3 = st.columns(3)
        c1.metric("Country avg swing", f"€{sub['Swing'].mean():,.1f}")
        c2.metric("Max swing day", f"€{sub['Swing'].max():,.1f}")
        c3.metric(
            "Date of max",
            sub.loc[sub["Swing"].idxmax(), "Date"].strftime("%d %b %Y"),
        )


# --- Country ranking --------------------------------------------------------
with tab_rank:
    st.subheader("Country ranking by intraday swing")

    metric_choice = st.radio(
        "Rank by",
        options=["Mean daily swing", "Median daily swing", "Max daily swing", "95th percentile"],
        horizontal=True,
    )

    agg_map = {
        "Mean daily swing": ("mean", "Mean swing"),
        "Median daily swing": ("median", "Median swing"),
        "Max daily swing": ("max", "Max swing"),
        "95th percentile": (lambda s: s.quantile(0.95), "P95 swing"),
    }
    agg_func, label = agg_map[metric_choice]

    ranking = (
        filtered.groupby("Country")["Swing"]
        .agg(agg_func)
        .reset_index()
        .rename(columns={"Swing": label})
        .sort_values(label, ascending=True)
    )

    fig_rank = px.bar(
        ranking,
        x=label,
        y="Country",
        orientation="h",
        text=ranking[label].round(1),
        color=label,
        color_continuous_scale=ACCENT_SCALE,
    )
    fig_rank.update_layout(
        coloraxis_showscale=False,
        xaxis_title=f"{label} (€/MWh)",
        yaxis_title="",
    )
    apply_dark_theme(fig_rank, height=max(350, 28 * len(ranking) + 60))
    fig_rank.update_traces(texttemplate="€%{text}", textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_rank, width="stretch")

    # Distribution box plot — context for the headline ranking
    st.markdown("##### Distribution of daily swings")
    fig_box = px.box(
        filtered,
        x="Country",
        y="Swing",
        points=False,
        category_orders={"Country": ranking["Country"].tolist()[::-1]},
        color_discrete_sequence=[COLOR_ACCENT],
    )
    fig_box.update_layout(
        yaxis_title="Daily swing (€/MWh)",
        xaxis_title="",
    )
    apply_dark_theme(fig_box, height=420)
    fig_box.update_xaxes(tickangle=-30)
    st.plotly_chart(fig_box, width="stretch")


# --- Data table -------------------------------------------------------------
with tab_data:
    st.subheader("Underlying daily aggregates")
    st.caption("Filtered to your sidebar selection. Click columns to sort.")

    display = filtered[["Country", "ISO3 Code", "Date", "Trough", "Peak", "Swing", "Mean"]].copy()
    display = display.sort_values(["Date", "Country"], ascending=[False, True])
    display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Trough", "Peak", "Swing", "Mean"]:
        display[col] = display[col].round(2)

    st.dataframe(display, width="stretch", height=500, hide_index=True)

    csv_buf = io.StringIO()
    display.to_csv(csv_buf, index=False)
    st.download_button(
        "⬇️ Download as CSV",
        data=csv_buf.getvalue(),
        file_name="intraday_swings_filtered.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()

footer_col1, footer_col2 = st.columns([3, 2])
with footer_col1:
    st.caption(
        f"Dataset spans {data_min_date.strftime('%d %b %Y')} → "
        f"{data_max_date.strftime('%d %b %Y')} · "
        f"{data_meta['countries']} countries · "
        f"{data_meta['total_rows']:,} hourly observations"
    )
with footer_col2:
    st.caption(
        "Data: [Ember](https://ember-energy.org/) — "
        "European Wholesale Electricity Price Data · "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)"
    )