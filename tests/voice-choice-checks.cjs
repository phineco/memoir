const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const hash=value=>require('node:crypto').createHash('sha256').update(value).digest('hex').slice(0,32);
const firstId=hash('voiceone'),secondId=hash('voicetwo');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL||'chrome'});
 try{
  const base=process.env.UI_TEST_URL,context=await browser.newContext({viewport:{width:390,height:844}});
  await context.request.post(base+'/login',{form:{phone:'ui-test',password:'ui-test-only'}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort());
  await context.addInitScript(()=>{
   window.__utterances=[];window.__cancelled=0;
   Object.defineProperty(window,'speechSynthesis',{value:{speak(u){window.__utterances.push(u);},cancel(){window.__cancelled++;},getVoices(){return[];}}});
   window.SpeechSynthesisUtterance=function(text){this.text=text;};
   HTMLMediaElement.prototype.play=function(){Object.defineProperty(this,'paused',{configurable:true,value:false});this.dispatchEvent(new Event('play'));return Promise.resolve();};
   HTMLMediaElement.prototype.pause=function(){Object.defineProperty(this,'paused',{configurable:true,value:true});};
   const interval=window.setInterval;
   window.setInterval=function(fn,delay,...args){if(delay===15000)window.__voicePoll=fn;return interval.call(window,fn,delay,...args);};
  });
  const page=await context.newPage(),errors=[],posts=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/f/ui/story/story/voice')posts.push(r.postDataJSON());});
  const tick=async()=>{const r=await context.request.post(base+'/__voice_test_tick',{headers:{'X-Voice-Test':'local-only-synthetic'},data:{}});assert(r.ok());return r.json();};
  await page.goto(base+'/f/ui/story/story');
  assert.equal(await page.locator('#voice-choice').inputValue(),firstId);
  assert.match(await page.locator('#voice-choice option:checked').innerText(),/林奶奶（讲述者）/);
  assert.equal(await page.locator('#storyReadBtn').count(),1);
  assert(await page.locator('#storyReadBtn').isHidden());
  assert.match(await page.locator('#voice-read').innerText(),/林奶奶/);
  for(const value of [secondId,'',firstId])await page.locator('#voice-choice').selectOption(value);
  await page.locator('#voice-audio').evaluate(a=>{a.dispatchEvent(new Event('ended'));a.dispatchEvent(new Event('error'));});
  assert.match(await page.locator('#voice-play-status').innerText(),/已选择林奶奶/);
  assert.equal(posts.length,0,'selection never sends text or incurs a synthesis charge');
  await page.locator('#voice-authorize').check();
  let heldPost,releasePost;let holdFirst=true;
  await page.route(base+'/f/ui/story/story/voice',async route=>{
   const response=await route.fetch();
   if(holdFirst){holdFirst=false;heldPost=response;await new Promise(resolve=>releasePost=resolve);}
   await route.fulfill({response});
  });
  await page.locator('#voice-read').click();await page.waitForFunction(()=>document.getElementById('voice-play-status').textContent.includes('正在准备林奶奶'));
  await waitUntil(()=>heldPost);
  await page.locator('#voice-choice').selectOption(secondId);
  assert(await page.locator('#voice-audio').isHidden());
  assert.equal(await page.locator('#voice-audio').getAttribute('src'),null);
  await page.locator('#voice-read').click();await waitUntil(()=>posts.length===2);
  await tick();await tick();
  await page.waitForFunction(id=>document.getElementById('voice-audio').dataset.profileId===id,secondId);
  const secondSrc=await page.locator('#voice-audio').getAttribute('src');
  const oldResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.request().postDataJSON().profile_id===firstId);
  releasePost();await oldResponse;
  // A round trip after the delayed response lets its JSON callbacks run.
  await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,80)));
  assert.equal(await page.locator('#voice-audio').getAttribute('src'),secondSrc);
  assert.match(await page.locator('#voice-play-status').innerText(),/林妈妈/);
  assert.equal(posts[0].profile_id,firstId);assert.equal(posts[1].profile_id,secondId);
  assert.equal((await tick()).syntheses,2);
  await page.unroute(base+'/f/ui/story/story/voice');

  // An expired permission poll for the previous voice must not stop the new one.
  let heldPoll,releasePoll;
  const secondStatus=secondSrc.replace(/\/audio$/,'');
  await page.route(base+secondStatus,async route=>{heldPoll=true;await new Promise(resolve=>releasePoll=resolve);await route.fulfill({status:404,contentType:'application/json',body:'{}'});});
  await page.evaluate(()=>{window.__pollDone=window.__voicePoll();});await waitUntil(()=>heldPoll);
  await page.locator('#voice-choice').selectOption(firstId);await page.locator('#voice-read').click();
  await page.waitForFunction(id=>document.getElementById('voice-audio').dataset.profileId===id,firstId);
  releasePoll();await page.evaluate(()=>window.__pollDone);
  assert.equal(await page.locator('#voice-audio').getAttribute('data-profile-id'),firstId);
  assert.equal(await page.locator('#voice-audio').evaluate(a=>a.paused),false);
  assert.match(await page.locator('#voice-play-status').innerText(),/林奶奶/);
  await page.unroute(base+secondStatus);
  assert.equal((await tick()).syntheses,2,'switching back reuses each person’s own cache');

  // The current permission check still stops audio immediately on refusal.
  const currentStatus=(await page.locator('#voice-audio').getAttribute('src')).replace(/\/audio$/,'');
  await page.route(base+currentStatus,route=>route.fulfill({status:404,contentType:'application/json',body:'{}'}));
  await page.evaluate(()=>window.__voicePoll());
  assert.equal(await page.locator('#voice-audio').getAttribute('src'),null);
  assert.match(await page.locator('#voice-play-status').innerText(),/授权或文章状态已变化/);
  await page.unroute(base+currentStatus);

  // Changing to device speech stops the previous voice without cloud requests.
  const countBefore=posts.length;
  await page.locator('#voice-choice').selectOption('');await page.locator('#storyReadBtn').click();
  assert.equal(posts.length,countBefore);assert(await page.locator('#voice-read').isHidden());
  assert.equal(await page.evaluate(()=>window.__utterances.length),1);
  await page.evaluate(()=>{window.__oldUtterance=window.__utterances[0];});
  await page.locator('#voice-choice').selectOption(secondId);
  assert(await page.locator('#voice-stop').isDisabled());
  await page.locator('#voice-choice').selectOption('');await page.locator('#storyReadBtn').click();
  await page.evaluate(()=>window.__oldUtterance.onend());
  assert.equal(await page.evaluate(()=>window.__utterances.length),2,'a stopped utterance cannot advance a new reading');
  await page.evaluate(()=>{window.__utterances.at(-1).onend();window.__utterances.at(-1).onend();});
  assert.match(await page.locator('#voice-play-status').innerText(),/普通朗读已停止/);
  await page.locator('#storyReadBtn').click();
  await page.locator('#voice-stop').click();assert(await page.locator('#voice-stop').isDisabled());

  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','26'));
   await page.locator('#voice-choice').selectOption(secondId);
   assert(await page.locator('#voice-ai-label').isVisible());assert(await page.locator('#voice-read').isVisible());
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'large-text layout '+width);
   if(process.env.UI_SCREENSHOTS){require('node:fs').mkdirSync(process.env.UI_SCREENSHOTS,{recursive:true});await page.locator('#family-voice-player').screenshot({path:process.env.UI_SCREENSHOTS+'/voice-choice-'+width+'.png'});}
  }
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.setAttribute('data-size','18'));
  // No narrator: prefer device speech even with other ready family voices.
  await page.goto(base+'/f/ui/story/voice-failure-story');assert.equal(await page.locator('#voice-choice').inputValue(),'');
  assert(await page.locator('#voice-authorize').isHidden());
  await page.locator('#voice-choice').selectOption(secondId);await page.locator('#voice-authorize').check();
  await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/voice')),page.locator('#voice-read').click()]);
  await context.request.post(base+'/__voice_test_tick',{headers:{'X-Voice-Test':'local-only-synthetic'},data:{fail_synthesis:true}});
  await page.waitForFunction(()=>document.getElementById('voice-play-status').textContent.includes('转为普通朗读'));
  assert(await page.locator('#voice-retry').isVisible());
  await page.locator('#voice-choice').selectOption(firstId);
  assert(await page.locator('#voice-retry').isHidden());assert(await page.locator('#voice-audio').isHidden());
  assert.match(await page.locator('#voice-play-status').innerText(),/已选择林奶奶/);
  assert.deepEqual(errors,[]);
  console.log('Voice choice UI passed: narrator default, explicit synthesis, person-specific cache, delayed request and permission-poll races, current revocation, ordinary speech cancellation, failure reset, and 3 large-text layouts.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
async function waitUntil(predicate){for(let i=0;i<200;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,25));}throw Error('Test condition did not arrive');}
