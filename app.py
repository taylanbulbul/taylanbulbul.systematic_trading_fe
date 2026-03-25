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

def render_action_breakdown_html(action_breakdown: dict) -> str:
    grouped = {
        "Long Trades": {
            "Long Trades": 0,
            "Stop Loss Exits": 0,
            "Time Exits": 0,
        },
        "Short Trades": {
            "Short Trades": 0,
            "Stop Loss Exits": 0,
            "Time Exits": 0,
        },
    }

    for key, value in action_breakdown.items():
        k = str(key).lower()
        label = ACTION_LABEL_MAP.get(k)
        if not label:
            continue

        if "long" in k:
            side = "Long Trades"
        elif "short" in k:
            side = "Short Trades"
        else:
            continue

        grouped[side][label] += value

    html = ""
    for section, items in grouped.items():
        rows = ""
        for label, count in items.items():
            rows += (
                f'<tr class="summary-tr">'
                f'<td class="summary-td-label">{label}</td>'
                f'<td class="summary-td-value">{int(count)}</td>'
                f"</tr>"
            )

        html += (
            f'<table class="summary-table">'
            f'<caption class="summary-caption">{section}</caption>'
            f"{rows}</table>"
        )

    return html

def build_action_breakdown_df(action_breakdown: dict) -> pd.DataFrame:
    grouped = {
        "Long Trades": {
            "Long Trades": 0,
            "Stop Loss Exits": 0,
            "Time Exits": 0,
        },
        "Short Trades": {
            "Short Trades": 0,
            "Stop Loss Exits": 0,
            "Time Exits": 0,
        },
    }

    for key, value in action_breakdown.items():
        k = str(key).lower()
        label = ACTION_LABEL_MAP.get(k)

        if not label:
            continue

        if "long" in k:
            side = "Long Trades"
        elif "short" in k:
            side = "Short Trades"
        else:
            continue

        grouped[side][label] += value

    rows = []
    for side, metrics in grouped.items():
        for label, count in metrics.items():
            rows.append({
                "Category": side,
                "Metric": label,
                "Count": count
            })

    return pd.DataFrame(rows)

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
    for old, new in {"Pnl": "PnL", "Close Time ": "Close ", " Time ": " "}.items():
        action = action.replace(old, new)
    # catch trailing "Time" too
    if action.endswith(" Time"):
        action = action[:-5]
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


# ── Color rules for summary values ────────────────────────────────────
COLORED_ROWS = {
    "Sharpe Ratio":   "sign",
    "Max Drawdown":   "sign",
    "Profit Factor":  "sign",
    "Avg Win PnL":    "force_good",
    "Avg Loss PnL":   "force_bad",
}

ACTION_LABEL_MAP = {
    "enter_long": "Long Trades",
    "enter_short": "Short Trades",
    "stop_loss_long": "Stop Loss Exits",
    "stop_loss_short": "Stop Loss Exits",
    "close_long": "Time Exits",
    "close_short": "Time Exits",
    "close_long_time": "Time Exits",
    "close_short_time": "Time Exits",
}


def value_color_class(label: str, raw_value) -> str:
    rule = COLORED_ROWS.get(label)
    if not rule:
        return ""
    if rule == "force_good":
        return "good"
    if rule == "force_bad":
        return "bad"
    if raw_value is None:
        return ""
    try:
        v = float(raw_value)
    except Exception:
        return ""
    if v > 0:
        return "good"
    if v < 0:
        return "bad"
    return ""


def build_grouped_summary(summary: dict):
    """Risk Metrics first, then Trade Statistics. Capital section removed."""
    return {
        "Risk Metrics": {
            "Sharpe Ratio":  (fmt_num(summary.get("sharpe_ratio")),      summary.get("sharpe_ratio")),
            "Max Drawdown":  (fmt_pct(summary.get("max_drawdown_pct")),  summary.get("max_drawdown_pct")),
            "Profit Factor": (fmt_num(summary.get("profit_factor")),     summary.get("profit_factor")),
        },
        "Trade Statistics": {
            "Total Trades":   (fmt_num(summary.get("total_trades"), 0),  None),
            "Winning Trades": (fmt_num(summary.get("winning_trades"), 0), None),
            "Losing Trades":  (fmt_num(summary.get("losing_trades"), 0), None),
            "Win Rate":       (fmt_pct(summary.get("win_rate_pct")),     None),
            "Loss Rate":      (fmt_pct(summary.get("loss_rate_pct")),    None),
            "Avg Win PnL":    (fmt_money(summary.get("avg_win_pnl")),    summary.get("avg_win_pnl")),
            "Avg Loss PnL":   (fmt_money(summary.get("avg_loss_pnl")),   summary.get("avg_loss_pnl")),
            "Implied Costs":  (fmt_money(summary.get("implied_costs")),  None),
        },
    }


