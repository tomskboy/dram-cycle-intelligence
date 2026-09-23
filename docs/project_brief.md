# Project brief: Gaming PC Cost Index

Draft, September 2026.

## 1. Problem

Since late 2025 the AI buildout has been absorbing memory production capacity
(HBM and server DDR5). Memory makers shifted wafers away from consumer DRAM and
NAND, and prices for RAM, SSDs and, partly, GPUs rose sharply. For gamers this
means a more expensive PC; for retailers, system integrators and gaming clubs it
means pressure on margins and on demand.

**Key question:** How much has the cost of a gaming PC changed because of the AI
boom, how does this differ between Russia and the global market, and which
business opportunities does it create?

## 2. Hypotheses

| # | Hypothesis | How we test it |
|---|------------|----------------|
| H1 | Memory (RAM + SSD) share of a typical build cost has grown significantly since 2025 | Build cost index by component |
| H2 | In Russia the price rise comes with a lag and is amplified or dampened by the RUB exchange rate and parallel imports | Compare USD and RUB indices, adjusted for FX |
| H3 | Contract DRAM prices (TrendForce) lead retail prices by 1–3 months, so they can be used as a "when to buy" signal | Lag correlation between contract and retail prices |
| H4 | Expensive new hardware increases demand for alternatives: used/refurbished PCs, PC rental, cloud gaming | Market sizing + unit economics of one selected venture |

## 3. Scope

**In scope**
- 3 reference builds (budget / mid / high-end), see `data/reference/builds.csv`
- Two markets: Russia (RUB) and global (USD)
- Period: January 2024 to today, monthly granularity
- One business case (new venture) with market sizing and unit economics

**Out of scope**
- Laptops and consoles
- Daily price forecasting / ML models
- Peripherals (monitors, keyboards, etc.)

## 4. Deliverables

1. **Dataset**: cleaned monthly component prices for both markets (`data/processed/`)
2. **Dashboard**: Power BI / Tableau, build cost index, component shares, RUB vs USD
3. **Strategy deck**: 10–12 slides, market analysis, conclusions, business case, recommendation
4. **README**: one-page summary with key findings and screenshots

## 5. Roadmap

| Week | Milestone | Output |
|------|-----------|--------|
| 1 | Framing & data sourcing | Brief, reference builds, list of data sources |
| 2 | Data collection & cleaning | Monthly price dataset, both markets |
| 3 | Analysis (H1–H3) | Build cost index, lag analysis, notebook |
| 4 | Business case (H4) | Market sizing, unit economics model |
| 5 | Packaging | Dashboard, deck, final README |

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| No clean historical retail prices for Russia | High | Combine price-archive sites, Wayback Machine snapshots, own collection going forward |
| Specific SKUs disappear from sale | Medium | Track component class (e.g. "32 GB DDR5-6000 kit"), not one SKU |
| Business case relies on assumptions | Medium | State all assumptions explicitly, run sensitivity analysis |
