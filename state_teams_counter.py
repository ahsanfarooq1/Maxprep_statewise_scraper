"""
MaxPreps Basketball – All States Team Counter


python state_teams_counter.py --sport girls
Just run these two commands from the project root:

python state_teams_counter.py --sport boys  --season 2024-2025
  
python state_teams_counter.py --sport girls --season 2024-2025

=============================================
Walks MaxPreps' full hierarchy for every US state.
Exposes a run() function to be used by other scripts.

Teams MaxPreps hasn't assigned to any league/region page yet (common for
small/independent schools, and for any school early in a season before
realignment finishes) are invisible to the league-page walk above, in
every season - not just a one-time rollover gap. A dedicated, sport/season-
specific sitemap MaxPreps publishes (Teams-Girls-Varsity-Basketball-Winter-
{years}-N-Sitemap.xml) lists every indexed team page regardless of league
assignment, so it's used here as a ground-truth backfill: any team present
in that sitemap but never found via any league leaf gets added too, with
its real league if its own page reports one for this season, else filed
under a synthetic "Unassigned" region so it isn't silently dropped from
the team list the rest of the pipeline scrapes.
"""

import os
import re
import sys
import json
import time
import argparse
import requests
import concurrent.futures
from collections import defaultdict, Counter
from typing import Optional

DATA_DIR = os.environ.get("DATA_DIR", ".")

# ─── Configuration ────────────────────────────────────────────────────────────

SPORT = "basketball"
STATE_CODES = [
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
]

STATE_NAMES = {
    "al":"Alabama",       "ak":"Alaska",         "az":"Arizona",
    "ar":"Arkansas",      "ca":"California",     "co":"Colorado",
    "ct":"Connecticut",   "de":"Delaware",       "fl":"Florida",
    "ga":"Georgia",       "hi":"Hawaii",         "id":"Idaho",
    "il":"Illinois",      "in":"Indiana",        "ia":"Iowa",
    "ks":"Kansas",        "ky":"Kentucky",       "la":"Louisiana",
    "me":"Maine",         "md":"Maryland",       "ma":"Massachusetts",
    "mi":"Michigan",      "mn":"Minnesota",      "ms":"Mississippi",
    "mo":"Missouri",      "mt":"Montana",        "ne":"Nebraska",
    "nv":"Nevada",        "nh":"New Hampshire",  "nj":"New Jersey",
    "nm":"New Mexico",    "ny":"New York",       "nc":"North Carolina",
    "nd":"North Dakota",  "oh":"Ohio",           "ok":"Oklahoma",
    "or":"Oregon",        "pa":"Pennsylvania",   "ri":"Rhode Island",
    "sc":"South Carolina","sd":"South Dakota",   "tn":"Tennessee",
    "tx":"Texas",         "ut":"Utah",           "vt":"Vermont",
    "va":"Virginia",      "wa":"Washington",     "wv":"West Virginia",
    "wi":"Wisconsin",     "wy":"Wyoming",        "dc":"District of Columbia",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.maxpreps.com/",
}

DELAY = 0.35

# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def get_build_id() -> Optional[str]:
    print("Fetching MaxPreps build ID...")
    try:
        r = requests.get("https://www.maxpreps.com", headers=HEADERS, timeout=20)
        r.raise_for_status()
        m = re.search(r'/_next/static/([a-zA-Z0-9_-]+)/_buildManifest\.js', r.text)
        if m:
            bid = m.group(1)
            print(f"  Build ID: {bid}")
            return bid
    except Exception as e:
        print(f"  Error: {e}")
    return None

def to_nextjs_url(build_id: str, public_href: str) -> str:
    if "?" in public_href:
        path_part, query = public_href.split("?", 1)
        query_suffix = f"?{query}"
    else:
        path_part, query_suffix = public_href, ""
    path = re.sub(r"^https?://www\.maxpreps\.com", "", path_part).rstrip("/")
    return f"https://www.maxpreps.com/_next/data/{build_id}{path}.json{query_suffix}"

def fetch_json(url: str, timeout: int = 20, retries: int = 3) -> Optional[dict]:
    for attempt in range(retries):
        time.sleep(DELAY * (2 ** attempt))  # exponential backoff: 0.35s, 0.7s, 1.4s
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 404: return None
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                print(f"  Failed after {retries} attempts: {e}")
    return None

def is_leaf_league(href: str) -> bool:
    return "leagueid=" in href

def get_link_cards(page_props: dict) -> list:
    lp = (page_props or {}).get("layoutProps") or {}
    return (lp.get("linkCardProps") or {}).get("data") or []

