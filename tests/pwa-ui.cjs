const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext();const base=process.env.UI_TEST_URL;const page=await context.newPage();
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await page.goto(base+'/easy?family_id=ui');
  const scope=await page.evaluate(()=>navigator.serviceWorker.ready.then(r=>r.scope));assert.equal(scope,base+'/easy');
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
  const audio='/f/ui/interview/pwa-session/audio/'+'d'.repeat(64),photo='/f/ui/album/'+'c'.repeat(32)+'/image';
  for(const path of ['/easy/records','/easy/f/ui/interview/pwa-session',audio,photo])assert.equal(await page.evaluate(async url=>(await fetch(url,{cache:'no-store'})).status,path),200);
  const keys=()=>page.evaluate(async()=>{const rows=[];for(const name of await caches.keys())for(const request of await (await caches.open(name)).keys())rows.push(new URL(request.url).pathname);return rows;});
  const paths=await keys();assert(paths.length>=21);assert(paths.every(p=>p.startsWith('/static/dist/')||p.startsWith('/static/icons/')||p==='/static/easy-offline.html'));
  await page.goto(base+'/easy/f/ui/organize/new');await page.locator('[name=content]').fill('尚未保存的原稿');
  await page.evaluate(async()=>{const cache=await caches.open('memoir-easy-static-obsolete');await cache.put('/static/obsolete.js',new Response('old public static'));});
  await context.request.post(base+'/__pwa_test_version',{headers:{'X-PWA-Test':'local-only-synthetic'}});
  await page.evaluate(async()=>{const registration=await navigator.serviceWorker.getRegistration('/easy');await registration.update();});
  await page.waitForFunction(()=>!document.getElementById('easy-update').hidden);
  await page.locator('#easy-update-button').click();assert((await page.locator('#easy-update-status').textContent()).includes('请先保存'));
  assert(await page.evaluate(async()=>!!(await navigator.serviceWorker.getRegistration('/easy')).waiting));
  await page.locator('[name=content]').fill('');
  await Promise.all([page.waitForNavigation({waitUntil:'load'}),page.locator('#easy-update-button').click()]);
  const names=await page.evaluate(()=>caches.keys());assert(names.length===1&&names[0].startsWith('memoir-easy-static-'));
  await context.setOffline(true);await page.goto(base+'/easy/records');
  assert((await page.locator('body').textContent()).includes('暂时没有网络'));
  assert(!(await page.locator('body').textContent()).includes('岁月里的家'));
  assert(await page.evaluate(async url=>{try{await fetch(url);return false}catch(e){return true}},audio));
  const css=(await keys()).find(p=>p.endsWith('.css'));assert.equal(await page.evaluate(async url=>(await fetch(url)).status,css),200);
  await context.setOffline(false);await context.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});
  await page.goto(base+'/easy/records?family_id=ui');assert(!(await page.locator('body').textContent()).includes('私有缓存测试问题'));
  assert.equal(await page.evaluate(async url=>(await fetch(url)).status,audio),404);
  assert((await keys()).every(p=>p.startsWith('/static/')));
  await context.request.get(base+'/logout');await page.goto(base+'/easy');assert(page.url().includes('/easy/login?next='));
  console.log('PWA scope, public-only caches, guarded update, offline privacy and account switch passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
