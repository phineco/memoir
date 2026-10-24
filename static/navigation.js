/* A compact mobile header; all links remain available without JavaScript. */
(function () {
  var header = document.querySelector('.topbar');
  var toggle = document.getElementById('site-menu-toggle');
  var menu = document.getElementById('site-menu');
  if (!header || !toggle || !menu) return;
  var mobile = window.matchMedia('(max-width: 768px)');
  function measure() {
    document.documentElement.style.setProperty('--site-header-height', header.getBoundingClientRect().height + 'px');
  }
  function close(restoreFocus) {
    if (!mobile.matches) return;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '菜单';
    menu.hidden = true;
    if (restoreFocus) toggle.focus({preventScroll:true});
  }
  function sync() {
    toggle.hidden = !mobile.matches;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '菜单';
    menu.hidden = mobile.matches;
    measure();
  }
  toggle.addEventListener('click', function () {
    var expanded = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.textContent = expanded ? '收起菜单' : '菜单';
    menu.hidden = !expanded;
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') close(true);
  });
  document.addEventListener('click', function (event) {
    if (!header.contains(event.target)) close(false);
  });
  document.addEventListener('focusin', function (event) {
    if (!header.contains(event.target)) close(false);
  });
  document.documentElement.classList.add('navigation-ready');
  sync();
  if (mobile.addEventListener) mobile.addEventListener('change', sync);
  else mobile.addListener(sync);
  if (window.ResizeObserver) new ResizeObserver(measure).observe(header);
  else window.addEventListener('resize', measure);
})();

/* Return to the same list position without relying on browser history. */
(function(){
 var body=document.body,prefix='memoir.navigation.v1.'+body.dataset.userId+'.'+body.dataset.familyId+'.';
 function key(path){return prefix+path;}
 window.addEventListener('pagehide',function(){try{sessionStorage.setItem(key(location.pathname+location.search),String(scrollY));}catch(e){}});
 document.addEventListener('click',function(event){
  var link=event.target.closest('a[data-restore-list]');
  if(link && new URL(link.href).origin===location.origin){try{sessionStorage.setItem(prefix+'restore',new URL(link.href).pathname+new URL(link.href).search);}catch(e){}}
  document.querySelectorAll('.family-switch[open]').forEach(function(item){if(!item.contains(event.target))item.open=false;});
 });
 document.addEventListener('keydown',function(event){if(event.key==='Escape')document.querySelectorAll('.family-switch[open]').forEach(function(item){item.open=false;item.querySelector('summary').focus();});});
 try{
  var path=location.pathname+location.search;
  if(sessionStorage.getItem(prefix+'restore')===path){
   sessionStorage.removeItem(prefix+'restore');
   var position=Number(sessionStorage.getItem(key(path)))||0;
   requestAnimationFrame(function(){requestAnimationFrame(function(){scrollTo(0,position);});});
  }
 }catch(e){}
})();
