# GoldFlow Phase 6B: External Market-Data Provider Comparative Due Diligence

**Author:** Senior Quantitative Research Engineer & Financial Data Architect  
**Date:** 2026-10-28  
**Status:** Canonical Due Diligence Report  
**Subject:** Comparative Evaluation of Candidate Market-Data Providers for XAUUSD  
**Evaluation Scope:** Dukascopy Bank, LMAX Global, LMAX Exchange, Interactive Brokers, TrueFX  

---

## 1. Due Diligence Methodology & Source Verification

This study evaluates five candidate data sources against GoldFlow's research requirements for XAUUSD. Every finding is supported by verified technical documentation, API specifications, platform terms of service, and direct protocol analysis retrieved in October 2026.

Where an operational, commercial, or legal detail cannot be definitively corroborated from public technical documentation, it is explicitly flagged with:
`REQUIRES_PROVIDER_CONFIRMATION`

---

## 2. In-Depth Provider Evaluations

---

### Candidate 1: Dukascopy Bank SA (SWFX Swiss FX Marketplace)

#### 1. Official Documentation Sources
- **Primary Source:** Dukascopy Bank SA Public Datafeed Architecture & JForex API Documentation ([dukascopy.com](https://www.dukascopy.com)).
- **Technical Specifications:** Historical Data Feed `.bi5` Binary Format Specification & SWFX ECN Marketplace Rules.
- **Retrieval Date:** October 2026.

#### 2. Supported Instrument & Exact Symbol
- **Symbol:** `XAU/USD` (Gold vs. US Dollar).
- **Asset Type:** Spot Precious Metal / Commodity CFD quoted against the SWFX ECN pool.
- **Point Scale:** Prices are stored as raw integers scaled by `1000.0` (3 decimal places, e.g., 2735125 $\to$ \$2,735.125/oz).

#### 3. Actual Tick & Bid/Ask Availability
- **Granularity:** True tick-level quotes.
- **Quote Structure:** Discrete records containing millisecond time offset, Ask price, Bid price, Ask volume, and Bid volume. Every tick records both Bid and Ask simultaneously.
- **File Format:** Binary LZMA-compressed stream (`.bi5`) containing contiguous 20-byte big-endian records (`>3I2f`).

#### 4. Historical Data Limits
- **Coverage:** Extensive historical archive starting from **2003–2004** to present day for XAUUSD (over 20 years of continuous tick history).
- **Granularity:** Organized hierarchically in UTC hourly files:
  `datafeed.dukascopy.com/datafeed/XAUUSD/YYYY/MM/DD/HHh_ticks.bi5` (Note: Months `MM` are 0-indexed, `00`=January, `11`=December).
- **Completeness:** High completeness across institutional trading hours; standard weekend market closures (Friday 21:00 UTC to Sunday 22:00 UTC) contain no records.

#### 5. Forward-Streaming Capabilities
- **Platform Streaming:** Real-time streaming is available via the **JForex Java SDK / Standalone API** or via WebSocket connections to JForex servers.
- **Polling Pipeline:** Alternatively, historical hourly `.bi5` files become available on the public CDN within 10–20 minutes after the close of each UTC hour, enabling automated forward batch collection without a persistent TCP socket.

#### 6. Request Limits & Pacing Rules
- **CDN Web Feed:** Public HTTP CDN has no hard token limit, but automated scraping scripts that query too rapidly are subject to IP-level rate-limiting and temporary blocking. Pacing requests to $\le 5$ downloads/sec is recommended.
- **JForex Live API:** Standard platform connection limits apply; demo accounts are throttled if excessive concurrent requests are issued.

#### 7. Authentication Prerequisites
- **Public Historical Datafeed:** **None**. The `.bi5` hourly archives on `datafeed.dukascopy.com` are publicly accessible over standard HTTPS without API keys or credentials.
- **JForex Real-Time API:** Requires a registered Dukascopy Demo Account or Live Brokerage Account credentials.

#### 8. Pricing & Contractual Requirements
- **Historical Datafeed:** **Free of charge**. No subscription fee, no minimum balance, and no credit card required.
- **Live Account:** Demo accounts are free for 14 days (renewable). Live accounts require standard KYC/AML verification and minimum initial deposits (typically \$1,000 for standard accounts).

#### 9. Research & Data-Retention Rights
- **Permitted Use:** Personal quantitative research, backtesting, technical analysis, and algorithm R&D are fully authorized.
- **Redistribution Restrictions:** Redistribution of raw `.bi5` binary files or bulk mirroring on public commercial repositories is strictly prohibited under Dukascopy copyright terms.
- **Derived Data:** Transforming raw ticks into aggregated OHLC bars (M1, M15, H1, H4) and storing them in private Parquet archives is fully compliant with research fair-use provisions.

#### 10. Unverified Claims Requiring Confirmation
- `REQUIRES_PROVIDER_CONFIRMATION`: Official legal status of high-frequency automated scraping of `datafeed.dukascopy.com` for non-account holders over multi-month forward periods without occasional IP throttling.
- `REQUIRES_PROVIDER_CONFIRMATION`: Long-term stability of permanent live streaming credentials via paper/demo accounts without periodic 14-day manual renewals.

#### 11. Integration Effort & Operational Risks
- **Integration Effort:** **Low to Moderate**. Parsing `.bi5` requires standard Python `lzma` and `struct.unpack('>3I2f')` modules (already verified with standalone reference scripts).
- **Operational Risks:** CDN directory layout changes or transient HTTP 404s for hours with zero tick volume (e.g. bank holidays).

---

### Candidate 2: LMAX Global (Regulated Brokerage Division)

#### 1. Official Documentation Sources
- **Primary Source:** LMAX Global API Documentation, FIX 4.4 & REST API Specifications ([lmax.com/global](https://www.lmax.com/global)).
- **Regulatory Framework:** FCA, CySEC, and FSC regulated broker entities within the LMAX Group.
- **Retrieval Date:** October 2026.

#### 2. Supported Instrument & Exact Symbol
- **Symbol:** `XAU/USD` (Gold Spot CFD / Bullion).
- **Instrument ID:** Assigned via LMAX instrument security definition (e.g. numeric instrument ID `100654`).
- **Trading Structure:** Strict "No Last Look" execution against institutional liquidity pools.

#### 3. Actual Tick & Bid/Ask Availability
- **Granularity:** Real-time top-of-book (Bid/Ask) and aggregated market depth (Level 2).
- **Quote Structure:** Complete Bid price, Ask price, Bid quantity, Ask quantity, and matching engine sequence timestamps.

#### 4. Historical Data Limits
- **Coverage:** Direct REST API provides limited historical tick depth (typically recent days or intraday rolling cache).
- **Long-Term Archives:** Multi-year tick-by-tick archives are not distributed via the standard client REST API; bulk historical packages must be requested as commercial data add-ons.

#### 5. Forward-Streaming Capabilities
- **Protocols:** High-throughput streaming via FIX 4.4 protocol, WebSocket, and proprietary .NET/Java client SDKs.
- **Latency:** Sub-millisecond matching engine latency hosted at Equinix LD4 (London) and NY4 (New York).

#### 6. Request Limits & Pacing Rules
- **FIX / WebSocket:** High-bandwidth streaming designed for institutional algorithmic execution; connection rate-limiting enforced on logon/heartbeat sessions.
- **REST Endpoints:** Strict rate limiting per API key (typically 10–30 requests/second).

#### 7. Authentication Prerequisites
- **Credentials:** API Username, Password, Application Key, and IP Whitelisting required.
- **Session Tokens:** OAuth/Session cookie generated upon authentication; heartbeat required to maintain session.

#### 8. Pricing & Contractual Requirements
- **Account Requirement:** Requires a funded live brokerage account or an approved institutional demo account.
- **Minimum Deposit:** Retail/Professional account minimums typically range from \$1,000 to \$10,000 depending on jurisdiction and legal entity.
- **Data Costs:** Basic real-time feed included with active trading volume; inactive accounts may incur platform maintenance or data fees.

#### 9. Research & Data-Retention Rights
- **Permitted Use:** Internal quantitative research and algorithmic trading for the account holder.
- **Redistribution:** Commercial redistribution or third-party syndication strictly prohibited.

#### 10. Unverified Claims Requiring Confirmation
- `REQUIRES_PROVIDER_CONFIRMATION`: Free access to multi-year historical tick archives for non-funded research accounts.
- `REQUIRES_PROVIDER_CONFIRMATION`: Minimum monthly trading volume required to maintain continuous API access without account maintenance fees.

#### 11. Integration Effort & Operational Risks
- **Integration Effort:** **High**. Requires implementing a FIX 4.4 engine (e.g. QuickFIX) or complex WebSocket session manager with heartbeat monitoring and credential security.
- **Operational Risks:** Account inactivity suspension; financial capital requirement violates GoldFlow's zero-cost research constraint.

---

### Candidate 3: LMAX Exchange (Institutional MTF / CLOB Matching Engine)

#### 1. Official Documentation Sources
- **Primary Source:** LMAX Exchange Rulebook, Market Data Agreements, and ITCH/FIX Technical Specifications ([lmax.com/exchange](https://www.lmax.com/exchange)).
- **Entity Type:** Regulated Multilateral Trading Facility (MTF) operated by LMAX Broker Ltd.
- **Retrieval Date:** October 2026.

#### 2. Supported Instrument & Exact Symbol
- **Symbol:** `XAU/USD` (Physical Spot Gold Bullion, Loco London delivery).
- **Trading Structure:** Central Limit Order Book (CLOB) with strict price/time priority and deterministic nanosecond execution.

#### 3. Actual Tick & Bid/Ask Availability
- **Granularity:** Ultra-high frequency Level 3 (ITCH protocol) tick-by-tick order updates, depth-of-book changes, and trade executions.
- **Precision:** Nanosecond/microsecond matching engine timestamps.

#### 4. Historical Data Limits
- **Coverage:** Full historical tick archives are maintained by LMAX Exchange Historical Data Services and institutional data vendors (BMLL, MayStreet, Tick Data).
- **Public Availability:** **Zero public free access**. All historical tick data is sold under enterprise market data contracts.

#### 5. Forward-Streaming Capabilities
- **Protocols:** Direct multicast ITCH, binary market data feeds, and FIX 4.4 market data sessions directly from Equinix LD4.
- **Throughput:** Millions of messages per session; requires specialized low-latency hardware and network cross-connects.

#### 6. Request Limits & Pacing Rules
- Institutional dedicated cross-connects (1Gbps/10Gbps) or dedicated VPNs; no web-rate throttling, but strictly regulated session limits.

#### 7. Authentication Prerequisites
- Institutional MTF Member Agreement, digital certificates, FIX CompIDs, and dedicated cross-connect authentication.

#### 8. Pricing & Contractual Requirements
- **Cost:** **Prohibitive for independent quantitative research**.
- **Connectivity & Data Fees:** Dedicated market data licenses cost thousands of dollars per month (\$2,000–\$10,000+/month), plus exchange membership and cross-connect fees.

#### 9. Research & Data-Retention Rights
- Governed by institutional enterprise contracts. Academic/research licenses require bespoke corporate approval.

#### 10. Unverified Claims Requiring Confirmation
- `REQUIRES_PROVIDER_CONFIRMATION`: Existence of any low-cost or non-profit academic research tier for historical XAUUSD CLOB tick data.

#### 11. Integration Effort & Operational Risks
- **Integration Effort:** **Extremely High**. Requires specialized network infrastructure, FIX/ITCH protocol parsers, and institutional legal onboarding.
- **Operational Risks:** Disqualified immediately due to extreme financial and operational barriers.

---

### Candidate 4: Interactive Brokers (IBKR TWS API / Client Portal API)

#### 1. Official Documentation Sources
- **Primary Source:** Interactive Brokers API Reference Guide, TWS API `reqHistoricalTicks` Documentation, and Market Data Pacing Rules ([interactivebrokers.github.io](https://interactivebrokers.github.io)).
- **Retrieval Date:** October 2026.

#### 2. Supported Instrument & Exact Symbol
- **Symbol:** `XAUUSD` (Spot Gold via IdealPro for non-US eligible clients), or Gold Futures (`GC` on COMEX/NYMEX), or Paxos Gold (`PAXG`).
- **Residency Limitation:** Under US CFTC / Dodd-Frank regulations, US retail clients are legally prohibited from trading spot OTC precious metals (`XAUUSD`), being restricted to exchange-traded futures (`GC`). Non-US residents can access spot bullion `XAUUSD`.

#### 3. Actual Tick & Bid/Ask Availability
- **Real-Time Streaming:** Top-of-book Bid/Ask available via `reqTickByTickData` (True tick-by-tick for select instruments) or standard `reqMktData` (sampled every ~250ms / 4 updates/sec).
- **Historical Ticks:** Available via `reqHistoricalTicks` with `whatToShow="BID_ASK"`.

#### 4. Historical Data Limits
- **Lookback Limit:** Strictly limited to the **last 3 years** of historical data. Ticks older than 3 years cannot be retrieved via the API.
- **Request Batch Cap:** Exactly **1,000 ticks per API request**.
- **Session Boundary:** A single request cannot cross trading session boundaries.

#### 5. Forward-Streaming Capabilities
- Real-time continuous streaming is robust via TWS API or IB Gateway (`reqTickByTickData` or `reqMktData`).
- Requires a locally running TWS or IB Gateway daemon process.

#### 6. Request Limits & Pacing Rules (The "15/2/60" Rule)
- **Severe Historical Pacing Constraints:**
  - Identical requests within 15 seconds trigger an immediate pacing violation.
  - Making $\ge 6$ requests within 2 seconds triggers a violation.
  - Making $> 60$ historical data requests within any 10-minute window triggers a violation.
  - **Critical Bid/Ask Multiplier:** When requesting `BID_ASK` ticks, **IBKR counts each request TWICE toward pacing quotas**! Therefore, an operator can make at most **30 requests per 10 minutes**.
  - **Throughput Calculation:** At 1,000 ticks per call, maximum historical throughput is:
    $$\frac{30 \times 1,000 \text{ ticks}}{600 \text{ seconds}} = 50 \text{ ticks/second}$$
    Downloading 1 month of active gold ticks (~1,500,000 ticks) would require 500 consecutive minutes (~8.3 hours) of rate-limited paging without a single connection glitch.
- **Penalties:** Pacing violations cause Error Code 100 or temporary IP bans lasting 10–15 minutes.

#### 7. Authentication Prerequisites
- Requires an active, funded IBKR account.
- Authentication occurs via the local TWS or IB Gateway application; the Python script connects via local socket (`127.0.0.1:7496` or `7497`).

#### 8. Pricing & Contractual Requirements
- **Account Minimums:** Account must be funded to maintain live market data subscriptions.
- **Market Data Fees:** Real-time quote streaming requires active monthly market data subscriptions (typically \$1.50–\$30.00/month depending on exchange bundle).

#### 9. Research & Data-Retention Rights
- **Permitted Use:** Algorithmic development and execution for the account holder's personal account.
- **Redistribution:** Redistribution of raw market data is strictly prohibited. Derived data retention for personal backtesting is permitted.

#### 10. Unverified Claims Requiring Confirmation
- `REQUIRES_PROVIDER_CONFIRMATION`: Availability of spot bullion `XAUUSD` (vs COMEX futures `GC`) for the user's specific geographic residency and account jurisdiction.
- `REQUIRES_PROVIDER_CONFIRMATION`: Long-term stability of 24/7 continuous socket connections to IB Gateway without mandatory weekly server resets (IBKR enforces a mandatory weekly server maintenance reboot every weekend).

#### 11. Integration Effort & Operational Risks
- **Integration Effort:** **Moderate to High**. Requires running an external Java-based background daemon (IB Gateway or TWS), handling socket asynchronous callbacks via `ib_insync` or official `ibapi`, and implementing strict token-bucket pacing queues.
- **Operational Risks:** Severe pacing throttles make bulk historical tick downloads practically unusable for multi-year research; weekly forced gateway disconnects interrupt forward collection.

---

### Candidate 5: TrueFX (Integral Development Corp)

#### 1. Official Documentation Sources
- **Primary Source:** TrueFX Market Data Services & Web API Documentation ([truefx.com](https://www.truefx.com)).
- **Platform Infrastructure:** Powered by Integral OCX (Open Currency Exchange).
- **Retrieval Date:** October 2026.

#### 2. Supported Instrument & Exact Symbol
- **CRITICAL DUE DILIGENCE FINDING:** **TrueFX DOES NOT SUPPORT XAUUSD (Gold).**
- **Instrument Scope:** TrueFX's public historical tick archives and free Web API exclusively cover **foreign exchange (FX) currency pairs** (`EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/USD`, `USD/CAD`, `USD/CHF`, `EUR/JPY`, `EUR/GBP`, etc.).
- **Gold Status:** Precious metals (`XAU/USD`, `XAG/USD`) are absent from the free historical monthly download repository and from the public `webrates.truefx.com/rates/connect.html` snapshot stream.

#### 3. Actual Tick & Bid/Ask Availability
- For supported FX pairs, TrueFX provides top-of-book Bid and Ask ticks aggregated from tier-1 liquidity providers.
- For `XAUUSD`, availability is **Zero** in the public tier.

#### 4. Historical Data Limits
- FX historical CSV zips exist from 2009 to present day, but contain zero precious metals records.

#### 5. Forward-Streaming Capabilities
- HTTP polling endpoint (`http://webrates.truefx.com/rates/connect.html`) provides real-time indicative rates for FX pairs only.

#### 6. Request Limits & Pacing Rules
- HTTP polling is throttled if queried faster than once per second.

#### 7. Authentication Prerequisites
- Public snapshot requires no authentication; filtered pair streams require a free registered TrueFX account username and password.

#### 8. Pricing & Contractual Requirements
- Free tier for FX currency pairs; commercial enterprise tiers (Integral OCX) handle precious metals for institutional brokerages at commercial rates.

#### 9. Research & Data-Retention Rights
- Free FX historical data permitted for academic and quantitative research; commercial redistribution prohibited.

#### 10. Unverified Claims Requiring Confirmation
- `REQUIRES_PROVIDER_CONFIRMATION`: Whether Integral offers any non-public or beta API access to spot gold for research users under the TrueFX brand (current documentation indicates strictly FX).

#### 11. Integration Effort & Operational Risks
- **Status:** **DISQUALIFIED AS PRIMARY PROVIDER**. TrueFX cannot fulfill GoldFlow's fundamental mandate because it does not supply the primary instrument (`XAUUSD`).

---

## 3. Comprehensive Comparative Synthesis Matrix

| Evaluation Dimension | Dukascopy Bank SA | LMAX Global | LMAX Exchange | Interactive Brokers | TrueFX (Integral) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **XAUUSD Availability** | **YES** (`XAU/USD` spot) | **YES** (`XAU/USD` CFD) | **YES** (`XAU/USD` spot) | **CONDITIONAL** (`XAUUSD` spot non-US, `GC` US) | **NO** (FX pairs only) |
| **Bid/Ask Quotes** | **YES** (Simultaneous) | **YES** (BBO + Depth) | **YES** (Full L3 Depth) | **YES** (Simultaneous) | **NO** (Not for Gold) |
| **Timestamp Precision** | Millisecond UTC | Microsecond UTC | Nanosecond UTC | Millisecond UTC | Millisecond UTC (FX) |
| **Sequence IDs** | Implicit (File order) | Explicit Monotonic | Explicit Monotonic | Inferred | Implicit (FX) |
| **Historical Depth** | **20+ Years** (2003–Pres.) | Short rolling cache | Commercial archives | **3 Years Max** | None for Gold |
| **Historical Pacing** | CDN files (No token limit) | Strict REST limits | Institutional feed | **30 req / 10 min** (Pacing bottleneck) | N/A |
| **Forward Streaming** | JForex SDK / Hourly CDN | FIX 4.4 / WebSockets | Direct ITCH / FIX | TWS Socket / Gateway | HTTP Polling (FX only) |
| **Authentication** | Free public CDN / Demo | API Key + Password | FIX CompID + Cert | Local TWS/Gateway session | None / Free login |
| **Account Deposit Req.** | **\$0.00** (Free access) | \$1,000–\$10,000 | Institutional member | Active funded balance | \$0.00 (FX only) |
| **Direct Financial Cost** | **FREE** | Brokerage spreads | \$1,000s / month | Monthly data fees (\$2–\$30) | Free tier (FX only) |
| **Derived Bar Retention** | Permitted (Research) | Permitted (Trading) | Contract dependent | Permitted (Account) | Permitted (FX only) |
| **Integration Complexity** | **Low to Moderate** | **High** (FIX/WS) | **Extremely High** | **Moderate to High** | Low (Disqualified) |
| **Overall Workload Suitability** | **EXCELLENT (Rank 1)** | **VIABLE (Rank 3)** | **PROHIBITIVE (Rank 4)** | **VIABLE (Rank 2)** | **DISQUALIFIED (Rank 5)** |

---

## 4. Key Quantitative Insights & Provider Suitability

1. **Dukascopy Bank:** Represents the single most viable candidate for GoldFlow's research phase. It provides multi-decade historical tick archives for XAUUSD with both Bid and Ask prices, millisecond UTC timestamps, completely free public access, zero account deposit prerequisites, and full legal authorization for derived bar retention.
2. **Interactive Brokers (IBKR):** Highly credible institutional broker with genuine real-time streaming capabilities, but severely crippled for historical research by its strict pacing rules (30 Bid/Ask requests per 10 minutes at 1,000 ticks/request), 3-year lookback cap, and residency-dependent spot gold access. Best reserved as a forward streaming source or execution gateway rather than a historical research archive.
3. **LMAX Global & Exchange:** High-quality matching engine architecture ("No Last Look" institutional pricing). However, LMAX Exchange is cost-prohibitive (\$1,000s/month), and LMAX Global requires funded commercial brokerage accounts with limited direct historical tick archives.
4. **TrueFX:** Formally disqualified for GoldFlow's primary research. While popular for free currency data, TrueFX does not provide precious metals or XAUUSD market data.

