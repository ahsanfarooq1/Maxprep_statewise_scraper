"""
Deep-dive into the data_gaps file to understand why games aren't being found.
Checks: 
  1. How many games/contests are in the gaps file
  2. What contest entries look like (URL format, c= param, index 18)
  3. Whether season 25-26 contests exist
  4. What the actual game URLs look like
"""
import json
import re

files = [
    ('Colorado_Scraped_data/co_data_gaps_boys_2025_2026.json', 'CO boys'),
    ('Colorado_Scraped_data/co_data_gaps_girls_2025_2026.json', 'CO girls'),
]

NULL = "00000000-0000-0000-0000-000000000000"

for path, label in files:
    print('=== ' + label + ' (' + path + ') ===')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    
    full_b    = data.get('teamsFullBoxScores', [])
    partial_b = data.get('teamsPartialBoxScores', [])
    none_b    = data.get('teamsNoBoxScores', [])
    print('  Teams full:', len(full_b))
    print('  Teams partial:', len(partial_b))
    print('  Teams no-data:', len(none_b))
    
    # Check the first team's contest structure
    sample_team = (full_b or partial_b or none_b or [None])[0]
    if not sample_team:
        print('  NO TEAMS')
        continue
    
    print('  Sample team:', sample_team.get('teamName'), '|', sample_team.get('teamUrl', '')[:80])
    contests = sample_team.get('contests', [])
    print('  Contests in first team:', len(contests))
    
    if contests:
        c0 = contests[0]
        print('  Type of contest[0]:', type(c0).__name__)
        if isinstance(c0, list):
            print('  Contest[0] length:', len(c0))
            print('  Contest[0] elements (first 20):')
            for i, v in enumerate(c0[:20]):
                print('    [' + str(i) + '] ' + repr(v)[:80])
            # Check index 18 (game URL)
            if len(c0) > 18:
                url = c0[18]
                print('  URL at index 18:', url)
                m = re.search(r'[?&]c=([A-Za-z0-9_-]+)', str(url))
                print('  c= param:', m.group(1) if m else 'MISSING')
            else:
                print('  INDEX 18 DOES NOT EXIST - only', len(c0), 'elements')
        elif isinstance(c0, dict):
            print('  Contest is DICT, keys:', list(c0.keys())[:15])
    
    # Check ALL first-team contests for URL pattern
    if contests:
        url_count = 0
        no_url = 0
        no_c_param = 0
        for c in contests:
            if isinstance(c, list) and len(c) > 18:
                url = c[18]
                if isinstance(url, str) and url.startswith('https://'):
                    url_count += 1
                    if not re.search(r'[?&]c=', url):
                        no_c_param += 1
                else:
                    no_url += 1
            else:
                no_url += 1
        print('  In first team: urls=' + str(url_count) + '  no_url=' + str(no_url) + '  no_c_param=' + str(no_c_param))
    
    print()
