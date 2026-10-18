/* 语音朗读（浏览器 speechSynthesis）：故事/小传/周报共用。
 * 用法：initReadAloud(按钮id, 语速选择框id, 内容容器id)
 * iOS 需用户点击触发；云 TTS（生产）后续替换为 MP3 播放。
 */
function initReadAloud(btnId, rateId, containerId) {
  var btn = document.getElementById(btnId);
  var rateSel = document.getElementById(rateId);
  var container = document.getElementById(containerId);
  if (!btn || !rateSel || !container) return;
  var label = btn.textContent;
  var paras = Array.prototype.slice.call(
    container.querySelectorAll('p, h1, h2, h3, li, blockquote')
  ).filter(function(el) {
    return el.textContent.trim() && !el.parentElement.closest('blockquote, pre');
  });
  if (!('speechSynthesis' in window)) {
    btn.disabled = true; btn.textContent = '🔇 当前浏览器不支持朗读'; return;
  }
  if (!paras.length) { btn.disabled = true; return; }
  var idx = 0, reading = false;

  function highlight() {
    paras.forEach(function(p, i) { p.classList.toggle('reading', reading && i === idx); });
  }
  function speakNext() {
    if (!reading || idx >= paras.length) { stop(); return; }
    var u = new SpeechSynthesisUtterance(paras[idx].textContent);
    u.lang = 'zh-CN';
    u.rate = parseFloat(rateSel.value);
    u.onend = function() { idx++; highlight(); speakNext(); };
    u.onerror = function() { idx++; speakNext(); };
    highlight();
    speechSynthesis.speak(u);
  }
  function start() {
    speechSynthesis.cancel();
    idx = 0; reading = true;
    btn.textContent = '⏹ 停止朗读';
    speakNext();
  }
  function stop() {
    reading = false;
    speechSynthesis.cancel();
    btn.textContent = label;
    highlight();
  }
  btn.addEventListener('click', function() { reading ? stop() : start(); });
  rateSel.addEventListener('change', function() {
    if (reading) { speechSynthesis.cancel(); speakNext(); }  // 语速立即生效
  });
}
