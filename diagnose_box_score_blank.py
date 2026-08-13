"""
Diagnose why box score files are empty.

Tests:
1. Fetch the known game URL and analyze what structure MaxPreps returns
2. Check if self.__next_f.push RSC payloads are present
3. Check if stat tables are in HTML
4. Check if boxscore.aspx still redirects correctly
5. Check the season suffix issue (25-26 vs 26-27)

Run: python diagnose_box_score_blank.py
"""
import re
import json
import sys
import requests
from bs4 import BeautifulSoup

# The exact URL from the user
TEST_URL = (
    "https://www.maxpreps.com/tx/basketball/game/"
    "allen-vs-dallas-jesuit/11-14-2025/"
    "?c=5dfde36d-7b8e-485d-9473-f57c74d44cc6&tab=Stats"
)
TEST_GUID = "5dfde36d-7b8e-485d-9473-f57c74d44cc6"
# A known CO game from the test file
CO_URL = (
    "https://www.maxpreps.com/co/basketball/game/"
    "adams-city-commerce-city-vs-westminster/12-2-2025/"
    "?c=dc2f2ce6-a427-4c18-93ca-839e288f67a0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.maxpreps.com/",
    "sec-ch-ua": '"Not.A/Brand";v="8", "Chromium";v="124", "Google Chrome";v="124"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

_RSC_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)

def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def fetch(url, session):
    print(f"\n  >> GET {url[:100]}")
    r = session.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    print(f"     Status : {r.status_code}")
    print(f"     Final URL: {r.url[:120]}")
    return r

def analyze_html(r):
    print(f"\n  HTML size: {len(r.text):,} chars")
    
    # Check for geo-block
    if "geo-block" in r.text.lower() or r.status_code in (403, 406):
        print("  !! GEO-BLOCKED / Not Acceptable — VPN/proxy needed")
        print(f"     First 300 chars: {r.text[:300]}")
        return None
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    # ── 1. RSC payload ────────────────────────────────────────────
    rsc_chunks = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "self.__next_f.push" not in text:
            continue
        for m in _RSC_PUSH_RE.finditer(text):
            try:
                rsc_chunks.append(json.loads(m.group(1)))
            except Exception:
                continue
    
    rsc_payload = "".join(rsc_chunks)
    print(f"\n  RSC payload total size: {len(rsc_payload):,} chars")
    
    if rsc_payload:
        # Look for stat group objects
        stat_groups = re.findall(r'"name":"([^"]*)".*?"subgroups":', rsc_payload)
        print(f"  Stat group names found: {stat_groups[:10]}")
        
        # Look for columns/rows pattern
        has_columns = '"columns"' in rsc_payload
        has_rows    = '"rows"'    in rsc_payload
        print(f"  Has 'columns' key: {has_columns}")
        print(f"  Has 'rows' key   : {has_rows}")
        
        # Find first occurrence of shooting stats
        m = re.search(r'"name"\s*:\s*"Shooting"', rsc_payload)
        if m:
            snippet = rsc_payload[m.start():m.start()+600]
            print(f"\n  RSC Shooting snippet (600 chars):\n{snippet}")
        else:
            print("  No 'Shooting' stat group found in RSC payload")
            # Look for any stat-like keys
            for keyword in ["Stats", "stats", "Player", "player", "subgroups"]:
                idx = rsc_payload.find(keyword)
                if idx >= 0:
                    print(f"  Found '{keyword}' at index {idx}, snippet: {rsc_payload[idx:idx+200]}")
                    break
        
        # Save full RSC to file for manual inspection
        with open("rsc_payload_dump.txt", "w", encoding="utf-8") as f:
            f.write(rsc_payload)
        print(f"\n  Full RSC payload saved to: rsc_payload_dump.txt")
    else:
        print("  !! NO RSC payload found in page")
        # Check for __NEXT_DATA__
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            try:
                nd = json.loads(next_data.string)
                print(f"  __NEXT_DATA__ keys: {list(nd.keys())}")
                pp = nd.get("props", {}).get("pageProps", {})
                print(f"  pageProps keys: {list(pp.keys())[:15]}")
            except Exception as e:
                print(f"  __NEXT_DATA__ parse error: {e}")
        else:
            print("  !! No __NEXT_DATA__ either")
        
        # Save full HTML for inspection
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("  Full HTML saved to: page_dump.html")
    
    # ── 2. HTML tables ────────────────────────────────────────────
    tables = soup.find_all("table")
    print(f"\n  <table> count: {len(tables)}")
    for i, t in enumerate(tables[:5]):
        headers = [th.get_text(strip=True) for th in t.find_all(["th"])]
        rows = t.find_all("tr")
        print(f"    Table {i}: {len(rows)} rows, headers={headers[:8]}")
    
    # ── 3. Tabs navigation ────────────────────────────────────────
    tab_links = soup.find_all("a", href=re.compile(r'tab=', re.I))
    print(f"\n  Tab links found: {[a.get_text(strip=True) for a in tab_links[:8]]}")
    
    # ── 4. Any JSON-LD or embedded JSON ──────────────────────────
    scripts_with_json = []
    for s in soup.find_all("script"):
        t = s.string or ""
        if "contestId" in t or "boxScore" in t or "playerStats" in t:
            scripts_with_json.append(t[:300])
    print(f"\n  Scripts with 'contestId/boxScore/playerStats': {len(scripts_with_json)}")
    if scripts_with_json:
        print(f"  Sample: {scripts_with_json[0][:300]}")
    
    # ── 5. Check for new API endpoints in source ──────────────────
    api_refs = re.findall(r'(https?://[^"\'<> ]+(?:api|graphql|stats|boxscore|contest)[^"\'<> ]{0,100})', r.text, re.I)
    unique_apis = list(dict.fromkeys(api_refs))[:10]
    print(f"\n  API endpoint refs in HTML ({len(unique_apis)} unique):")
    for u in unique_apis:
        print(f"    {u[:120]}")
    
    return soup

