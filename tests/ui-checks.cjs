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
    const external = [], errors = [];
    await context.route('**/*', route => {
      if(new URL(route.request().url()).origin === new URL(base).origin) return route.continue();
      external.push(route.request().url());return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    const paths = ['/?switch=1', '/f/ui', '/f/empty', '/f/ui/stories', '/f/ui/story/story', '/f/ui/person/grandma', '/f/ui/write', '/f/ui/ask', '/f/ui/more', '/account?family_id=ui', '/guide?family_id=ui', '/account/drafts?family_id=ui', '/f/ui/manage', '/display?family_id=ui', '/f/ui/plans', '/f/ui/shares', '/f/ui/sync'];
    let checks = 0;
    for (const width of [320,375,390,430,768,1280,1440]) {
      await page.setViewportSize({width,height:900});
      for (const path of paths) {
        const r = await page.goto(base + path, {waitUntil:'domcontentloaded'});
        assert.equal(r.status(),200, path);
        const layout = await page.evaluate(() => ({width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth}));
        assert(layout.scroll <= layout.width + 1, `${width} ${path}: overflow ${JSON.stringify(layout)}`);
        const bad = await page.locator('.btn-primary, .btn-secondary, .btn-small, .navlinks a, .read-btn, .replybtn, .likebtn, summary').evaluateAll(nodes => nodes.filter(n => n.getClientRects().length).filter(n => {
          const r=n.getBoundingClientRect(); return r.height < 43 || r.width < 43;
        }).map(n=>n.textContent.trim()));
        assert.deepEqual(bad,[], `${width} ${path}: small targets`);
        const covered=await page.locator('.form-actions a, .form-actions button, .navlinks a').evaluateAll(ns=>ns.filter(n=>{
          const r=n.getBoundingClientRect();
          if(!r.width || !r.height || r.top<0 || r.bottom>innerHeight)return false;
          const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return !hit || !n.contains(hit);
        }).map(n=>n.textContent.trim()));
        assert.deepEqual(covered,[],`${width} ${path}: covered actions`);
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
          const lowContrast=await page.locator('.hint, .navlinks a, .btn-primary, .btn-small, .replybtn, .likebtn, .engagement, #articleBody').evaluateAll(nodes=>{
            function rgb(s){return (s.match(/[\d.]+/g)||[]).map(Number);}
            function luminance(c){return c.slice(0,3).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;}).reduce((v,n,i)=>v+n*[.2126,.7152,.0722][i],0);}
            return nodes.filter(n=>n.getClientRects().length && n.textContent.trim() && !n.disabled).flatMap(n=>{
              let el=n,bg;
              while(el){bg=rgb(getComputedStyle(el).backgroundColor);if(bg.length===3 || bg[3]===1)break;el=el.parentElement;}
              if(!el)return [];
              const fg=rgb(getComputedStyle(n).color),a=luminance(fg),b=luminance(bg);
              const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
              return ratio<4.5?[{text:n.textContent.trim().slice(0,20),ratio}]:[];
            });
          });
          assert.deepEqual(lowContrast,[],`${theme} low contrast`);
          if(theme==='contrast') {
            const field = await page.locator('textarea[name=content]').evaluate(n=>({bg:getComputedStyle(n).backgroundColor,fg:getComputedStyle(n).color}));
            assert.equal(field.bg,'rgb(18, 18, 18)');assert.equal(field.fg,'rgb(255, 255, 255)');
          }
          if(process.env.UI_SCREENSHOTS && width===390 && theme==='contrast' && size==='26') {
            fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});
            await page.screenshot({path:process.env.UI_SCREENSHOTS+'/contrast-large-mobile.png',fullPage:true});
            await page.screenshot({path:process.env.UI_SCREENSHOTS+'/contrast-large-top-mobile.png'});
          }
          await page.goto(base+'/display?family_id=ui');
          checks++;
        }
      }
      await page.locator('#display-reset').click();
    }
    await page.setViewportSize({width:320,height:844});
    await page.goto(base+'/display?family_id=ui');
    await page.locator('input[name=size][value="26"]').check();
    await page.locator('input[name=font][value=rounded]').check();
    for(const theme of ['modern','paper','contrast']) {
      await page.goto(base+'/display?family_id=ui');
      await page.locator(`input[name=theme][value=${theme}]`).check();
      for(const path of paths) {
        await page.goto(base+path);
        const sizes=await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.clientWidth]);
        assert(sizes[0]<=sizes[1]+1,`${theme} 26px 320px ${path}: ${sizes}`);
        checks++;
      }
    }
    await page.goto(base+'/display?family_id=ui');await page.locator('#display-reset').click();
    await page.goto(base+'/f/ui');
    await page.locator('#family-tree summary').click();
    await page.waitForFunction(()=>document.querySelector('#tree canvas')?.width>200);
    await page.goto(base+'/f/ui/write');
    assert.equal(await page.locator('#editor-toolbar button[aria-label]').count(),5);
    await page.locator('#story-details').evaluate(n=>n.open=true);
    assert(await page.locator('select[name=subject_id]').isVisible());
    await page.locator('input[value=specific]').check();
    assert(await page.locator('#viewer-box').isVisible());
    assert(await page.locator('.ql-editor').isVisible(),'self-hosted editor unavailable');
    await page.locator('input[name=topic]').fill('UI 回归：一段可以继续编辑的回忆');
    await page.locator('.ql-editor').fill('这是在隔离测试库里保存的正文。');
    await page.locator('#editor-toolbar .ql-list').click();
    await page.locator('select[name=subject_id]').selectOption('grandma');
    await page.locator('input[name=visibility][value=private]').check();
    await page.locator('button[name=action][value=draft]').click();
    await page.waitForURL('**/drafts');
    await page.getByRole('link', {name:'继续编辑', exact:true}).click();
    assert.match(await page.locator('.ql-editor').innerText(),/隔离测试库/);
    assert.equal(await page.locator('select[name=subject_id]').inputValue(),'grandma');
    assert(await page.locator('input[name=visibility][value=private]').isChecked());
    await page.locator('button[name=action][value=publish]').click();
    await page.waitForURL('**/story/*');
    assert.match(await page.locator('#articleBody').textContent(),/隔离测试库/);
    assert.equal(await page.locator('#articleBody li[data-list=bullet]').evaluate(n=>getComputedStyle(n).listStyleType),'disc');
    // The fallback must keep existing HTML when the editor resource is unavailable.
    await context.route('**/quill-2.0.3.*.js',route=>route.abort());
    await page.goto(base+'/f/ui/write');
    assert(await page.locator('#editor-fallback').isVisible());
    await page.locator('input[name=topic]').fill('UI 文本降级测试');
    await page.locator('#editor-fallback').fill('编辑器加载失败后仍能保存。');
    await page.locator('button[name=action][value=draft]').click();
    await page.waitForURL('**/drafts');
    await context.unroute('**/quill-2.0.3.*.js');
    await page.goto(base+'/f/ui');
    await page.goto(base+'/');
    await page.waitForURL('**/f/ui/stories');
    await page.goto(base+'/?switch=1');
    assert.equal(await page.locator('a[data-family-choice]').count(),2);
    // A stale/revoked family cannot create a redirect outside the rendered list.
    await page.evaluate(()=>localStorage.setItem('memoir.last-family.v1.ui-user','not-authorized'));
    await page.goto(base+'/');
    assert.equal(await page.locator('a[data-family-choice]').count(),2);
    for(const path of ['/f/ui/story/story','/f/ui/write','/f/ui/manage']) {
      await page.setViewportSize({width:390,height:844});
      await page.goto(base+path);
      await page.evaluate(()=>{
        const nodes=Array.from(document.querySelectorAll('*'));
        const sizes=nodes.map(n=>parseFloat(getComputedStyle(n).fontSize));
        nodes.forEach((n,i)=>{if(sizes[i])n.style.setProperty('font-size',sizes[i]*2+'px','important');});
      });
      const metrics=await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.clientWidth]);
      assert(metrics[0]<=metrics[1]+1,`200% text ${path}: ${metrics}`);
    }
    await page.goto(base+'/f/ui/stories');
    await page.keyboard.press('Tab');
    assert(await page.locator('.skip-link').evaluate(n=>n===document.activeElement));
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
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
    assert.deepEqual(external,[], 'unexpected external runtime resources');
    assert.deepEqual(errors,[], 'browser JavaScript errors');
    console.log(`UI layout: ${checks} pages/viewports passed; 14-level comments, self-hosted assets, preferences, draft/edit/publish and editor fallback passed.`);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
