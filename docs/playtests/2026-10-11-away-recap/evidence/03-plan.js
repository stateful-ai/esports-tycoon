async page => {
 await page.getByRole('button',{name:'Game plan',exact:true}).click();
 for(const [label,value] of [['Pace',70],['Map control',30]]){
 const row=page.locator('.gp-dial').filter({has:page.getByText(label,{exact:true})});
 await row.locator('input[type=checkbox]').check();
 const slider=row.locator('input[type=range]'); await slider.focus();await slider.press('Home');
 for(let n=0;n<value;n++)await slider.press('ArrowRight');
 }
 const response=page.waitForResponse(r=>r.url().endsWith('/api/actions/gameplan')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Lock in',exact:false}).click();
 const res=await response;return {status:res.status(),response:await res.json(),visible:await page.locator('body').innerText()};
}
