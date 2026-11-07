const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL;
  for(const mode of ['native','missing','denied']){
   const context=await browser.newContext();
   if(mode!=='native')await context.addInitScript(kind=>{Element.prototype.requestFullscreen=kind==='missing'?undefined:function(){return Promise.reject(new Error('Denied'))};},mode);
   await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   for(const width of (mode==='native'?[1280]:[390,320])){
    await page.setViewportSize({width,height:844});await page.goto(base+'/f/ui?view=tree');
    await page.waitForFunction(()=>document.querySelectorAll('#tree .tree-person-card').length>0);
    const section=page.locator('#family-tree'),button=page.getByRole('button',{name:'全屏查看家族树',exact:true});
    await page.getByRole('button',{name:'放大家族树',exact:true}).click();
    const zoom=await page.evaluate(()=>f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg')).k);
    await button.click();await page.waitForFunction(()=>document.getElementById('family-tree').classList.contains('tree-fullscreen'));
    const exit=page.getByRole('button',{name:'退出家族树全屏',exact:true});await page.waitForFunction(()=>!document.querySelector('[data-tree-action=fullscreen]').disabled);
    assert.equal(await section.getAttribute('aria-modal'),'true');
    if(mode==='native')assert.equal(await page.evaluate(()=>document.fullscreenElement?.id),'family-tree');
    else assert.equal(await page.evaluate(()=>document.fullscreenElement),null);
    const box=await section.boundingBox();assert(Math.abs(box.x)<1&&Math.abs(box.y)<1);
    const screen=await page.evaluate(()=>[innerWidth,innerHeight]);assert(Math.abs(box.width-screen[0])<2&&Math.abs(box.height-screen[1])<2);
    assert(Math.abs(await page.evaluate(()=>f3.handlers.getCurrentZoom(document.querySelector('#tree svg.main_svg')).k)-zoom)<.001);
    const exitBox=await exit.boundingBox();assert(exitBox.y>=0&&exitBox.y+exitBox.height<screen[1]);
    assert(await page.locator('#tree').evaluate(n=>n.clientHeight>160));
    await page.getByRole('button',{name:'缩小家族树',exact:true}).click();
    await page.getByRole('button',{name:'移动家族树',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'移动家族树',exact:true}).getAttribute('aria-pressed'),'true');
    await page.getByRole('button',{name:'重置视图',exact:true}).click();
    assert.equal(await exit.getAttribute('aria-pressed'),'true');
    if(process.env.UI_SCREENSHOTS){fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.UI_SCREENSHOTS,'tree-fullscreen-'+mode+'-'+width+'.png')});}
    await exit.click();await page.waitForFunction(()=>!document.querySelector('.tree-fullscreen'));
    assert.equal(await page.evaluate(()=>document.body.classList.contains('tree-fullscreen-open')),false);
    assert.equal(await page.evaluate(()=>document.fullscreenElement),null);
    await button.click();await page.waitForFunction(()=>!document.querySelector('[data-tree-action=fullscreen]').disabled);
    if(mode==='native')await page.evaluate(()=>document.exitFullscreen());else await page.keyboard.press('Escape');
    await page.waitForFunction(()=>!document.querySelector('.tree-fullscreen'));
    assert.equal(await section.getAttribute('aria-modal'),null);
   }
   assert.deepEqual(errors,[]);await context.close();
  }
  console.log('Tree fullscreen: native/missing/denied API, mobile viewport, zoom retention, tools, exit button and Escape/OS exit passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
