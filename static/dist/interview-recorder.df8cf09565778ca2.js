/* Foreground, click-to-stop recording; account-encrypted IndexedDB is not a general cache. */
(function(){
 'use strict';
 const root=document.getElementById('interview-recorder');if(!root)return;
 const start=document.getElementById('record-start'),stop=document.getElementById('record-stop');
 const status=document.getElementById('record-status'),consent=document.getElementById('recording-consent');
 const player=document.getElementById('record-playback'),list=document.getElementById('record-pending');
 let recorder=null,stream=null,timer=null,warning=null,generation=0,recording=false,waiting=false,pendingCount=0,playUrl=null;
 const phaseLabel=document.getElementById('record-phase'),elapsed=document.getElementById('record-elapsed');
 const easy=root.dataset.easy==='yes';
 let phase='idle',clock=null,startedAt=0;
 function tick(){
  const seconds=Math.max(0,Math.floor((performance.now()-startedAt)/1000));
  if(elapsed)elapsed.textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
 }
 function setPhase(value){
  if(recording && value!=='recording')return;
  if(waiting&&phase==='requesting'&&['uploading','saved','retry'].includes(value))return;
  phase=value;root.dataset.recordState=value;
  const labels={idle:'准备录音',requesting:'正在打开麦克风',recording:'正在录音，请开始讲',saving:'已停止，正在保存',uploading:'正在上传录音',saved:'录音已保存',retry:'录音待上传',error:'录音未开始或已中断'};
  if(phaseLabel)phaseLabel.textContent=labels[value]||labels.idle;
  start.textContent=value==='requesting'?'正在打开麦克风…':'开始回答';
  start.setAttribute('aria-pressed',recording?'true':'false');
  stop.textContent=value==='requesting'?'取消打开麦克风':'说完了';
  if(easy){start.hidden=recording;stop.hidden=!(recording||value==='requesting');}
  if(value!=='recording'){clearInterval(clock);clock=null;}
 }
 const owner=root.dataset.owner,sid=root.dataset.session,token=root.dataset.csrf;
 const asrConsent=document.getElementById('recording-asr-consent'),noticePanel=document.getElementById('recording-notice'),noticeSummary=document.getElementById('recording-notice-summary');
 function choiceSummary(){if(easy&&noticeSummary){noticeSummary.textContent=consent.checked?'录音选择 · 可随时更改':'录音前先确认';return;}if(noticeSummary)noticeSummary.textContent=!consent.checked?'录音与转写选择（先确认）':asrConsent&&asrConsent.checked?'录音/转写选择 · 已确认':asrConsent?'录音已确认 · 未选转写':'录音已确认 · 仅保存';}
 const choiceKey='memoir.interview.choice.v1.'+JSON.stringify([root.dataset.user,sid,root.dataset.notice]);
 try{const choice=JSON.parse(sessionStorage.getItem(choiceKey)||'null');if(choice){consent.checked=choice.recording===true;if(asrConsent)asrConsent.checked=choice.asr===true;}}catch(e){}
 choiceSummary();if(consent.checked&&noticePanel)noticePanel.open=false;
 function retainChoice(){choiceSummary();try{sessionStorage.setItem(choiceKey,JSON.stringify({recording:consent.checked,asr:!!(asrConsent&&asrConsent.checked)}));}catch(e){}}
 consent.addEventListener('change',retainChoice);if(asrConsent)asrConsent.addEventListener('change',retainChoice);
 function openNotice(){if(noticePanel){noticePanel.open=true;const button=noticePanel.querySelector('[data-record-choice]');if(button){button.focus({preventScroll:true});noticePanel.scrollIntoView({block:'nearest'});}else consent.focus();}}
 document.querySelectorAll('[data-record-choice]').forEach(button=>button.addEventListener('click',()=>{
  if(recording||waiting)return;
  consent.checked=button.dataset.recordChoice!=='off';if(asrConsent)asrConsent.checked=button.dataset.recordChoice==='asr';
  retainChoice();noticePanel.open=false;
  if(!consent.checked){const text=document.getElementById('interview-text');if(text){text.open=true;text.querySelector('textarea').focus();}say('已改用文字，后续录音和转写选择已关闭。');return;}
  start.click();
 }));
 const choiceOpen=document.getElementById('record-choice-open');if(choiceOpen)choiceOpen.addEventListener('click',()=>{if(recording||waiting)return;const options=document.getElementById('easy-interview-options');if(options)options.open=false;openNotice();});
 const fileForm=document.getElementById('record-file-form');if(fileForm)fileForm.addEventListener('submit',()=>{try{sessionStorage.setItem(choiceKey,JSON.stringify({recording:fileForm.elements.consent_recording.checked,asr:!!(fileForm.elements.consent_asr&&fileForm.elements.consent_asr.checked)}));}catch(e){}});
 function say(message){status.textContent=message;}
 function notify(){root.dataset.recordBusy=recording||waiting?'yes':'no';root.dispatchEvent(new CustomEvent('interview:record-state',{bubbles:true,detail:{recording,waiting}}));}
 function pausePlayback(){document.querySelectorAll('audio,video').forEach(a=>a.pause());Object.values(window.memoirReaders||{}).forEach(r=>r.stop());if(window.speechSynthesis)window.speechSynthesis.cancel();}
 async function identity(){
  const r=await fetch(root.dataset.identity,{cache:'no-store',redirect:'error'});
  if(!r.ok||(await r.json()).user_id!==root.dataset.user)throw Error('登录身份已变化，请回到本人账号；本机片段不会交给其他账号。');
 }
 function database(){return new Promise((resolve,reject)=>{
  const request=indexedDB.open('memoir.interview.pending.v1',1);
  request.onupgradeneeded=()=>request.result.createObjectStore('clips',{keyPath:'id'});
  request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(Error('本机存储不可用，请保持本页并下载录音。'));
 });}
 async function transaction(mode,fn){const db=await database();try{return await new Promise((resolve,reject)=>{
  const tx=db.transaction('clips',mode);let value;
  const req=fn(tx.objectStore('clips'));req.onsuccess=()=>{value=req.result};
  tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(Error('本机空间不足或未允许保存，请下载本段录音。'));tx.onabort=tx.onerror;
 });}finally{db.close();}}
 async function key(){return crypto.subtle.importKey('raw',Uint8Array.from(atob(root.dataset.key),c=>c.charCodeAt(0)),'AES-GCM',false,['encrypt','decrypt']);}
 async function seal(blob){
  const iv=crypto.getRandomValues(new Uint8Array(12));
  return {iv,cipher:await crypto.subtle.encrypt({name:'AES-GCM',iv},await key(),await blob.arrayBuffer())};
 }
 async function unseal(row){await identity();return new Blob([await crypto.subtle.decrypt({name:'AES-GCM',iv:row.iv},await key(),row.cipher)],{type:row.mime});}
 function play(blob){player.hidden=false;pausePlayback();if(playUrl)URL.revokeObjectURL(playUrl);playUrl=URL.createObjectURL(blob);player.src=playUrl;return player.play().catch(()=>say('可以点击播放器回听。'));}
 async function rows(){return (await transaction('readonly',s=>s.getAll())).filter(r=>r.owner===owner&&r.sid===sid);}
 async function render(){
  const saved=await rows();pendingCount=saved.length;root.dataset.pendingCount=String(pendingCount);list.textContent='';
  saved.forEach(row=>{
   const box=document.createElement('div');box.className='disclosure';
   const label=document.createElement('p');label.textContent='本机待上传录音 · '+new Date(row.created).toLocaleString();box.append(label);
   const actions=document.createElement('div');actions.className='form-actions';box.append(actions);
   function button(text,fn){const b=document.createElement('button');b.type='button';b.className='btn-secondary';b.textContent=text;b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){say(e.message||'操作未完成，本机片段保留。');}finally{b.disabled=false}};actions.append(b);}
   button('回听',async()=>play(await unseal(row)));
   button('上传',()=>upload(row));
   button('下载本机片段',async()=>{
    const blob=await unseal(row);const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='家音待上传录音';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
   });
   button('删除本机片段',async()=>{await identity();if(!window.confirm('确认删除尚未上传的本机片段？删除后不能恢复。'))return;await transaction('readwrite',s=>s.delete(row.id));await render();say('已删除所选本机片段。');});
   list.append(box);
  });
 }
 const uploading=new Set();
 async function upload(row){if(uploading.has(row.id))return;uploading.add(row.id);try{await performUpload(row);}finally{uploading.delete(row.id);}}
 async function performUpload(row){
  await identity();
  if(!consent.checked)throw Error('请先确认允许录音私有保存。');
  const blob=await unseal(row);const body=new FormData();
  body.append('audio',blob,'answer');body.append('revision',String(row.revision));body.append('nonce',row.id);body.append('consent_recording','yes');const asr=document.getElementById('recording-asr-consent');if(asr&&asr.checked)body.append('consent_asr','yes');body.append('csrf_token',token);
  setPhase('uploading');say('正在上传，本机片段保留至服务器确认保存。');
  let r;try{r=await fetch(root.dataset.upload,{method:'POST',body,headers:{Accept:'application/json','X-CSRFToken':token},redirect:'error'});}catch(e){setPhase('retry');say('网络中断，本机片段已保留，可稍后重试上传或先下载。');return;}
  if(!r.ok){setPhase('retry');let failure;try{failure=await r.json();}catch(e){}if(failure&&typeof failure.error==='string'){say(failure.error+' 本机片段仍保留，可回听或下载。');return;}say(r.status===409?'采访进度已变化，片段仍在本机，可下载后从对应记录重新上传。':'上传未完成，片段仍在本机；可稍后重试或下载保存。');return;}
  const result=await r.json();if(['uploading','upload_failed'].includes(result.status)){setPhase('retry');say('服务器还未确认录音保存，本机片段保留，请稍后重试上传。');return;}if(!result.id)throw Error('未收到保存确认，片段仍在本机。');
  await transaction('readwrite',s=>s.delete(row.id));await render();setPhase('saved');say(result.note||(result.status==='queued'||result.status==='running'?'服务器已保存录音，正在转写。':'服务器已私有保存，当前未发起转写，可回听或填写文字继续。'));
  root.dispatchEvent(new CustomEvent('interview:uploaded',{bubbles:true,detail:result}));
 }
 function release(){clearTimeout(timer);clearTimeout(warning);if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;}
 function finish(reason){
  if(!recording||!recorder)return;
  recording=false;stop.disabled=true;start.disabled=true;waiting=true;setPhase('saving');notify();
  say(reason||'已停止录音，正在封存本机片段。'); // Immediate feedback, independent of upload/transcription.
  try{if(recorder.state!=='inactive')recorder.stop();}catch(e){say('停止时遇到问题，请保留本页并检查播放器。');}
  release();
 }
 start.addEventListener('click',async()=>{
  if(recording||waiting)return;const text=document.querySelector('#interview-answer-form textarea');if(text&&text.value.trim()){say('请先保存已有文字回答，再录下一题；也可以清空未保存文字后录音。');return;}if(!consent.checked){say('请先确认录音保存告知。');openNotice();return;}
  if(!navigator.mediaDevices||!window.MediaRecorder||!window.crypto||!crypto.subtle){setPhase('error');say('此浏览器暂不支持本站录音，可上传手机录音文件，或用手机键盘听写。');return;}
  const turn=++generation;waiting=true;start.disabled=true;stop.disabled=false;setPhase('requesting');notify();say('正在申请麦克风权限。');
  try{
   await identity();if(turn!==generation)return;pausePlayback();
   const acquired=await navigator.mediaDevices.getUserMedia({audio:true});
   if(turn!==generation||document.hidden){acquired.getTracks().forEach(t=>t.stop());throw Error('录音未开始，请回到本页再试。');}
   stream=acquired;
   const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(t=>typeof MediaRecorder.isTypeSupported==='function'&&MediaRecorder.isTypeSupported(t));
   recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);const chunks=[];let bytes=0;
   recorder.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);bytes+=e.data.size;if(bytes>16*1024*1024)finish('片段较大，已停止，正在封存。');}};
   recorder.onerror=()=>finish('录音发生中断，正在尽力保存已有片段。');
   recorder.onstop=async()=>{
    recording=false;waiting=true;setPhase('saving');notify();release();const blob=new Blob(chunks,{type:recorder.mimeType||'audio/webm'});
    try{
     if(!blob.size)throw Error('没有收到录音数据，请检查麦克风；未上传空片段。');
     await identity();await play(blob);player.pause();
     const sealed=await seal(blob);const row={id:Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join(''),owner,sid,revision:Number(root.dataset.revision),mime:blob.type,created:Date.now(),...sealed};
     await transaction('readwrite',s=>s.put(row));await render();say('本机已暂存，准备上传。');await upload(row);
    }catch(e){setPhase('error');say((e.message||'本机保存未完成。')+' 若播放器可回听，请从播放器下载保存。');}
    finally{waiting=false;start.disabled=false;stop.disabled=true;notify();}
   };
   recorder.start(1000);recording=true;waiting=false;stop.disabled=false;startedAt=performance.now();tick();clock=setInterval(tick,250);setPhase('recording');notify();say('正在录音，讲完点击“说完了”。');
   stream.getTracks().forEach(track=>track.addEventListener('ended',()=>finish('麦克风已中断，正在尽力保存已有片段。')));
   warning=setTimeout(()=>say('已录音2分30秒，快到分段时间，讲完这一句即可。'),150000);
   timer=setTimeout(()=>finish('已满3分钟，已停止录音，正在保存本段。'),180000);
  }catch(e){if(turn!==generation)return;release();waiting=false;start.disabled=false;stop.disabled=true;setPhase('error');notify();say(e.name==='NotAllowedError'?'未获得麦克风权限，请在浏览器设置允许，或用文字回答。':e.message||'无法开始录音。');}
 });
 function cancelRequest(){if(phase!=='requesting')return;generation++;release();waiting=false;start.disabled=false;stop.disabled=true;setPhase('idle');notify();say('已取消，录音尚未开始。');}
 stop.addEventListener('click',()=>phase==='requesting'?cancelRequest():finish());
 document.addEventListener('play',e=>{if(recording)finish('开始播放，已停止录音并封存。');},true);
 document.addEventListener('visibilitychange',()=>{if(document.hidden){if(phase==='requesting')cancelRequest();else generation++;finish('离开前台，已停止录音，尽力保存本段。');pausePlayback();}else identity().catch(e=>{pausePlayback();player.removeAttribute('src');list.textContent='';say(e.message);});});
 window.addEventListener('beforeunload',e=>{if(recording||waiting||pendingCount){e.preventDefault();e.returnValue='';}});
 setPhase('idle');render().catch(e=>say(e.message));
})();
