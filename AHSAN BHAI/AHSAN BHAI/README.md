# HS Basketball Box Score Scraper

Scrapes MaxPreps box scores for every team listed in a state **data gaps** file. Output is JSON compatible with `Accumulation_data.py`.

---

## Files you need

| File | Role |
|------|------|
| `scrape_box_scores.py` | Scraper script |
| `{state}_data_gaps_{sport}_{season}.json` | **Input** — team list (from gap finder) |
| `{state}_box_scores_{sport}_{season}.json` | **Output** — scraped games (created by script) |
| `boys_basketball_all_states.json` or `girls_basketball_all_states.json` | Opponent lookup index (auto-loaded) |
| `requirements.txt` | Python dependencies |

**Example (NM boys 2025-2026):**
- Input: `nm_data_gaps_boys_2025_2026.json`
- Output: `nm_box_scores_boys_2025_2026.json`

---

## Setup

```powershell
pip install -r requirements.txt
```

Requires **Python 3.10+**, system **curl** (built into Windows 10+), and a **US VPN** if you are outside the US (MaxPreps geo-blocks some regions with **403**).

---

## Usage

### Test run (first 5 teams)

```powershell
python scrape_box_scores.py --state NM --sport boys --season 2025-2026 --input nm_data_gaps_boys_2025_2026.json --output nm_box_scores_boys_2025_2026.json --workers 2 --limit 5 --no-accumulate
```

### Continue remaining teams (resume)

Same command **without** `--limit`. Already-processed teams are skipped automatically:

```powershell
python scrape_box_scores.py --state NM --sport boys --season 2025-2026 --input nm_data_gaps_boys_2025_2026.json --output nm_box_scores_boys_2025_2026.json --workers 2 --no-accumulate
```

### Full run (all teams, faster)

```powershell
python scrape_box_scores.py --state NM --sport boys --season 2025-2026 --input nm_data_gaps_boys_2025_2026.json --output nm_box_scores_boys_2025_2026.json --workers 15 --no-accumulate
```

---

## Resume

- Progress is saved in the **output file** under `meta.processedTeams`.
- Saves every 10 teams and at the end.
- **Interrupted?** Re-run the same command — it continues where it left off.
- **Do not delete** the output file if you want to resume.
- Errored teams are re-queued on the next run.
- **Fresh start:** delete or rename the output file, then run again.

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--state` | State code (e.g. `NM`, `TX`) |
| `--sport` | `boys` or `girls` |
| `--season` | e.g. `2025-2026` |
| `--input` | Path to gaps JSON |
| `--output` | Path to box scores JSON (default: input name with `data_gaps` → `box_scores`) |
| `--workers` | Parallel teams (default: 15) |
| `--limit N` | Process only first N teams (testing) |
| `--no-accumulate` | Skip auto-run of `Accumulation_data.py` |

---

## Output format

```json
{
  "meta": {
    "totalGames": 189,
    "totalTeams": 163,
    "processedTeams": ["nm/albuquerque/la-cueva-bears/basketball", "..."],
    "errors": [],
    "last_updated": "2026-08-18 14:21:21"
  },
  "games": [
    {
      "contest_id": "...",
      "game_url": "https://www.maxpreps.com/...",
      "game_date": "12-5-2025",
      "team": { "team_id": "...", "team_name": "..." },
      "opponent": { "team_id": "...", "team_name": "..." },
      "shooting": { "team": { "players": [...] }, "opponent": { "players": [...] } },
      "detailed_shooting": { ... },
      "totals": { ... },
      "misc": { ... }
    }
  ]
}
```

Each game record is from the **scraped team’s perspective** (`team` = that team, `opponent` = other team).

---

## How it works

1. Loads teams from the gaps input file.
2. Fetches each team’s schedule from MaxPreps.
3. Scrapes each game’s **Stats** tab (player shooting, totals, misc).
4. Uses **curl_cffi** (Chrome TLS impersonation) with **system curl** fallback — plain `requests` is not used (MaxPreps returns **406**).
5. Writes JSON output; optionally chains `Accumulation_data.py` (omit `--no-accumulate` to enable).

---

## What to expect in the data

- The script **tries to capture both teams** per game (`team` + `opponent` player stats).
- On MaxPreps’ current layout, **often only one side** is available per fetch; both sides appear when the embedded RSC payload includes both teams.
- The same game may appear **more than once** (once per team’s schedule) with different `team`/`opponent` labels.
- Player **stats (points, FG, etc.)** match the live MaxPreps pages; names may be full (`Drew Bramlett`) or abbreviated (`D. Bramlett`).

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `403 Geo-block` | IP outside allowed region | Connect **US VPN**, confirm maxpreps.com loads in browser |
| `Build ID not found` | Usually geo-block or network | VPN + re-run |
| `406 Not Acceptable` | Bot fingerprint (old clients) | Use current script (`curl_cffi` + curl fallback) |
| Slow / rate limits | Too many parallel workers | Lower `--workers` (e.g. 2) |
| Teams skipped | Already in `processedTeams` | Normal resume behavior; delete output to re-scrape all |

---

## Optional: accumulation step

After box scores are scraped, run accumulation manually or omit `--no-accumulate`:

```powershell
python Accumulation_data.py
```

Output file name: replace `box_scores` with `accumulated_stats` in the output path.