def get_leaf_hrefs_from_cards(cards: list) -> tuple[list, list]:
    leaves, sections = [], []
    for card in cards:
        lt = card.get("linkType")
        for group in card.get("groups") or []:
            for link in group.get("links") or []:
                href = link.get("href") or ""
                if is_leaf_league(href): leaves.append(href)
                elif lt == 4: sections.append(href)
    return leaves, sections

def league_name_from_href(href: str) -> str:
    for kw in ("/district/", "/league/", "/conference/", "/region/"):
        m = re.search(rf"{kw}([^/?]+)", href)
        if m: return m.group(1).replace("-", " ").title()
    path = href.split("?")[0].rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    return slug.replace("-", " ").title() if slug else "Unknown League"

def season_from_href(href: str) -> str:
    m = re.search(r"/basketball/(?:girls/)?(\d{2}-\d{2})/", href)
    return m.group(1) if m else "unknown"

def parse_season(raw: str) -> str:
    raw = raw.strip().replace("/", "-")
    m = re.match(r"^(20\d{2})-(?:20)?(\d{2})$", raw)
    if m:
        return f"{int(m.group(1))%100:02d}-{int(m.group(2)):02d}"
    if re.match(r"^\d{2}-\d{2}$", raw): return raw
    m = re.match(r"^(20\d{2})$", raw)
    if m:
        end = int(m.group(1)) % 100
        return f"{(end-1)%100:02d}-{end:02d}"
    raise ValueError(f"Cannot parse season '{raw}'.")

# ─── Sitemap backfill (catches teams never assigned to any league) ──────────

SITEMAP_INDEX_URL = "https://www.maxpreps.com/Index-Sitemap.xml"
_sitemap_cache = {}  # (sport_label, season_short) -> set of team base URLs

def _full_season_years(short_season: str) -> str:
    """'26-27' -> '2026-2027' (sitemap filenames use full 4-digit years)."""
    a, _b = short_season.split("-")
    y1 = 2000 + int(a)
    return f"{y1}-{y1 + 1}"

def _fetch_xml_locs(url: str, timeout: int = 30, retries: int = 3) -> list:
    """Fetch a sitemap XML file and return every <loc> entry in it."""
    for attempt in range(retries):
        time.sleep(DELAY * (2 ** attempt))
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            return re.findall(r"<loc>(.*?)</loc>", r.text)
        except Exception as e:
            if attempt == retries - 1:
                print(f"  [WARN] sitemap fetch failed {url}: {e}")
    return []

def get_sitemap_team_urls(sport_label: str, season_short: str) -> set:
    """Every team page MaxPreps has indexed for this sport/season, regardless
    of league assignment. Cached - called once per (sport, season), not once
    per state, since the sitemap itself isn't state-partitioned."""
    cache_key = (sport_label, season_short)
    if cache_key in _sitemap_cache:
        return _sitemap_cache[cache_key]

    full_years = _full_season_years(season_short)
    prefix = f"Teams-{sport_label}-Varsity-Basketball-Winter-{full_years}-"
    sitemap_files = [l for l in _fetch_xml_locs(SITEMAP_INDEX_URL) if prefix in l]

    # Boys team pages have no gender segment in the URL (".../basketball/"),
    # unlike girls (".../basketball/girls/") - matches the SPORT convention
    # used everywhere else in this file.
    suffix = "/basketball/girls" if sport_label == "Girls" else "/basketball"
    urls = set()
    for sm_url in sitemap_files:
        for l in _fetch_xml_locs(sm_url):
            if l.rstrip("/").endswith(suffix):
                urls.add(l)

    print(f"  Sitemap: {len(sitemap_files)} file(s) -> {len(urls)} team pages ({sport_label} {full_years})")
    _sitemap_cache[cache_key] = urls
    return urls

def _team_slug_key(team_url: str):
    """(STATE, team-name-slug), ignoring the city slug - MaxPreps sometimes
    corrects a team's city slug across a realignment while the team-name
    slug itself stays stable, which would otherwise look like a duplicate."""
    m = re.match(r"https?://(?:www\.)?maxpreps\.com/([^/]+)/([^/]+)/([^/]+)/", team_url)
    return (m.group(1).upper(), m.group(3)) if m else None

def get_team_context_live(build_id: str, team_url: str, season_short: Optional[str]) -> Optional[dict]:
    """One team's own page, fetched for its current schoolId/city/league -
    only used for teams the league-leaf crawl never found. An explicit
    season suffix avoids MaxPreps silently serving a stale prior-season
    page when this team hasn't been rolled over to the target season yet."""
    sched = team_url.rstrip("/") + (f"/{season_short}/schedule/" if season_short else "/schedule/")
    data = fetch_json(to_nextjs_url(build_id, sched))
    if not data:
        return None
    return ((data.get("pageProps") or {}).get("teamContext") or {}).get("data") or None

