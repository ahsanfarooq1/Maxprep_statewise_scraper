"""
Live smoke test for the box-score scraper against ONE real MaxPreps game.

IMPORTANT — VPN REQUIRED
    MaxPreps serves a 403 "Geo-block" page to requests from some countries.
    This is genuinely geographic: with a VPN in an allowed region both
    browsers and scripts work; without one, even a real headless Chrome is
    blocked. Turn the VPN on before running this, or you'll just get 403.

What it checks, in order:
  1. Raw HTTP status (surfaces a 403/geo-block instead of hiding it as None).
  2. That ?tab=stats returns the stat tables — the 2026 redesign puts player
     stats behind that tab; the default (Recap) view has none.
  3. That the parser extracts BOTH teams' players from the page's embedded
     Next.js RSC payload, with correct canonical opponent identity.

Usage:
    python test_live_box_score.py
"""
from scrape_box_scores import (scrape_game, _get_opp_index, _get_session,
                               HTML_HEADERS, _with_stats_tab)

# A real Colorado boys game the 2026-08-03 pipeline run wrongly recorded as
# "no_data" (Adams City Eagles @ Westminster Wolves, 12-2-2025).
GAME_URL = ("https://www.maxpreps.com/co/basketball/game/"
            "adams-city-commerce-city-vs-westminster/12-2-2025/"
            "?c=dc2f2ce6-a427-4c18-93ca-839e288f67a0")
GUID = "dc2f2ce6-a427-4c18-93ca-839e288f67a0"
TEAM_ID = "co/commerce-city/adams-city-eagles/basketball"
TEAM_NAME = "Adams City Eagles"

if __name__ == "__main__":
    print(f"Fetching: {GAME_URL}\n")

    # Raw status first — scrape_game() returns a bare None on any non-200,
    # which hides whether we were blocked or the page simply had no stats.
    r1 = _get_session().get(GAME_URL, headers=HTML_HEADERS, timeout=25,
                            allow_redirects=True)
    print(f"[raw] initial status : {r1.status_code}")
    if r1.status_code != 200:
        head = r1.text[:200].replace("\n", " ")
        print(f"[raw] body snippet   : {head}")
        if "geo-block" in r1.text.lower():
            print("\n>> GEO-BLOCKED. Turn on your VPN and re-run.")
        raise SystemExit(1)

    stats_url = _with_stats_tab(r1.url)
    r2 = _get_session().get(stats_url, headers=HTML_HEADERS, timeout=25,
                            allow_redirects=True)
    print(f"[raw] tab=stats      : {r2.status_code}  ({stats_url})")
    print()

    opp_index = _get_opp_index("boys", "2025-2026")
    record = scrape_game(GAME_URL, GUID, ssid=None, our_team_name=TEAM_NAME,
                         team_id=TEAM_ID, opp_index=opp_index)

    if not record or (isinstance(record, dict) and record.get("_404")):
        print(f"FAILED — scrape_game returned {record!r}")
        raise SystemExit(1)

    print("SUCCESS — parsed record:\n")
    print("  team    :", record["team"])
    print("  opponent:", record["opponent"])
    for cat in ("shooting", "detailed_shooting", "totals", "misc"):
        t = len(record[cat]["team"]["players"])
        o = len(record[cat]["opponent"]["players"])
        print(f"  {cat:<18} team_players={t:<3} opp_players={o}")

    ours = record["shooting"]["team"]["players"]
    theirs = record["shooting"]["opponent"]["players"]
    if ours:
        print("\n  sample our player :", ours[0])
    if theirs:
        print("  sample opp player :", theirs[0])

    if not theirs:
        print("\n  NOTE: opponent side empty — expected only if MaxPreps has no "
              "stats for them; otherwise the RSC payload parse may have failed.")
