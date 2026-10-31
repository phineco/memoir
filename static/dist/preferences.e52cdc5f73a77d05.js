/* One account-scoped device store. Account defaults are opt-in and never override a device choice. */
(function(){
 'use strict';
 let boot={user:'',enabled:false,values:null,revision:0,easyEnabled:false};
 try{boot=Object.assign(boot,JSON.parse(document.getElementById('display-bootstrap').textContent));}catch(e){}
 const scope=boot.user?'user.'+boot.user:'guest',key='memoir.display.device.v2.'+scope,hintKey='memoir.display-hint.v2.'+scope,reviewedKey='memoir.display.legacy-reviewed.v2.'+scope;
 const choices={theme:['modern','paper','contrast'],font:['sans','serif','rounded'],size:['18','22','26'],mode:['standard','simple'],entry:['standard','easy']};
 const defaults={theme:'modern',font:'sans',size:document.documentElement.hasAttribute('data-easy')?'22':'18',mode:'standard',entry:'standard'};
 function normalize(value){const result={};Object.keys(defaults).forEach(name=>{result[name]=value&&choices[name].includes(value[name])?value[name]:defaults[name];});return result;}
 function stored(name){try{return JSON.parse(localStorage.getItem(name));}catch(e){return null;}}
 function read(){return normalize(stored(key)||boot.values||defaults);}
 let current=read();
 function status(message){document.querySelectorAll('#display-status,[data-display-status]').forEach(n=>n.textContent=message);}
 function apply(value){
  current=normalize(value);Object.keys(current).forEach(name=>document.documentElement.setAttribute('data-'+name,current[name]));
  document.documentElement.dataset.easyEnabled=boot.easyEnabled?'yes':'no';
  document.dispatchEvent(new Event('memoir:display-change'));
  document.querySelectorAll('[data-display-setting]').forEach(n=>{n.checked=current[n.name]===n.value;});
  document.querySelectorAll('[data-reading-size]').forEach(n=>n.setAttribute('aria-pressed',String(current.size===n.dataset.readingSize)));
 }
 function save(value){
  apply(value);let message='已保留本人在本浏览器的设置；账号默认未改变。';
  try{localStorage.setItem(key,JSON.stringify(current));}
  catch(e){message='已应用。浏览器未允许保存，关闭页面后可能恢复默认。';}
  status(message);
 }
 apply(current);
 async function account(section,write){
  const response=await fetch(section.dataset.api,{method:write?'POST':'GET',cache:'no-store',redirect:'error',
   headers:write?{'Content-Type':'application/json','X-CSRF-Token':section.dataset.csrf}:{},
   body:write?JSON.stringify({values:current,base_revision:boot.revision,expected_user_id:boot.user}):undefined});
  if(!response.ok)throw Error(response.status===409?'账号或设置版本已变化，请先读取核对；本机设置保留。':'账号设置未确认保存，请检查登录和网络；本机设置保留。');
  const result=await response.json();if(result.user!==boot.user)throw Error('账号已切换，请重新打开本人设置页。');
  boot.values=result.values;boot.revision=result.revision;
  try{localStorage.removeItem(key);}catch(e){throw Error((write?'账号默认已保存':'账号默认已读取')+'，但浏览器不允许清理本机覆盖；关闭页面后可能仍显示旧设置。');}
  apply(read());return write?'已保存为账号默认，本设备现在跟随账号。':'本设备已跟随账号默认；若账号尚未保存则使用页面默认。';
 }
 document.addEventListener('DOMContentLoaded',()=>{
  apply(current);
  const form=document.getElementById('display-settings');
  if(form){form.addEventListener('change',e=>{if(e.target.matches('[data-display-setting]'))save(Object.assign({},current,{[e.target.name]:e.target.value}));});document.getElementById('display-reset').addEventListener('click',()=>save(defaults));}
  document.querySelectorAll('[data-reading-size]').forEach(button=>button.addEventListener('click',()=>save(Object.assign({},current,{size:button.dataset.readingSize}))));
  const hint=document.getElementById('large-text-hint');
  if(hint){let dismissed=false;try{dismissed=localStorage.getItem(hintKey)==='dismissed';}catch(e){}hint.hidden=dismissed||current.size!=='18';
   const close=()=>{hint.hidden=true;try{localStorage.setItem(hintKey,'dismissed');}catch(e){}};
   document.getElementById('large-text-dismiss').addEventListener('click',close);document.getElementById('large-text-enable').addEventListener('click',()=>{save(Object.assign({},current,{size:'22'}));close();});
  }
  const legacy=stored('memoir.display.v1'),reviewed=stored(reviewedKey);
  if(boot.user&&legacy&&!reviewed&&!stored(key)&&!boot.values){
   const banner=document.createElement('aside');banner.className='disclosure';banner.id='display-legacy';
   const message=document.createElement('p');message.textContent='发现此浏览器的旧显示设置。共用设备时，请确认是否用于当前账号（仅本机）。';banner.append(message);
   const actions=document.createElement('div');actions.className='form-actions';banner.append(actions);
   function choose(label,adopt){const button=document.createElement('button');button.type='button';button.className='btn-secondary';button.textContent=label;button.onclick=()=>{if(adopt)save(legacy);try{localStorage.setItem(reviewedKey,'true');}catch(e){}banner.remove();};actions.append(button);}
   choose('应用旧设置（仅本机）',true);choose('忽略旧设置',false);const main=document.querySelector('main');if(main)main.prepend(banner);
  }
  const section=document.getElementById('account-display-sync');
  if(section)for(const [id,write] of [['display-account-save',true],['display-account-follow',false]]){
   const button=document.getElementById(id);button.addEventListener('click',async()=>{
    button.disabled=true;const message=document.getElementById('display-account-status');message.textContent=write?'正在保存账号默认，请稍候。':'正在读取账号默认，请稍候。';
    try{message.textContent=await account(section,write);}catch(e){message.textContent=e.name==='TypeError'?'网络暂不可用，账号默认尚未确认，本机设置保留。':e.message||'账号默认暂不可用，本机设置保留。';}finally{button.disabled=false;}
   });
  }
 });
 window.addEventListener('storage',async event=>{
  if(event.key!==key&&event.key!==null)return;
  if(!stored(key)&&boot.enabled){
   try{const response=await fetch('/account/display-preferences',{cache:'no-store'});if(response.ok){const data=await response.json();if(data.user===boot.user){boot.values=data.values;boot.revision=data.revision;}}}catch(e){}
  }
  apply(read());
 });
})();