def get_teams_from_leaf(build_id: str, leaf_href: str) -> list:
    url = to_nextjs_url(build_id, leaf_href)
    data = fetch_json(url)
    if not data: return []
    lp = (data.get("pageProps") or {}).get("layoutProps") or {}
    table = lp.get("tableData") or []
    league, season = league_name_from_href(leaf_href), season_from_href(leaf_href)
    lid = (re.search(r"leagueid=([^&]+)", leaf_href) or ["",""])[1]
    teams = []
    for entry in table:
        name = entry.get("schoolName") or ""
        team_url = entry.get("teamCanonicalUrl") or ""
        city, state = "", ""
        if team_url:
            m = re.match(r"https?://(?:www\.)?maxpreps\.com/([^/]+)/([^/]+)/([^/]+)/", team_url)
            if m:
                state = m.group(1).upper()
                city = m.group(2).replace("-", " ").title()
                full_name = m.group(3).replace("-", " ").title()
                if full_name:
                    name = full_name

        if name:
            teams.append({
                "schoolId": entry.get("schoolId") or "", 
                "teamName": name,
                "city": city,
                "state": state,
                "teamUrl": team_url, 
                "leagueId": lid,
                "league": league, 
                "season": season,
            })
    return teams

def get_all_teams_for_state(build_id: str, state: str, season: Optional[str] = None) -> list:
    global SPORT
    base = f"https://www.maxpreps.com/{state}/{SPORT}/{season}/" if season else f"https://www.maxpreps.com/{state}/{SPORT}/"
    state_url = to_nextjs_url(build_id, base)
    data = fetch_json(state_url)
    # Don't bail out here even if the state hub page fetch failed - the
    # sitemap backfill below doesn't depend on it, so this state still gets
    # whatever that finds instead of nothing.
    cards = get_link_cards((data or {}).get("pageProps") or {})
    leaf_hrefs, section_hrefs = get_leaf_hrefs_from_cards(cards)
    for sec_href in section_hrefs:
        sec_url = to_nextjs_url(build_id, sec_href)
        sec_data = fetch_json(sec_url)
        if sec_data:
            sec_cards = get_link_cards(sec_data.get("pageProps") or {})
            sl, _ = get_leaf_hrefs_from_cards(sec_cards)
            leaf_hrefs.extend(sl)

    unique_leaves = list(set(leaf_hrefs))
    all_teams, seen_ids = [], set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_teams_from_leaf, build_id, leaf): leaf for leaf in unique_leaves}
        for future in concurrent.futures.as_completed(futures):
            try:
                teams_from_leaf = future.result()
            except Exception as e:
                leaf = futures[future]
                print(f"  [WARN] leaf {leaf} failed: {e}")
                continue
            for t in teams_from_leaf:
                # Prefer teamUrl as the dedup key — it's unique per real-world team.
                # schoolId may be missing for some entries, and teamName collides
                # (e.g. multiple 'Heritage Christian Eagles' across TX districts).
                uid = t.get("teamUrl") or t.get("schoolId") or t.get("teamName")
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    all_teams.append(t)
                    print(f"      [Scraped Team] {t['teamName']} ({t['league']})")

    # ── Sitemap backfill: teams never assigned to any league page are
    # structurally invisible to the leaf walk above, in every season - see
    # get_sitemap_team_urls's docstring. season_short is needed both to pick
    # the right sitemap file and to tell a current vs. stale league apart on
    # each missing team's own page; infer it from the leaves actually found
    # when no --season was given (matches this function's "current season"
    # behaviour in that case).
    season_short = season or (Counter(season_from_href(l) for l in unique_leaves).most_common(1)[0][0]
                               if unique_leaves else None)
    sport_label = "Girls" if SPORT.endswith("/girls") else "Boys"

    sitemap_urls = set()
    if season_short:
        try:
            sitemap_urls = get_sitemap_team_urls(sport_label, season_short)
        except Exception as e:
            print(f"  [WARN] sitemap lookup failed: {e}")

    seen_keys = {_team_slug_key(t.get("teamUrl", "")) for t in all_teams}
    state_prefix = f"https://www.maxpreps.com/{state}/"
    missing_urls = [
        u for u in sitemap_urls
        if u.startswith(state_prefix) and u not in seen_ids and _team_slug_key(u) not in seen_keys
    ]

    if missing_urls:
        print(f"  [{state.upper()}] {len(missing_urls)} team(s) in sitemap but not found via any league page - fetching directly")

        def _resolve_missing(team_url):
            return team_url, get_team_context_live(build_id, team_url, season_short)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_resolve_missing, u): u for u in missing_urls}
            for future in concurrent.futures.as_completed(futures):
                team_url, tc = future.result()
                m = re.match(r"https?://(?:www\.)?maxpreps\.com/([^/]+)/([^/]+)/([^/]+)/", team_url)
                city_slug, team_slug = (m.group(2), m.group(3)) if m else ("", "")
                tc = tc or {}
                is_current = season_short is None or tc.get("year") == season_short
                league_id, league_name = tc.get("leagueId"), tc.get("leagueName")
                has_league = bool(is_current and league_name
                                   and league_id and league_id != "00000000-0000-0000-0000-000000000000")

                entry = {
                    "schoolId": tc.get("teamId") or "",
                    "teamName": tc.get("schoolName") or team_slug.replace("-", " ").title(),
                    "city": tc.get("schoolCity") or city_slug.replace("-", " ").title(),
                    "state": state.upper(),
                    "teamUrl": team_url,
                    "leagueId": league_id if has_league else "00000000-0000-0000-0000-000000000000",
                    "league": league_name if has_league else "Unassigned",
                    "season": season_short or "unknown",
                }
                if entry["teamUrl"] not in seen_ids:
                    seen_ids.add(entry["teamUrl"])
                    all_teams.append(entry)
                    print(f"      [Sitemap Team] {entry['teamName']} ({entry['league']})")

    return all_teams

