"""
Self-tracking trade signals for The Stock Market Game.
Reads holdings.json, decides trades, writes holdings.json back.
You never edit it by hand -- it assumes you entered whatever it told you to.
"""

import json
import datetime
import yfinance as yf

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "AMD",
    "JPM", "V", "BAC", "WMT", "COST", "PG", "KO", "UNH", "LLY",
    "XOM", "CVX", "CRWD", "PANW", "HD", "NFLX", "DIS",
]

MAX_POSITIONS = 8
TARGET_WEIGHT = 0.12
STOP_LOSS = 0.08
COMMISSION = 5.00
MIN_SHARES = 10
MIN_PRICE = 3.00


def load():
    with open("holdings.json") as f:
        return json.load(f)


def save(state):
    with open("holdings.json", "w") as f:
        json.dump(state, f, indent=2)


def metrics(ticker):
    df = yf.Ticker(ticker).history(period="1y")
    if len(df) < 60:
        return None
    c = df["Close"]
    ma20, ma50 = c.rolling(20).mean(), c.rolling(50).mean()
    d = c.diff()
    gain = d.clip(lower=0).rolling(14).mean()
    loss = -d.clip(upper=0).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    return {
        "price": float(c.iloc[-1]),
        "ma20": float(ma20.iloc[-1]), "ma50": float(ma50.iloc[-1]),
        "ma20p": float(ma20.iloc[-2]), "ma50p": float(ma50.iloc[-2]),
        "rsi": float(rsi.iloc[-1]),
        "mom": float(c.iloc[-1] / c.iloc[-21] - 1) * 100,
    }


def decide(state, data):
    sells, buys = [], []

    for t, shares in list(state["positions"].items()):
        d = data.get(t)
        if not d:
            continue
        why = None
        if d["price"] < d["ma50"] * (1 - STOP_LOSS):
            why = "fell 8% below its 50-day average"
        elif d["ma20"] < d["ma50"] and d["ma20p"] >= d["ma50p"]:
            why = "20-day average crossed below the 50-day"
        elif d["rsi"] > 78:
            why = f"overbought, RSI {d['rsi']:.0f}"
        if why:
            sells.append({"ticker": t, "shares": shares,
                          "price": d["price"], "why": why})

    cash = state["cash"] + sum(s["shares"] * s["price"] - COMMISSION
                               for s in sells)
    held = set(state["positions"]) - {s["ticker"] for s in sells}
    room = MAX_POSITIONS - len(held)

    cands = []
    for t, d in data.items():
        if t in held or d["price"] < MIN_PRICE:
            continue
        crossed = d["ma20"] > d["ma50"] and d["ma20p"] <= d["ma50p"]
        trending = d["price"] > d["ma50"] and 40 < d["rsi"] < 70
        if crossed or trending:
            cands.append((t, d))
    cands.sort(key=lambda x: x[1]["mom"], reverse=True)

    equity = cash + sum(state["positions"].get(t, 0) * data[t]["price"]
                        for t in held if t in data)

    for t, d in cands[:max(room, 0)]:
        budget = min(equity * TARGET_WEIGHT, cash - COMMISSION)
        shares = int(budget // d["price"])
        if shares < MIN_SHARES:
            continue
        cash -= shares * d["price"] + COMMISSION
        buys.append({"ticker": t, "shares": shares, "price": d["price"],
                     "why": f"{d['mom']:+.1f}% this month, RSI {d['rsi']:.0f}"})

    return sells, buys


def apply(state, sells, buys):
    today = datetime.date.today().isoformat()
    for s in sells:
        state["cash"] += s["shares"] * s["price"] - COMMISSION
        del state["positions"][s["ticker"]]
        state["log"].append({"date": today, "action": "SELL", **s})
    for b in buys:
        state["cash"] -= b["shares"] * b["price"] + COMMISSION
        state["positions"][b["ticker"]] = (
            state["positions"].get(b["ticker"], 0) + b["shares"])
        state["log"].append({"date": today, "action": "BUY", **b})
    return state


def main():
    state = load()
    tickers = set(WATCHLIST) | set(state["positions"])
    data = {}
    for t in tickers:
        try:
            m = metrics(t)
            if m:
                data[t] = m
        except Exception:
            pass

    sells, buys = decide(state, data)

    lines = []
    for s in sells:
        lines.append(f"SELL {s['shares']} {s['ticker']} "
                     f"(about ${s['price']:.2f}) -- {s['why']}")
    for b in buys:
        lines.append(f"BUY {b['shares']} {b['ticker']} "
                     f"(about ${b['price']:.2f}) -- {b['why']}")

    if lines:
        state = apply(state, sells, buys)
        save(state)
        equity = state["cash"] + sum(
            sh * data[t]["price"] for t, sh in state["positions"].items()
            if t in data)
        body = "\n".join(lines)
        body += f"\n\nAfter these, you hold: "
        body += ", ".join(f"{sh} {t}" for t, sh
                          in sorted(state["positions"].items())) or "nothing"
        body += f"\nCash ${state['cash']:,.2f}, total equity ${equity:,.2f}"
        body += ("\n\nEnter these in SMG today. Prices are last close, so round "
                 "down if the live price is higher.")
        with open("report.txt", "w") as f:
            f.write(body)
        print(body)
    else:
        print("NO TRADES")


if __name__ == "__main__":
    main()
