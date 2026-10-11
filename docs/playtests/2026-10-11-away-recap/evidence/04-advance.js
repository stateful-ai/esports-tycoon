async page => {
 const response=page.waitForResponse(r=>r.url().endsWith('/api/advance')&&r.request().method()==='POST',{timeout:180000});
 await page.getByRole('button',{name:'Advance Week',exact:false}).click();
 const res=await response;return {status:res.status(),response:await res.json(),visible:await page.locator('body').innerText()};
}
