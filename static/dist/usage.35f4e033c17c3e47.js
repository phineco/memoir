/* First-party status samples only. No text, article id, URL or question enters the queue. */
(function(){
  'use strict';
  var body=document.body,user=body.dataset.userId,family=body.dataset.familyId;
  var token=document.querySelector('meta[name="csrf-token"]');
  if(!user||!family||!token)return;
  var queue=[],sending=false;
  function id(){return crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random().toString(36).slice(2);}
  function flush(){
    if(sending||!queue.length)return;
    var batch=queue.splice(0,20);sending=true;
    fetch('/f/'+encodeURIComponent(family)+'/usage',{method:'POST',credentials:'same-origin',keepalive:true,
      headers:{'Content-Type':'application/json','X-CSRF-Token':token.content},
      body:JSON.stringify({user_id:user,events:batch})
    }).then(function(response){if(!response.ok)throw Error('not accepted');})
      .catch(function(){queue=batch.concat(queue).slice(-100);})
      .finally(function(){sending=false;});
  }
  window.memoirUsage=function(kind,outcome,duration){
    if(['retention','restore'].indexOf(kind)===-1||['success','failed'].indexOf(outcome)===-1)return;
    queue.push({id:id(),kind:kind,outcome:outcome,duration_ms:Math.min(60000,Math.max(0,Math.round(duration||0)))});
    if(queue.length>100)queue.shift();
    if(queue.length>=20)flush();
  };
  setInterval(flush,10000);
  window.addEventListener('pagehide',flush);
  document.addEventListener('visibilitychange',function(){if(document.hidden)flush();});
})();
