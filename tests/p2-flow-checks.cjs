const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try {
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/f/ui/stories');
  await page.locator('[name=q]').fill('老院子');await page.getByRole('button',{name:'搜索',exact:true}).click();
  assert.equal(await page.locator('.story-results a.card').count(),1);
  await page.locator('[name=q]').fill('没有这篇xyz');await page.getByRole('button',{name:'搜索',exact:true}).click();
  assert(await page.getByRole('heading',{name:'没有找到符合条件的故事'}).isVisible());
  await page.locator('[name=q]').fill('分页测试');await page.getByRole('button',{name:'搜索',exact:true}).click();
  assert.equal(await page.locator('.story-results a.card').count(),20);
  await page.getByRole('link',{name:'下一页',exact:true}).click();
  assert.equal(await page.locator('.story-results a.card').count(),5);
  assert.equal(new URL(page.url()).searchParams.get('q'),'分页测试');
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});await page.locator('summary').first().click();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.reload();
  }
  await page.goto(base+'/account/ai-memory?family_id=ui');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'重置此家庭的 AI 记忆'}).click();
  assert(await page.getByRole('status').getByText(/摘要已清空/).isVisible());
  assert.deepEqual(errors,[]);
  console.log('P2 flow: search, empty state, 20/5 pagination with preserved query, 3 viewport layouts, and CSRF-protected AI reset passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
