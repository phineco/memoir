const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
(async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'memoir-easy-mic-')),mic=path.join(folder,'tone.wav');
 const frames=16000*5,wav=Buffer.alloc(44+frames*2);wav.write('RIFF',0);wav.writeUInt32LE(36+frames*2,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(frames*2,40);for(let i=0;i<frames;i++)wav.writeInt16LE(Math.round(3000*Math.sin(i/16000*440*2*Math.PI)),44+i*2);fs.writeFileSync(mic,wav);
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome',args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+mic]});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext({permissions:['microphone']});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.addInitScript(()=>{window.__spoken=[];window.SpeechSynthesisUtterance=class{constructor(text){this.text=text}};Object.defineProperty(window,'speechSynthesis',{value:{speak(u){window.__spoken.push(u.text)},cancel(){}}});window.__micCalls=0;const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=(...args)=>{window.__micCalls++;return gum(...args);};});
  async function visibleChoices(){return page.locator('input[type=checkbox],select,textarea').evaluateAll(nodes=>nodes.filter(n=>n.checkVisibility()).map(n=>n.id||n.name));}
  for(const [width,height,size] of [[320,740,22],[390,844,22],[430,900,22],[320,740,26],[390,844,26]]){
   await page.setViewportSize({width,height});await page.goto(base+'/easy/settings?family_id=ui');await page.locator('[name=size][value="'+size+'"]').check();await page.goto(base+'/easy/f/ui/interview/new');
   assert.deepEqual(await visibleChoices(),[]);
   assert.equal(await page.locator('[name=topic]').inputValue(),'free');
   const start=await page.getByRole('button',{name:'开始这一段'}).boundingBox();assert(start.y+start.height<height-90);
   await page.getByRole('button',{name:'开始这一段'}).click();
   assert.deepEqual(await visibleChoices(),[]);
   for(const selector of ['#interview-question','#hear-question','#record-start']){
    const box=await page.locator(selector).boundingBox();assert(box.y>=0&&box.y+box.height<height-90,`${width}: ${selector} not on first screen`);
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   if(process.env.UI_SCREENSHOTS){fs.mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.UI_SCREENSHOTS,'easy-tell-'+width+'-'+size+'.png')});}
  }
  await page.setViewportSize({width:390,height:844});
  await page.locator('#record-start').click();
  assert.equal(await page.evaluate(()=>window.__micCalls),0);
  assert.equal(await page.locator('#recording-notice').evaluate(n=>n.open),true);
  assert.equal(await page.locator('#recording-consent').isChecked(),false);
  assert.equal(await page.locator('input[type=checkbox]').evaluateAll(nodes=>nodes.filter(n=>n.checkVisibility()).length),0);
  await page.locator('#hear-recording-choice').click();assert.match(await page.evaluate(()=>window.__spoken.join(' ')),/保存这段录音/);
  await page.locator('[data-record-choice=asr]').click();
  await page.waitForFunction(()=>document.querySelector('#interview-recorder').dataset.recordState==='recording');
  await page.waitForFunction(()=>document.getElementById('record-elapsed').textContent!=='00:00');
  assert(await page.locator('#record-start').isHidden());assert(await page.locator('#record-stop').isVisible());
  assert(await page.locator('#recording-consent').isChecked());assert(await page.locator('#recording-asr-consent').isChecked());
  const stop=await page.locator('#record-stop').boundingBox();assert(stop.y+stop.height<844-70);
  if(process.env.UI_SCREENSHOTS)await page.screenshot({path:path.join(process.env.UI_SCREENSHOTS,'easy-recording.png')});
  await page.locator('#record-stop').click();
  await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('正在转写'));
  const tick=await context.request.post(base+'/__interview_test_tick',{headers:{'X-Interview-Test':'local-only-synthetic'}});assert.equal(tick.status(),200);
  await page.waitForURL('**?listen=1');
  assert(await page.locator('#recording-consent').isChecked());assert(await page.locator('#recording-asr-consent').isChecked());
  assert.equal(await page.locator('#recording-notice').evaluate(n=>n.open),false);
  await page.locator('#easy-interview-options>summary').click();await page.locator('#record-choice-open').click();
  await page.locator('[data-record-choice=off]').click();
  assert.equal(await page.locator('#recording-consent').isChecked(),false);assert.equal(await page.locator('#recording-asr-consent').isChecked(),false);
  assert(await page.locator('#interview-answer-form textarea').isVisible());
  await page.locator('#interview-answer-form textarea').fill('我还想起小时候和家人一起吃饭。');
  await page.getByRole('button',{name:'保存回答，下一题'}).click();
  assert(page.url().includes('/easy/f/ui/interview/'));
  assert.deepEqual(errors,[]);
  console.log('Easy telling: first-screen defaults/no visible checkboxes, explicit consent before microphone, single stop button/timer, ASR continuation, retained/revoked choices and text alternative passed.');
 }finally{await browser.close();fs.rmSync(folder,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
