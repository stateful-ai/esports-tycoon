import json
from pathlib import Path

root=Path(r'C:\Users\aidan\workspace\esports-sponsor-playtest-20261010')
run=root/'runs/playtests/2026-10-10-next-fixture-development'
snap=(root/'.playwright-cli/page-2026-10-10T21-46-08-971Z.yml').read_text(encoding='utf-8')
roster=json.loads((run/'03-roster-response.txt').read_text(encoding='utf-8-sig'))
tactics=json.loads((run/'03-tactics-response.txt').read_text(encoding='utf-8-sig'))
assert 'cell "Ghost" [ref=f1e694]' in snap
assert roster['effective_lineup_ids']==['apex','vortex','ghost','fa_13','echo']
assert {p['id'] for p in tactics['lineup']['players']}=={'apex','vortex','ghost','fa_13','echo','fa_0'}
print('Fresh captured-file audit: Ghost present; default five excludes Hollowlock; six roster agent-lock rows.')
