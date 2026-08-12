# Deep Research Report — Nifty Options Microstructure & IV Skew Arbitrage Models

**Date:** 12-Aug-2026 00:15 IST (post-close)
**Data basis:** `data/research.db` (325k ticks, NIFTY weekly expiry 11-Aug-2026, 09:36-13:16 IST), OI snapshots 08 & 11-Aug, India VIX 12.01, `live_trader_brain.py` master verdict, web research.
**Status:** Expiry day closed Tuesday 11-Aug; NIFTY weeklies now expire Tuesday (lot 75).

---

## 1. Market State at Time of Research

| Item | Value |
|---|---|
| NIFTY spot range (11-Aug) | 24,430 - 24,490 (narrow day) |
| Close prev session | 24,583.8 |
| Max pain (11-Aug expiry) | 24,450 |
| Spot at last tick | 24,447 (~3 pts from max pain = PINNED) |
| PCR (OI) | 0.749, PCR-chg -0.339 (falling = call heavy) |
| OI walls | Res: 24500 (440K CE OI!), 24600; Sup: 24450, 24400 |
| 24500 CE OI build | +379K OI (+615%) — massive call writing = ceiling |
| Murarkar matrix | OI up + PCR down = CALL HEAVY, watch cap at 24500 |
| India VIX | 12.01 (NORMAL regime boundary 12-16) |
| Expected daily move | 24460 x (12.015/100)/sqrt(252) = ±185 pts |
| Master brain verdict | RECOMMENDED_BULLISH_CALL, conf HIGH (ML ensemble 0.58; FOMO warning: already +100pts from breakout 24400) |

**Takeaway:** Textbook expiry-day pinning — spot drifted to max pain, capped by the
24500 call wall. Call-heavy structure + VIX NORMAL + ML mildly bullish = "buy dips,
not chase" context.

---

## 2. IV Surface Reconstructed from Ticks (Black-Scholes, vectorized Newton)

IV field in the stream is NULL; IV below is reconstructed from bid/ask mid + spot
(rate 6.5%, T to 11-Aug 15:30). Absolute expiry-day IV is unstable (T small); the
RELATIVE structure is the signal.

### 2.1 Day-average IV Smile (moneyness buckets)

| Moneyness | CE mean IV | PE mean IV |
|---|---|---|
| < -3.5% | 150% | 115% |
| -3.5..-2% | 92% | 51% |
| -2..-1% | 59% | 33% |
| -1..-0.5% | 39% | 25% |
| ATM | 28.6% | 19.8% |
| +0.5..1% | 28.3% | 3.5%* |
| +1..2% | 35.3% | 0.2%* |
| +2..3.5% | 53.5% | 0.1%* |
| > +3.5% | 106% | 17%* |

*PE strikes above spot = worthless puts at ₹0.05-0.10 min-tick; IV there is a
min-tick artifact, not signal. Both wings rich = classic expiry-day smile.

### 2.2 Skew Slopes (IV vs moneyness, per 30-min)

| Time | Put skew slope | Call skew slope |
|---|---|---|
| 09:30 | -9.55 | +4.19 |
| 10:00 | -9.92 | +4.00 |
| 11:30 | -12.44 | +4.64 |
| 12:00 | -13.18 | +4.71 |
| 12:30 | -13.98 | +5.35 |
| 13:00 | -15.18 | +5.29 |

Negative put slope = put IV RISES as strikes go deeper OTM (put smirk). Positive
call slope = call IV RISES going OTM (call wing rich). The call wing kept STEEPENING
into the close — retail call-lottery flow.

### 2.3 IV Skew Ratio (OTM Put IV / OTM Call IV, 1-1.5% OTM)

- 0.970 -> 0.963 -> 0.925 -> 0.932 -> 0.959 -> 0.955 (all < 1 = CALL-SKEWED all day)
- Reconstructed risk-reversal IV(OTM put) - IV(OTM call) ~ -3 to -4 vol pts.
- corr(dSpot, dSkewRatio) = +0.77 (small n, flag as weak).

**Verdict:** This expiry day was call-skewed at the ATM/near-ATM layer — opposite
of the permanent deep-OTM put smirk. Consistent with Indian-platform literature:
"when call IV > put IV in Nifty expiry => upside panic hedging / call-heavy gamma"
(5paisa, StockMojo). India skew is much flatter than US (25d ~2-6 vol pts vs SPX
10-20), weeklies steeper than monthlies.

---

## 3. Microstructure Analysis (order book / execution reality)

### 3.1 Bid-Ask Spreads

- ATM spread ~0.13-0.15 pts (0.3% of premium) — TIGHT, tradeable.
- Average absolute spread by time: 3.6 (10-11) -> 4.7 (11-12) -> 11.0 (12-13) -> 16.0 (13-13:16) pts.
- Relative spread: 8% (morning) -> 27% (afternoon) — widens into expiry.
- OTM (+2-3.5%) relative spreads: 13% (CE) to 30-59% (PE) — UNTRADEABLE for retail.

### 3.2 No-Arbitrage Tests

| Test | Result |
|---|---|
| Butterfly convexity (mid, ATM band) | 0 violations — static no-arb HOLDS |
| Put-call parity implied F | std 0.2-0.3 pts across strikes — parity HOLDS |
| Futures basis (F - spot, PCP implied) | +10.6 -> +13.6 pts (positive carry) |
| Box / conversion arb | Dead after 0.2-0.3 pt parity + friction |

### 3.3 Liquidity Halo

Only ATM +/-1.5% is liquid. Any multi-leg skew structure crosses 3-4 books; round-trip
cost ~5-15 pts/lot (75 lot). This single fact kills most textbook skew-arb on weeklies.

