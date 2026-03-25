import os
import json
import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Systematic Trading Demo",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── Helpers ───────────────────────────────────────────────────────────
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
        return "good" if v > 0 else ("bad" if v < 0 else "neutral")
    else:
        return "bad" if v < 0 else ("good" if v > 0 else "neutral")


def safe_get(summary, key, default=None):
    return summary.get(key, default) if isinstance(summary, dict) else default


def prettify_action(action: str) -> str:
    if not action:
        return "—"
    action = str(action).replace("_", " ").strip().title()
    for old, new in {"Pnl": "PnL"}.items():
        action = action.replace(old, new)
    return action


def get_backtest_end_date(summary: dict):
    for key in ("end_date", "last_date", "latest_date", "backtest_end_date"):
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
    html = ""
    for section, items in grouped.items():
        visible = {k: v for k, v in items.items() if v != "—"}
        if not visible:
            continue
        rows = "".join(
            f'<tr class="summary-tr">'
            f'<td class="summary-td-label">{label}</td>'
            f'<td class="summary-td-value">{value}</td>'
            f"</tr>"
            for label, value in visible.items()
        )
        html += (
            f'<table class="summary-table">'
            f'<caption class="summary-caption">{section}</caption>'
            f"{rows}</table>"
        )
    return html



# ── Styling ───────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Hide Streamlit chrome */
    header, header[data-testid="stHeader"],
    div[data-testid="stToolbar"], div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"], #MainMenu, footer, .stDeployButton {
        display: none !important;
        height: 0 !important;
        visibility: hidden !important;
    }

    :root {
        --bg: #060b1a;
        --panel: #0d1630;
        --border: rgba(80, 140, 255, 0.22);
        --text: #eef4ff;
        --muted: #94a7c6;
        --blue: #59a7ff;
        --green: #31d67b;
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
        padding-top: 1rem;
        padding-bottom: 3rem;
        max-width: 1440px;
    }

    h1, h2, h3, h4, h5, h6, p, label, div, span { color: var(--text); }

    .top-spacer-fix { height: 0.35rem; }

    .panel-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        color: #8caef9;
        margin-bottom: 0.9rem;
        font-weight: 800;
    }

    .hero-kicker {
        font-size: 0.78rem;
        letter-spacing: 0.20em;
        text-transform: uppercase;
        color: #7ea6ff;
        margin-bottom: 0.4rem;
        font-weight: 700;
    }

    .hero-sub {
        color: var(--muted);
        font-size: 1rem;
        margin-bottom: 0.35rem;
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

    .metric-value { font-size: 2rem; font-weight: 800; line-height: 1.05; margin-bottom: 0.2rem; }
    .metric-sub   { color: var(--muted); font-size: 0.85rem; }

    .good    { color: var(--green); }
    .bad     { color: var(--red); }
    .neutral { color: var(--blue); }

    /* Summary tables */
    .summary-table {
        width: 100%; border-collapse: collapse;
        border: 1px solid rgba(120,150,255,0.18);
        border-radius: 14px; overflow: hidden;
        background: rgba(10,18,36,0.72);
        margin-bottom: 0.9rem;
    }
    .summary-caption {
        caption-side: top; text-align: left;
        font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.14em; font-weight: 800;
        color: #dfe9ff; padding: 0.8rem 0.9rem;
        background: rgba(255,255,255,0.03);
        border-bottom: 1px solid rgba(120,150,255,0.18);
    }
    .summary-tr         { border-bottom: 1px solid rgba(120,150,255,0.10); }
    .summary-tr:last-child { border-bottom: none; }
    .summary-td-label   { color: #d5e1fb; font-size: 0.92rem; padding: 0.72rem 0.9rem; }
    .summary-td-value   { color: white; font-weight: 700; text-align: right; white-space: nowrap; padding: 0.72rem 0.9rem; }

    .footer-banner {
        margin-top: 1rem;
        background: linear-gradient(90deg, rgba(7,85,37,0.95), rgba(10,120,48,0.95));
        border: 1px solid rgba(94,255,154,0.25);
        border-radius: 16px;
        padding: 0.9rem 1rem;
        color: #d7ffe6; font-weight: 800; font-size: 1rem;
        box-shadow: 0 8px 22px rgba(0,0,0,0.24);
    }

    /* Form controls */
    div[data-testid="stForm"] { background: transparent; border: none; padding: 0; margin: 0; }
    .stDateInput, .stNumberInput { margin-top: 0 !important; }
    .stDateInput > div, .stNumberInput > div { margin-top: 0 !important; }
    div[data-baseweb="input"],
    div[data-baseweb="select"] > div,
    .stDateInput > div > div {
        background: rgba(9,18,38,0.96) !important;
        border-radius: 14px !important;
        border: 1px solid rgba(85,142,255,0.28) !important;
    }
    .stNumberInput input, .stDateInput input { color: white !important; font-weight: 600; }

    div.stButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        width: 100%; border-radius: 14px;
        border: 1px solid rgba(67,229,126,0.25);
        background: linear-gradient(180deg, #28d866 0%, #1ebb58 100%);
        color: white; font-size: 1.02rem; font-weight: 800;
        padding: 0.75rem 1rem;
        box-shadow: 0 8px 20px rgba(20,140,65,0.28);
    }

    .stDataFrame { border-radius: 16px; overflow: hidden; border: 1px solid rgba(88,130,255,0.18); }

    .small-note { color: var(--muted); font-size: 0.82rem; margin-top: 0.8rem; }

    /* Stickman loader */
    .stickman-loader { font-size: 1.1rem; color: var(--muted, #94a7c6); font-weight: 600; padding: 0.6rem 0; }
    @keyframes stickbounce {
        0%, 100% { transform: translateY(0); }
        50%      { transform: translateY(-3px); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── API config ────────────────────────────────────────────────────────
if "API_URI" in os.environ:
    BASE_URI = st.secrets[os.environ.get("API_URI")]
else:
    BASE_URI = st.secrets["cloud_api_uri"]

BASE_URI = BASE_URI if BASE_URI.endswith("/") else BASE_URI + "/"
url = BASE_URI + "backtest"


# ── Layout ────────────────────────────────────────────────────────────
left_col, right_col = st.columns([1.0, 1.9], gap="large")

with left_col:
    st.markdown('<p class="top-spacer-fix"></p>', unsafe_allow_html=True)
    st.markdown('<p class="panel-title">Inputs</p>', unsafe_allow_html=True)

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
        '<p class="small-note">'
        "Powered by our Systematic Trading API: real model outputs, real metrics. "
        "Strategy engine still in active development."
        "</p>",
        unsafe_allow_html=True,
    )


# ── Run backtest ──────────────────────────────────────────────────────
if submitted:
    params = {
        "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
        "initial_capital": float(initial_capital),
    }

    _loader = st.empty()
    _loader.markdown(
        '<p class="stickman-loader">'
        '<span style="display:inline-block; animation: stickbounce 0.45s steps(1) infinite; '
        'font-size:1.3rem; margin-right:0.4rem;">🏃‍♀️</span>'
        "Running backtest…"
        "</p>",
        unsafe_allow_html=True,
    )

    try:
        response = requests.get(url, params=params, timeout=(10, 120))
        response.raise_for_status()
        summary = json.loads(response.content)
        _loader.empty()

        final_capital      = safe_get(summary, "final_capital")
        total_return_pct   = safe_get(summary, "total_return_pct")
        win_rate_pct       = safe_get(summary, "win_rate_pct")
        max_drawdown_pct   = safe_get(summary, "max_drawdown_pct")
        initial_capital_r  = safe_get(summary, "initial_capital", initial_capital)
        bnh_return_pct     = safe_get(summary, "bnh_return_pct")
        total_trades       = safe_get(summary, "total_trades")
        sharpe_ratio       = safe_get(summary, "sharpe_ratio")
        profit_factor      = safe_get(summary, "profit_factor")
        end_date           = get_backtest_end_date(summary)
        equity_curve       = safe_get(summary, "equity_curve", [])
        action_breakdown   = safe_get(summary, "action_breakdown", {})

        # ── Left column: model summary ─────────────────────────────────
        with left_col:
            st.markdown('<p class="panel-title">Model Summary</p>', unsafe_allow_html=True)
            st.markdown(render_grouped_summary_html(summary), unsafe_allow_html=True)

        # ── Right column: full results ────────────────────────────────
        with right_col:
            st.markdown('<p class="top-spacer-fix"></p>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="hero-kicker">Strategy Backtest — Execution Results</p>'
                f'<p style="font-size:1.15rem; font-weight:800; color:#7fb5ff;">'
                f'{cutoff_date.strftime("%Y-%m-%d")} → {end_date or "—"}</p>',
                unsafe_allow_html=True,
            )

            m1, m2, m3, m4 = st.columns(4, gap="small")
            for col, label, value, sub, pos_good in [
                (m1, "Final Capital",  fmt_money_0(final_capital),  f"Starting from {fmt_money_0(initial_capital_r)}", True),
                (m2, "Total Return",   fmt_pct(total_return_pct),   "Strategy return over the test window",            True),
                (m3, "Win Rate",       fmt_pct(win_rate_pct),       "Share of winning trades",                         True),
                (m4, "Max Drawdown",   fmt_pct(max_drawdown_pct),   "Worst peak-to-trough decline",                    False),
            ]:
                raw = total_return_pct if label == "Total Return" else (win_rate_pct if label == "Win Rate" else (max_drawdown_pct if label == "Max Drawdown" else None))
                cls = metric_class(raw, positive_good=pos_good) if raw is not None else "neutral"
                with col:
                    st.markdown(
                        f'<table class="metric-card"><tr><td>'
                        f'<p class="metric-label">{label}</p>'
                        f'<p class="metric-value {cls}">{value}</p>'
                        f'<p class="metric-sub">{sub}</p>'
                        f"</td></tr></table>",
                        unsafe_allow_html=True,
                    )

            st.markdown('<p class="panel-title">Equity Curve</p>', unsafe_allow_html=True)
            if equity_curve:
                eq_df = pd.DataFrame(equity_curve)
                if "date" in eq_df.columns:
                    eq_df["date"] = pd.to_datetime(eq_df["date"])
                    eq_df = eq_df.sort_values("date").set_index("date")
                if "equity" in eq_df.columns:
                    st.line_chart(eq_df["equity"], use_container_width=True)
                else:
                    st.info("Equity curve found, but no `equity` field was present.")
            else:
                st.info("No equity curve returned yet.")

            if action_breakdown:
                st.markdown('<p class="panel-title" style="margin-top:1rem;">Action Breakdown</p>', unsafe_allow_html=True)
                action_df = pd.DataFrame({
                    "Action": [prettify_action(k) for k in action_breakdown],
                    "Count": list(action_breakdown.values()),
                })
                st.dataframe(action_df, use_container_width=True, hide_index=True)

            if total_return_pct is not None and bnh_return_pct is not None:
                try:
                    spread = float(total_return_pct) - float(bnh_return_pct)
                    badge = "Outperformed" if spread >= 0 else "Underperformed"
                    st.markdown(
                        f'<p class="footer-banner">{badge} buy &amp; hold by {spread:+.1f} percentage points</p>',
                        unsafe_allow_html=True,
                    )
                except Exception:
                    pass

    except Exception as e:
        _loader.empty()
        st.error(f"Backtest failed: {e}")

else:
    with right_col:
        st.markdown('<p class="top-spacer-fix"></p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="hero-kicker">Ready</p>'
            '<p style="font-size:2rem; font-weight:800; margin-bottom:0.6rem;">'
            "Run a backtest to populate the dashboard</p>"
            '<p class="hero-sub">'
            "Our app simulates a trading strategy from your chosen date and capital, "
            "then shows you how it would have performed; returns, risk metrics, and an equity curve. "
            "It also compares the strategy against simple buy-and-hold to see if the model added value."
            "</p>",
            unsafe_allow_html=True,
        )
