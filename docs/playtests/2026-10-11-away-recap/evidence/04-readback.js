async page => {
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByRole('button',{name:'Dashboard',exact:false}).click();
 await page.getByText('NEWS',{exact:true}).waitFor();
 return {visible:await page.locator('body').innerText(),state:await page.evaluate(async()=>await(await fetch('/api/state')).json())};
}