---

## 4. IV Skew Arbitrage Models — The Matrix (web-researched, verified)

### 4.1 Risk Reversal (skew carry)
- **Construction:** Buy 25d call, sell 25d put (same expiry). Put-skewed Nifty = net credit.
- **Payoff:** P_T = max(S-Kc,0) - max(Kp-S,0); credit = C - P < 0. Delta-hedge with futures for carry.
- **Entry:** RR z-score > +1.5s (puts rich); exit on mean-reversion or 50% premium decay; stop on spot < Kp.
- **Nifty verdict:** Thin — 25d skew only 2-6 vol pts; weekly credit small; costs eat half. Monthly better.

### 4.2 Put-Skew Mean Reversion (credit spreads)
- **Construction:** z_t = (Skew_t - Skew_20bar)/s. z>+2 => sell rich OTM puts via put credit spreads; z<-1 => buy cheap puts.
- **Payoff (put credit spread):** max profit = credit; max loss = Ks - Kl + credit (defined risk).
- **Nifty verdict:** MOST tradeable retail skew trade; equalize by DELTA not distance; widen wing one strike.

### 4.3 Ratio Backspread (1x2 put ratio)
- Payoff: S>=Kl => +c; Ks<S<Kl => c + (Kl-S); S<=Ks => c + (Kl-S) - 2(Ks-S).
- **Verdict:** Post-panic high-IV regimes only; margin on 2 short lots; monthly only.

### 4.4 Butterfly / Convexity (Breeden-Litzenberger)
- B = C(K-d) - 2C(K) + C(K+d) = d^2 * d2C/dK2 = e^{-rT} q(K) >= 0.
- Buy cheap butterflies = RND fattening; sell = flattening. **Verdict:** 0 arb found on our data; dead on weeklies net of costs; occasionally monthly pre-event.

### 4.5 Calendar / Diagonal Skew
- Sell front-month skew-rich, buy back-month; theta(T) must be non-decreasing (else arb). Weekly vs monthly skew gap is real.
- **Verdict:** Tradeable but front-leg gamma must be managed (expiry-Tuesday).

### 4.6 Box / Parity
- Box = C(K1)-C(K2)+P(K2)-P(K1) = PV(K2-K1). **Verdict:** DEAD on NSE (parity holds to 0.2-0.3 pts; conversion not worth it post-STT).

### 4.7 SSVI/SVI no-arb (Gatheral)
- Static-arb-free surface requires butterfly-arb-free slices: no mid-price violations found => NSE surface is statically admissible; use SVI to INTERPOLATE strikes, not to trade violations.

### 4.8 Dispersion Trading
- Index IV vs weighted constituent IV/realized. **Verdict:** Not retail-tradeable (needs 50 legs).

### 4.9 VPIN / Toxicity
- VPIN = sum|Vbuy-Vsell|/(nV), BVC-bucketed. High VPIN = adverse selection. **Verdict:** flow descriptor only (Andersen-Bondarenko critique); expiry-afternoon ATM toxicity spikes are real.

---

## 5. Empirical / Regime Gate

- SEBI (2024-25): ~89-91% retail F&O traders lose; FY25 retail F&O losses ~Rs 1.06 lakh crore; ~96% of profits to algo traders.
- NIFTY IV > realized ~70% of time (VRP exists); vendors claim short-vol ~20-28% ann, Sharpe 1.0-1.3, win ~70% (MARKETING-GRADE — verify independently; no peer-reviewed numbers for skew-arb on NIFTY weeklies exist).
- VIX regime gate (research-backed, in AGENTS.md): <12 buy vol; 12-16 normal; 16-20 start selling; 20-25 sell aggressive; >25 panic mean-revert.
- Expected move = NIFTY x (VIX/100)/sqrt(252) = ±185 pts @ VIX 12.

---

## 6. Practical Verdict (Hinglish)

**Kya kaam karta hai NIFTY weekly pe:**
1. VIX/IV-rank-gated premium SELLING (credit spreads / iron condors) — only well-documented structural edge; expiry-day IV-crush is your friend (sell morning, cover 12-2 PM crush).
2. Put-skew z-score mean-reversion via put credit spreads — defined risk, tradeable.
3. Calendar skew (sell front, buy back) — manage Tuesday-expiry gamma.
4. Expiry-day flow tactics (ATM gamma into 2:30 PM; fade max-pain pinning; avoid buying far OTM lottery).

**Kya nahi chalta:** box/parity arb, naked butterfly convexity, dispersion, koi bhi "guaranteed" 25d skew carry. Expiry-day call-skew = microstructure noise, edge nahi. Kisi bhi vendor ke Sharpe/win-rate ko independent backtest se verify karo.

**Cost reality (post-2025 SEBI):** lot 75; STT 0.1% sell premium; +2% ELM expiry day; calendar margin removed on expiry; multi-leg friction 5-15 pts/lot. Sirf credit-collecting defined-risk structures survive.

---

## 7. Quant Files / Artifacts

- `/tmp/opencode/micro_skew_analysis.py` — IV reconstruction, smile, skew ratio/slopes, spreads, depth, volume.
- `/tmp/opencode/noarb_check.py` — butterfly convexity, PCP implied F, risk-reversal per 30-min.
- Findings recorded in `AGENTS.md` (IV Skew & Microstructure findings section).

## 8. Risk Rules Applied (hard)

1% per trade max; stop 1.5x ATR; 3% daily / 7% weekly kill; no averaging down; defined-risk only; expiry day no entries after 14:30, square by 15:05; RANGE_LV = NO TRADE. VIX PANIC = no trade.
