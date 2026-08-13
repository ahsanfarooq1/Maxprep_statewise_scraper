import json

files = [
    'Colorado_Scraped_data/co_box_scores_boys_2025_2026.json',
    'Wisconsin_scraped_data/wi_box_scores_boys_2025_2026.json',
    'Colorado_Scraped_data/co_box_scores_girls_2025_2026.json',
    'Wisconsin_scraped_data/wi_box_scores_girls_2025_2026.json',
]

for f in files:
    try:
        with open(f) as fp:
            d = json.load(fp)
        meta = d.get('meta', {})
        games = d.get('games', [])
        print('=== ' + f + ' ===')
        print('  totalGames:', meta.get('totalGames'))
        print('  totalTeams:', meta.get('totalTeams'))
        print('  processedTeamsCount:', meta.get('processedTeamsCount'))
        print('  errors count:', len(meta.get('errors', [])))
        print('  games list length:', len(games))
        if games:
            g = games[0]
            print('  sample game:', g.get('team'), 'vs', g.get('opponent'))
            for cat in ['shooting', 'detailed_shooting', 'totals', 'misc']:
                tp = len(g.get(cat, {}).get('team', {}).get('players', []))
                op = len(g.get(cat, {}).get('opponent', {}).get('players', []))
                print('    ' + cat + ': team=' + str(tp) + ' opp=' + str(op))
        else:
            print('  NO GAMES in file')
        errs = meta.get('errors', [])
        if errs:
            reasons = set()
            for e in errs[:30]:
                reasons.add(e.get('reason') or e.get('stage') or '?')
            print('  Error reasons:', reasons)
        print()
    except Exception as ex:
        print('ERROR reading', f, ':', ex)
