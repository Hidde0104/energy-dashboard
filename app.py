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

# Open Graph metadata — controls preview cards when the URL is shared on
# LinkedIn, Slack, WhatsApp, X, etc. Streamlit doesn't expose <head> directly,
# so we inject these tags via markdown. They get picked up by most crawlers.
st.markdown(
    """
    <meta property="og:title" content="European Power Market Volatility | Impulse" />
    <meta property="og:description" content="Intraday electricity price spreads across European day-ahead markets — a proxy for battery storage and trading revenue opportunity." />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="description" content="Intraday power market volatility dashboard for European countries. Built by Impulse." />
    """,
    unsafe_allow_html=True,
)

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


# BESS battery durations we pre-compute spread capture for. Confirmed by user: 1, 2, 3, 4 hours.
BESS_DURATIONS = [1, 2, 3, 4]


def _nhour_spread(hourly_prices: list, n: int) -> float:
    """Per-MWh spread captured by an N-hour battery on a day with these hourly prices.

    Charge during the cheapest N hours, discharge during the most expensive N hours.
    Returns mean(top N) - mean(bottom N) in €/MWh. If fewer than 2N hours are
    available (incomplete day), returns NaN — caller should drop those days.
    """
    if len(hourly_prices) < 2 * n:
        return float("nan")
    sorted_prices = sorted(hourly_prices)
    bottom_n_mean = sum(sorted_prices[:n]) / n
    top_n_mean = sum(sorted_prices[-n:]) / n
    return top_n_mean - bottom_n_mean


@st.cache_data(show_spinner="Loading and aggregating price data…")
def load_and_aggregate(source) -> tuple[pd.DataFrame, dict]:
    """Stream the hourly CSV in chunks and aggregate to daily metrics.

    For each (country, date) we accumulate the list of hourly prices, then at
    the end compute:
      - Peak, Trough, Mean, Swing (daily max, min, mean, max-min)
      - N-hour spread capture for each duration in BESS_DURATIONS

    The hourly lists are bounded — at most 24 floats per (country, date),
    so total memory stays well under the chunk size itself.

    Returns (daily_df, metadata_dict).
    """
    CHUNK_SIZE = 200_000

    # Per-(country, iso, date) list of hourly prices. Bounded at 24 entries each.
    prices_by_day: dict = {}

    total_rows = 0
    countries_seen: set = set()
    header_checked = False

    reader = pd.read_csv(
        source,
        chunksize=CHUNK_SIZE,
        usecols=list(EXPECTED_COLUMNS),
    )

    for chunk in reader:
        if not header_checked:
            missing = EXPECTED_COLUMNS - set(chunk.columns)
            if missing:
                raise ValueError(
                    f"Missing expected columns: {missing}. Found: {list(chunk.columns)}"
                )
            header_checked = True

        chunk["Datetime"] = pd.to_datetime(chunk["Datetime (Local)"], errors="coerce")
        chunk["Price"] = pd.to_numeric(chunk["Price (EUR/MWhe)"], errors="coerce")
        chunk = chunk.dropna(subset=["Datetime", "Price"])
        if chunk.empty:
            continue

        chunk["Date"] = chunk["Datetime"].dt.date
        countries_seen.update(chunk["Country"].unique())
        total_rows += len(chunk)

        # Iterate with itertuples for speed — much faster than iterrows
        # and avoids the chunk-level groupby overhead.
        for row in chunk[["Country", "ISO3 Code", "Date", "Price"]].itertuples(
            index=False, name=None
        ):
            country, iso, date, price = row
            key = (country, iso, date)
            lst = prices_by_day.get(key)
            if lst is None:
                prices_by_day[key] = [price]
            else:
                lst.append(price)

        del chunk

    if not prices_by_day:
        raise ValueError("No usable rows found in the data.")

    # Build the final DataFrame. For each day with enough coverage, compute
    # daily aggregates + the N-hour spreads for each BESS duration.
    keys, peaks, troughs, means, hours_list, swings_list = [], [], [], [], [], []
    spread_cols: dict[int, list] = {n: [] for n in BESS_DURATIONS}

    for key, prices in prices_by_day.items():
        n_hours = len(prices)
        if n_hours < 20:
            continue  # drop days with poor coverage
        keys.append(key)
        peaks.append(max(prices))
        troughs.append(min(prices))
        means.append(sum(prices) / n_hours)
        hours_list.append(n_hours)
        swings_list.append(peaks[-1] - troughs[-1])
        for n in BESS_DURATIONS:
            spread_cols[n].append(_nhour_spread(prices, n))

    if not keys:
        raise ValueError("No days with sufficient hourly coverage (≥20 of 24 hours).")

    daily = pd.DataFrame(
        {
            "Country": [k[0] for k in keys],
            "ISO3 Code": [k[1] for k in keys],
            "Date": pd.to_datetime([k[2] for k in keys]),
            "Peak": peaks,
            "Trough": troughs,
            "Mean": means,
            "Hours": hours_list,
            "Swing": swings_list,
        }
    )
    for n in BESS_DURATIONS:
        daily[f"Spread_{n}h"] = spread_cols[n]

    metadata = {
        "total_rows": total_rows,
        "countries": len(countries_seen),
    }
    return daily, metadata


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
        st.title("European Power Market Volatility")
