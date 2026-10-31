/* Read-only polling never calls AI again. Recorded answers are accepted server-side once. */
(function(){
 'use strict';
 const root=document.getElementById('interview-flow');if(!root)return;
 const answer=document.getElementById('interview-answer-form'),hear=document.getElementById('hear-question');
 let busy=false,asr=root.dataset.pendingAsr==='yes',stopped=false,attempts=0;
 const status=document.getElementById('record-status');
 function setStatus(text){if(status)status.textContent=text;}
 function controls(){
  if(answer)answer.querySelectorAll('textarea,button').forEach(n=>n.disabled=busy||asr);
  if(hear)hear.disabled=busy||!(window.memoirReaders&&window.memoirReaders['hear-question']);
  const start=document.getElementById('record-start');if(start&&!busy)start.disabled=asr;
 }
 if(hear){
  initReadAloud('hear-question','question-rate','question-content');
  hear.addEventListener('memoir:reading-state',e=>{
   const reader=window.memoirReaders&&window.memoirReaders['hear-question'];
   if(busy&&reader&&e.detail.reading)reader.stop();
  });
  if(new URL(location.href).searchParams.get('listen')==='1'){
   const reader=window.memoirReaders&&window.memoirReaders['hear-question'];
   if(reader)reader.start();
  }
 }
 document.addEventListener('interview:record-state',e=>{busy=e.detail.recording||e.detail.waiting;controls();});
 function dirty(){return !!(answer&&answer.querySelector('textarea').value.trim());}
 function next(){if(!busy&&!dirty())location.replace(root.dataset.detail+'?listen=1');else setStatus('服务器进度已更新；当前还有未保存文字，请先复制核对，再刷新查看。');}
 async function query(url){
  const r=await fetch(url,{cache:'no-store',redirect:'error'});if(!r.ok)throw Error('查询未完成；已保存录音保留，可稍后重新打开采访。');return r.json();
 }
 async function poll(clip){
  if(stopped)return;
  if(document.hidden){setTimeout(()=>poll(clip),2500);return;}
  try{
   if(clip){
    const result=await query(root.dataset.asrBase.replace('CLIP',encodeURIComponent(clip)));
    if(result.status==='succeeded'){
     asr=false;controls();if(result.accepted){next();return;}
     setStatus('转写已保存，本题进度已变化或需要人工核对，请刷新查看原转写。');return;
    }
    if(!['queued','running'].includes(result.status)){
     asr=false;controls();setStatus('本次转写未完成，录音保留，可回听或用文字继续；不会自动重试。');return;
    }
   }else{
    const result=await query(root.dataset.progress);
    if(result.revision!==Number(root.dataset.revision)||!result.pending){next();return;}
   }
   attempts=0;
  }catch(e){attempts++;setStatus('网络或登录状态暂不可用；已保存内容保留，可稍后重新打开采访。');if(attempts>=5)return;}
  setTimeout(()=>poll(clip),2000);
 }
 document.addEventListener('interview:uploaded',e=>{
  if(['queued','running','succeeded'].includes(e.detail.status)){asr=true;controls();setTimeout(()=>poll(e.detail.id),1200);}
 });
 if(root.dataset.pending==='yes')setTimeout(()=>poll(null),1200);
 if(asr){
  const task=document.querySelector('[data-asr-pending]');
  if(task)setTimeout(()=>poll(task.dataset.asrPending),1200);
 }
 let submitting=false;document.addEventListener('submit',()=>{submitting=true;});
 window.addEventListener('beforeunload',e=>{if(dirty()&&!submitting){e.preventDefault();e.returnValue='';}});
 controls();window.addEventListener('pagehide',()=>{stopped=true;});
})();
