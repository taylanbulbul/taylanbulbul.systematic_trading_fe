import os
import json
import time
import traceback
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Systematic Trading Demo",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# Helpers
# =========================================================
def fmt_money(value):
    if value is None:
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def fmt_money_0(value):
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except Exception:
        return str(value)


def fmt_pct(value):
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return str(value)


def fmt_num(value, digits=2):
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except Exception:
        return str(value)


def metric_class(value, positive_good=True):
    if value is None:
        return "neutral"
    try:
        v = float(value)
    except Exception:
        return "neutral"

    if positive_good:
        if v > 0:
            return "good"
        if v < 0:
            return "bad"
        return "neutral"
    else:
        if v < 0:
            return "bad"
        if v > 0:
            return "good"
        return "neutral"


def safe_get(summary, key, default=None):
    return summary.get(key, default) if isinstance(summary, dict) else default


def prettify_action(action: str) -> str:
    if not action:
        return "—"
    action = str(action).replace("_", " ").strip().title()
    replacements = {
        "Pnl": "PnL",
    }
    for old, new in replacements.items():
        action = action.replace(old, new)
    return action


def get_backtest_end_date(summary: dict):
    for key in ["end_date", "last_date", "latest_date", "backtest_end_date"]:
        if summary.get(key):
            try:
                return pd.to_datetime(summary[key]).strftime("%Y-%m-%d")
            except Exception:
                pass

    equity_curve = summary.get("equity_curve", [])
    if equity_curve:
        try:
            eq = pd.DataFrame(equity_curve)
            if "date" in eq.columns and not eq.empty:
                return pd.to_datetime(eq["date"]).max().strftime("%Y-%m-%d")
        except Exception:
            pass

    return None


def build_grouped_summary(summary: dict):
    return {
        "Capital": {
            "Initial": fmt_money(summary.get("initial_capital")),
            "Final": fmt_money(summary.get("final_capital")),
            "Total Return": fmt_pct(summary.get("total_return_pct")),
            "Annualised": fmt_pct(summary.get("annualised_return_pct")),
        },
        "Trade Statistics": {
            "Total Trades": fmt_num(summary.get("total_trades"), 0),
            "Winning Trades": fmt_num(summary.get("winning_trades"), 0),
            "Losing Trades": fmt_num(summary.get("losing_trades"), 0),
            "Win Rate": fmt_pct(summary.get("win_rate_pct")),
            "Loss Rate": fmt_pct(summary.get("loss_rate_pct")),
            "Avg Win PnL": fmt_money(summary.get("avg_win_pnl")),
            "Avg Loss PnL": fmt_money(summary.get("avg_loss_pnl")),
            "Implied Costs": fmt_money(summary.get("implied_costs")),
        },
        "Risk Metrics": {
            "Sharpe Ratio": fmt_num(summary.get("sharpe_ratio")),
            "Max Drawdown": fmt_pct(summary.get("max_drawdown_pct")),
            "Profit Factor": fmt_num(summary.get("profit_factor")),
        },
        "Buy & Hold Benchmark": {
            "Buy & Hold Return": fmt_pct(summary.get("bnh_return_pct")),
        },
    }


def render_grouped_summary_html(summary: dict) -> str:
    grouped = build_grouped_summary(summary)
    html = '<div class="summary-shell">'

    for section, items in grouped.items():
        visible_items = {k: v for k, v in items.items() if v != "—"}
        if not visible_items:
            continue

        html += f"""
        <div class="summary-section">
            <div class="summary-section-title">{section}</div>
        """

        for label, value in visible_items.items():
            html += f"""
            <div class="summary-row">
                <div class="summary-label">{label}</div>
                <div class="summary-value">{value}</div>
            </div>
            """

        html += "</div>"

    html += "</div>"
    return html


