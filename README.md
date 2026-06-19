# Crypto Analytics OSS

A coin-agnostic, **educational** cryptocurrency analytics engine. Pick any coin,
get a 5-layer confluence signal — an entry **zone**, an **invalidation** level,
and a **confidence %** — plus a **liquidation-distance guardrail** that refuses
to bless reckless leverage. Pure-Python engine, zero required dependencies, and
a tiny self-hostable web page.

## ⛔ NOT FINANCIAL ADVICE — read this first

This project is for **education and information only**. It is **not** financial,
investment, or trading advice.

- It **never executes trades.** There is no order-execution code anywhere.
- It **holds no exchange API keys** and connects to **no** trade/withdraw endpoints.
- It ingests **read-only public market data** and computes signals + math.
- Cryptocurrency and **leverage trading can lose you more than your deposit.**
- **You are solely responsible for your own decisions. Do your own research.**

The liquidation-distance guardrail is deliberately blunt: if a leverage setup
would be liquidated by a single normal daily move, it tells you so and refuses.
That honesty is the point.

## What it does

For any coin you select (by CoinGecko id, symbol, or name), it scores five
independent layers, each producing a sub-score in `[-1, +1]` where `+1` is
strongly favorable for a long entry:

| Layer | Source | Notes |
|---|---|---|
| **TA** | CoinGecko price history | 50/200 DMA, RSI (+ bullish divergence), swing structure, ATR |
| **Derivatives** | CoinGlass (free tier) | perp funding regime — deeply negative funding = crowded shorts = squeeze fuel |
| **On-chain** | DefiLlama | protocol TVL 7d/30d trend (only if the coin maps to a DeFi protocol) |
| **Macro** | FRED | broad dollar index + Fed funds trend — rising dollar / hikes = risk-off |
| **Sentiment** | alternative.me | Fear & Greed index (contrarian: extreme fear = accumulation) |

**No single layer triggers a call — alignment (confluence) does.** Any layer with
no data scores **neutral (0.0)**, and the overall **confidence is discounted by
data coverage** — the engine never pretends it has data it doesn't.

Output: a weighted confluence → confidence %, an **entry zone**, an
**invalidation level**, and the **guardrail verdict** for your intended leverage.

### The liquidation-distance guardrail (the responsible core)

Given an entry and intended leverage, it computes the long liquidation price:

```
liquidation ≈ Entry × (1 − 1/Leverage + MaintenanceMarginRate)
```

and **REFUSES** any setup where:

1. leverage is above the hard cap (default **3x**), or
2. the liquidation price sits within ~**1 ATR** of entry (a normal daily move would liquidate it).

It refuses with the math and a plain-language explanation, and points you at the
safer pattern (spot for the core thesis, low leverage with a hard stop only).

## Data sources — all free

- **CoinGecko** — price, market cap, daily close history. No key needed.
- **alternative.me** — Fear & Greed index. No key needed.
- **DefiLlama** — protocol TVL. No key needed (requires a protocol slug for the coin).
- **FRED** — macro. Optional free key (`FRED_API_KEY`); degrades to neutral without it.
- **CoinGlass** — funding rate. Optional key (`COINGLASS_API_KEY`); free tier often
  rate-limited, degrades to neutral.

Every fetch degrades cleanly — a missing source never crashes the run.

## Install

No dependencies are required to run the engine or the web server (pure stdlib).
`python-dotenv` is optional, only used to load a `.env` file.

```bash
git clone https://github.com/JDDavenport/crypto-analytics-oss.git
cd crypto-analytics-oss
# optional: pip install -e ".[dotenv,test]"
cp .env.example .env   # optional — add free API keys for the macro/derivatives layers
```

## Usage — CLI

```bash
# Analyze any coin (id, symbol, or name)
python3 -m crypto_analytics.analyzer bitcoin
python3 -m crypto_analytics.analyzer ETH
python3 -m crypto_analytics.analyzer solana

# Run an intended leverage through the guardrail
python3 -m crypto_analytics.analyzer bitcoin --leverage 10

# Add the on-chain layer for a DeFi protocol coin (DefiLlama slug)
python3 -m crypto_analytics.analyzer curve-dao-token --symbol CRV --defillama curve-dex

# Raw JSON
python3 -m crypto_analytics.analyzer bitcoin --json
```

## Usage — web page

A minimal single-page UI backed by a zero-dependency stdlib HTTP API.

```bash
python3 -m crypto_analytics.api          # http://localhost:8787
PORT=9000 python3 -m crypto_analytics.api
```

Open the URL, type a coin, optionally a leverage, and read the analytics. The
page is fully self-hostable and the API is read-only.

API endpoint: `GET /api/analyze?coin=<id|symbol|name>&leverage=<n>&defillama=<slug>&symbol=<TICKER>`

## Configuration

All optional, via environment variables (see `.env.example`):

- `CA_MAX_LEVERAGE` (default `3.0`) — guardrail hard cap
- `CA_MMR` (default `0.005`) — maintenance margin rate in the liquidation formula
- `CA_LIQ_ATR_BUFFER` (default `1.0`) — required liquidation distance in ATRs
- `CA_W_TA`, `CA_W_DERIVATIVES`, `CA_W_ONCHAIN`, `CA_W_MACRO`, `CA_W_SENTIMENT` — layer weights
- `FRED_API_KEY`, `COINGLASS_API_KEY` — unlock the macro / derivatives layers
- `PORT` — web server port

## Tests

```bash
python3 -m pytest tests/ -q
```

The guardrail tests are the critical ones: they assert that reckless leverage
(e.g. 10x, or any liquidation within 1 ATR of entry) is **refused** across price
scales.

## Out of scope (by design, forever)

Autonomous order execution, exchange trade/withdraw keys, "set 10x and walk
away," or promising a price target as a certainty. This is an analytics and
risk-education tool, not a trading bot.

## License

[MIT](./LICENSE). Educational use, no warranty, not financial advice.
