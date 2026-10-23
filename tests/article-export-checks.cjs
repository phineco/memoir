const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'memoir-export-browser-'));
 try {
  const base=process.env.UI_TEST_URL;
  const context=await browser.newContext({viewport:{width:390,height:844},acceptDownloads:true});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/account?family_id=ui');await page.getByRole('link',{name:/导出我的文章/}).click();
  await page.waitForURL('**/f/ui/exports/articles');
  assert.match(await page.locator('body').innerText(),/我记录的文章与草稿/);
  const pending=page.waitForEvent('download');
  await page.getByRole('button',{name:/下载本范围全部文章/}).click();
  const download=await pending;assert.equal(await download.failure(),null);
  const zip=path.join(temp,'articles.zip');await download.saveAs(zip);
  execFileSync(path.resolve('.venv/bin/python'),['-c','import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])',zip,temp]);
  const data=JSON.parse(fs.readFileSync(path.join(temp,'articles.json'),'utf8'));
  assert(data.articles.length>=1);assert.equal(data.export.article_count,data.articles.length);
  const offline=await browser.newContext({viewport:{width:320,height:844}});
  const read=await offline.newPage(),outside=[];
  read.on('request',req=>{if(/^https?:/.test(req.url()))outside.push(req.url());});
  await read.goto('file://'+path.join(temp,'index.html'));
  assert.match(await read.locator('body').innerText(),/夏天的傍晚/);
  assert.equal(await read.locator('article').count(),data.articles.length);
  assert(await read.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(outside,[]);await offline.close();
  await page.goto(base+'/f/ui/manage/tools');await page.getByRole('link',{name:'查看导出范围',exact:true}).click();
  assert(new URL(page.url()).searchParams.get('scope')==='family');
  await page.goto(base+'/display?family_id=ui');await page.locator('[name=size][value="26"]').check();
  for(const width of [320,390,1280]) {
   await page.setViewportSize({width,height:844});
   for(const target of ['/account/exports','/f/ui/exports/articles','/f/ui/exports/articles?scope=family','/f/empty/exports/articles','/f/ui/ebook','/f/ui/manage/tools','/f/empty']) {
    await page.goto(base+target);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),target+' '+width);
   }
  }
  assert.deepEqual(errors,[]);
  console.log('Article export: personal/family entry, real ZIP download and offline reading without network, empty state and seven pages at three large-text widths passed.');
 } finally {await browser.close();fs.rmSync(temp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
