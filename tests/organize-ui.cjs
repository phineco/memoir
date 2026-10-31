const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try {
  const context=await browser.newContext(); const base=process.env.UI_TEST_URL;
  assert.equal((await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}})).status(),200);
  const page=await context.newPage(); const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/f/ui/organize/new');
  await page.locator('[name=content]').fill('小时候我在老院子里长大。夏天的傍晚，妈妈会带着我们坐在门口乘凉。');
  await page.getByRole('button',{name:'保存原稿（仅自己）'}).click();
  const recordUrl=page.url().split('?')[0];
  await page.getByRole('button',{name:'用当前原稿人工整理（不调用 AI）'}).click();
  await page.locator('[name=title]').fill('老院子的夏夜');
  await page.locator('[name=body]').fill('妈妈带着我们在门口乘凉。');
  assert(await page.locator('[data-preview-confirm] button[type=submit]').isDisabled());
  await page.getByRole('button',{name:'暂存核对结果'}).click();
  await page.reload();assert.equal(await page.locator('[name=body]').inputValue(),'妈妈带着我们在门口乘凉。');
  let layouts=0;
  for(const width of [320,375,390,430,768,1280,1440]){
   await page.setViewportSize({width,height:900});
   for(const path of ['/f/ui/organize/new','/account/organize',new URL(recordUrl).pathname]){
    assert.equal((await page.goto(base+path)).status(),200);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),`${width} ${path} overflow`);
    const tiny=await page.locator('.btn-primary,.btn-secondary,.btn-danger,summary').evaluateAll(nodes=>nodes.filter(n=>n.checkVisibility()).filter(n=>{const r=n.getBoundingClientRect();return r.width<43||r.height<43}).map(n=>n.textContent));
    assert.deepEqual(tiny,[]);layouts++;
   }
  }
  await page.goto(recordUrl);await page.locator('[name=confirm_review]').check();
  await page.getByRole('button',{name:'保存为我的故事草稿'}).click();
  assert(page.url().includes('/edit'));
  assert.equal(await page.locator('[name=topic]').inputValue(),'老院子的夏夜');
  await page.goto(recordUrl);assert(await page.getByRole('link',{name:'进入故事编辑'}).isVisible());
  assert.deepEqual(errors,[]);console.log(`Organize manual flow + ${layouts} layout checks passed`);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
