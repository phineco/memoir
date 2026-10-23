(function(){
 'use strict';
 var player=document.getElementById('family-voice-player');
 if(player){
  var start=document.getElementById('voice-read'),stop=document.getElementById('voice-stop'),retry=document.getElementById('voice-retry');
  var audio=document.getElementById('voice-audio'),status=document.getElementById('voice-play-status'),choice=document.getElementById('voice-choice');
  var serial=0,timer,activeStatus='',initiallyDisabled=start.disabled;
  function ordinary(){return window.memoirReaders&&window.memoirReaders.storyReadBtn;}
  function halt(){serial++;clearTimeout(timer);audio.pause();stop.disabled=true;start.disabled=initiallyDisabled;}
  function fallback(message){halt();status.textContent=message+' 已尝试转为普通朗读，也可继续阅读正文。';retry.hidden=false;var reader=ordinary();if(reader)reader.start();}
  async function watch(url,number,tries){
   if(number!==serial)return;
   try{
    var response=await fetch(url,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('unavailable');
    var result=await response.json();
    if(number!==serial)return;
    if(result.status==='ready'){
     activeStatus=url;audio.src=result.audio_url;audio.hidden=false;status.textContent='音频已准备好；如未自动开始，请点播放器播放。';start.disabled=false;
     try{await audio.play();}catch(_){status.textContent='音频已准备好，请点播放器播放。';}return;
    }
    if(['failed','revoked'].indexOf(result.status)!==-1)throw Error('not completed');
    if(tries>=30){fallback('后台仍在处理，此次先用普通朗读，稍后可再次点选家人声音。');return;}
    timer=setTimeout(function(){watch(url,number,tries+1);},1000);
   }catch(_){if(number===serial)fallback('家人声音暂不可用。');}
  }
  async function requestAudio(again){
   halt();var number=serial;var reader=ordinary();if(reader)reader.stop();audio.removeAttribute('src');retry.hidden=true;
   var authorization=document.getElementById('voice-authorize');
   if(authorization&&!authorization.checked){status.textContent='请作者先单独确认本版本正文的语音服务处理。';return;}
   start.disabled=true;stop.disabled=false;status.textContent='正在准备家人声音…';
   try{
    var response=await fetch(player.dataset.endpoint,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':player.dataset.csrf},body:JSON.stringify({profile_id:choice.value,stamp:player.dataset.stamp,authorize:authorization&&authorization.checked?'yes':undefined,retry:again?'yes':undefined})});
    var result=await response.json();if(number!==serial)return;
    if(!response.ok){fallback(result.error||'家人声音暂不可用。');return;}
    watch(result.status_url,number,0);
   }catch(_){if(number===serial)fallback('连接未完成。');}
  }
  start.onclick=function(){requestAudio(false);};retry.onclick=function(){requestAudio(true);};stop.onclick=function(){halt();status.textContent='已停止播放。';};
  var basic=document.getElementById('storyReadBtn');if(basic)basic.addEventListener('click',halt,true);
  var speed=document.getElementById('storyReadRate');if(speed)speed.addEventListener('change',function(){audio.playbackRate=Number(speed.value)||1;});
  audio.addEventListener('play',function(){var reader=ordinary();if(reader)reader.stop();stop.disabled=false;});
  audio.addEventListener('ended',function(){stop.disabled=true;});audio.addEventListener('error',function(){if(audio.getAttribute('src'))fallback('音频暂时无法播放。');});
  setInterval(async function(){if(audio.paused||!activeStatus)return;try{var response=await fetch(activeStatus,{cache:'no-store'});if(!response.ok){halt();audio.removeAttribute('src');status.textContent='声音授权或文章状态已变化，播放已停止。';}}catch(_){halt();status.textContent='无法核对当前声音权限，播放已停止。';}},15000);
  window.addEventListener('pagehide',function(){halt();audio.removeAttribute('src');});
 }
 var form=document.getElementById('voice-sample-form');if(!form)return;
 var record=document.getElementById('voice-record'),stopRecord=document.getElementById('voice-stop-record'),recordStatus=document.getElementById('voice-record-status');
 var preview=document.getElementById('voice-sample-preview'),file=form.querySelector('[name=sample]'),recorder,stream,blob,url,chunks=[],recordTimer,generation=0;
 function release(){if(stream){stream.getTracks().forEach(function(track){track.stop();});stream=null;}clearTimeout(recordTimer);record.disabled=false;stopRecord.disabled=true;}
 function show(value){if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(value);preview.src=url;preview.hidden=false;}
 record.onclick=async function(){
  var current=++generation;record.disabled=true;stopRecord.disabled=false;
  if(!navigator.mediaDevices||!window.MediaRecorder){recordStatus.textContent='此浏览器无法录音，请上传本机已有录音。';release();return;}
  recordStatus.textContent='正在请求麦克风权限…';
  try{
   var permission=await fetch(form.dataset.permission,{credentials:'same-origin',cache:'no-store'});
   if(!permission.ok){release();recordStatus.textContent='声音授权状态已变化，请刷新核对。';return;}
   if(current!==generation)return;
   var acquired=await navigator.mediaDevices.getUserMedia({audio:true});
   if(current!==generation){acquired.getTracks().forEach(function(track){track.stop();});return;}
   stream=acquired;chunks=[];blob=null;recorder=new MediaRecorder(stream);var currentRecorder=recorder;
   recorder.ondataavailable=function(event){if(event.data.size)chunks.push(event.data);};
   recorder.onstop=function(){blob=new Blob(chunks,{type:currentRecorder.mimeType||'audio/webm'});show(blob);release();recordStatus.textContent='录音已停止。请试听并选择清晰片段后提交。';};
   recorder.onerror=function(){release();recordStatus.textContent='录音未完成，请重录或上传已有录音。';};
   recorder.start();recordStatus.textContent='正在录音，最多 3 分钟；请点停止。';recordTimer=setTimeout(function(){if(recorder.state==='recording')recorder.stop();},180000);
  }catch(_){release();recordStatus.textContent='麦克风未能开启，可检查权限或上传已有录音。';}
 };
 stopRecord.onclick=function(){generation++;if(recorder&&recorder.state==='recording'){recorder.stop();release();record.disabled=true;}else{release();recordStatus.textContent='已取消启动录音。';}};
 file.onchange=function(){blob=null;if(file.files[0])show(file.files[0]);};
 form.addEventListener('submit',async function(event){
  event.preventDefault();var message=document.getElementById('voice-upload-status');
  if(recorder&&recorder.state==='recording'){message.textContent='请先停止录音并试听。';return;}
  var data=new FormData(form);if(blob)data.set('sample',blob,'recording.webm');
  if(!blob&&!file.files.length){message.textContent='请先录音或选择已有录音。';return;}
  var button=form.querySelector('button[type=submit]');button.disabled=true;message.textContent='正在处理所选片段，请稍候…';
  try{var response=await fetch(form.getAttribute('action')||location.href,{method:'POST',body:data,credentials:'same-origin'});if(response.redirected&&response.ok){location.assign(response.url);return;}message.textContent='片段未提交。请核对时长、格式及授权状态；原录音仍在本页，可重新选择。';}catch(_){message.textContent='连接未完成，请保留原录音并刷新核对处理状态。';}finally{button.disabled=false;}
 });
 window.addEventListener('pagehide',function(){generation++;if(recorder&&recorder.state==='recording')recorder.stop();release();if(url)URL.revokeObjectURL(url);});
})();
