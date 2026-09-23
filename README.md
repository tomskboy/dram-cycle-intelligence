# Gaming PC Cost Index: how the AI boom reshapes the PC hardware market

A strategy and market analysis project. It measures how the AI-driven memory
supercycle changed the cost of a gaming PC in Russia and globally, and assesses
which business opportunities this creates.

> 🚧 Work in progress. See the [project brief](docs/project_brief.md) for the
> problem statement, hypotheses, scope and roadmap.

## Key question

How much has the cost of a gaming PC changed because of the AI boom, how does
this differ between Russia (RUB) and the global market (USD), and which
business opportunities does it create?

## Approach

1. **Market analysis**: monthly price index for 3 reference builds
   ([builds.csv](data/reference/builds.csv)), broken down by component
2. **Russia vs global**: effect of the exchange rate and parallel imports
3. **Leading indicators**: do contract DRAM prices predict retail prices?
4. **Business case**: market sizing and unit economics of one new venture

## Repository structure

```
data/
  raw/          # source data as collected
  processed/    # cleaned monthly datasets
  reference/    # reference builds and lookup tables
docs/           # project brief, methodology, data sources
notebooks/      # analysis notebooks
src/            # data collection and processing scripts
reports/        # dashboard exports and strategy deck
```

## Stack

Python (pandas) · Excel · Power BI / Tableau
