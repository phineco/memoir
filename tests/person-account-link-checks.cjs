const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext();
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/display?family_id=ui');await page.locator('[name=size][value="26"]').check();
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:900});await page.goto(base+'/f/ui/tree/add');
   const select=page.locator('[name=link_user_id]');await select.scrollIntoViewIfNeeded();
   assert(await select.isVisible());assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   assert.deepEqual(await select.locator('option').evaluateAll(items=>items.map(i=>i.value).sort()),['','ui-relative','ui-user']);
   await select.selectOption('ui-relative');await page.locator('[name=name]').fill('创建即关联'+width);
   await page.getByRole('button',{name:'添加',exact:true}).click();await page.waitForURL('**/f/ui');
   const href=await page.locator('#family-people').getByRole('link',{name:new RegExp('创建即关联'+width)}).getAttribute('href');
   const pid=new URL(href,base).pathname.split('/').pop();
   await page.goto(base+'/f/ui/tree/'+pid+'/edit');
   assert.equal(await page.locator('[name=link_user_id]').inputValue(),'ui-relative');
   await page.goto(base+'/f/ui/tree/add');await page.locator('[name=name]').fill('重复关联'+width);
   await page.locator('[name=link_user_id]').selectOption('ui-relative');await page.getByRole('button',{name:'添加',exact:true}).click();
   assert.match(await page.locator('.error').innerText(),/一人只能关联一个人物/);
   assert.equal(await page.locator('[name=link_user_id]').inputValue(),'ui-relative');
   await page.goto(base+'/f/ui/tree/'+pid+'/edit');await page.locator('[name=link_user_id]').selectOption('');
   await page.getByRole('button',{name:'保存修改',exact:true}).click();await page.waitForURL('**/person/'+pid);
   await page.goto(base+'/f/ui/tree/'+pid+'/edit');assert.equal(await page.locator('[name=link_user_id]').inputValue(),'');
  }
  assert.deepEqual(errors,[]);
  console.log('Person account link: create selector, first-save persistence, duplicate error with selection retained and edit unlink passed at 320/390/1280 with large text.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
