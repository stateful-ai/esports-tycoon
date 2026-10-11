import asyncio,json,sys,hashlib
from pathlib import Path
from playwright.async_api import async_playwright
sys.stdout.reconfigure(encoding='utf-8')
async def main():
 out=Path('runs/playtests/gap26'); sessions=json.loads(Path('saves/sessions.json').read_text(encoding='utf-8')); sid=next(iter(sessions['sessions']))
 campaign=next(Path('saves').glob('campaign_*.json')); before=json.loads(campaign.read_text(encoding='utf-8')); result={}
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(); context=await browser.new_context(viewport={'width':1500,'height':1000})
  await context.add_cookies([{'name':'esports_sid','value':sid,'url':'http://127.0.0.1:8488'}])
  page=await context.new_page(); await page.goto('http://127.0.0.1:8488/',wait_until='networkidle'); await page.locator('nav#tabs [data-tab="company"]').click()
  sentence=page.locator('b').filter(has_text='Play Ghost').first
  await sentence.wait_for(); result['sentence_textContent']=await sentence.text_content(); result['sentence_innerText']=await sentence.inner_text()
  assert result['sentence_textContent']=='Play Ghost against Saracen Guard',repr(result['sentence_textContent'])
  await sentence.screenshot(path=out/'sponsor-demand.png'); (out/'finances-aria.yml').write_text(await page.locator('body').aria_snapshot(),encoding='utf-8')
  player=sentence.locator('[data-pid]'); opponent=sentence.locator('[data-tid]'); result['link_count']=await sentence.locator('[data-pid],[data-tid]').count()
  await player.click(); await page.locator('#profile:not(.hidden)').wait_for(); await page.wait_for_timeout(1000); result['player_profile']=await page.locator('#profile-body').inner_text()
  (out/'player-profile.txt').write_text(result['player_profile'],encoding='utf-8'); assert 'ghost' in result['player_profile'].lower(); await page.get_by_role('button',name='Close profile').click()
  await opponent.click(); await page.locator('#profile:not(.hidden)').wait_for(); await page.wait_for_timeout(1000); result['opponent_profile']=await page.locator('#profile-body').inner_text()
  assert 'saracen guard' in result['opponent_profile'].lower(); await page.get_by_role('button',name='Close profile').click()
  result['player_profile']='Ghost profile opened'; result['opponent_profile']='Saracen Guard team profile opened'
  await page.locator('#save-btn').click(); await page.wait_for_timeout(1500); await context.close(); await browser.close()
 after=json.loads(campaign.read_text(encoding='utf-8')); result['saved_campaign_unchanged']=before==after; result['decision_count_before']=len(before.get('action_log',[])); result['decision_count_after']=len(after.get('action_log',[])); assert before==after
 (out/'browser-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result))
asyncio.run(main())
