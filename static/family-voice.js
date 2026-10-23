(function(){
 'use strict';
 var player=document.getElementById('family-voice-player');
 if(player){
  var start=document.getElementById('voice-read'),stop=document.getElementById('voice-stop'),retry=document.getElementById('voice-retry');
  var audio=document.getElementById('voice-audio'),status=document.getElementById('voice-play-status'),choice=document.getElementById('voice-choice');
  var basic=document.getElementById('storyReadBtn'),speed=document.getElementById('storyReadRate'),authorizationPanel=document.getElementById('voice-authorization');
  var serial=0,timer,activeStatus='',pending=false,initiallyDisabled=start.disabled;
  function ordinary(){return window.memoirReaders&&window.memoirReaders.storyReadBtn;}
  function selectedName(){return choice.options[choice.selectedIndex].dataset.name||'家人';}
  function halt(){
   serial++;clearTimeout(timer);activeStatus='';pending=false;audio.pause();audio.removeAttribute('src');audio.removeAttribute('data-profile-id');audio.load();audio.hidden=true;
   stop.disabled=true;start.disabled=initiallyDisabled;retry.hidden=true;
  }
  function selectVoice(){
   halt();var reader=ordinary();if(reader)reader.stop();
   var family=!!choice.value;basic.hidden=family;start.hidden=!family;authorizationPanel.hidden=!family;
   start.textContent=family?'用'+selectedName()+'的声音读':'用所选家人的声音读';
   status.textContent=family?'已选择'+selectedName()+'的 AI 合成声音，点击朗读开始。':'已选择普通朗读，使用当前设备的声音。';
  }
  function fallback(message){
   halt();var reader=ordinary();if(reader)reader.start();
   status.textContent=message+' 已尝试转为普通朗读，也可继续阅读正文。';retry.hidden=false;
  }
  async function watch(url,number,tries,name,profile){
   if(number!==serial)return;
   try{
    var response=await fetch(url,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error('unavailable');
    var result=await response.json();if(number!==serial)return;
    if(result.status==='ready'){
     pending=false;activeStatus=url;audio.dataset.profileId=profile;audio.src=result.audio_url;audio.playbackRate=Number(speed.value)||1;audio.hidden=false;
     status.textContent=name+'的 AI 合成音频已准备好；如未自动开始，请点播放器播放。';start.disabled=false;
     try{await audio.play();}catch(_){if(number===serial)status.textContent=name+'的音频已准备好，请点播放器播放。';}return;
    }
    if(['failed','revoked'].indexOf(result.status)!==-1)throw Error('not completed');
    if(tries>=30){fallback(name+'的声音仍在处理，此次先用普通朗读，稍后可再次点选家人声音。');return;}
    timer=setTimeout(function(){watch(url,number,tries+1,name,profile);},1000);
   }catch(_){if(number===serial)fallback(name+'的合成声音暂不可用。');}
  }
  async function requestAudio(again){
   if(!choice.value)return;
   halt();var number=serial,name=selectedName(),profile=choice.value,reader=ordinary();if(reader)reader.stop();
   var authorization=document.getElementById('voice-authorize');
   if(authorization&&!authorization.checked){status.textContent='请作者先单独确认本版本正文的语音服务处理。';return;}
   pending=true;start.disabled=true;stop.disabled=false;status.textContent='正在准备'+name+'的 AI 合成声音…';
   try{
    var response=await fetch(player.dataset.endpoint,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':player.dataset.csrf},body:JSON.stringify({profile_id:profile,stamp:player.dataset.stamp,authorize:authorization&&authorization.checked?'yes':undefined,retry:again?'yes':undefined})});
    var result=await response.json();if(number!==serial)return;
    if(!response.ok){fallback(result.error||name+'的合成声音暂不可用。');return;}
    watch(result.status_url,number,0,name,profile);
   }catch(_){if(number===serial)fallback('连接未完成。');}
  }
  choice.addEventListener('change',selectVoice);
  start.onclick=function(){requestAudio(false);};retry.onclick=function(){requestAudio(true);};
  stop.onclick=function(){halt();var reader=ordinary();if(reader)reader.stop();status.textContent='已停止播放，点击朗读可重新开始。';};
  basic.addEventListener('memoir:reading-state',function(event){
   if(event.detail.reading){halt();stop.disabled=false;status.textContent='正在普通朗读，使用当前设备的声音。';}
   else if(!pending&&audio.paused){stop.disabled=true;if(!choice.value)status.textContent='普通朗读已停止，可点击重新开始。';}
  });
  speed.addEventListener('change',function(){audio.playbackRate=Number(speed.value)||1;});
  audio.addEventListener('play',function(){
   if(!activeStatus||audio.dataset.profileId!==choice.value){halt();return;}
   var reader=ordinary();if(reader)reader.stop();stop.disabled=false;status.textContent='正在用'+selectedName()+'的 AI 合成声音朗读。';
  });
  audio.addEventListener('ended',function(){if(!audio.ended||!activeStatus)return;stop.disabled=true;status.textContent=selectedName()+'的合成朗读已结束。';});
  audio.addEventListener('error',function(){if(audio.error&&audio.getAttribute('src'))fallback('音频暂时无法播放。');});
  setInterval(async function(){
   if(audio.paused||!activeStatus)return;
   var number=serial,url=activeStatus;
   try{var response=await fetch(url,{credentials:'same-origin',cache:'no-store'});if(number!==serial)return;if(!response.ok){halt();status.textContent='声音授权或文章状态已变化，播放已停止。';}}
   catch(_){if(number===serial){halt();status.textContent='无法核对当前声音权限，播放已停止。';}}
  },15000);
  selectVoice();
  window.addEventListener('pagehide',function(){halt();});
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
