# Systematic Trading

Streamlit dashboard for the BTC Signal Classifier project. Displays live trading signals (BUY / SELL / FLAT), backtest results, and model performance metrics powered by our LightGBM pipeline.

## Description

This is the frontend interface for a systematic trading system that classifies hourly Bitcoin price action into BUY, SELL, or FLAT signals. The model uses 11 technical indicators across three strategy groups (Trend Momentum, RSI Divergence + Volume, Volatility Breakout) and applies a regime gate filter (SMA 50/200 crossover) before executing trades.

## Data Used

- **Source:** Binance BTCUSDT 1-hour candles
- **Period:** January 2018 – March 2026
- **Size:** ~71,500 bars
- **Columns:** OHLCV (Open, High, Low, Close, Volume)

## API

The frontend connects to a FastAPI backend hosted in the `systematic_trading_backend` repo. The API exposes endpoints for predictions, backtest results, and trade logs.
