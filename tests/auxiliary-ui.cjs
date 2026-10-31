const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});const base=process.env.UI_TEST_URL;
  await context.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/f/ui/organize');await page.getByRole('link',{name:/辅助联动原稿/}).click();
  const material=page.url();assert(await page.getByRole('heading',{name:'已发布故事',exact:true}).isVisible());
  await page.getByText('选择人物建议交管理员核对',{exact:true}).click();await page.locator('[name=people_index][value="0"]').check();await page.locator('[name=confirm_share]').check();
  await page.getByRole('button',{name:'提交人物建议',exact:true}).click();assert((await page.locator('[role=status]').first().textContent()).includes('人物建议已提交'));
  await page.getByText('建议更新写作计划',{exact:true}).click();await page.getByRole('button',{name:/建议“辅助采访计划”此条进行中/}).click();
  assert((await page.locator('[role=status]').first().textContent()).includes('进度建议已提交'));
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  assert.equal((await context.request.get(material)).status(),404);
  await page.goto(base+'/f/ui/people/suggestions');assert(await page.getByRole('heading',{name:'邻居阿姨',exact:true}).isVisible());
  for(const width of [320,390,1280]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  await page.getByText('或新增独立人物',{exact:true}).click();await page.getByRole('button',{name:'确认新增人物（不建关系）'}).click();
  await page.goto(base+'/f/ui');assert(await page.getByRole('link',{name:/邻居阿姨/}).isVisible());
  await page.goto(base+'/f/ui/plans');await page.getByText('待确认的进度建议（1）',{exact:true}).click();await page.getByRole('button',{name:'确认此条进行中',exact:true}).click();
  assert((await page.locator('body').textContent()).includes('进行中'));
  const editable=await page.getByRole('link',{name:'编辑',exact:true}).getAttribute('href');await page.goto(base+editable);assert.equal(await page.locator('[name=item_status]').first().inputValue(),'doing');
  assert.deepEqual(errors,[]);console.log('Public evidence submission, admin person confirmation, plan review and 3 layouts passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
