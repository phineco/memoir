const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL;const one=await browser.newContext();await one.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const first=await one.newPage();await first.goto(base+'/display?family_id=ui');
  await first.locator('[name=size][value="26"]').check();await first.locator('[name=theme][value=contrast]').check();await first.locator('[name=entry][value=easy]').check();
  await first.locator('#display-account-save').click();await first.waitForFunction(()=>document.getElementById('display-account-status').textContent.includes('已保存为账号默认'));
  const two=await browser.newContext();await two.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});const second=await two.newPage();
  await second.goto(base+'/display?family_id=ui');assert.equal(await second.locator('html').getAttribute('data-size'),'26');
  await second.locator('[name=size][value="18"]').check();
  await first.locator('[name=size][value="22"]').check();await first.locator('#display-account-save').click();await first.waitForFunction(()=>document.getElementById('display-account-status').textContent.includes('已保存为账号默认'));
  await second.reload();assert.equal(await second.locator('html').getAttribute('data-size'),'18');
  await second.locator('#display-account-follow').click();await second.waitForFunction(()=>document.documentElement.dataset.size==='22');
  await second.goto(base+'/');await second.waitForURL('**/easy');
  await two.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});await second.goto(base+'/display?family_id=ui');
  assert.equal(await second.locator('html').getAttribute('data-size'),'18');assert.equal(await second.locator('html').getAttribute('data-theme'),'modern');
  // Old global storage is never silently assigned to another account.
  await second.evaluate(()=>localStorage.setItem('memoir.display.v1',JSON.stringify({size:'26',theme:'paper',font:'serif',mode:'simple'})));
  await second.reload();assert.equal(await second.locator('html').getAttribute('data-size'),'18');assert(await second.locator('#display-legacy').isVisible());
  await second.getByRole('button',{name:'应用旧设置（仅本机）'}).click();assert.equal(await second.locator('html').getAttribute('data-size'),'26');
  assert.equal((await (await two.request.get(base+'/account/display-preferences')).json()).values,null);
  await two.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});await second.reload();assert.equal(await second.locator('html').getAttribute('data-size'),'22');
  const original=await one.request.get(base+'/account/display-preferences');assert.equal((await original.json()).values.size,'22');
  await one.close();await two.close();console.log('Account defaults, two-device override precedence, entry choice, account isolation and explicit legacy migration passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
