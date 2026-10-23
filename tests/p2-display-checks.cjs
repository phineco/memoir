const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try {
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/f/ui');assert(await page.locator('#large-text-hint').isVisible());
  await page.locator('#large-text-dismiss').click();await page.reload();assert(!(await page.locator('#large-text-hint').isVisible()));
  await page.goto(base+'/f/ui/story/story');
  for(const size of ['22','26','18']) {
   await page.locator(`[data-reading-size="${size}"]`).click();
   assert.equal(await page.locator('html').getAttribute('data-size'),size);
   assert.equal(await page.locator('#articleBody').evaluate(n=>getComputedStyle(n).fontSize),size+'px');
   await page.reload();assert.equal(await page.locator('html').getAttribute('data-size'),size);
  }
  await page.locator('[data-reading-size="26"]').click();
  await page.goto(base+'/display?family_id=ui');assert(await page.locator('[name=size][value="26"]').isChecked());
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});await page.goto(base+'/f/ui/story/story');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  assert.deepEqual(errors,[]);
  const blocked=await browser.newContext({viewport:{width:390,height:844}});
  await blocked.addCookies(await context.cookies());
  await blocked.addInitScript(()=>{Storage.prototype.setItem=function(){throw new Error('disabled');};});
  const other=await blocked.newPage();await other.goto(base+'/f/ui/story/story');
  await other.locator('[data-reading-size="22"]').click();
  assert.equal(await other.locator('html').getAttribute('data-size'),'22');
  assert.match(await other.locator('[data-display-status]').innerText(),/未允许保存/);
  await context.close();await blocked.close();
  console.log('P2 display: first-use hint, dismissal, shortcuts, persistence, shared settings, blocked storage and 3 viewport layouts passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
