/* Runs before CSS to restore this browser's display preferences without a flash. */
(function () {
  'use strict';
  var key = 'memoir.display.v1';
  var choices = {theme:['modern','paper','contrast'], font:['sans','serif','rounded'], size:['18','22','26'], mode:['standard','simple']};
  var defaults = {theme:'modern',font:'sans',size:'18',mode:'standard'};
  function normalize(value) {
    var result = {};
    Object.keys(defaults).forEach(function(k){ result[k] = value && choices[k].indexOf(value[k]) !== -1 ? value[k] : defaults[k]; });
    return result;
  }
  function read() {try {return normalize(JSON.parse(localStorage.getItem(key)));} catch(e){return normalize(null);}}
  var current = read();
  function apply(value) {
    current = normalize(value);
    Object.keys(current).forEach(function(k){document.documentElement.setAttribute('data-'+k,current[k]);});
    document.dispatchEvent(new Event('memoir:display-change'));
    document.querySelectorAll('[data-display-setting]').forEach(function(input){input.checked=current[input.name] === input.value;});
  }
  apply(current);
  document.addEventListener('DOMContentLoaded',function(){
    apply(current);
    var form=document.getElementById('display-settings');
    if(!form) return;
    function save(value) {
      apply(value);
      var status=document.getElementById('display-status');
      try {localStorage.setItem(key,JSON.stringify(current));status.textContent='已保存，下次在此浏览器打开时继续使用。';}
      catch(e){status.textContent='已应用。浏览器未允许保存，关闭页面后可能恢复默认。';}
    }
    form.addEventListener('change',function(e){
      if(!e.target.matches('[data-display-setting]'))return;
      var next=Object.assign({},current);next[e.target.name]=e.target.value;save(next);
    });
    document.getElementById('display-reset').addEventListener('click',function(){save(defaults);});
  });
  window.addEventListener('storage',function(e){if(e.key===key || e.key===null) apply(read());});
})();
