const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try {
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.goto(base+'/f/empty');
  assert(await page.getByRole('link',{name:'记录第一段回忆',exact:true}).isVisible());
  await page.getByRole('link',{name:'记录第一段回忆',exact:true}).click();
  await page.locator('#writing-questions summary').click();
  const first=page.locator('[data-writing-question]').first();
  const question=await first.getAttribute('data-question-text');await first.click();
  assert.equal(await page.locator('[name=topic]').inputValue(),question);
  assert.equal((await page.locator('.ql-editor').innerText()).trim(),'');
  await page.locator('[name=topic]').fill('自己起的题目');
  await page.locator('.ql-editor').fill('这些是我自己写下的内容，不能被问题卡替换。');
  await page.locator('#writing-questions summary').click();await page.locator('[data-writing-question]').nth(1).click();
  assert.equal(await page.locator('[name=topic]').inputValue(),'自己起的题目');
  assert.match(await page.locator('.ql-editor').innerText(),/不能被问题卡替换/);
  await page.locator('[name=recording_mode][value=accompany]').check();
  assert(await page.locator('#story-details').evaluate(n=>n.open));
  assert.equal(await page.locator('[name=narrator_person_id]').inputValue(),'');
  await page.waitForFunction(()=>document.getElementById('recovery-status').textContent.includes('已自动保留'));
  await page.reload();await page.locator('#recovery-list button').first().click();
  assert(await page.locator('[name=recording_mode][value=accompany]').isChecked());
  assert.match(await page.locator('#writing-question-status').innerText(),/小时候住的家/);
  assert.match(await page.locator('.ql-editor').innerText(),/不能被问题卡替换/);
  await page.locator('button[name=action][value=draft]').click();await page.waitForURL(url=>url.pathname==='/account/drafts');
  await page.getByRole('link',{name:'继续编辑',exact:true}).click();
  assert.match(await page.locator('.ql-editor').innerText(),/不能被问题卡替换/);
  assert.equal(await page.locator('[name=narrator_person_id]').inputValue(),'');
  await page.goto(base+'/display?family_id=empty');await page.locator('[name=size][value="26"]').check();
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});await page.goto(base+'/f/empty/write');
   await page.locator('#writing-questions summary').click();await page.locator('[name=recording_mode][value=accompany]').check();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'large text layout '+width);
  }
  await context.route('**/quill-2.0.3.*.js',route=>route.abort());
  await page.goto(base+'/f/ui/write');
  await page.locator('#editor-fallback').fill('格式编辑器加载失败时的原文');
  await page.locator('#writing-questions summary').click();await page.locator('[data-writing-question]').first().click();
  assert.equal(await page.locator('#editor-fallback').inputValue(),'格式编辑器加载失败时的原文');
  assert.deepEqual(errors,[]);
  console.log('Writing aids: curated topic, original text preservation, companion identity, browser recovery, draft roundtrip, editor fallback and three large-text layouts passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
