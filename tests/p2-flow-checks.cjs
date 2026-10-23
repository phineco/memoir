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
  async function navigate(action,target=page) {
    const [response]=await Promise.all([target.waitForNavigation({waitUntil:'domcontentloaded'}),action()]);
    assert.equal(response.status(),200);
  }
  async function search(term) {
    await page.locator('[name=q]').fill(term);
    await navigate(()=>page.getByRole('button',{name:'搜索',exact:true}).click());
  }
  await page.goto(base+'/f/ui/stories');
  await search('老院子');
  assert.equal(await page.locator('.story-results a.card').count(),1);
  await search('没有这篇xyz');
  assert(await page.getByRole('heading',{name:'没有找到符合条件的故事'}).isVisible());
  await search('分页测试');
  assert.equal(await page.locator('.story-results a.card').count(),20);
  await navigate(()=>page.getByRole('link',{name:'下一页',exact:true}).click());
  assert.equal(await page.locator('.story-results a.card').count(),5);
  assert.equal(new URL(page.url()).searchParams.get('q'),'分页测试');
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});await page.locator('summary').first().click();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.reload();
  }
  await page.goto(base+'/account/ai-memory?family_id=ui');
  page.once('dialog',dialog=>dialog.accept());
  await navigate(()=>page.getByRole('button',{name:'重置此家庭的 AI 记忆'}).click());
  await page.locator('.success[role="status"]').waitFor({state:'visible'});
  assert.match(await page.locator('.success[role="status"]').innerText(),/摘要已清空/);
  await page.goto(base+'/account/privacy-requests');
  await page.locator('[name=details]').fill('请处理这个测试账号的旧对话记录。');
  await Promise.all([page.waitForURL(/\/account\/privacy-requests\/[a-f0-9]{64}/),page.getByRole('button',{name:'提交申请',exact:true}).click()]);
  const requestPath=new URL(page.url()).pathname;
  assert.match(await page.locator('body').innerText(),/待运营人员反馈/);
  assert.equal((await context.request.get(base+'/operations/privacy')).status(),403);
  const operator=await browser.newContext();
  await operator.request.post(base+'/login',{form:{phone:'ui-operator',password:'ui-operator-test-only'}});
  const op=await operator.newPage();await op.goto(base+requestPath.replace('/account/privacy-requests/','/operations/privacy/'));
  await op.locator('[name=content]').fill('已收到，正在核验申请范围。');
  await navigate(()=>op.getByRole('button',{name:'提交人工反馈',exact:true}).click(),op);
  await op.getByText('已收到，正在核验申请范围。',{exact:true}).waitFor();
  await page.reload();assert.match(await page.locator('body').innerText(),/已收到，正在核验申请范围/);
  await op.locator('[name=content]').fill('已完成合成测试资料的处理。');
  await op.locator('[name=status]').selectOption('completed');await op.locator('[name=verified]').check();
  await navigate(()=>op.getByRole('button',{name:'提交人工反馈',exact:true}).click(),op);
  await op.getByText('已完成合成测试资料的处理。',{exact:true}).waitFor();
  await page.reload();assert.match(await page.locator('body').innerText(),/已处理完成/);
  await operator.close();
  assert.deepEqual(errors,[]);
  console.log('P2 flow: search, pagination, 3 viewport layouts, AI reset, private request submission and explicit-operator feedback/completion passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
