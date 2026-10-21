/* Browser event doubles reproduce speech failures without accessing a microphone. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
async function checkVoice(browser, signedIn, base, screenshots) {
  const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.addCookies(await signedIn.cookies());
  const errors=[];let sent=0;
  await context.route('**/f/ui/ask/stream',route=>{
    sent++;
    return route.fulfill({contentType:'text/event-stream',body:'data: {"chunk":"这是本地模拟回答。"}\n\ndata: [DONE]\n\n'});
  });
  await context.addInitScript(()=>{
    window.mockSpeech={mode:'normal',instances:[]};
    class FakeRecognition {
      constructor(){this.stops=0;this.aborts=0;window.mockSpeech.instances.push(this);}
      start(){
        if(window.mockSpeech.mode==='throw-start')throw new Error('unavailable');
        if(window.mockSpeech.mode!=='hold-start')queueMicrotask(()=>this.onstart?.());
      }
      stop(){this.stops++;if(window.mockSpeech.mode!=='hang-stop')queueMicrotask(()=>this.onend?.());}
      abort(){this.aborts++;queueMicrotask(()=>{this.onerror?.({error:'aborted'});this.onend?.();});}
      results(items){
        const results=items.map(([text,final])=>{const r=[{transcript:text}];r.isFinal=final;return r;});
        this.onresult?.({resultIndex:0,results});
      }
      fail(error){this.onerror?.({error});this.onend?.();}
    }
    window.SpeechRecognition=FakeRecognition;
    window.webkitSpeechRecognition=FakeRecognition;
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  async function start(){await page.locator('#voice-btn').click();await page.waitForFunction(()=>document.getElementById('voice-btn').textContent==='停止语音输入');}
  async function idle(){await page.waitForFunction(()=>document.getElementById('voice-btn').textContent==='语音输入');}
  async function result(items){await page.evaluate(items=>window.mockSpeech.instances.at(-1).results(items),items);}
  let checks=0;
  try {
    for(const [name,path,target] of [['ask','/f/ui/ask','#msg-input'],['write','/f/ui/write','.ql-editor']]) {
      await page.goto(base+path);
      await page.locator(target).fill('已经输入的内容。');
      await start();
      assert(!(await page.locator(target).evaluate(n=>n===document.activeElement)),'recording must not open the phone keyboard');
      await page.evaluate(()=>window.mockSpeech.instances.at(-1).fail('service-not-allowed'));
      await idle();
      const errorText=await page.locator('#voice-status').innerText();
      assert.match(errorText,/当前浏览器未提供可用/);
      assert(await page.locator('#voice-fallback').isVisible());
      const read=()=>name==='ask'?page.locator(target).inputValue():page.locator(target).innerText();
      assert.match(await read(),/已经输入的内容。/);
      // Late end/error events must not erase the actionable error message.
      await page.evaluate(()=>window.mockSpeech.instances.at(-1).onend());
      assert.equal(await page.locator('#voice-status').innerText(),errorText);
      if(screenshots){fs.mkdirSync(screenshots,{recursive:true});await page.screenshot({path:`${screenshots}/${name}-voice-fallback.png`,fullPage:true});}
      await page.locator('#voice-keyboard').click();
      assert(await page.locator(target).evaluate(n=>n===document.activeElement));
      assert.match(await page.locator('#voice-status').innerText(),/键盘上的麦克风/);
      checks++;

      // Missing end after stop: retain final and interim text, then release recognition.
      await page.evaluate(()=>window.mockSpeech.mode='hang-stop');
      await start();
      await result([['第一句话。',true],['最后一段',false]]);
      await result([['第一句话。',true],['最后一段',false]]);
      await page.locator('#voice-btn').click();
      assert.match(await page.locator('#voice-status').innerText(),/停止/);
      await idle();
      assert.equal((await read()).match(/第一句话。/g).length,1,'final text was inserted twice');
      assert.match(await read(),/已经输入的内容。第一句话。最后一段/);
      const stopped=await page.evaluate(()=>{const r=window.mockSpeech.instances.at(-1);return [r.stops,r.aborts];});
      assert.deepEqual(stopped,[1,1]);
      checks++;

      // Starting can be cancelled before the browser has emitted onstart.
      await page.evaluate(()=>window.mockSpeech.mode='hold-start');
      await page.locator('#voice-btn').click();
      assert.equal(await page.locator('#voice-btn').innerText(),'取消启动');
      await page.locator('#voice-btn').click();await idle();
      assert.equal(await page.evaluate(()=>window.mockSpeech.instances.at(-1).aborts),1);
      checks++;

      await page.evaluate(()=>window.mockSpeech.mode='throw-start');
      await page.locator('#voice-btn').click();await idle();
      assert.match(await page.locator('#voice-status').innerText(),/无法启动/);
      assert.match(await read(),/最后一段/);
      checks++;

      // Ordinary stop preserves the last final result; submit must stop speech first.
      await page.evaluate(()=>window.mockSpeech.mode='normal');
      await start();
      await result([['继续补充。',true]]);
      if(name==='ask') {
        await page.locator('#send-btn').click();await idle();assert.equal(sent,0);
        await page.locator('#auto-speak').uncheck();
        await page.locator('#send-btn').click();
        await page.waitForFunction(()=>document.querySelector('.chatlog').textContent.includes('本地模拟回答'));
        assert.equal(sent,1);
      } else {
        await page.locator('[name=topic]').fill('语音生命周期回归草稿');
        await page.getByRole('button',{name:'保存草稿',exact:true}).click();await idle();
        assert(new URL(page.url()).pathname==='/f/ui/write');
        await page.getByRole('button',{name:'保存草稿',exact:true}).click();
        await page.waitForURL('**/drafts');
        await page.locator('li.card').filter({hasText:'语音生命周期回归草稿'}).getByRole('link',{name:'继续编辑',exact:true}).click();
        assert.match(await page.locator('.ql-editor').innerText(),/继续补充。/);
      }
      checks++;
    }
    // Rich editor resource failure still permits voice text in the plain editor.
    await context.route('**/quill-2.0.3.*.js',route=>route.abort());
    await page.goto(base+'/f/ui/write');
    await page.locator('#editor-fallback').fill('原有文本。');
    await start();await result([['识别补充。',true]]);await page.locator('#voice-btn').click();await idle();
    assert.equal(await page.locator('#editor-fallback').inputValue(),'原有文本。识别补充。');
    checks++;

    const unsupported=await browser.newContext({viewport:{width:390,height:844}});
    await unsupported.addCookies(await signedIn.cookies());
    await unsupported.addInitScript(()=>{
      Object.defineProperty(window,'SpeechRecognition',{value:undefined,configurable:true});
      Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true});
    });
    try {
      const unsupportedPage=await unsupported.newPage();
      for(const path of ['/f/ui/ask','/f/ui/write']) {
        await unsupportedPage.goto(base+path);
        assert(await unsupportedPage.locator('#voice-btn').isDisabled());
        assert(await unsupportedPage.locator('#voice-keyboard').isVisible());
        await unsupportedPage.locator('#voice-keyboard').click();
        assert(await unsupportedPage.locator(path.endsWith('/ask')?'#msg-input':'.ql-editor').evaluate(n=>n===document.activeElement));
        checks++;
      }
    } finally {await unsupported.close();}
    assert.deepEqual(errors,[],'voice lifecycle emitted JavaScript errors');
    return checks;
  } finally {await context.close();}
}
module.exports={checkVoice};
