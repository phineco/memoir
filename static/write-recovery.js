/* Local recovery is scoped by account, family and story; each window writes its own copy. */
(function () {
  'use strict';
  var prefix = 'memoir:writer:v1:';
  window.clearWriteRecoveries = function (notice) {
    if (!notice || !Array.isArray(notice.ids)) return;
    notice.ids.forEach(function (id) {
      if (/^[a-zA-Z0-9-]{8,80}$/.test(id)) {
        try { localStorage.removeItem(prefix + notice.user + ':' + notice.family + ':' + notice.story + ':' + id); } catch (_) {}
      }
    });
  };
  window.initWriteRecovery = function (options) {
    var form = document.getElementById('write-form'), status = document.getElementById('recovery-status');
    var list = document.getElementById('recovery-list'), clear = document.getElementById('recovery-clear');
    var scope = prefix + options.user + ':' + options.family + ':' + options.story + ':';
    function freshId() { return window.crypto && crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random().toString(36).slice(2); }
    var id = freshId();
    var key = scope + id, used = [id], timer, leaving = false, dirty = false;
    function fields() {
      var data = {};
      new FormData(form).forEach(function (value, name) {
        if (['content', 'recovery_ids', 'action'].indexOf(name) !== -1) return;
        if (!data[name]) data[name] = [];
        data[name].push(value);
      });
      return {fields:data, content:options.read(), at:Date.now()};
    }
    function save() {
      if (!dirty) return;
      try {
        localStorage.setItem(key, JSON.stringify(fields()));
        status.textContent = '已自动保留在此浏览器；正式保存请点下方按钮。';
      } catch (_) { status.textContent = '自动保留失败，请及时保存草稿；离开前请复制正文。'; }
    }
    function changed() {
      dirty = true; clear.hidden = false; status.textContent = '正在保留…'; clearTimeout(timer); timer = setTimeout(save, 350);
    }
    function show() {
      list.replaceChildren();
      try {
        var rows = [];
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i); if (k.indexOf(scope) !== 0 || k === key) continue;
          try { var value = JSON.parse(localStorage.getItem(k)); if (value && value.fields && typeof value.content === 'string') rows.push({key:k, value:value}); } catch (_) {}
        }
        rows.sort(function (a,b) { return b.value.at - a.value.at; });
        rows.forEach(function (row) {
          var button = document.createElement('button'); button.type = 'button'; button.className = 'btn-small btn-secondary';
          button.textContent = '恢复：' + ((row.value.fields.topic || [])[0] || '未命名回忆') + '（' + new Date(row.value.at).toLocaleString() + '）';
          button.onclick = function () {
            if (dirty && !window.confirm('恢复会替换当前编辑区；当前内容已另存一份。继续恢复吗？')) return;
            if (dirty) { try { localStorage.setItem(scope + freshId(), JSON.stringify(fields())); } catch (_) { status.textContent = '无法另存当前内容，请先保存草稿。'; return; } }
            Array.from(form.elements).forEach(function (el) {
              var name = el.name; if (!name || ['recovery_ids','action','content'].indexOf(name) !== -1) return;
              var values = row.value.fields[name] || [];
              if (el.type === 'checkbox' || el.type === 'radio') el.checked = values.indexOf(el.value) !== -1;
              else if (el.type !== 'submit' && el.type !== 'button') el.value = values[0] || '';
            });
            options.write(row.value.content);
            var visibility = form.querySelector('input[name="visibility"]:checked');
            if (visibility) visibility.dispatchEvent(new Event('change', {bubbles:true}));
            form.dispatchEvent(new Event('change', {bubbles:true})); changed(); save();
          };
          list.appendChild(button);
        });
        clear.hidden = rows.length === 0 && !dirty;
      } catch (_) { status.textContent = '此浏览器不能保留内容，请及时保存草稿。'; }
    }
    document.getElementById('recovery-ids').value = id;
    form.addEventListener('input', changed); form.addEventListener('change', changed);
    options.subscribe(changed);
    form.addEventListener('submit', function (event) {
      if (event.defaultPrevented) return;
      save(); leaving = true;
    });
    window.addEventListener('beforeunload', function (event) {
      save();
      if (dirty && !leaving) { event.preventDefault(); event.returnValue = ''; }
    });
    window.addEventListener('pagehide', save);
    document.addEventListener('visibilitychange', function () { if (document.hidden) save(); });
    window.addEventListener('storage', function (event) { if (event.key && event.key.indexOf(scope) === 0) show(); });
    clear.onclick = function () {
      if (!window.confirm('清除此账号在本页的所有本机恢复记录？当前编辑区仍保留，请及时保存。')) return;
      try {
        var keys = []; for (var i=0;i<localStorage.length;i++) if(localStorage.key(i).indexOf(scope)===0) keys.push(localStorage.key(i));
        keys.forEach(function (k) { localStorage.removeItem(k); });
        dirty = false; status.textContent = '本机恢复记录已清除。'; show();
      } catch (_) { status.textContent = '清除失败，请检查浏览器存储设置。'; }
    };
    show();
    return {save:save};
  };
})();
