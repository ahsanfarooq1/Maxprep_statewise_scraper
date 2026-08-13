"""
Check what's ACTUALLY in the data gaps file - the full structure
of a few teams to understand why contests=0
"""
import json

with open('Colorado_Scraped_data/co_data_gaps_boys_2025_2026.json', encoding='utf-8') as f:
    data = json.load(f)

meta = data.get('meta', {})
print('META:')
for k, v in meta.items():
    if not isinstance(v, list):
        print('  ' + str(k) + ':', v)

print('\nTeamsNoBoxScores sample (first 3 teams):')
no_data = data.get('teamsNoBoxScores', [])
for team in no_data[:3]:
    print('\n  Team:', team.get('teamName'))
    print('  URL:', team.get('teamUrl'))
    print('  gamesChecked:', team.get('gamesChecked'))
    print('  gamesWithStats:', team.get('gamesWithStats'))
    print('  contests count:', len(team.get('contests', [])))
    contests = team.get('contests', [])
    if contests:
        print('  First contest:', str(contests[0])[:200])

print('\nFirst team with contests > 0:')
for team in no_data:
    c = team.get('contests', [])
    if len(c) > 0:
        print('  Team:', team.get('teamName'), '- contests:', len(c))
        print('  Contest[0]:', str(c[0])[:300])
        break
else:
    print('  NONE found with any contests!')

# Check how many teams have gamesChecked > 0
has_games = [t for t in no_data if t.get('gamesChecked', 0) > 0]
print('\nTeams with gamesChecked > 0:', len(has_games))
