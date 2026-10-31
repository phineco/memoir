(function(){
 'use strict';
 const install=document.getElementById('easy-install'),state=document.getElementById('easy-install-status');
 let prompt=null;
 window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();prompt=event;if(install)install.hidden=false;});
 if(install)install.addEventListener('click',async()=>{
  if(!prompt)return;const event=prompt;prompt=null;await event.prompt();const choice=await event.userChoice;
  install.hidden=true;if(state)state.textContent=choice.outcome==='accepted'?'已提交安装，请从桌面打开后实际试用采访和回听。':'暂未安装，可稍后从浏览器菜单添加到桌面。';
 });
 if(!('serviceWorker' in navigator)||!window.isSecureContext){if(state)state.textContent='当前环境不能启用安装能力，可继续使用网页；请在手机HTTPS浏览器中查看。';return;}
 const banner=document.getElementById('easy-update'),button=document.getElementById('easy-update-button'),message=document.getElementById('easy-update-status');let asked=false,registration;
 function unsaved(){const recorder=document.getElementById('interview-recorder');
  return !!(recorder&&(recorder.dataset.recordBusy==='yes'||Number(recorder.dataset.pendingCount)>0))||
   !!document.querySelector('#interview-answer-form textarea:not(:placeholder-shown)')&&!!document.querySelector('#interview-answer-form textarea').value.trim()||
   !!document.querySelector('form[data-dirty=yes]');}
 function available(){if(banner)banner.hidden=false;}
 if(button)button.addEventListener('click',()=>{
  if(unsaved()){message.textContent='请先保存文字或下载、上传本机录音，完成后再更新。';return;}
  if(registration&&registration.waiting){asked=true;registration.waiting.postMessage({type:'SKIP_WAITING'});}
 });
 navigator.serviceWorker.addEventListener('controllerchange',()=>{
  if(asked&&!unsaved())location.reload();else if(asked&&message)message.textContent='版本已就绪，请先保存当前内容，再刷新页面。';
 });
 navigator.serviceWorker.register('/easy/sw.js',{scope:'/easy',updateViaCache:'none'}).then(reg=>{
  registration=reg;if(reg.waiting)available();reg.addEventListener('updatefound',()=>{const worker=reg.installing;if(worker)worker.addEventListener('statechange',()=>{if(worker.state==='installed'&&navigator.serviceWorker.controller)available();});});
 }).catch(()=>{if(state)state.textContent='安装暂不可用，可以继续使用网页；请检查浏览器和网络。';});
})();
