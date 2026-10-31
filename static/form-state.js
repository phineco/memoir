/* A separate confirmation form must never silently ignore unsaved source/preview edits. */
(function(){
 'use strict';
 const forms=Array.from(document.querySelectorAll('form[data-source-editor],form[data-preview-editor]'));
 let submitted=false;
 function snapshot(form){return JSON.stringify(Array.from(new FormData(form).entries()).map(([key,value])=>[key,value instanceof File?(value.name?[value.name,value.size,value.lastModified]:''):value]));}
 const initial=new Map(forms.map(form=>[form,snapshot(form)]));
 const actions=Array.from(document.querySelectorAll('input[name=action]')).filter(n=>['generate','manual','confirm'].includes(n.value)).flatMap(n=>Array.from(n.form.querySelectorAll('button[type=submit],button:not([type])'))).map(button=>({button,disabled:button.disabled}));
 function update(){const dirty=forms.some(form=>form.dataset.dirty==='yes');
  actions.forEach(item=>item.button.disabled=item.disabled||dirty);
  const message=document.getElementById('preview-save-needed');if(message)message.hidden=!dirty;
 }
 forms.forEach(form=>{function changed(){form.dataset.dirty=snapshot(form)===initial.get(form)?'no':'yes';update();}form.addEventListener('input',changed);form.addEventListener('change',changed);});
 document.addEventListener('submit',()=>{submitted=true;});
 window.addEventListener('beforeunload',e=>{if(!submitted&&forms.some(f=>f.dataset.dirty==='yes')){e.preventDefault();e.returnValue='';}});
})();
