const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try {
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function openMenu() {
   const toggle=page.locator('#site-menu-toggle');
   if(await toggle.isVisible() && await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
  }
  async function checkMenu(fid) {
   await openMenu();
   assert.equal(await page.locator('nav[aria-label="家庭导航"] a').count(),4);
   for(const [title,tail] of [['故事','stories'],['家人',''],['记录','write'],['更多','more']]) {
    const link=page.locator('nav[aria-label="家庭导航"]').getByRole('link',{name:title,exact:true});
    assert(await link.isVisible());assert.equal(await link.getAttribute('href'),'/f/'+fid+(tail?'/'+tail:''));
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   // Close the expanded mobile panel before interacting with the content below it.
   await page.keyboard.press('Escape');
  }
  await page.goto(base+'/display?family_id=ui');await page.locator('[name=size][value="26"]').check();
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});
   await page.goto(base+'/account?family_id=ui');
   await page.getByRole('link',{name:/我的声音授权/}).click();
   assert.equal(new URL(page.url()).searchParams.get('family_id'),'ui');
   await checkMenu('ui');
   await page.locator('main').getByRole('link',{name:'← 个人中心',exact:true}).click();
   assert.equal(new URL(page.url()).searchParams.get('family_id'),'ui');
   await page.getByRole('link',{name:/我的家庭/}).click();
   assert.equal(new URL(page.url()).searchParams.get('switch'),'1');
   assert.equal(await page.locator('a[data-family-choice]').count(),2);
   await checkMenu('ui');
   await page.locator('a[data-family-choice="empty"]').click();
   await checkMenu('empty');
   await openMenu();
   await page.getByRole('link',{name:'个人中心：测试家人',exact:true}).click();
   await page.getByRole('link',{name:/我的声音授权/}).click();
   assert.equal(new URL(page.url()).searchParams.get('family_id'),'empty');
   await checkMenu('empty');
  }
  assert.deepEqual(errors,[]);
  console.log('Account navigation: voice authorizations, return to account, explicit family picker, switch to another family and large-text menus at 320/390/1280 passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
