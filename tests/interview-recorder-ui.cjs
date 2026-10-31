const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const mic=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'memoir-mic-')),'tone.wav');
 const frames=16000*5,buffer=Buffer.alloc(44+frames*2);buffer.write('RIFF',0);buffer.writeUInt32LE(36+frames*2,4);buffer.write('WAVEfmt ',8);buffer.writeUInt32LE(16,16);buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(16000,24);buffer.writeUInt32LE(32000,28);buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(frames*2,40);for(let i=0;i<frames;i++)buffer.writeInt16LE(Math.round(3000*Math.sin(i/16000*440*2*Math.PI)),44+i*2);fs.writeFileSync(mic,buffer);
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome',args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+mic]});
 try{
  const context=await browser.newContext({permissions:['microphone']});const base=process.env.UI_TEST_URL;
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  const page=await context.newPage();page.on('dialog',d=>d.accept());
  await page.goto(base+'/f/ui/interview/new');await page.getByRole('button',{name:'开始这一段'}).click();
  const path=page.url();await page.locator('#recording-consent').check();
  await page.route('**/upload',r=>r.abort());
  await page.locator('#record-start').click();await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('正在录音'));
  await new Promise(resolve=>setTimeout(resolve,450));
  const before=Date.now();await page.locator('#record-stop').click();
  assert(await page.locator('#record-stop').isDisabled());assert(Date.now()-before<1000);
  await page.waitForFunction(()=>document.querySelector('#record-pending button'));
  const raw=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('memoir.interview.pending.v1',1);r.onsuccess=()=>{const q=r.result.transaction('clips').objectStore('clips').getAll();q.onsuccess=()=>resolve(q.result.map(v=>({cipher:v.cipher instanceof ArrayBuffer,mime:v.mime,hasBlob:!!v.blob,hasKey:!!v.key})));q.onerror=reject;};r.onerror=reject;}));
  assert(raw.length===1&&raw[0].cipher&&!raw[0].hasBlob&&!raw[0].hasKey);
  await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('网络中断'));
  await page.unroute('**/upload');await page.locator('#record-pending').getByRole('button',{name:'上传',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#record-status').textContent.includes('服务器已私有保存')).catch(async e=>{console.error(await page.locator('#record-status').textContent());throw e});
  await page.reload();assert((await page.locator('audio[src*="/audio/"]').count())===1);
  for(const width of [320,390,768]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  await context.request.post(base+'/login',{form:{phone:'ui-relative',password:'ui-relative-test-only'}});
  assert.equal((await context.request.get(path)).status(),404);
  console.log('Recording stop, encrypted local retry, private upload and 3 layouts passed');
 }finally{await browser.close();fs.rmSync(path.dirname(mic),{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
