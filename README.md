# `data` branch

This branch holds the daily-scraped MaxPreps data, committed automatically by
the `.github/workflows/daily-scrape.yml` workflow on `master`.

It is intentionally a **separate branch from `master`** so that automated
daily data commits never trigger a Streamlit Cloud redeploy (which watches
`master` for code changes) — this branch is data-only, decoupled from the
app's own deploy cycle.

## Layout

Each state gets its own folder (matching the naming already used on `master`
for the 25-26 season data, e.g. `Oregon_scraped_data/`), containing the 4
pipeline outputs per sport for the current season:

- `{state}_data_gaps_{sport}_{season}.json` — persisted (used for per-game
  incremental caching on the next run)
- `{state}_box_scores_{sport}_{season}.json` — persisted (same reason;
  this is the expensive-to-regenerate file)
- `{state}_all_stats_tab_{sport}_{season}.json` — NOT persisted between runs
  by design (cheap to regenerate fully every time, one request per team)
- `Final_{state}_accumulated_{sport}_{ss}.json` — the deliverable; also
  regenerated fresh each run from the other three

## Do not commit code changes here

Code lives on `master`. This branch should only ever receive automated data
commits from the workflow (or a manual `workflow_dispatch` run of it).
