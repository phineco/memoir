const {chromium}=require('playwright');
const assert=require('node:assert/strict');
function wav(){const frames=24000*12,b=Buffer.alloc(44+frames*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(24000,24);b.writeUInt32LE(48000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(frames*2,40);for(let i=0;i<frames;i++)b.writeInt16LE(i%2?1200:-1200,44+i*2);return b;}
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  await context.addInitScript(()=>{window.__spoken=0;Object.defineProperty(window,'speechSynthesis',{value:{speak(){window.__spoken++;},cancel(){},getVoices(){return[];}}});window.SpeechSynthesisUtterance=function(text){this.text=text;};});
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  async function nav(action,target=page){await Promise.all([target.waitForNavigation({waitUntil:'domcontentloaded'}),action()]);}
  await page.goto(base+'/account?family_id=ui');await nav(()=>page.getByRole('link',{name:/我的声音/}).click());
  assert(await page.getByRole('heading',{name:'上传声音或录音克隆',exact:true}).isVisible());
  assert.equal(await page.locator('nav[aria-label="家庭导航"] a').count(),4);
  await nav(()=>page.getByRole('button',{name:'开始建立声音档案'}).click());
  assert.equal(await page.locator('#voice-sample-form').count(),0);
  await page.locator('[name=adult]').check();await page.locator('[name=agree]').check();
  await nav(()=>page.getByRole('button',{name:'提交本人的单独同意'}).click());
  const operator=await browser.newContext({viewport:{width:320,height:844}});
  await operator.request.post(base+'/login',{form:{phone:'ui-voice-operator',password:'ui-voice-operator-test-only'}});
  const op=await operator.newPage();await op.goto(base+'/operations/voices');
  for(const name of ['identity_verified','provider_authorized','scope_verified'])await op.locator('[name='+name+']').check();
  await op.locator('[name=evidence_ref]').fill('qa-synthetic-only');await nav(()=>op.getByRole('button',{name:'记录人工核验通过'}).click(),op);
  assert(await op.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.reload();await page.locator('#voice-sample-form').waitFor();
  assert.equal(new URL(page.url()).pathname,'/account/voices');
  for(const width of [320,390,1280]){await page.setViewportSize({width,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','26'));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'personal capture large-text layout '+width);}
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','18'));
  await page.locator('[name=sample]').setInputFiles({name:'uploaded.wav',mimeType:'audio/wav',buffer:wav()});
  assert(await page.locator('#voice-sample-preview').isVisible());
  await page.evaluate(recorded=>{window.__recordedAudio=Uint8Array.from(atob(recorded),c=>c.charCodeAt(0));window.__tracksStopped=0;Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia(){return new Promise(resolve=>window.__resolveMic=resolve);}}});window.MediaRecorder=class{constructor(){this.state='inactive';this.mimeType='audio/wav';}start(){this.state='recording';}stop(){this.state='inactive';setTimeout(()=>{this.ondataavailable({data:new Blob([window.__recordedAudio],{type:'audio/wav'})});this.onstop();},0);}};},wav().toString('base64'));
  await page.locator('#voice-record').click();await page.waitForFunction(()=>typeof window.__resolveMic==='function');await page.locator('#voice-stop-record').click();
  await page.evaluate(()=>window.__resolveMic({getTracks(){return[{stop(){window.__tracksStopped++;}}];}}));
  await page.waitForFunction(()=>window.__tracksStopped===1);
  await page.evaluate(()=>{navigator.mediaDevices.getUserMedia=async()=>({getTracks(){return[{stop(){window.__tracksStopped++;}}];}});});
  await page.locator('#voice-record').click();await page.waitForFunction(()=>document.getElementById('voice-record-status').textContent.includes('正在录音，最多'));await page.locator('#voice-stop-record').click();
  await page.waitForFunction(()=>document.getElementById('voice-record-status').textContent.includes('录音已停止'));
  await page.locator('[name=length]').fill('10');await page.locator('[name=quality]').check();
  const sampleRequest=page.waitForRequest(r=>r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/voice'));
  await nav(()=>page.getByRole('button',{name:'提交片段并申请复刻'}).click());
  assert((await sampleRequest).postDataBuffer().includes(Buffer.from('filename="recording.webm"')),'latest recorder blob must replace the previously chosen file');
  assert.equal(new URL(page.url()).pathname,'/account/voices');
  assert.equal(new URL(page.url()).searchParams.get('person_id'),'grandma');
  const tick=()=>context.request.post(base+'/__voice_test_tick',{headers:{'X-Voice-Test':'local-only-synthetic'},data:{}});
  await tick();await page.goto(base+'/f/ui/story/story');
  await page.locator('#voice-authorize').check();
  await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/voice')),page.locator('#voice-read').click()]);
  await tick();await page.waitForFunction(()=>document.getElementById('voice-audio').getAttribute('src'));
  assert(await page.locator('#voice-ai-label').isVisible());await page.locator('#voice-stop').click();
  await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/voice')),page.locator('#voice-read').click()]);
  const counts=await (await tick()).json();assert.equal(counts.creates,1);assert.equal(counts.syntheses,1);
  for(const width of [320,390,1280]){await page.setViewportSize({width,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','26'));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),JSON.stringify(await page.evaluate(()=>Array.from(document.querySelectorAll('body *')).filter(n=>n.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(n=>({tag:n.tagName,id:n.id,right:n.getBoundingClientRect().right,text:n.textContent.slice(0,40)})))));assert(await page.locator('#voice-ai-label').isVisible());}
  await page.goto(base+'/f/ui/story/voice-failure-story');await page.locator('#voice-choice').selectOption(await page.locator('#voice-choice option[data-name]').first().getAttribute('value'));await page.locator('#voice-authorize').check();
  await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/voice')),page.locator('#voice-read').click()]);
  await context.request.post(base+'/__voice_test_tick',{headers:{'X-Voice-Test':'local-only-synthetic'},data:{fail_synthesis:true}});
  await page.waitForFunction(()=>window.__spoken>0);assert.match(await page.locator('#voice-play-status').innerText(),/普通朗读/);
  await page.goto(base+'/f/ui/person/grandma/voice');page.once('dialog',d=>d.accept());
  await nav(()=>page.getByRole('button',{name:'撤回授权并删除声音'}).click());await tick();await page.reload();
  assert.match(await page.locator('body').innerText(),/此音色及本站样本、生成音频已删除/);
  assert.deepEqual(errors,[]);await operator.close();
  console.log('Personal and family voice UI: account capture entry, separate consent, operator verification, recorder cancel/stop, sample upload, clone, version cache, AI label, fallback, delete and 3 viewport layouts passed.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
