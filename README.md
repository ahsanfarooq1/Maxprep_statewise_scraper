# MaxPreps Statewise Scraper

Scrapes high-school basketball box scores from MaxPreps for a whole state and
season, and accumulates them into one per-player season stat file.

## ⚠️ MaxPreps geo-blocks some countries

MaxPreps returns a `403 - Geo-block` page to requests from certain countries.
This is **genuinely geographic**, not bot detection:

* A VPN with an allowed exit IP fixes it — for browsers *and* scripts.
* Without one, even a real headless Chrome is blocked.
* Header tweaks and TLS impersonation (`curl_cffi`) do **not** help.

A **browser VPN extension is not enough** — it only routes the browser's own
traffic, so Python still exits via your real IP. Use a **system-wide VPN
client** (or run the scraper on a host in an allowed region).

Quick check that the scraper can reach MaxPreps:

```bash
python test_live_box_score.py
```

It prints the raw HTTP status and says plainly if you're geo-blocked.

## Pipeline

`APP/pipeline.py` runs four stages in order:

| # | Stage | Script | Output |
|---|-------|--------|--------|
| 1 | Gap finder — enumerate teams, check every game | `app.py --gap-only` | `{state}_data_gaps_{sport}_{season}.json` |
| 2 | Season stats tab for every team | `accumulate_from_stats_tab.py` | `{state}_all_stats_tab_{sport}_{season}.json` |
| 3 | Per-game box scores | `scrape_box_scores.py` | `{state}_box_scores_{sport}_{season}.json` |
| 4 | Accumulate + merge + repair TotalGamesChecked | `Accumulation_data.py`, `merge_all_stats_tab.py`, `fix_total_games_checked.py` | `Final_scraped_data/Final_{state}_accumulated_{sport}_{ss}.json` |

Downstream consumers should read only the stage-4 `Final_*` file.

### Run it

```bash
python -m APP.pipeline --state CO --sport boys --season 2025-2026
```

Useful flags: `--workers N`, `--start-at N`, `--end-at N` (resume a single
stage), `--output-dir DIR`.

### Streamlit UI

```bash
streamlit run streamlit_app.py
```

Wraps the pipeline as a subprocess and renders live progress.

## Resuming

Every stage records processed teams in its output file and skips them on a
re-run. **This also means a re-run after a parser fix will do nothing** — the
old file still lists every team as processed. Move or delete the affected
state's output files first to force a genuine re-scrape.

## Team master lists

`boys_basketball_all_states*.json` / `girls_basketball_all_states*.json` are
tracked because the scraper needs them at runtime — to enumerate a state's
teams and to resolve opponents to canonical names/ids. The `_25-26` variants
are preferred when present; the un-suffixed files are the fallback.
Regenerate with `state_teams_counter.py`.

Scraped output is **not** tracked (see `.gitignore`) — a full set runs to
several GB and single files can exceed GitHub's 100 MB limit.

## Notes on MaxPreps' 2026 redesign

Game pages became tabbed (Recap/Stats/Roster/Matchup) React Server Components:

* Player stats render only under `?tab=stats`; the default Recap view has none.
* The HTML shows only **one** team (a client-side switcher picks it), so stats
  are read from the page's embedded Next.js RSC payload instead — it carries
  **both** teams, and each player's athlete link identifies their school, which
  makes team attribution deterministic.
* Game URLs are now `/{state}/{sport}[/{gender}]/game/{a}-vs-{b}/{date}/`.

MaxPreps' own data is often partial — listed players' points can sum to less
than the team total they publish. That's upstream, not a parsing error.
