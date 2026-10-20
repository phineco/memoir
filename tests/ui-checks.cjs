/* Run against tests/ui_server.py only. It owns a disposable database. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless:true, channel:process.env.UI_BROWSER_CHANNEL || "chrome"});
  try {
    const context = await browser.newContext();
    const base = process.env.UI_TEST_URL || 'http://127.0.0.1:5015';
    const response = await context.request.post(base + '/login', {form:{phone:'ui-test', password:'ui-test-only'}});
    assert.equal(response.status(), 200);
    const page = await context.newPage();
    const paths = ['/', '/f/ui', '/f/empty', '/f/ui/stories', '/f/ui/story/story', '/f/ui/person/grandma', '/f/ui/write', '/f/ui/ask', '/f/ui/more', '/f/ui/manage', '/display?family_id=ui', '/f/ui/plans', '/f/ui/shares', '/f/ui/sync'];
    let checks = 0;
    for (const width of [320,390,768,1280]) {
      await page.setViewportSize({width,height:900});
      for (const path of paths) {
        const r = await page.goto(base + path, {waitUntil:'domcontentloaded'});
        assert.equal(r.status(),200, path);
        const layout = await page.evaluate(() => ({width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth}));
        assert(layout.scroll <= layout.width + 1, `${width} ${path}: overflow ${JSON.stringify(layout)}`);
        const bad = await page.locator('.form-actions a, .form-actions button, .navlinks a, .read-btn, .suggest-q').evaluateAll(nodes => nodes.filter(n => n.getClientRects().length).filter(n => {
          const r=n.getBoundingClientRect(); return r.height < 43 || r.width < 43;
        }).map(n=>n.textContent.trim()));
        assert.deepEqual(bad,[], `${width} ${path}: small targets`);
        checks++;
      }
    }
    await page.goto(base+'/f/ui/story/story');
    assert.equal(await page.locator('.comment').count(),14);
    const widths=await page.locator('.comment').evaluateAll(ns=>ns.map(n=>n.getBoundingClientRect().width));
    assert(Math.min(...widths)>200,'deep comments become too narrow');
    for (const width of [320,390,1280]) {
      await page.setViewportSize({width,height:900});
      await page.goto(base+'/display?family_id=ui');
      for(const theme of ['modern','paper','contrast']) {
        for(const size of ['18','22','26']) {
          await page.locator(`input[name=theme][value=${theme}]`).check();
          await page.locator(`input[name=size][value="${size}"]`).check();
          await page.locator('input[name=font][value=serif]').check();
          await page.locator('input[name=mode][value=simple]').check();
          await page.goto(base+'/f/ui/story/story');
          assert.equal(await page.locator('html').getAttribute('data-theme'),theme);
          assert.equal(await page.locator('html').getAttribute('data-size'),size);
          assert.equal(await page.locator('html').getAttribute('data-font'),'serif');
          const metric=await page.locator('#articleBody').evaluate(n=>({font:parseFloat(getComputedStyle(n).fontSize),scroll:document.documentElement.scrollWidth,width:document.documentElement.clientWidth}));
          assert.equal(metric.font,Number(size));assert(metric.scroll<=metric.width+1,JSON.stringify(metric));
          if(process.env.UI_SCREENSHOTS && width===390 && theme==='contrast' && size==='26') {
            fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});
            await page.screenshot({path:process.env.UI_SCREENSHOTS+'/contrast-large-mobile.png',fullPage:true});
          }
          await page.goto(base+'/display?family_id=ui');
          checks++;
        }
      }
      await page.locator('#display-reset').click();
    }
    await page.goto(base+'/f/ui/write');
    assert.equal(await page.locator('#editor-toolbar button[aria-label]').count(),5);
    await page.locator('#story-details').evaluate(n=>n.open=true);
    assert(await page.locator('select[name=subject_id]').isVisible());
    await page.locator('input[value=specific]').check();
    assert(await page.locator('#viewer-box').isVisible());
    const unavailable=await browser.newContext();
    await unavailable.addInitScript(() => Object.defineProperty(window,'localStorage',{get(){throw Error('storage unavailable');}}));
    const settings=await unavailable.newPage();
    await settings.goto(base+'/display');
    await settings.locator('input[name=size][value="26"]').check();
    assert.equal(await settings.locator('html').getAttribute('data-size'),'26');
    assert.match(await settings.locator('#display-status').textContent(),/未允许保存/);
    await unavailable.close();
    if(process.env.UI_SCREENSHOTS) {
      fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});
      for (const [name,path,width] of [['family-mobile','/f/ui',390],['story-mobile','/f/ui/story/story',390],['family-desktop','/f/ui',1280],['write-mobile','/f/ui/write',390]]) {
        await page.setViewportSize({width,height:844}); await page.goto(base+path); await page.screenshot({path:`${process.env.UI_SCREENSHOTS}/${name}.png`,fullPage:true});
      }
    }
    console.log(`UI layout: ${checks} pages/viewports passed; 14-level comments readable.`);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