# =========================================================
# Styling
# =========================================================
st.markdown(
    """
    <style>
    :root {
        --bg: #060b1a;
        --panel: #0d1630;
        --panel-2: #101c3d;
        --border: rgba(80, 140, 255, 0.22);
        --border-strong: rgba(64, 140, 255, 0.55);
        --text: #eef4ff;
        --muted: #94a7c6;
        --blue: #59a7ff;
        --green: #31d67b;
        --yellow: #ffbf47;
        --red: #ff5d6c;
        --glow: 0 0 0 1px rgba(83, 140, 255, 0.22), 0 10px 30px rgba(0, 0, 0, 0.28);
        --radius: 18px;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(48, 88, 255, 0.18), transparent 22%),
            radial-gradient(circle at top right, rgba(0, 194, 255, 0.10), transparent 18%),
            linear-gradient(180deg, #030816 0%, #081022 100%);
        color: var(--text);
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1440px;
    }

    h1, h2, h3, h4, h5, h6, p, label, div, span {
        color: var(--text);
    }

    .hero-wrap {
        margin-bottom: 1rem;
        margin-top: 0;
    }

    .hero-kicker {
        font-size: 0.78rem;
        letter-spacing: 0.20em;
        text-transform: uppercase;
        color: #7ea6ff;
        margin-bottom: 0.4rem;
        font-weight: 700;
    }

    .hero-title {
        font-size: 2.35rem;
        line-height: 1.05;
        font-weight: 800;
        margin-bottom: 0.35rem;
    }

    .hero-sub {
        color: var(--muted);
        font-size: 1rem;
        margin-bottom: 0.35rem;
    }

    .top-spacer-fix {
        height: 0.35rem;
    }

    .panel {
        background: linear-gradient(180deg, rgba(13,22,48,0.96), rgba(9,17,38,0.96));
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1rem 1rem 1.1rem 1rem;
        box-shadow: var(--glow);
    }

    .panel-tight {
        padding-top: 0.9rem;
    }

    .panel-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        color: #8caef9;
        margin-bottom: 0.9rem;
        font-weight: 800;
    }

    .metric-card {
        background: linear-gradient(180deg, rgba(15,25,54,0.98), rgba(11,19,42,0.98));
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1rem;
        min-height: 124px;
        box-shadow: var(--glow);
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.05;
        margin-bottom: 0.2rem;
    }

    .metric-sub {
        color: var(--muted);
        font-size: 0.85rem;
    }

    .good { color: var(--green); }
    .bad { color: var(--red); }
    .neutral { color: var(--blue); }

    .signal-card {
        background: linear-gradient(180deg, rgba(6,56,24,0.96), rgba(6,42,20,0.96));
        border: 1px solid rgba(49,214,123,0.35);
        border-radius: 18px;
        padding: 1.1rem;
        box-shadow:
            0 0 0 1px rgba(49,214,123,0.16),
            0 12px 28px rgba(0, 0, 0, 0.30);
        margin-top: 1rem;
    }

    .signal-kicker {
        color: #87f7b6;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.78rem;
        font-weight: 800;
        margin-bottom: 0.8rem;
    }

    .signal-main {
        font-size: 2.8rem;
        font-weight: 900;
        color: #4df08e;
        line-height: 1;
        margin-bottom: 0.35rem;
    }

    .signal-caption {
        color: #b7f8d0;
        font-size: 0.95rem;
    }

    .mini-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.8rem;
        margin-top: 1rem;
    }

    .mini-box {
        background: rgba(0, 0, 0, 0.18);
        border: 1px solid rgba(100,255,175,0.12);
        border-radius: 14px;
        padding: 0.9rem;
    }

    .mini-label {
        color: #a3eec0;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 0.35rem;
        font-weight: 700;
    }

    .mini-value {
        color: white;
        font-size: 1.35rem;
        font-weight: 800;
        line-height: 1.1;
    }

    .mini-sub {
        color: #b7f8d0;
        opacity: 0.9;
        font-size: 0.82rem;
        margin-top: 0.22rem;
    }

    .summary-shell {
        display: flex;
        flex-direction: column;
        gap: 0.9rem;
    }

    .summary-section {
        border: 1px solid rgba(120, 150, 255, 0.18);
        border-radius: 14px;
        overflow: hidden;
        background: rgba(10, 18, 36, 0.72);
    }

    .summary-section-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-weight: 800;
        color: #dfe9ff;
        padding: 0.8rem 0.9rem;
        border-bottom: 1px solid rgba(120, 150, 255, 0.18);
        background: rgba(255,255,255,0.03);
    }

    .summary-row {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.72rem 0.9rem;
        border-bottom: 1px solid rgba(120, 150, 255, 0.10);
    }

    .summary-row:last-child {
        border-bottom: none;
    }

    .summary-label {
        color: #d5e1fb;
        font-size: 0.92rem;
    }

    .summary-value {
        color: white;
        font-weight: 700;
        text-align: right;
        white-space: nowrap;
    }

    .footer-banner {
        margin-top: 1rem;
        background: linear-gradient(90deg, rgba(7,85,37,0.95), rgba(10,120,48,0.95));
        border: 1px solid rgba(94,255,154,0.25);
        border-radius: 16px;
        padding: 0.9rem 1rem;
        color: #d7ffe6;
        font-weight: 800;
        font-size: 1rem;
        box-shadow: 0 8px 22px rgba(0,0,0,0.24);
    }

    div[data-testid="stForm"] {
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }

    .stDateInput,
    .stNumberInput {
        margin-top: 0 !important;
    }

    .stDateInput > div,
    .stNumberInput > div {
        margin-top: 0 !important;
    }

    div[data-baseweb="input"],
    div[data-baseweb="select"] > div,
    .stDateInput > div > div {
        background: rgba(9, 18, 38, 0.96) !important;
        border-radius: 14px !important;
        border: 1px solid rgba(85, 142, 255, 0.28) !important;
    }

    .stNumberInput input,
    .stDateInput input {
        color: white !important;
        font-weight: 600;
    }

    div.stButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        width: 100%;
        border-radius: 14px;
        border: 1px solid rgba(67, 229, 126, 0.25);
        background: linear-gradient(180deg, #28d866 0%, #1ebb58 100%);
        color: white;
        font-size: 1.02rem;
        font-weight: 800;
        padding: 0.75rem 1rem;
        box-shadow: 0 8px 20px rgba(20, 140, 65, 0.28);
    }

    div[data-testid="stMetric"] {
        background: transparent;
    }

    .stDataFrame {
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid rgba(88, 130, 255, 0.18);
    }

    [data-testid="stSidebar"] {
        background: #081022;
    }

    .small-note {
        color: var(--muted);
        font-size: 0.82rem;
        margin-top: 0.8rem;
    }

    .placeholder-card {
        min-height: 520px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .placeholder-inner {
        text-align: center;
        max-width: 620px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# API config
# =========================================================
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets["cloud_api_uri"]

BASE_URI = BASE_URI if BASE_URI.endswith("/") else BASE_URI + "/"
url = BASE_URI + "backtest"

# =========================================================
# Header
# =========================================================
st.markdown(
    """
    <div class="hero-wrap">
        <div class="hero-kicker">Live Demo</div>
        <div class="hero-title">Point-in-Time Backtest Dashboard</div>
        <div class="hero-sub">
            Run a historical cutoff, evaluate your model’s output, and visualize the strategy
            performance in a cleaner trading-dashboard layout.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# Sidebar
# =========================================================
with st.sidebar:
    st.markdown("### Debug")
    show_debug = st.checkbox("Show debug logs", value=False)
    if show_debug:
        st.caption(f"API endpoint: `{url}`")

# =========================================================
# Layout
# =========================================================
left_col, right_col = st.columns([1.0, 1.9], gap="large")

with left_col:
    st.markdown('<div class="top-spacer-fix"></div>', unsafe_allow_html=True)
    st.markdown('<div class="panel panel-tight">', unsafe_allow_html=True)
    st.markdown('<div class="panel-title">Inputs</div>', unsafe_allow_html=True)

    with st.form("backtest_form"):
        cutoff_date = st.date_input(
            "Date",
            value=pd.to_datetime("2025-01-01"),
            help="Historical date used as the backtest cutoff.",
        )

        initial_capital = st.number_input(
            "Investment (USD)",
            min_value=100.0,
            value=1000.0,
            step=100.0,
        )

        submitted = st.form_submit_button("▶ Run Backtest")

    st.markdown(
        """
        <div class="small-note">
            Uses the current API response fields only — the layout is styled like a product demo,
            while the model remains work in progress.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# Main request + results
# =========================================================
if submitted:
    params = {
        "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
        "initial_capital": float(initial_capital),
    }

    status = st.status("Running backtest...", expanded=show_debug)

    try:
        t0 = time.time()
        session = requests.Session()

        if show_debug:
            status.write(f"Sending GET to `{url}`")
            status.write(f"Params: `{params}`")
            status.write("Waiting for API response...")

        response = session.get(
            url,
            params=params,
            timeout=(10, 120),
            stream=True,
        )

        elapsed_connect = time.time() - t0
        if show_debug:
            status.write(f"Connected in {elapsed_connect:.1f}s — status {response.status_code}")
            with status.expander("Response headers"):
                st.write(dict(response.headers))

        response.raise_for_status()

        raw_body = response.content
        summary = json.loads(raw_body)

        if show_debug:
            status.write(f"Body received in {time.time() - t0:.1f}s ({len(raw_body)} bytes)")
            with status.expander("Raw JSON response"):
                st.json(summary)

        status.update(label="Backtest complete", state="complete", expanded=False)

        final_capital = safe_get(summary, "final_capital")
        total_return_pct = safe_get(summary, "total_return_pct")
        win_rate_pct = safe_get(summary, "win_rate_pct")
        max_drawdown_pct = safe_get(summary, "max_drawdown_pct")
        initial_capital_resp = safe_get(summary, "initial_capital", initial_capital)
        bnh_return_pct = safe_get(summary, "bnh_return_pct")
        total_trades = safe_get(summary, "total_trades")
        sharpe_ratio = safe_get(summary, "sharpe_ratio")
        profit_factor = safe_get(summary, "profit_factor")
        end_date = get_backtest_end_date(summary)

        # -----------------------------
        # LEFT COLUMN RESULT SNAPSHOT
        # -----------------------------
        with left_col:
            st.markdown(
                f"""
                <div class="signal-card">
                    <div class="signal-kicker">Backtest Snapshot</div>
                    <div class="signal-main">{fmt_pct(total_return_pct)}</div>
                    <div class="signal-caption">Net strategy return from the selected cutoff date</div>

                    <div class="mini-grid">
                        <div class="mini-box">
                            <div class="mini-label">Capital</div>
                            <div class="mini-value">{fmt_money_0(final_capital)}</div>
                            <div class="mini-sub">Final portfolio value</div>
                        </div>
                        <div class="mini-box">
                            <div class="mini-label">Trades</div>
                            <div class="mini-value">{fmt_num(total_trades, 0)}</div>
                            <div class="mini-sub">Executed by strategy</div>
                        </div>
                        <div class="mini-box">
                            <div class="mini-label">Sharpe</div>
                            <div class="mini-value">{fmt_num(sharpe_ratio)}</div>
                            <div class="mini-sub">Risk-adjusted return</div>
                        </div>
                        <div class="mini-box">
                            <div class="mini-label">Profit Factor</div>
                            <div class="mini-value">{fmt_num(profit_factor)}</div>
                            <div class="mini-sub">Gross win / gross loss</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # -----------------------------
        # RIGHT COLUMN MAIN RESULTS
        # -----------------------------
        with right_col:
            header_end = end_date if end_date else "—"
            st.markdown(
                f"""
                <div class="hero-kicker">Strategy Backtest — Execution Results</div>
                <div class="hero-sub" style="font-size:1.15rem; font-weight:800; color:#7fb5ff;">
                    {cutoff_date.strftime("%Y-%m-%d")} → {header_end}
                </div>
                """,
                unsafe_allow_html=True,
            )

            m1, m2, m3, m4 = st.columns(4, gap="small")

            with m1:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Final Capital</div>
                        <div class="metric-value neutral">{fmt_money_0(final_capital)}</div>
                        <div class="metric-sub">Starting from {fmt_money_0(initial_capital_resp)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with m2:
                cls = metric_class(total_return_pct, positive_good=True)
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Total Return</div>
                        <div class="metric-value {cls}">{fmt_pct(total_return_pct)}</div>
                        <div class="metric-sub">Strategy return over the test window</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with m3:
                cls = metric_class(win_rate_pct, positive_good=True)
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Win Rate</div>
                        <div class="metric-value {cls}">{fmt_pct(win_rate_pct)}</div>
                        <div class="metric-sub">Share of winning trades</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with m4:
                cls = metric_class(max_drawdown_pct, positive_good=False)
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">Max Drawdown</div>
                        <div class="metric-value {cls}">{fmt_pct(max_drawdown_pct)}</div>
                        <div class="metric-sub">Worst peak-to-trough decline</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            chart_col, side_col = st.columns([1.55, 1.0], gap="small")

            equity_curve = safe_get(summary, "equity_curve", [])
            action_breakdown = safe_get(summary, "action_breakdown", {})

            with chart_col:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                st.markdown('<div class="panel-title">Equity Curve</div>', unsafe_allow_html=True)

                if equity_curve:
                    equity_df = pd.DataFrame(equity_curve)
                    if "date" in equity_df.columns:
                        equity_df["date"] = pd.to_datetime(equity_df["date"])
                        equity_df = equity_df.sort_values("date").set_index("date")

                    if "equity" in equity_df.columns:
                        st.line_chart(equity_df["equity"], use_container_width=True)
                    else:
                        st.info("Equity curve found, but no `equity` field was present.")
                else:
                    st.info("No equity curve returned yet.")

                st.markdown("</div>", unsafe_allow_html=True)

            with side_col:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                st.markdown('<div class="panel-title">Model Summary</div>', unsafe_allow_html=True)
                st.markdown(render_grouped_summary_html(summary), unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            if action_breakdown:
                st.markdown('<div class="panel" style="margin-top:1rem;">', unsafe_allow_html=True)
                st.markdown('<div class="panel-title">Action Breakdown</div>', unsafe_allow_html=True)

                action_df = pd.DataFrame(
                    {
                        "Action": [prettify_action(k) for k in action_breakdown.keys()],
                        "Count": list(action_breakdown.values()),
                    }
                )
                st.dataframe(action_df, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)

            if total_return_pct is not None and bnh_return_pct is not None:
                try:
                    spread = float(total_return_pct) - float(bnh_return_pct)
                    badge = "Outperformed" if spread >= 0 else "Underperformed"
                    st.markdown(
                        f"""
                        <div class="footer-banner">
                            {badge} buy & hold by {spread:+.1f} percentage points
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                except Exception:
                    pass

        if show_debug and equity_curve:
            with st.expander("Raw equity curve data"):
                st.dataframe(pd.DataFrame(equity_curve), use_container_width=True)

    except requests.exceptions.ConnectTimeout:
        status.update(label="Failed — connection timeout", state="error")
        st.error("Could not connect to the API within 10 seconds. Is the service running?")
        if show_debug:
            st.code(traceback.format_exc(), language="python")

    except requests.exceptions.ReadTimeout:
        status.update(label="Failed — read timeout", state="error")
        st.error("Connected to the API but the response took longer than 120 seconds.")
        if show_debug:
            st.code(traceback.format_exc(), language="python")

    except requests.exceptions.HTTPError as e:
        status.update(label=f"Failed — HTTP {response.status_code}", state="error")
        st.error(f"HTTP error: {e}")
        if show_debug:
            st.code(response.text if "response" in locals() else "No response body", language="text")
            st.code(traceback.format_exc(), language="python")

    except requests.exceptions.ConnectionError as e:
        status.update(label="Failed — connection error", state="error")
        st.error(f"Could not reach the API: {e}")
        if show_debug:
            st.code(traceback.format_exc(), language="python")

    except requests.exceptions.RequestException as e:
        status.update(label="Failed — request error", state="error")
        st.error(f"Request error: {e}")
        if show_debug:
            st.code(traceback.format_exc(), language="python")

    except Exception as e:
        status.update(label="Failed — unexpected error", state="error")
        st.error(f"Unexpected error: {e}")
        if show_debug:
            st.code(traceback.format_exc(), language="python")

else:
    with right_col:
        st.markdown(
            """
            <div class="panel placeholder-card">
                <div class="placeholder-inner">
                    <div class="hero-kicker">Ready</div>
                    <div style="font-size:2rem; font-weight:800; margin-bottom:0.6rem;">
                        Run a backtest to populate the dashboard
                    </div>
                    <div class="hero-sub">
                        The layout is already structured like a polished trading product:
                        inputs on the left, metrics and charts on the right, and only your
                        currently available API fields are rendered.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
