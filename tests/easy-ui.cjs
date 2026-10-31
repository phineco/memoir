const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext();const base=process.env.UI_TEST_URL;
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/easy?family_id=ui');assert.equal(await page.evaluate(()=>getComputedStyle(document.body).fontSize),'22px');
  const paths=['/easy?family_id=ui','/easy/records','/easy/listen','/easy/settings','/easy/help','/easy/photos','/easy/f/ui/story/story','/easy/f/ui/interview/new'];let layouts=0;
  for(const width of [320,375,390,430,768,1280,1440]){
   await page.setViewportSize({width,height:900});
   for(const path of paths){
    assert.equal((await page.goto(base+path)).status(),200,path);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),`${width} ${path} overflow`);
    const tiny=await page.locator('.btn-primary,.btn-secondary,.btn-danger,.btn-small,button,summary,.easy-nav a').evaluateAll(ns=>ns.filter(n=>n.checkVisibility()).filter(n=>{const r=n.getBoundingClientRect();return r.height<55||r.width<55}).map(n=>n.textContent));
    assert.deepEqual(tiny,[],`${width} ${path} tiny targets`);layouts++;
   }
  }
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/easy/settings');
  await page.locator('[data-display-setting][name=size][value="26"]').check();
  await page.goto(base+'/easy/f/ui/story/story');assert.equal(await page.locator('#articleBody').evaluate(n=>getComputedStyle(n).fontSize),'26px');
  await page.setViewportSize({width:320,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.goto(base+'/easy/f/ui/interview/new');await page.getByRole('button',{name:'开始这一段'}).click();assert(page.url().includes('/easy/f/ui/interview/'));
  await page.locator('#interview-answer-form [name=answer]').fill('小时候我和家人在老院子乘凉。');await page.getByRole('button',{name:'保存回答，下一题'}).click();assert(page.url().includes('/easy/'));
  await page.getByRole('button',{name:'先休息，稍后继续'}).click();await page.goto(base+'/easy');assert(await page.getByRole('link',{name:'继续上次讲述'}).isVisible());
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/private/tmp/memoir-easy-home.png',fullPage:true});
  await page.getByRole('link',{name:'继续上次讲述'}).click();await page.getByRole('button',{name:'结束本段，去整理'}).click();assert(page.url().includes('/easy/f/ui/organize/'));
  await page.getByRole('button',{name:'用当前原稿人工整理（不调用 AI）'}).click();await page.locator('[name=confirm_review]').check();await page.getByRole('button',{name:'保存为我的故事草稿'}).click();assert(page.url().includes('/edit'));
  assert.deepEqual(errors,[]);console.log(`Easy interview -> draft flow + ${layouts} layouts and large font passed`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