def render_grouped_summary_html(summary: dict) -> str:
    grouped = build_grouped_summary(summary)
    html = ""
    for section, items in grouped.items():
        visible = {k: v for k, v in items.items() if v[0] != "—"}
        if not visible:
            continue
        rows = ""
        for label, (formatted, raw) in visible.items():
            cls = value_color_class(label, raw)
            val_html = f'<span class="{cls}">{formatted}</span>' if cls else formatted
            rows += (
                f'<tr class="summary-tr">'
                f'<td class="summary-td-label">{label}</td>'
                f'<td class="summary-td-value">{val_html}</td>'
                f"</tr>"
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
        display: flex;
        align-items: center;
    }

    .hero-kicker {
        font-size: 0.78rem;
        letter-spacing: 0.20em;
        text-transform: uppercase;
        color: #7ea6ff;
        margin-bottom: 0.4rem;
        font-weight: 700;
        display: flex;
        align-items: center;
    }

    .hero-sub {
        color: var(--muted);
        font-size: 1rem;
        margin-bottom: 0.35rem;
    }

/* Fixed-size, evenly aligned metric cards */
.metric-card {
    width: 100%;
    min-height: 130px;
    height: 130px;
    box-sizing: border-box;
    background: linear-gradient(180deg, rgba(15,25,54,0.98), rgba(11,19,42,0.98));
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1rem;
    box-shadow: var(--glow);

    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.metric-label {
    color: var(--muted);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
}

.metric-value {
    font-size: 2rem;
    font-weight: 800;
    line-height: 1.05;
    margin: 0;
}

.metric-sub {
    color: var(--muted);
    font-size: 0.85rem;
    margin: 0.35rem 0 0 0;
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

    /* Section tooltip */
    .tip-icon {
        display: inline-flex; align-items: center; justify-content: center;
        width: 13px; height: 13px; border-radius: 50%;
        background: rgba(89,167,255,0.12); border: 1px solid rgba(89,167,255,0.28);
        color: #59a7ff; font-size: 0.58rem; font-weight: 800;
        cursor: default; margin-left: 0.3rem;
        position: relative; flex-shrink: 0;
    }
    .tip-icon::after {
        content: attr(data-tip);
        display: none;
        position: absolute; left: 50%; top: calc(100% + 7px);
        transform: translateX(-50%);
        background: #0d1630; border: 1px solid rgba(80,140,255,0.28);
        color: #d5e1fb; font-size: 0.78rem; font-weight: 400; letter-spacing: 0;
        text-transform: none;
        padding: 0.4rem 0.75rem; border-radius: 8px;
        white-space: nowrap; z-index: 200;
        box-shadow: 0 4px 18px rgba(0,0,0,0.45);
    }
    .tip-icon:hover::after { display: block; }
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
            value=pd.to_datetime("2024-10-23"),
            min_value=pd.to_datetime("2023-09-01"),
            max_value=pd.Timestamp.today(),
            help="Historical date used as the backtest cutoff.",
        )
        initial_capital = st.number_input(
            "Investment (USD)",
            min_value=100.0,
            value=1000.0,
            step=100.0,
            help="Starting capital for the simulation in US dollars.",
        )
        position_size = st.select_slider(
            "Risk per Trade",
            options=[i / 10 for i in range(1, 11)],
            value=1.0,
            format_func=lambda x: f"{int(x * 100)}%",
            help="How much of your capital is put into each trade. 100% = all in, 10% = cautious.",
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
        "position_size": float(position_size),
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
        if not response.ok:
            try:
                detail = response.json().get("detail") or response.text[:500]
            except Exception:
                detail = response.text[:500] or response.reason
            _loader.empty()
            st.error(f"API error {response.status_code}: {detail}")
            st.stop()
        summary = json.loads(response.content)
        _loader.empty()

        final_capital      = safe_get(summary, "final_capital")
        total_return_pct   = safe_get(summary, "total_return_pct")
        win_rate_pct       = safe_get(summary, "win_rate_pct")
        annualised_pct     = safe_get(summary, "annualised_return_pct")
        initial_capital_r  = safe_get(summary, "initial_capital", initial_capital)
        bnh_return_pct     = safe_get(summary, "bnh_return_pct")
        bnh_entry_price    = safe_get(summary, "bnh_buy_price")
        bnh_current_price  = safe_get(summary, "bnh_final_price")
        bnh_final_value    = safe_get(summary, "bnh_final_value")
        end_date           = get_backtest_end_date(summary)
        equity_curve       = safe_get(summary, "equity_curve", [])
        action_breakdown   = safe_get(summary, "action_breakdown", {})

        # ── Left column: model summary + action breakdown ─────────────
        with left_col:
            st.markdown('<p class="panel-title">Model Summary <span class="tip-icon" data-tip="Risk and trade stats computed from the backtest run">?</span></p>', unsafe_allow_html=True)
            st.markdown(render_grouped_summary_html(summary), unsafe_allow_html=True)

            if action_breakdown:
                st.markdown('<p class="panel-title" style="margin-top:1rem;">Action Breakdown <span class="tip-icon" data-tip="Count of each trade action the engine executed">?</span></p>', unsafe_allow_html=True)
                st.markdown(render_action_breakdown_html(action_breakdown), unsafe_allow_html=True)

        # ── Right column: full results ────────────────────────────────
        with right_col:
            st.markdown('<p class="top-spacer-fix"></p>', unsafe_allow_html=True)
            st.markdown(
                f'<p class="hero-kicker">Trading Engine Performance <span class="tip-icon" data-tip="Live results from the strategy engine over the selected period">?</span></p>'
                f'<p class="metric-sub" style="margin-bottom:0.9rem;">'
                f'Trading engine executes from '
                f'<span style="color:var(--text); font-weight:700;">{cutoff_date.strftime("%Y-%m-%d")}</span>'
                f' to '
                f'<span style="color:var(--text); font-weight:700;">{end_date or "—"}</span>'
                f'</p>',
                unsafe_allow_html=True,
)

            m1, m2, m3, m4 = st.columns(4, gap="small")
            for col, label, value, sub, raw, pos_good in [
                (m1, "Final Capital",  fmt_money_0(final_capital),  f"Starting from {fmt_money_0(initial_capital_r)}", None,            True),
                (m2, "Total Return",   fmt_pct(total_return_pct),   "Strategy return over the test window",            total_return_pct, True),
                (m3, "Win Rate",       fmt_pct(win_rate_pct),       "Share of winning trades",                         win_rate_pct,     True),
                (m4, "Annualised",     fmt_pct(annualised_pct),     "Yearly compounded return",                        annualised_pct,   True),
            ]:
                cls = metric_class(raw, positive_good=pos_good) if raw is not None else "neutral"
                with col:
                    st.markdown(
                    f'''
                    <div class="metric-card">
                        <p class="metric-label">{label}</p>
                        <p class="metric-value {cls}">{value}</p>
                        <p class="metric-sub">{sub}</p>
                    </div>
                    ''',
    unsafe_allow_html=True,
)

            # ── BTC Benchmark cards ───────────────────────────────
            if bnh_return_pct is not None:
                ret_cls = metric_class(bnh_return_pct, positive_good=True)

                _bnh_value = bnh_final_value
                if _bnh_value is None:
                    try:
                        _bnh_value = float(initial_capital_r) * (1 + float(bnh_return_pct) / 100)
                    except Exception:
                        _bnh_value = None

                st.markdown(
                    f'<p class="panel-title" style="margin-top:1.4rem;">BTC Benchmark <span class="tip-icon" data-tip="What a simple buy &amp; hold of BTC returned over the same period">?</span></p>'
                    f'<p class="metric-sub" style="margin-top:-0.6rem; margin-bottom:0.6rem;">'
                    f'Buy &amp; Hold since {cutoff_date.strftime("%Y-%m-%d")}</p>',
                    unsafe_allow_html=True,
                )

                b1, b2, b3, b4 = st.columns(4, gap="small")
                for col, label, value, sub in [
                    (b1, "Entry Price", fmt_money_0(bnh_entry_price),   "BTC price at entry"),
                    (b2, "Current",     fmt_money_0(bnh_current_price), "BTC price at close"),
                    (b3, "Value",       fmt_money_0(_bnh_value),        "Portfolio value"),
                    (b4, "Return",      fmt_pct(bnh_return_pct),        "Buy & hold return"),
                ]:
                    v_cls = ret_cls if label == "Return" else "neutral"
                    with col:
                        st.markdown(
                            f'''
                            <div class="metric-card">
                                <p class="metric-label">{label}</p>
                                <p class="metric-value {v_cls}">{value}</p>
                                <p class="metric-sub">{sub}</p>
                            </div>
                            ''',
                            unsafe_allow_html=True,
                        )

                if total_return_pct is not None:
                    try:
                        spread = float(total_return_pct) - float(bnh_return_pct)
                        badge  = "Outperformed" if spread >= 0 else "Underperformed"
                        s_cls  = "good" if spread >= 0 else "bad"
                        st.markdown(
                            f'<p class="metric-sub" style="margin-top:0.5rem;">'
                            f'Trading engine <span class="{s_cls}"><strong>{badge}</strong></span> '
                            f'by <span class="{s_cls}"><strong>{spread:+.1f}pp</strong></span></p>',
                            unsafe_allow_html=True,
                        )
                    except Exception:
                        pass

            st.markdown(
               '<div style="margin-top:1.5rem;"><p class="panel-title">Equity Curve <span class="tip-icon" data-tip="Portfolio value over time throughout the backtest">?</span></p></div>',
                unsafe_allow_html=True
)
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
