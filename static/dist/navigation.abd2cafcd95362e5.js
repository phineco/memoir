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
