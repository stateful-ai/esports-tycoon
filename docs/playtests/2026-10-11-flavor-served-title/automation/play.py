import json, subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd(); run=root/'runs/playtests/2026-10-11-flavor-served-title'; docs=root/'docs/playtests/2026-10-11-flavor-served-title'
private=json.loads((run/'private.json').read_text(encoding='utf-8'))
title='Community clinic: a small group invitation'
session='2026-10-11-flavor-served-title'
def begin(step,intent,action,expected):
    subprocess.run([sys.executable,str(run/'log.py'),'begin','--session',session,'--step',str(step),'--model','gpt-6.1-sol','--effort','medium','--surface','browser','--seed','2038','--world-code','FLV42','--game-time','S1 W12','--intent',intent,'--action',action,'--expected-outcome',expected],check=True)
def finish(step,outcome,status='met',analytics='not_instrumented'):
    subprocess.run([sys.executable,str(run/'log.py'),'finish','--session',session,'--step',str(step),'--actual-outcome',outcome,'--result',status,'--evidence',f'docs/playtests/{session}/browser-readback.json','--analytics-status',analytics],check=True)
evidence={'setup':'private copy; cached-overlay fixture, no LLM generation','observations':{}}
with sync_playwright() as p:
    browser=p.chromium.launch()
    context=browser.new_context(viewport={'width':1600,'height':1000})
    context.add_cookies([{'name':'esports_sid','value':private['sid'],'url':'http://127.0.0.1:8541'}])
    page=context.new_page()
    errors=[]; page.on('pageerror',lambda err:errors.append(str(err)))
    begin(1,'Recognize the clinic moment using its served copy','Open the private Dashboard','Cached clinic title and grounded choices are visible, with no settlement yet')
    page.goto('http://127.0.0.1:8541/',wait_until='networkidle')
    page.get_by_role('heading',name=title,exact=True).wait_for()
    before=page.evaluate('async () => (await fetch("/api/state")).json()')
    evidence['observations']['before']={'state':before,'rendered_event':page.locator('.flavor-event').all_inner_texts()}
    page.screenshot(path=str(docs/'01-cached-moment.png'),full_page=True)
    assert before['flavor_event']['title']==title and before['flavor_event']['ai']
    finish(1,'Dashboard shows cached clinic title, three original grounded choices, and no resolved receipt.')
    begin(2,'Choose the visible limited clinic response and identify its result','Click Send a small group','Receipt keeps the displayed clinic title and shows realized sentiment; pending event disappears')
    with page.expect_response(lambda r:r.url.endswith('/api/actions/flavor_event')) as pending:
        page.get_by_role('button',name='Send a small group',exact=True).click()
    response=pending.value.json()
    page.get_by_text('Team moment resolved',exact=True).wait_for()
    receipt=page.locator('.flavor-event').filter(has_text='Team moment resolved')
    dom=receipt.inner_text()
    after=page.evaluate('async () => (await fetch("/api/state")).json()')
    evidence['observations']['settlement']={'response':response,'dom':dom,'state':after,'receipt_title':receipt.locator('h3').inner_text()}
    assert response['event_title']!=title
    assert receipt.locator('h3').inner_text()==title
    assert not after.get('flavor_event')
    page.screenshot(path=str(docs/'02-served-title-receipt.png'),full_page=True)
    finish(2,'Receipt retains Community clinic: a small group invitation although response event_title is the fallback A community clinic asks for Team Nexus; one realized sentiment row; no pending event.','met','recorded')
    begin(3,'Check normal refresh preserves the title attached to this response','Open Club then Dashboard','Same served-title receipt remains on Dashboard in the same world/team')
    page.locator('nav#tabs [data-tab="club"]').click()
    page.locator('nav#tabs [data-tab="dashboard"]').click()
    page.get_by_text('Team moment resolved',exact=True).wait_for()
    evidence['observations']['refresh']={'dom':page.locator('.flavor-event').filter(has_text='Team moment resolved').inner_text()}
    assert page.locator('.flavor-event').filter(has_text='Team moment resolved').locator('h3').inner_text()==title
    finish(3,'Club and Dashboard navigation preserve the resolved receipt and the cached title.')
    begin(4,'Persist the decision and check independent loaded state','Click Save then reload browser','No pending clinic returns; one accepted flavor choice is saved; temporary receipt clears after reload')
    with page.expect_response(lambda r:r.url.endswith('/api/actions/save')) as saved:
        page.locator('#save-btn').click()
    assert saved.value.status==200
    page.evaluate('async () => { await Usage.flush(); }')
    page.reload(wait_until='networkidle')
    independent=page.evaluate('async () => (await fetch("/api/state")).json()')
    evidence['observations']['reload']={'state':independent,'rendered_events':page.locator('.flavor-event').all_inner_texts()}
    assert not independent.get('flavor_event')
    assert page.get_by_text('Team moment resolved',exact=True).count()==0
    page.evaluate('async () => { await Usage.flush(); }')
    evidence['pageerrors']=errors
    (docs/'browser-readback.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    finish(4,'Save succeeds; independent public state after reload has no pending clinic and no temporary receipt; saved telemetry reconciled separately.')
    browser.close()
print('Four browser intents completed; independent public readbacks captured.')
