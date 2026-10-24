/* Disposable UI data only: measure scrolling and verify usable button targets. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext();
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const dir=process.env.UI_SCREENSHOTS||'/private/tmp/memoir-menu-qa';fs.mkdirSync(dir,{recursive:true});
  const baselinePath=path.join(dir,'menu-baseline.json');
  const baseline=fs.existsSync(baselinePath)?JSON.parse(fs.readFileSync(baselinePath)):{};
  const result={},reduction=[];
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});
   for(const mode of ['normal','large','contrast']){
    await page.goto(base+'/display?family_id=ui');await page.locator('#display-reset').click();
    if(mode!=='normal'){
     await page.locator('[name=size][value="26"]').check();await page.locator('[name=mode][value=simple]').check();
     if(mode==='contrast')await page.locator('[name=theme][value=contrast]').check();
    }
    for(const [name,url] of [['more','/f/ui/more'],['account','/account?family_id=ui']]){
     await page.goto(base+url);
     const key=name+'-'+width+'-'+mode;
     const metrics=await page.locator('main').evaluate(n=>({height:n.getBoundingClientRect().height,scroll:document.documentElement.scrollWidth,width:innerWidth}));
     result[key]=metrics.height;assert(metrics.scroll<=metrics.width+1,key+' horizontal overflow');
     if(process.env.MENU_BASELINE_WRITE!=='1'){
      assert.equal(await page.locator('main a.card').count(),0,key+' still has clickable cards');
      const buttons=page.locator('.menu-buttons a:visible');assert(await buttons.count()>4);
      const bad=await buttons.evaluateAll(ns=>ns.filter(n=>{
       const r=n.getBoundingClientRect();return r.height<48||r.width<44||n.scrollWidth>n.clientWidth+1||n.scrollHeight>n.clientHeight+1;
      }).map(n=>n.innerText));assert.deepEqual(bad,[],key+' clipped or undersized controls');
      for(const button of await buttons.all()){
       await button.scrollIntoViewIfNeeded();
       assert(await button.evaluate(n=>{const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}),key+' covered control');
      }
      await page.evaluate(()=>scrollTo(0,0));
      if(baseline[key] && width<768){const ratio=1-metrics.height/baseline[key];assert(ratio>.25,key+' did not reduce scrolling by 25%');reduction.push(Math.round(ratio*100));}
      const names=await buttons.allTextContents();
      for(const label of name==='more'?['问 AI','写作计划','周报','生成电子书','使用帮助','家庭管理']:['关于我的故事','我记录的故事','我的草稿','导出我的文章','我的声音','显示设置','我的家庭','隐私申请'])assert(names.some(n=>n.trim()===label),label+' missing');
      if(name==='more'){
       assert.equal(await page.getByRole('link',{name:'导出我的文章',exact:true}).count(),0);
       assert.match(await page.locator('main').innerText(),/付费功能.*尚未开放/);
      }
      if(mode==='large')await page.screenshot({path:path.join(dir,'compact-'+name+'-'+width+'.png'),fullPage:true});
     }
    }
   }
  }
  assert.deepEqual(errors,[]);
  if(process.env.MENU_BASELINE_WRITE==='1'){fs.writeFileSync(baselinePath,JSON.stringify(result,null,2));console.log('Captured previous menu heights: '+JSON.stringify(result));}
  else console.log('Compact menus: 18 layouts, large text/high contrast, target size, coverage and entries passed.'+(reduction.length?' Mobile content height reduced '+Math.min(...reduction)+'–'+Math.max(...reduction)+'%.':''));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
