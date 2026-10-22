(function(){
  document.querySelectorAll('[data-copy-target]').forEach(function(button){
    button.addEventListener('click',async function(){
      var input=document.getElementById(button.dataset.copyTarget),status=document.getElementById('share-copy-status');
      try{
        if(!navigator.clipboard||!navigator.clipboard.writeText)throw Error('unavailable');
        await navigator.clipboard.writeText(input.value);status.textContent='分享链接已复制；请通过可靠渠道另行告知访问密码。';
      }catch(_){input.focus();input.select();status.textContent='链接已选中，请长按或使用复制操作。';}
    });
  });
})();
