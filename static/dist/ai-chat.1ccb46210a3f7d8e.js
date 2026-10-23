/* Durable request IDs prevent accidental duplicate provider calls. */
window.initAiChat = function (options) {
  'use strict';
  var log=document.getElementById('chatlog'), form=document.getElementById('chatform'), input=document.getElementById('msg-input');
  var send=document.getElementById('send-btn'), retry=document.getElementById('retry-ai'), cancel=document.getElementById('cancel-ai');
  var state=document.getElementById('ai-state'), restores=document.getElementById('ai-recoveries');
  var prefix='memoir:ai:pending:'+options.user+':'+options.family+':';
  var active=null, last=null, serial=0, controller=null, draftId=freshId(), pending=false;
  function freshId(){return window.crypto && crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random().toString(36).slice(2);}
  function remember(item){try{localStorage.setItem(prefix+item.id,JSON.stringify(item));}catch(_){state.textContent='本机保留不可用，请勿关闭页面，并复制问题留存。';}}
  function remove(id){try{localStorage.removeItem(prefix+id);}catch(_){}}
  function add(role,text){var div=document.createElement('div');div.className='chat-msg '+role;
    var label=document.createElement('div');label.className='chat-role';label.textContent=role==='user'?'你':'家音';div.appendChild(label);
    var body=document.createElement('div');body.className='chat-body';body.textContent=text;div.appendChild(body);log.appendChild(div);log.scrollTop=log.scrollHeight;return {div:div,body:body};}
  function sources(div,rows){
    var old=div.querySelector('.ai-sources');if(old)old.remove();if(!rows||!rows.length)return;
    var box=document.createElement('details');box.className='ai-sources disclosure';var summary=document.createElement('summary');summary.textContent='本次检索依据（请核对原文）';box.appendChild(summary);
    rows.forEach(function(row){
      if(typeof row.url!=='string'||row.url.indexOf(options.storyPrefix)!==0)return;
      var p=document.createElement('p'),a=document.createElement('a');a.href=row.url;a.textContent='['+row.index+'] '+row.title;p.appendChild(a);box.appendChild(p);
      var quote=document.createElement('blockquote');quote.textContent=row.excerpt;box.appendChild(quote);
    });div.appendChild(box);
  }
  function speak(text){
    if(!('speechSynthesis' in window))return;
    speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(text);u.lang='zh-CN';
    var stop=document.getElementById('stop-speak');stop.style.display='';u.onend=u.onerror=function(){stop.style.display='none';};speechSynthesis.speak(u);
  }
  function speakButton(div,text){var b=document.createElement('button');b.type='button';b.className='btn-small';b.textContent='朗读';b.onclick=function(){speak(text);};div.appendChild(b);}
  log.addEventListener('click',function(e){var b=e.target.closest('.speak-btn');if(b&&b.dataset.text)speak(b.dataset.text);});
  document.getElementById('stop-speak').onclick=function(){if('speechSynthesis' in window)speechSynthesis.cancel();this.style.display='none';};
  var voice=initVoiceInput({continuous:false,beforeStart:function(){if('speechSynthesis' in window)speechSynthesis.cancel();},onText:function(t){input.value+=t;input.dispatchEvent(new Event('input',{bubbles:true}));},focus:function(){input.focus();input.scrollIntoView({block:'center'});}});
  var voiceButton=document.getElementById('voice-btn'),voiceDisabled=voiceButton.disabled;
  function busy(value){pending=value;send.disabled=value;input.readOnly=value;voiceButton.disabled=value||voiceDisabled;cancel.hidden=!value;send.textContent=value?'正在回答…':'发送';}
  function fail(item,node,message,number){
    if(number!==serial)return;
    busy(false);retry.hidden=false;input.value=item.text;last=item;
    remember(item);state.textContent=message;node.body.textContent=node.body.textContent==='思考中…'?'本次没有收到完整回答。':node.body.textContent;
    var hint=document.createElement('p');hint.className='error';hint.textContent=message;node.div.appendChild(hint);active=null;
  }
  function success(item,node,answer,rows,number){
    if(number!==serial)return;
    node.body.textContent=answer;sources(node.div,rows);busy(false);retry.hidden=true;remove(item.id);last=null;active=null;
    if(input.value.trim()===item.text)input.value='';draftId=freshId();state.textContent='回答已保存，请核对检索依据。';
    speakButton(node.div,answer);if(document.getElementById('auto-speak').checked)speak(answer);showRecoveries();
  }
  async function statusOf(item){var r=await fetch(options.turnPrefix+encodeURIComponent(item.id));if(r.status===404)return null;if(!r.ok)throw Error('status');return r.json();}
  async function poll(item,node,number){
    try{
      var result=await statusOf(item);if(number!==serial)return;
      if(result&&result.status==='running'){
        state.textContent='服务器仍在处理同一个问题，可取消；不会重复发起生成。';
        setTimeout(function(){if(number===serial&&pending)poll(item,node,number);},2000);return;
      }
      if(result&&result.status==='succeeded')return success(item,node,result.answer,result.sources,number);
      fail(item,node,result&&result.error||'问题已保留，请点击重试。',number);
    }catch(_){fail(item,node,'无法确认生成结果，问题已保留；重试时会先检查原请求。',number);}
  }
  async function run(item){
    var number=++serial;active=item;last=item;remember(item);retry.hidden=true;busy(true);state.textContent='正在生成，可随时取消。';
    if('speechSynthesis' in window)speechSynthesis.cancel();
    var empty=document.getElementById('empty-hint');if(empty)empty.remove();
    add('user',item.text);var node=add('assistant','思考中…');
    controller=typeof AbortController!=='undefined'?new AbortController():null;
    var full='',rows=[],done=false,trace='';
    try{
      var response=await fetch(options.stream,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:item.text,request_id:item.id,retry_of:item.retryOf||undefined}),signal:controller?controller.signal:undefined});
      trace=response.headers.get('X-Request-ID')||'';
      if(response.status===409)return poll(item,node,number);
      if(!response.ok||!response.body)throw Error('http');
      var reader=response.body.getReader(),decoder=new TextDecoder(),buffer='';
      while(true){
        var part=await reader.read();if(number!==serial)return;
        if(part.done)break;buffer+=decoder.decode(part.value,{stream:true});
        var split;
        while((split=buffer.indexOf('\n\n'))>=0){
          var line=buffer.slice(0,split);buffer=buffer.slice(split+2);if(line.indexOf('data:')!==0)continue;
          var value=line.slice(5).trim();
          if(value==='[DONE]'){done=true;break;}
          var event;try{event=JSON.parse(value);}catch(_){continue;}
          if(event.error){var reference=event.request_id||trace;fail(item,node,event.error+(/^[a-f0-9]{24}$/.test(reference)?'（故障编号：'+reference+'）':''),number);await reader.cancel();return;}
          if(event.sources){rows=event.sources;sources(node.div,rows);}
          if(event.chunk){full+=event.chunk;node.body.textContent=full;log.scrollTop=log.scrollHeight;}
        }
        if(done)break;
      }
      if(!done||!full)throw Error('incomplete');success(item,node,full,rows,number);
    }catch(error){if(number===serial)fail(item,node,(error.name==='AbortError'?'已取消生成，问题已保留。':'连接中断或服务暂不可用，问题已保留，可重试。')+(/^[a-f0-9]{24}$/.test(trace)?'（故障编号：'+trace+'）':''),number);}
  }
  async function submit(){
    if(pending)return;if(voice&&voice.active()){voice.stop();return;}
    var text=input.value.trim();if(!text)return;
    if(last&&last.text===text){
      var previous=last;busy(true);
      try{
        var result=await statusOf(previous);
        if(result&&result.status==='running'){var n=++serial;active=previous;add('user',text);return poll(previous,add('assistant','思考中…'),n);}
        if(result&&result.status==='succeeded'){var n=++serial;return success(previous,add('assistant',''),result.answer,result.sources,n);}
        if(result) {remove(previous.id);previous={id:freshId(),text:text,retryOf:previous.id};}
        busy(false);return run(previous);
      }catch(_){busy(false);state.textContent='暂时无法核对原请求，请稍后重试；不会自动重复生成。';retry.hidden=false;return;}
    }
    run({id:draftId,text:text});
  }
  form.onsubmit=function(e){e.preventDefault();submit();};retry.onclick=submit;
  cancel.onclick=function(){
    if(!active)return;var item=active;++serial;if(controller)controller.abort();
    fetch(options.turnPrefix+encodeURIComponent(item.id),{method:'POST'}).catch(function(){});
    busy(false);input.value=item.text;last=item;active=null;retry.hidden=false;remember(item);state.textContent='已请求取消，问题已保留；服务器会在收到下一段回复时停止。';
  };
  input.addEventListener('input',function(){if(!pending){if(last&&last.text!==input.value.trim()){draftId=freshId();last=null;}remember({id:draftId,text:input.value});}});
  document.querySelectorAll('.suggest-q').forEach(function(b){b.onclick=function(){if(pending)return;input.value=b.textContent.trim();input.dispatchEvent(new Event('input'));input.focus();};});
  function showRecoveries(){
    restores.replaceChildren();
    try{Object.keys(localStorage).filter(function(k){return k.indexOf(prefix)===0;}).forEach(function(k){
      var row;try{row=JSON.parse(localStorage.getItem(k));}catch(_){return;}if(!row||!row.text||row.id===draftId)return;
      var b=document.createElement('button');b.type='button';b.className='btn-small btn-secondary';b.textContent='恢复未完成的问题：'+row.text.slice(0,40);
      b.onclick=function(){if(pending)return;input.value=row.text;last=row;draftId=row.id;retry.hidden=false;state.textContent='问题已恢复；发送前会先检查原请求状态。';};restores.appendChild(b);
    });}catch(_){}
  }
  document.getElementById('ai-clear-pending').onclick=function(){if(pending)return;try{Object.keys(localStorage).filter(function(k){return k.indexOf(prefix)===0;}).forEach(function(k){localStorage.removeItem(k);});}catch(_){}showRecoveries();state.textContent='本机未完成问题已清除；服务器上的对话记录保留。';};
  document.querySelectorAll('.resume-ai').forEach(function(b){b.onclick=function(){if(pending)return;input.value=b.dataset.question;last={id:b.dataset.request,text:b.dataset.question};retry.hidden=false;};});
  showRecoveries();
};
