const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext();
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:900});
   await page.goto(base+'/display?family_id=ui');
   await page.locator('[name=size][value="26"]').check();
   await page.locator('[name=mode][value=simple]').check();
   for(const [path,active] of [['/f/ui?view=list','家人'],['/f/ui?view=tree','家人'],['/f/ui/stories','故事'],['/f/ui/album','相册'],['/f/ui/more','更多'],['/account?family_id=ui',null],['/guide?family_id=ui',null]]){
    await page.goto(base+path);
    assert.deepEqual(await page.locator('.navlinks a').allTextContents(),['家人','故事','相册','更多']);
    assert.deepEqual(await page.locator('.navlinks [aria-current=page]').allTextContents(),active?[active]:[]);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),width+' '+path);
    if(path.includes('view=tree')){
     await page.waitForFunction(()=>document.querySelector('#tree canvas')?.width>0);
     assert(await page.getByRole('link',{name:/林奶奶/}).isVisible());
     if(process.env.UI_SCREENSHOTS){fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:process.env.UI_SCREENSHOTS+'/people-tree-'+width+'.png',fullPage:true});}
    }
   }
   await page.goto(base+'/f/ui?view=tree');
   await page.getByRole('link',{name:/林奶奶/}).click();
   assert.equal(new URL(page.url()).searchParams.get('return_to'),'/f/ui?view=tree');
   await page.getByRole('link',{name:'← 返回家人',exact:true}).click();
   assert.equal(new URL(page.url()).searchParams.get('view'),'tree');
   await page.goto(base+'/f/ui?view=list&q=奶奶');
   assert.equal(await page.locator('#family-people .person-card').count(),1);
   await page.locator('.family-switch summary').click();
   await page.locator('.family-switch-panel').getByRole('link',{name:'等待第一段故事的家',exact:true}).click();
   assert.equal(new URL(page.url()).pathname,'/f/empty');
   assert.equal(await page.locator('.navlinks [aria-current=page]').innerText(),'家人');
  }
  await context.route('**/echarts-*.js',r=>r.abort());
  await page.goto(base+'/f/ui?view=tree');
  assert.match(await page.locator('#tree-status').innerText(),/暂时无法显示/);
  assert(await page.locator('#family-people .person-card').first().isVisible());
  const plain=await browser.newContext({javaScriptEnabled:false,viewport:{width:320,height:900}});
  await plain.addCookies(await context.cookies());const plainPage=await plain.newPage();await plainPage.goto(base+'/f/ui?view=tree');
  assert(await plainPage.locator('#family-people .person-card').first().isVisible());
  assert.deepEqual(errors,[]);
  console.log('Navigation redesign: four groups, large-text tree/list, return context, search, family switching and no-JS/chart failure at 320/390/1280 passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
