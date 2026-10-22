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
    async function openMenu(target) {
      const toggle=target.locator('#site-menu-toggle');
      if(await toggle.isVisible() && await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
    }
    const page = await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    const paths = ['/?switch=1', '/terms', '/privacy', '/register', '/f/ui', '/f/empty', '/f/ui/stories', '/f/ui/story/story', '/f/ui/story/story/history', '/f/ui/person/grandma', '/f/ui/write', '/f/ui/ask', '/f/ui/more', '/account?family_id=ui', '/guide?family_id=ui', '/account/drafts?family_id=ui', '/f/ui/manage', '/f/ui/manage/accounts', '/f/ui/manage/invites', '/f/ui/manage/tools', '/f/ui/tree/add', '/f/ui/tree/grandma/edit', '/display?family_id=ui', '/f/ui/plans', '/f/ui/shares', '/f/ui/sync'];
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
          if(!n.checkVisibility() || !r.width || !r.height || r.top<0 || r.bottom>innerHeight)return false;
          const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return !hit || !n.contains(hit);
        }).map(n=>n.textContent.trim()));
        assert.deepEqual(covered,[],`${width} ${path}: covered actions`);
        checks++;
      }
    }
    // Mobile navigation is one compact row, remains visible while reading, and is keyboard usable.
    await page.setViewportSize({width:390,height:844});
    await page.goto(base+'/f/ui/story/story');
    const menuToggle=page.locator('#site-menu-toggle');
    assert(await menuToggle.isVisible());
    assert(!(await page.locator('#site-menu').isVisible()));
    assert(await page.locator('.topbar').evaluate(n=>n.getBoundingClientRect().height<80));
    await page.evaluate(()=>window.scrollTo(0,700));
    assert(Math.abs(await page.locator('.topbar').evaluate(n=>n.getBoundingClientRect().top))<1);
    await menuToggle.click();
    assert.equal(await page.getByRole('navigation',{name:'家庭导航'}).getByRole('link').count(),4);
    await page.keyboard.press('Escape');
    assert.equal(await menuToggle.getAttribute('aria-expanded'),'false');
    assert(await menuToggle.evaluate(n=>n===document.activeElement));
    await menuToggle.click();
    await page.locator('#articleBody').click();
    assert.equal(await menuToggle.getAttribute('aria-expanded'),'false');
    await page.setViewportSize({width:1280,height:844});
    await page.locator('#site-menu').waitFor({state:'visible'});
    assert(await page.locator('#site-menu').isVisible());
    assert(!(await menuToggle.isVisible()));
    const plainContext=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});
    await plainContext.addCookies(await context.cookies());
    const plainPage=await plainContext.newPage();await plainPage.goto(base+'/f/ui');
    assert.equal(await plainPage.getByRole('navigation',{name:'家庭导航'}).getByRole('link').count(),4);
    await plainContext.close();
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
    for(const path of ['/f/ui/story/story','/f/ui/write','/f/ui/manage','/f/ui/tree/add']) {
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
    await page.goto(base+'/f/ui');
    await openMenu(page);
    await page.locator('.auth a[aria-label^="个人中心"]').click();
    await page.waitForURL('**/account?family_id=ui');
    assert(await page.locator('.menu-cards a[href^="/display"]').isVisible());
    await openMenu(page);
    await page.getByRole('link',{name:'帮助',exact:true}).click();
    await page.waitForURL('**/guide?family_id=ui');
    assert.equal(await page.locator('.navlinks a').count(),4);
    await openMenu(page);
    assert(await page.locator('.auth a[aria-label^="个人中心"]').isVisible());
    await page.goto(base+'/f/ui/tree/add');
    await page.locator('input[name=name]').fill('双历日期回归人物');
    for(const [name,value] of Object.entries({birth_solar_year:'1940',birth_solar_month:'2',birth_solar_day:'29',birth_lunar_year:'1940',birth_lunar_month:'1',birth_lunar_day:'22',death_solar_year:'2001',death_solar_month:'3',death_solar_day:'1',death_lunar_year:'2001',death_lunar_month:'2',death_lunar_day:'7'})) {
      const field=page.locator(`[name=${name}]`);
      if(name.endsWith('_year'))await field.fill(value);else await field.selectOption(value);
    }
    await page.locator('input[name=birth_lunar_leap]').check();
    await page.getByRole('button',{name:'添加',exact:true}).click();
    await page.waitForURL('**/f/ui');
    await page.getByRole('link').filter({hasText:'双历日期回归人物'}).click();
    await page.waitForURL('**/person/*');
    assert.match(await page.locator('.stats').innerText(),/公历 1940年2月29日 \/ 农历 1940年闰正月廿二/);
    assert.match(await page.locator('.stats').innerText(),/去世：公历 2001年3月1日 \/ 农历 2001年二月初七/);
    await page.getByRole('link',{name:'✏️ 编辑人物',exact:true}).click();
    assert.equal(await page.locator('[name=birth_solar_day]').inputValue(),'29');
    assert.equal(await page.locator('[name=death_lunar_day]').inputValue(),'7');
    assert(await page.locator('[name=birth_lunar_leap]').isChecked());
    await page.locator('[name=birth_solar_day]').selectOption('28');
    await page.getByRole('button',{name:'保存修改',exact:true}).click();
    await page.waitForURL('**/person/*');
    assert.match(await page.locator('.stats').innerText(),/公历 1940年2月28日/);
    await page.goto(base+'/f/ui/manage/invites');
    await page.locator('[name=days]').fill('7');
    await page.getByRole('button',{name:'生成邀请链接',exact:true}).click();
    await page.waitForURL('**/f/ui/manage/invites');
    const invitation=page.locator('.invite-card').first();
    assert.match(await invitation.locator('.invite-link').innerText(),/^https:\/\/family\.scyllatech\.cn\/join\/[A-Za-z0-9_-]+$/);
    await invitation.locator('img').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>document.querySelector('.invite-qr')?.naturalWidth>=256);
    const [download]=await Promise.all([
      page.waitForEvent('download'),
      invitation.getByRole('link',{name:'下载二维码（PNG）',exact:true}).click()
    ]);
    assert.equal(download.suggestedFilename(),'family-invite.png');
    const stream=await download.createReadStream();const chunks=[];
    for await(const chunk of stream)chunks.push(chunk);
    assert(Buffer.concat(chunks).subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])));
    // URL sections survive refresh; expanded member controls stay usable at large sizes.
    await page.goto(base+'/f/ui/manage');
    await page.getByRole('link',{name:'开通账号',exact:true}).click();
    await page.reload();
    assert.equal(await page.locator('.management-tabs [aria-current=page]').innerText(),'开通账号');
    assert.equal(await page.locator('input[name=days]').count(),0);
    await page.goto(base+'/display?family_id=ui');
    await page.locator('input[name=size][value="26"]').check();
    await page.locator('input[name=mode][value=simple]').check();
    for(const width of [320,390,1280]) {
      await page.setViewportSize({width,height:900});
      await page.goto(base+'/f/ui/manage');
      await page.locator('.member-controls').evaluateAll(ns=>ns.forEach(n=>n.open=true));
      await page.locator('.member-heading h3').first().evaluate(n=>n.prepend('这是用于核查长昵称布局的家庭管理员'));
      assert(await page.locator('input[name=new_password]').first().isVisible());
      const bad=await page.locator('.member-controls button, .management-tabs a').evaluateAll(ns=>ns.filter(n=>{
        const r=n.getBoundingClientRect();return r.width<43 || r.height<43;
      }).map(n=>n.textContent.trim()));
      assert.deepEqual(bad,[]);
      const dims=await page.evaluate(()=>[document.documentElement.scrollWidth,document.documentElement.clientWidth]);
      assert(dims[0]<=dims[1]+1,`open member controls ${width}: ${dims}`);
      const alignment=await page.locator('.member-controls form').evaluateAll(ns=>ns.map(n=>{
        const button=n.querySelector('button'),field=n.querySelector('input');
        return !field || (button.getBoundingClientRect().top>=field.getBoundingClientRect().bottom && Math.abs(button.getBoundingClientRect().left-field.getBoundingClientRect().left)<=1);
      }));
      assert(alignment.every(Boolean),'password actions should align below fields');
      if(width===1280) {
        const bottoms=await page.locator('.management-panel .form-row input, .management-panel .form-row select').evaluateAll(ns=>ns.map(n=>n.getBoundingClientRect().bottom));
        assert(Math.max(...bottoms)-Math.min(...bottoms)<=1,'member inputs should share a baseline');
      }
      if(process.env.UI_SCREENSHOTS)await page.screenshot({path:`${process.env.UI_SCREENSHOTS}/members-expanded-large-${width}.png`,fullPage:true});
      checks++;
    }
    await page.goto(base+'/display?family_id=ui');await page.locator('#display-reset').click();
    // Printing remains readable even when the browser uses high contrast.
    await page.goto(base+'/privacy');
    await page.locator('html').evaluate(n=>n.dataset.theme='contrast');
    await page.emulateMedia({media:'print'});
    assert.equal(await page.locator('.legal-body').evaluate(n=>getComputedStyle(n).color),'rgb(0, 0, 0)');
    assert.equal(await page.locator('.legal-body a').first().evaluate(n=>getComputedStyle(n).color),'rgb(0, 0, 0)');
    assert(!(await page.locator('.topbar').isVisible()));
    await page.emulateMedia({media:'screen'});
    // Policies are public, preserve the family menu, and never preselect consent.
    await page.goto(base+'/f/ui/manage');
    await page.getByRole('navigation',{name:'服务条款'}).getByRole('link',{name:'隐私政策',exact:true}).click();
    await openMenu(page);
    assert.equal(await page.getByRole('navigation',{name:'家庭导航'}).getByRole('link').count(),4);
    const publicContext=await browser.newContext();
    const publicPage=await publicContext.newPage();
    await publicPage.goto(base+'/register?invite=ui-invite-only');
    const agreement=publicPage.locator('#legal-accepted');
    assert(!(await agreement.isChecked()));
    await publicPage.locator('#phone').fill('13800009999');
    let attempted=0;publicPage.on('request',r=>{if(r.url().endsWith('/api/sms-code'))attempted++;});
    const dismissed=publicPage.waitForEvent('dialog').then(d=>d.dismiss());
    await publicPage.getByRole('button',{name:'获取验证码',exact:true}).click();await dismissed;
    assert.equal(attempted,0,'unconfirmed registration must not send SMS');
    await agreement.check();
    const sent=publicPage.waitForEvent('dialog').then(d=>d.dismiss());
    const smsResponse=publicPage.waitForResponse(r=>r.url().endsWith('/api/sms-code'));
    await publicPage.getByRole('button',{name:'获取验证码',exact:true}).click();
    const smsData=await(await smsResponse).json();await sent;
    assert(smsData.ok && smsData.dev_code,'isolated server should use fake SMS');
    await publicPage.locator('[name=code]').fill(smsData.dev_code);
    await publicPage.locator('[name=nickname]').fill('注册协议回归');
    await publicPage.locator('#reg-pw').fill('ui-legal-test-password');
    await publicPage.getByRole('button',{name:'注册并登录',exact:true}).click();
    await publicPage.waitForURL('**/f/ui');
    await publicContext.close();
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
      for (const [name,path,width] of [['family-mobile','/f/ui',390],['story-mobile','/f/ui/story/story',390],['family-desktop','/f/ui',1280],['write-mobile','/f/ui/write',390],['account-mobile','/account?family_id=ui',390],['dates-mobile','/f/ui/tree/add',390],['dates-desktop','/f/ui/tree/add',1280],['invite-mobile','/f/ui/manage/invites',390],['privacy-mobile','/privacy',390],['terms-desktop','/terms',1280],['register-mobile','/register',390],['members-mobile','/f/ui/manage',390],['members-desktop','/f/ui/manage',1280],['create-account-desktop','/f/ui/manage/accounts',1280],['tools-desktop','/f/ui/manage/tools',1280]]) {
        await page.setViewportSize({width,height:844}); await page.goto(base+path); await page.screenshot({path:`${process.env.UI_SCREENSHOTS}/${name}.png`,fullPage:true});
      }
    }
    await require('./revision-checks.cjs')(browser, context, base);
    await require('./ai-chat-checks.cjs')(browser,context,base);
    const recoveryChecks = await require('./recovery-checks.cjs')(browser, context, base);
    const speechChecks=await require('./voice-checks.cjs').checkVoice(browser,context,base,process.env.UI_SCREENSHOTS);
    assert.deepEqual(external,[], 'unexpected external runtime resources');
    assert.deepEqual(errors,[], 'browser JavaScript errors');
    console.log(`UI layout: ${checks} pages/viewports passed; comments, profile/help navigation, dual-calendar create/edit, invite QR download, legal consent registration and story workflows passed; ${speechChecks} speech failure/stop workflows passed.`);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
