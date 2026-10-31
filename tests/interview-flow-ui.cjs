const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const mic=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'memoir-mic-')),'tone.wav');
 const frames=16000*5,buffer=Buffer.alloc(44+frames*2);buffer.write('RIFF',0);buffer.writeUInt32LE(36+frames*2,4);buffer.write('WAVEfmt ',8);buffer.writeUInt32LE(16,16);buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(16000,24);buffer.writeUInt32LE(32000,28);buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(frames*2,40);for(let i=0;i<frames;i++)buffer.writeInt16LE(Math.round(3000*Math.sin(i/16000*440*2*Math.PI)),44+i*2);fs.writeFileSync(mic,buffer);
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome',args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+mic]});
 try{
  const context=await browser.newContext({permissions:['microphone']});const base=process.env.UI_TEST_URL;
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage();await page.addInitScript(()=>{window.__speech={utterances:[],cancelled:0};window.SpeechSynthesisUtterance=class{constructor(text){this.text=text}};Object.defineProperty(window,'speechSynthesis',{value:{speak(u){window.__speech.utterances.push(u)},cancel(){window.__speech.cancelled++}}});});page.on('dialog',d=>d.accept());
  await page.goto(base+'/f/ui/interview/new');await page.locator('[name=ai_consent]').check();await page.getByRole('button',{name:'开始这一段'}).click();
  const path=page.url();await page.locator('#recording-consent').check();await page.locator('#recording-asr-consent').check();
  await page.route('**/upload',r=>r.abort());
  await page.locator('#hear-question').click();assert.equal(await page.evaluate(()=>window.__speech.utterances.length),1);await page.locator('#record-start').click();await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('正在录音'));
  await new Promise(resolve=>setTimeout(resolve,450));
  assert.equal(await page.locator('#hear-question').textContent(),'听问题');await page.evaluate(()=>window.__speech.utterances[0].onend());assert.equal(await page.evaluate(()=>window.__speech.utterances.length),1);
  const before=Date.now();await page.locator('#record-stop').click();
  assert(await page.locator('#record-stop').isDisabled());assert(await page.locator('#hear-question').isDisabled());assert(Date.now()-before<1000);
  await page.waitForFunction(()=>document.querySelector('#record-pending button'));
  const raw=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('memoir.interview.pending.v1',1);r.onsuccess=()=>{const q=r.result.transaction('clips').objectStore('clips').getAll();q.onsuccess=()=>resolve(q.result.map(v=>({cipher:v.cipher instanceof ArrayBuffer,mime:v.mime,hasBlob:!!v.blob,hasKey:!!v.key})));q.onerror=reject;};r.onerror=reject;}));
  assert(raw.length===1&&raw[0].cipher&&!raw[0].hasBlob&&!raw[0].hasKey);
  await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('网络中断'));
  await page.unroute('**/upload');await page.locator('#record-pending').getByRole('button',{name:'上传',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('正在转写'));
  assert(await page.locator('#interview-answer-form textarea').isDisabled());
  const tick=await context.request.post(base+'/__interview_test_tick',{headers:{'X-Interview-Test':'local-only-synthetic'}});assert.equal(tick.status(),200);
  await page.waitForURL('**?listen=1');
  assert.equal(await page.locator('#interview-question').textContent(),'老院子的夏天，您最记得什么？');
  assert(!(await page.locator('#interview-answer-form textarea').isDisabled()));
  assert(await page.locator('#recording-consent').isChecked());assert(await page.locator('#recording-asr-consent').isChecked());
  assert.equal(await page.locator('#recording-notice').evaluate(n=>n.open),false);await page.locator('#recording-notice-summary').click();await page.locator('#recording-asr-consent').uncheck();await page.reload();assert(!(await page.locator('#recording-asr-consent').isChecked()));
  await page.getByText('已保存的回答（1）',{exact:true}).click();assert(await page.locator('details').filter({has:page.getByText('已保存的回答（1）',{exact:true})}).locator('p.whitespace-pre-wrap').first().isVisible());
  await context.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});
  assert.equal((await context.request.get(path)).status(),404);
  console.log('Recording/playback exclusion, ASR acceptance, next question polling and answer recovery passed');
 }finally{await browser.close();fs.rmSync(path.dirname(mic),{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
