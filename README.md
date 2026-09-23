# Gaming PC Cost Index

How much more does a gaming PC cost because of the AI memory boom, and who can make money on it?

**Status:** in progress (week 1 of 5, framing and data sourcing). Findings below will be filled in as the analysis is done.

**Tools:** Python (pandas) · Excel · Power BI

---

## Business problem

Since late 2025 memory makers have been moving production capacity to HBM and server DRAM for AI data centers. Consumer RAM and SSDs got scarce and expensive, and it shows up in the final price of a gaming PC.

This project tracks the cost of three typical gaming builds from January 2024 to today in two markets, Russia (RUB) and global (USD), and answers four questions:

1. How much did each build get more expensive, and which components drove it?
2. Does the Russian market follow the global one, and what role do the ruble and parallel imports play?
3. Can contract DRAM prices tell you in advance when retail prices will move?
4. What business opportunity does expensive hardware open up, and does its unit economics work?

## Executive summary

_To be written after the analysis (week 3–4). Planned format: 3–4 key numbers, one chart, one recommendation._

| Metric | Budget | Mid | High-end |
|---|---|---|---|
| Build cost, Jan 2024 | – | – | – |
| Build cost, latest | – | – | – |
| Change, % | – | – | – |
| Memory share of cost (RAM + SSD) | – | – | – |

## Reference builds

Prices are tracked per component class, not a single SKU, so the series survives when a model goes out of stock. Full list: [`data/reference/builds.csv`](data/reference/builds.csv).

| Component | Budget (1080p) | Mid (1440p) | High-end (4K) |
|---|---|---|---|
| CPU | Ryzen 5 7500F | Ryzen 5 9600X | Ryzen 7 9800X3D |
| GPU | RTX 5060 8 GB | RTX 5070 12 GB | RTX 5080 16 GB |
| RAM | 16 GB DDR5-6000 | 32 GB DDR5-6000 | 32 GB DDR5-6000 CL30 |
| SSD | 1 TB NVMe Gen4 | 2 TB NVMe Gen4 | 2 TB NVMe Gen4 (high-end) |
| Motherboard | B650 mATX | B650 ATX | X870 ATX |
| PSU | 650 W Bronze | 750 W Gold | 850 W Gold |
| Case | mATX airflow | ATX airflow | ATX airflow |

## Data

| Source | What | Market |
|---|---|---|
| Retail price archives | Monthly component prices | RU, global |
| TrendForce / DRAMeXchange | Contract and spot DRAM prices | global |
| Central Bank of Russia | USD/RUB exchange rate | RU |
| Samsung, SK hynix, Micron reports | Capacity, capex, HBM share | global |

The detailed list with links and collection method will be in `docs/data_sources.md`.

## Approach

1. Collect monthly prices for every component class in both markets.
2. Build a cost index for each build (Jan 2024 = 100) and break the change down by component.
3. Compare RUB and USD indices with and without the exchange rate effect.
4. Check the lag between contract DRAM prices and retail RAM prices.
5. Pick one business opportunity, size the market and model unit economics with a sensitivity analysis.

More detail: [project brief](docs/project_brief.md).

## Repository structure

```
data/raw/          source data as collected
data/processed/    cleaned monthly datasets
data/reference/    reference builds
docs/              brief, data sources, methodology
notebooks/         analysis
src/               collection and cleaning scripts
reports/           dashboard and deck
```

## Limitations

- Historical retail prices for Russia are patchy, so some months are reconstructed from archive snapshots.
- A fixed set of builds does not reflect how people actually change their purchases when prices go up.
- The business case is based on stated assumptions, not company data.

## Author

[tomskboy](https://github.com/tomskboy). Feedback and questions are welcome in Issues.
