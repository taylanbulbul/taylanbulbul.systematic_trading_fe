import os
import streamlit as st
import pandas as pd
import requests
import traceback
import time
import json

st.set_page_config(page_title="Systematic Trading Demo", layout="wide")

# ── API Configuration ────────────────────────────────────────────
# Source: .streamlit/secrets.toml or Streamlit Cloud secrets
# Shell variable selects which URI to use (see Makefile shortcuts)
# if 'API_URI' in os.environ:
#     BASE_URI = st.secrets[os.environ.get('API_URI')]
# else:
#     BASE_URI = st.secrets['cloud_api_uri']

# BASE_URI = BASE_URI if BASE_URI.endswith('/') else BASE_URI + '/'
# url = BASE_URI + 'backtest'
url = 'https://api-469354767887.europe-west1.run.app/backtest'

# ── Title & Introduction ─────────────────────────────────────────
st.title("Systematic Trading Demo")
st.write("Run a simple backtest with a cutoff date and starting budget.")

# ── Sidebar ──────────────────────────────────────────────────────
show_debug = st.sidebar.checkbox("Show debug logs", value=True)
if show_debug:
    st.sidebar.caption(f"API endpoint: `{url}`")

# ── User Input ───────────────────────────────────────────────────
with st.form("backtest_form"):
    cutoff_date = st.date_input("Cutoff date", value=pd.to_datetime("2025-01-01"))
    initial_capital = st.number_input(
        "Budget / Initial capital",
        min_value=100.0,
        value=1000.0,
        step=100.0,
    )
    submitted = st.form_submit_button("Run backtest")

# ── Call API & Display Results ───────────────────────────────────
if submitted:
    params = {
        "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
        "initial_capital": float(initial_capital),
    }

    status = st.status("Running backtest...", expanded=True)

    try:
        # Send request
        status.write(f"Sending GET to `{url}`")
        status.write(f"Params: `{params}`")

        t0 = time.time()
        status.write("Waiting for API response...")

        session = requests.Session()
        response = session.get(
            url,
            params=params,
            timeout=(10, 120),
            stream=True,
        )

        elapsed_connect = time.time() - t0
        status.write(f"Connected in {elapsed_connect:.1f}s — status {response.status_code}")

        if show_debug:
            with status.expander("Response headers"):
                st.write(dict(response.headers))

        # Check response
        response.raise_for_status()

        status.write("Reading response body...")
        raw_body = response.content
        elapsed_total = time.time() - t0
        status.write(f"Body received in {elapsed_total:.1f}s ({len(raw_body)} bytes)")

        # Retrieve prediction / results from JSON
        summary = json.loads(raw_body)

        if show_debug:
            with status.expander("Raw JSON response"):
                st.json(summary)

        status.update(label="Backtest complete", state="complete", expanded=False)

        # ── Display Results ──────────────────────────────────────
        st.success("Backtest complete")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Final capital", f"${summary.get('final_capital', 0):,.2f}")
        col2.metric("Total return", f"{summary.get('total_return_pct', 0)}%")
        col3.metric("Win rate", f"{summary.get('win_rate_pct', 0)}%")
        col4.metric("Max drawdown", f"{summary.get('max_drawdown_pct', 0)}%")

        st.subheader("Performance summary")
        summary_table = {
            "Initial capital": summary.get("initial_capital"),
            "Final capital": summary.get("final_capital"),
            "Total return %": summary.get("total_return_pct"),
            "Annualised return %": summary.get("annualised_return_pct"),
            "Total trades": summary.get("total_trades"),
            "Winning trades": summary.get("winning_trades"),
            "Losing trades": summary.get("losing_trades"),
            "Win rate %": summary.get("win_rate_pct"),
            "Loss rate %": summary.get("loss_rate_pct"),
            "Avg win PnL": summary.get("avg_win_pnl"),
            "Avg loss PnL": summary.get("avg_loss_pnl"),
            "Implied costs": summary.get("implied_costs"),
            "Sharpe ratio": summary.get("sharpe_ratio"),
            "Max drawdown %": summary.get("max_drawdown_pct"),
            "Profit factor": summary.get("profit_factor"),
            "Buy & hold return %": summary.get("bnh_return_pct"),
        }
        summary_df = pd.DataFrame(
            {"Metric": list(summary_table.keys()), "Value": list(summary_table.values())}
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # Equity curve
        equity_curve = summary.get("equity_curve", [])
        if equity_curve:
            st.subheader("Equity curve")
            equity_df = pd.DataFrame(equity_curve)
            equity_df["date"] = pd.to_datetime(equity_df["date"])
            equity_df = equity_df.set_index("date")
            st.line_chart(equity_df["equity"])

            if show_debug:
                with st.expander("Raw equity curve data"):
                    st.dataframe(equity_df.reset_index(), use_container_width=True)

        # Action breakdown
        action_breakdown = summary.get("action_breakdown", {})
        if action_breakdown:
            st.subheader("Action breakdown")
            action_df = pd.DataFrame(
                {
                    "Action": list(action_breakdown.keys()),
                    "Count": list(action_breakdown.values()),
                }
            )
            st.dataframe(action_df, use_container_width=True, hide_index=True)

    # ── Error Handling ───────────────────────────────────────────
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