else:
    st.title("European Power Market Volatility")
st.caption(
    "Intraday price spreads across European day-ahead electricity markets — "
    "a proxy for battery storage and trading revenue opportunity."
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

# Default selection — only include names that actually appear in the dataset,
# so this stays robust if Ember changes the country list.
PREFERRED_DEFAULTS = [
    "Netherlands",
    "Germany",
    "Poland",
    "Estonia",
    "Latvia",
    "Lithuania",
]
default_countries = [c for c in PREFERRED_DEFAULTS if c in countries_all]

# Fallback if none of the preferred ones are present: pick the top-swing countries
window_mask = (swings["Date"] >= start_ts) & (swings["Date"] <= end_ts)
if not default_countries:
    default_countries = (
        swings[window_mask]
        .groupby("Country")["Swing"]
        .mean()
        .sort_values(ascending=False)
        .head(6)
        .index.tolist()
    )

selected_countries = st.sidebar.multiselect(
    "Countries",
    options=countries_all,
    default=default_countries if default_countries else countries_all[:6],
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
avg_swing = filtered["Swing"].mean()
max_swing_val = filtered["Swing"].max()
max_swing_row = filtered.loc[filtered["Swing"].idxmax()]

# Hero summary — dynamic, narrative, sets the framing for what follows
country_list = sorted(filtered["Country"].unique().tolist())
if len(country_list) == 1:
    country_phrase = country_list[0]
elif len(country_list) == 2:
    country_phrase = f"{country_list[0]} and {country_list[1]}"
elif len(country_list) <= 5:
    country_phrase = ", ".join(country_list[:-1]) + f", and {country_list[-1]}"
else:
    country_phrase = f"{len(country_list)} selected markets"

window_label = f"{start_ts.strftime('%b %Y')} to {end_ts.strftime('%b %Y')}"
median_swing = filtered["Swing"].median()
p95_swing = filtered["Swing"].quantile(0.95)

# Headline 2-hour BESS revenue across the selected markets (gross)
hero_spread_2h = filtered["Spread_2h"].dropna().mean() if "Spread_2h" in filtered.columns else None
hero_annual_2h = hero_spread_2h * 2 * 365 if hero_spread_2h is not None else None

bess_sentence = (
    f"A 2-hour battery operating across these markets would have captured roughly "
    f"<strong style='color: {COLOR_ACCENT};'>€{hero_annual_2h:,.0f}/MW/year</strong> "
    f"in gross arbitrage revenue."
    if hero_annual_2h is not None
    else "See the BESS revenue tab for arbitrage opportunity estimates."
)

st.markdown(
    f"""
    <div style="
        background: linear-gradient(135deg, rgba(0, 196, 144, 0.08) 0%, rgba(0, 196, 144, 0.02) 100%);
        border-left: 3px solid {COLOR_ACCENT};
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin: 0.5rem 0 1.25rem 0;
        font-size: 1.02rem;
        line-height: 1.55;
        color: {COLOR_TEXT};
    ">
        Across <strong>{country_phrase}</strong> ({window_label}), day-ahead power prices
        swung by a median of <strong style="color: {COLOR_ACCENT};">€{median_swing:,.0f} /MWh</strong>
        between the daily peak and trough hour. The top 5% of days saw spreads above
        <strong style="color: {COLOR_ACCENT};">€{p95_swing:,.0f} /MWh</strong>.
        {bess_sentence}
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Countries selected",
    f"{filtered['Country'].nunique()}",
    help="Number of countries currently included in the view.",
)
col2.metric(
    "Days analysed",
    f"{filtered['Date'].nunique():,}",
    help="Total trading days observed across the selected countries and date range.",
)
col3.metric(
    "Average daily swing",
    f"€{avg_swing:,.0f} /MWh",
    help=(
        "Average gap between the most expensive and cheapest hour of each day "
        "(€ per megawatt-hour). Divide by 1000 to get € per kWh — the unit on "
        "most household bills."
    ),
)
col4.metric(
    "Largest single day",
    f"€{max_swing_val:,.0f} /MWh",
    help=(
        f"Biggest one-day swing in the selection: {max_swing_row['Country']} on "
        f"{max_swing_row['Date'].strftime('%d %b %Y')}, when prices ranged from "
        f"€{max_swing_row['Trough']:,.0f} to €{max_swing_row['Peak']:,.0f} /MWh."
    ),
)

st.divider()


# ---------------------------------------------------------------------------
# Tabs for the four views
# ---------------------------------------------------------------------------
tab_ts, tab_heat, tab_rank, tab_bess, tab_data = st.tabs(
    ["📈 Volatility trend", "🗓️ Calendar heatmap", "🏆 Market ranking", "💰 BESS revenue", "📋 Data"]
)


# --- Time series ------------------------------------------------------------
with tab_ts:
    st.subheader("How is volatility evolving across markets?")

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

    # Auto-generated insight — which country trended the most, up or down?
    if len(country_list) >= 2 and len(ts) > 60:
        # Compare first 30-day mean to last 30-day mean per country
        recency = ts.copy()
        latest_date = recency["Date"].max()
        first_30_cutoff = recency["Date"].min() + pd.Timedelta(days=30)
        last_30_cutoff = latest_date - pd.Timedelta(days=30)
        first_period = recency[recency["Date"] <= first_30_cutoff].groupby("Country")["Swing"].mean()
        last_period = recency[recency["Date"] >= last_30_cutoff].groupby("Country")["Swing"].mean()
        common = first_period.index.intersection(last_period.index)
        if len(common) >= 2:
            change_pct = ((last_period[common] - first_period[common]) / first_period[common] * 100).dropna()
            if not change_pct.empty:
                top_riser = change_pct.idxmax()
                top_change = change_pct[top_riser]
                if abs(top_change) >= 5:
                    direction = "increased" if top_change > 0 else "decreased"
                    st.info(
                        f"📊 **Key trend:** {top_riser}'s daily volatility has {direction} "
                        f"by **{abs(top_change):.0f}%** comparing the start versus end of the "
                        f"selected window — the largest shift among the selected markets."
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

    # Annotate major macro events if they fall inside the visible window
    MACRO_EVENTS = [
        (pd.Timestamp("2022-02-24"), "Russian invasion<br>of Ukraine"),
        (pd.Timestamp("2022-08-26"), "TTF gas peak"),
        (pd.Timestamp("2022-12-12"), "Winter cold snap"),
        (pd.Timestamp("2023-07-01"), "Summer solar<br>oversupply"),
    ]
    ymax_for_ann = ts["Smoothed"].max() * 1.05 if not ts.empty else 100
    for event_date, label in MACRO_EVENTS:
        if start_ts <= event_date <= end_ts:
            fig_ts.add_vline(
                x=event_date,
                line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"),
            )
            fig_ts.add_annotation(
                x=event_date,
                y=ymax_for_ann,
                yref="y",
                text=label,
                showarrow=False,
                font=dict(color="rgba(255,255,255,0.55)", size=10),
                align="center",
                bgcolor="rgba(31, 39, 57, 0.7)",
                borderpad=4,
            )

    apply_dark_theme(fig_ts, height=500)
    st.plotly_chart(fig_ts, width="stretch")

    with st.expander("ℹ️ How to read this"):
        st.markdown(
            "Each line tracks one country's daily peak-to-trough spread over time, "
            "smoothed by a rolling average. **Upward trends** typically reflect rising "
            "renewable penetration (cheap midday solar, expensive evening peak) or "
            "tightening capacity margins. **Spikes** mark stress events — cold snaps, "
            "low-wind periods, fuel supply shocks. For a trading or BESS operator, the "
            "trajectory matters as much as the level: a market where spreads are "
            "*growing* offers compounding revenue upside over an asset's lifetime."
        )


# --- Calendar heatmap -------------------------------------------------------
with tab_heat:
    st.subheader("When does volatility happen?")

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
                colorbar=dict(
                    title=dict(text="€/MWh", side="top", font=dict(color=COLOR_TEXT, size=12)),
                    tickfont=dict(color=COLOR_TEXT, size=11),
                    thickness=14,
                    len=0.9,
                    x=1.02,           # position just outside the plot area
                    xanchor="left",   # anchor by its left edge so width grows rightward
                    xpad=4,
                    tickformat=",.0f",
                ),
                hovertemplate="Week %{x}<br>%{y}<br>Swing: €%{z:.0f} /MWh<extra></extra>",
            )
        )
        fig_heat.update_layout(
            xaxis=dict(title="", tickangle=-45, nticks=20),
            yaxis=dict(title="", autorange="reversed"),
        )
        apply_dark_theme(fig_heat, height=320)
        # Override the right margin so the colorbar isn't clipped
        fig_heat.update_layout(margin=dict(l=10, r=110, t=30, b=10))
        st.plotly_chart(fig_heat, width="stretch")

        sub_avg = sub["Swing"].mean()
        sub_max_row = sub.loc[sub["Swing"].idxmax()]
        c1, c2, c3 = st.columns(3)
        c1.metric(
            f"{heat_country} avg swing",
            f"€{sub_avg:,.0f} /MWh",
            help="Mean daily peak-to-trough spread for this country in the selected window.",
        )
        c2.metric(
            "Biggest one-day swing",
            f"€{sub_max_row['Swing']:,.0f} /MWh",
            help=(
                f"Prices ranged from €{sub_max_row['Trough']:,.0f} (cheapest hour) "
                f"to €{sub_max_row['Peak']:,.0f} (most expensive hour) on this date."
            ),
        )
        c3.metric(
            "On",
            sub_max_row["Date"].strftime("%d %b %Y"),
            help="Date of the largest single-day swing for this country.",
        )


# --- Country ranking --------------------------------------------------------
with tab_rank:
    st.subheader("Where is the opportunity biggest?")
    st.caption(
        "Ranking markets by the size of their intraday spreads. For battery storage and "
        "intraday trading, bigger and more consistent spreads mean more revenue per MW."
    )

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
        text=ranking[label].round(0),
        color=label,
        color_continuous_scale=ACCENT_SCALE,
    )
    fig_rank.update_layout(
        coloraxis_showscale=False,
        xaxis_title=f"{label} (€/MWh)",
        yaxis_title="",
    )
    apply_dark_theme(fig_rank, height=max(350, 28 * len(ranking) + 60))
    fig_rank.update_traces(
        texttemplate="€%{text:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>" + label + ": €%{x:,.0f} /MWh<extra></extra>",
    )
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


# --- BESS revenue calculator ------------------------------------------------
with tab_bess:
    st.subheader("How much could a battery have earned?")
    st.caption(
        "Modelled as gross arbitrage revenue: charge during the cheapest N hours of "
        "each day, discharge during the most expensive N. Numbers are **gross** — no "
        "round-trip efficiency losses, degradation, fees, or imbalance costs deducted. "
        "Useful as a market-attractiveness ranking, not as an investment forecast."
    )

    # Duration selector
    duration = st.radio(
        "Battery duration",
        options=BESS_DURATIONS,
        index=1,  # default to 2h — the most common utility-scale spec
        horizontal=True,
        format_func=lambda h: f"{h}-hour",
        help=(
            "Hours of energy storage at rated power. A 2-hour, 10 MW battery can "
            "discharge 10 MW for 2 hours (20 MWh delivered per full cycle)."
        ),
    )
    spread_col = f"Spread_{duration}h"

    # Verify we have the column (sanity guard against future schema drift)
    if spread_col not in filtered.columns:
        st.error(
            f"BESS spread column `{spread_col}` not found in the data. "
            "This usually means BESS_DURATIONS changed in load_and_aggregate."
        )
        st.stop()

    # Per-day daily revenue per MW (gross): spread × duration MWh × 1 cycle/day
    # Then aggregate to annual €/MW/year by averaging daily revenue × 365
    bess_data = filtered[["Country", "ISO3 Code", "Date", spread_col]].copy()
    bess_data = bess_data.dropna(subset=[spread_col])
    bess_data["Daily_Revenue_per_MW"] = bess_data[spread_col] * duration  # €/MW/day

    # Annualised by country — mean daily × 365 to extrapolate to a full year
    annual_per_country = (
        bess_data.groupby("Country")["Daily_Revenue_per_MW"]
        .mean()
        .mul(365)
        .reset_index()
        .rename(columns={"Daily_Revenue_per_MW": "Annual_per_MW"})
        .sort_values("Annual_per_MW", ascending=False)
    )

    # Headline metrics
    overall_avg_spread = bess_data[spread_col].mean()
    overall_annual = overall_avg_spread * duration * 365
    best_country = annual_per_country.iloc[0]
    worst_country = annual_per_country.iloc[-1]

    m1, m2, m3 = st.columns(3)
    m1.metric(
        f"Avg gross revenue ({duration}h BESS)",
        f"€{overall_annual:,.0f} /MW/year",
        help=(
            f"Across all selected markets, a {duration}-hour battery would have captured "
            f"€{overall_avg_spread:,.1f}/MWh per cycle on average. Multiplied by "
            f"{duration} MWh per cycle and 365 cycles/year."
        ),
    )
    m2.metric(
        "Best market",
        f"{best_country['Country']}",
        delta=f"€{best_country['Annual_per_MW']:,.0f} /MW/yr",
        delta_color="off",
        help="Country with the highest gross revenue per MW in the selected window.",
    )
    m3.metric(
        "Worst market",
        f"{worst_country['Country']}",
        delta=f"€{worst_country['Annual_per_MW']:,.0f} /MW/yr",
        delta_color="off",
        help="Country with the lowest gross revenue per MW in the selected window.",
    )

    # Ranking bar chart: annual €/MW/year by country
    st.markdown("##### Annual gross revenue by market")
    ranking_for_plot = annual_per_country.sort_values("Annual_per_MW", ascending=True)
    fig_bess = px.bar(
        ranking_for_plot,
        x="Annual_per_MW",
        y="Country",
        orientation="h",
        text=ranking_for_plot["Annual_per_MW"].round(0),
        color="Annual_per_MW",
        color_continuous_scale=ACCENT_SCALE,
    )
    fig_bess.update_traces(
        texttemplate="€%{text:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "%{y}<br>Gross revenue: €%{x:,.0f} /MW/year"
            f"<br>({duration}-hour battery, 365 cycles, no losses)<extra></extra>"
        ),
    )
    fig_bess.update_layout(
        coloraxis_showscale=False,
        xaxis_title=f"€/MW/year (gross, {duration}-hour battery, 365 cycles)",
        yaxis_title="",
    )
    apply_dark_theme(fig_bess, height=max(350, 28 * len(ranking_for_plot) + 60))
    st.plotly_chart(fig_bess, width="stretch")

    # Monthly revenue trend — useful for seeing when in the year revenue is concentrated
    st.markdown("##### Monthly revenue trend")
    monthly = bess_data.copy()
    monthly["Month"] = monthly["Date"].dt.to_period("M").dt.to_timestamp()
    monthly_revenue = (
        monthly.groupby(["Country", "Month"])["Daily_Revenue_per_MW"]
        .sum()  # sum of daily revenues across the month = actual monthly capture
        .reset_index()
        .rename(columns={"Daily_Revenue_per_MW": "Monthly_Revenue_per_MW"})
    )

    fig_monthly = px.line(
        monthly_revenue,
        x="Month",
        y="Monthly_Revenue_per_MW",
        color="Country",
        labels={"Monthly_Revenue_per_MW": "€/MW/month", "Month": ""},
        color_discrete_sequence=ACCENT_SEQUENCE,
        markers=True,
    )
    fig_monthly.update_traces(
        hovertemplate="%{x|%b %Y}<br>%{y:,.0f} €/MW<extra></extra>",
    )
    fig_monthly.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    apply_dark_theme(fig_monthly, height=420)
    st.plotly_chart(fig_monthly, width="stretch")

    with st.expander("📐 Methodology and limits"):
        st.markdown(
            f"""
            **What this calculates:** For each day and country, we take the actual 24 hourly
            day-ahead prices, sort them, and assume a perfect-foresight battery charges during
            the cheapest **{duration}** hours and discharges during the most expensive **{duration}** hours.
            The spread captured per MWh discharged is multiplied by **{duration} MWh per cycle** and
            **365 cycles per year** to produce annual gross revenue per MW of installed power.

            **What's deliberately excluded:**
            - **Round-trip efficiency losses** (real lithium-ion BESS: ~85–90%)
            - **Degradation and capex** — this is a top-line revenue figure, not a return
            - **Imbalance, grid fees, taxes, balancing market participation**
            - **Auction clearing & price-taker dynamics** — assumes you can transact at the
              clearing price without moving it
            - **Forecasting error** — assumes perfect foresight of when the daily peak/trough will be

            **Why this is still a useful market-selection signal:** All the excluded factors apply
            *similarly* across markets. A market with 2× the gross arbitrage opportunity will,
            after losses, still have roughly 2× the net opportunity. The ranking is more
            defensible than the absolute number — point this at your client as a relative
            attractiveness map, not as a P&L forecast.
            """
        )


# --- Data table -------------------------------------------------------------
with tab_data:
    st.subheader("Daily aggregates · downloadable")
    st.caption("Filtered to your sidebar selection. Click columns to sort.")

    base_cols = ["Country", "ISO3 Code", "Date", "Trough", "Peak", "Swing", "Mean"]
    bess_cols = [f"Spread_{n}h" for n in BESS_DURATIONS if f"Spread_{n}h" in filtered.columns]
    display = filtered[base_cols + bess_cols].copy()
    display = display.sort_values(["Date", "Country"], ascending=[False, True])
    display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
    for col in ["Trough", "Peak", "Swing", "Mean"] + bess_cols:
        display[col] = display[col].round(2)

    st.dataframe(display, width="stretch", height=500, hide_index=True)

    csv_buf = io.StringIO()
    display.to_csv(csv_buf, index=False)
    st.download_button(
        "⬇️ Download as CSV",
        data=csv_buf.getvalue(),
        file_name="impulse_european_power_volatility.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()

# Impulse branding block
st.markdown(
    f"""
    <div style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 1rem;
        padding: 0.75rem 0 0.25rem 0;
        margin-bottom: 0.5rem;
    ">
        <div style="color: {COLOR_TEXT}; font-size: 0.95rem;">
            Built by <strong style="color: {COLOR_ACCENT};">Impulse</strong> —
            <span style="color: {COLOR_MUTED};">market intelligence for the energy transition</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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