def run(sport="boys", season=None, states=None):
    """Fetch teams for all states (or a specific subset via `states` list).

    When `states` is provided, the existing output file is patched in-place
    rather than fully regenerated, preserving data for all other states.
    """
    global SPORT
    if sport == "girls":
        SPORT, sport_label, prefix = "basketball/girls", "Girls Basketball", "girls_basketball_all_states"
    else:
        SPORT, sport_label, prefix = "basketball", "Boys Basketball", "boys_basketball_all_states"

    out_file = os.path.join(DATA_DIR, f"{prefix}_{season}.json") if season else os.path.join(DATA_DIR, f"{prefix}.json")

    # Always load existing file to support resuming
    if os.path.exists(out_file):
        try:
            with open(out_file) as f:
                existing = json.load(f)
            results = existing.get("byState") or {}
        except json.JSONDecodeError:
            results = {}
    else:
        results = {}

    print(f"Counting teams: {sport_label} | Season: {season or 'current'}")
    build_id = get_build_id()
    if not build_id: return None

    target_states = [s.lower() for s in states] if states else STATE_CODES
    
    # Resume logic: if no specific states were asked for, skip those already downloaded
    if not states and results:
        done_states = [s.lower() for s in results.keys()]
        target_states = [s for s in target_states if s not in done_states]
        if target_states:
            print(f"Resume mode: Skipping {len(done_states)} completed states. {len(target_states)} states left.")
        else:
            print(f"All {len(STATE_CODES)} states already completed in {out_file}.")
            return out_file

    for state in target_states:
        state_name = STATE_NAMES.get(state, state.upper())
        teams = get_all_teams_for_state(build_id, state, season)

        if not teams:
            results[state.upper()] = {"stateName": state_name, "totalTeams": 0, "regions": {}}
        else:
            by_league = defaultdict(list)
            for t in teams: by_league[t["league"]].append(t)
            total = len(teams)
            results[state.upper()] = {
                "stateName": state_name, "totalTeams": total,
                "regions": {r: {"teamCount": len(ts), "teams": ts} for r, ts in by_league.items()}
            }
            print(f"  [{state.upper()}] {total} teams")
            
        # Save at runtime after every state finishes so progress is never lost.
        # Atomic write avoids corrupting the file on Ctrl+C / power loss.
        grand_total = sum(v.get("totalTeams", 0) for v in results.values())
        output = {"meta": {"sport": sport_label, "grandTotal": grand_total}, "byState": results}
        tmp = out_file + ".tmp"
        with open(tmp, "w") as f: json.dump(output, f, indent=2)
        os.replace(tmp, out_file)

    print(f"Finished. Saved -> {out_file}")
    return out_file

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", default="boys")
    parser.add_argument("--season", default=None)
    parser.add_argument("--states", default=None, help="Comma-separated state codes to refresh, e.g. TX,CA")
    args = parser.parse_args()
    s = parse_season(args.season) if args.season else None
    states = [x.strip() for x in args.states.split(",")] if args.states else None
    run(sport=args.sport, season=s, states=states)

if __name__ == "__main__":
    main()