def test_boxscore_aspx(session):
    sep("TEST: boxscore.aspx redirect (old method)")
    url = f"https://www.maxpreps.com/local/stats/boxscore.aspx?contestid={TEST_GUID}"
    try:
        r = session.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        print(f"  Status: {r.status_code}  Final URL: {r.url[:120]}")
        if r.status_code == 200:
            print("  boxscore.aspx STILL WORKS — redirected to canonical URL")
        elif r.status_code in (301, 302, 307, 308):
            print(f"  Redirected (but allow_redirects=True should follow) — final: {r.url}")
        elif r.status_code == 404:
            print("  404 — boxscore.aspx endpoint REMOVED")
        else:
            print(f"  Got {r.status_code}")
    except Exception as e:
        print(f"  ERROR: {e}")

def test_schedule_api(session):
    sep("TEST: Schedule JSON (_next/data) - season suffix check")
    seed = "https://www.maxpreps.com/tx/allen/allen-eagles/basketball/schedule/"
    r = session.get(seed, headers=HEADERS, timeout=30, allow_redirects=True)
    print(f"  Seed page status: {r.status_code}")
    
    if r.status_code not in (200,):
        print("  Can't get build ID - geo-blocked")
        return
    
    m = re.search(r"/_next/static/([a-zA-Z0-9_-]+)/_buildManifest\.js", r.text)
    if not m:
        print("  !! Build ID NOT found in seed page")
        # Try to find it another way
        m2 = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
        if m2:
            bid = m2.group(1)
            print(f"  Build ID from __NEXT_DATA__: {bid}")
        else:
            print("  Could not extract build ID at all")
            return
    else:
        bid = m.group(1)
        print(f"  Build ID: {bid}")
    
    team_path = "tx/allen/allen-eagles/basketball"
    
    for suffix in ["25-26", "26-27", None]:
        if suffix:
            url = f"https://www.maxpreps.com/_next/data/{bid}/{team_path}/{suffix}/schedule.json"
        else:
            url = f"https://www.maxpreps.com/_next/data/{bid}/{team_path}/schedule.json"
        r2 = session.get(url, headers={**HEADERS, "Accept": "application/json, */*"}, timeout=20)
        suffix_label = suffix or "(current/default)"
        games = 0
        if r2.status_code == 200:
            try:
                data = r2.json()
                contests = (
                    data.get("pageProps", {}).get("initialPageProps", {}).get("contests")
                    or data.get("pageProps", {}).get("contests")
                    or []
                )
                games = len(contests)
            except Exception:
                pass
        print(f"  Season {suffix_label:16s}: HTTP {r2.status_code}  games/contests={games}")

def main():
    print("MaxPreps Box Score Diagnostic")
    print("="*60)
    
    session = requests.Session()
    
    sep("TEST: Main game page (tab=Stats)")
    r = fetch(TEST_URL, session)
    soup = analyze_html(r)
    
    if soup is None:
        print("\n!! Page is geo-blocked from this machine.")
        print("   The scraper will also be blocked unless running behind a VPN.")
        print("   ROOT CAUSE of empty box score files = GEO-BLOCK.")
        # Still test the other endpoints
    
    test_boxscore_aspx(session)
    test_schedule_api(session)
    
    sep("SUMMARY")
    print("Done. Review the output above.")
    print("Key things to check:")
    print("  1. Is RSC payload present? (stat groups / columns / rows)")
    print("  2. Does boxscore.aspx still redirect?")
    print("  3. Which season suffix (25-26 or 26-27) returns games?")

if __name__ == "__main__":
    main()
