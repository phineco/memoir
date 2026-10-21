/* Shared browser speech lifecycle. No audio upload or paid transcription service. */
(function () {
  window.initVoiceInput = function (options) {
    var button = document.getElementById('voice-btn');
    var status = document.getElementById('voice-status');
    var fallback = document.getElementById('voice-fallback');
    var keyboard = document.getElementById('voice-keyboard');
    var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var current = null, state = 'idle', startTimer, stopTimer, pending = '', received = false;
    function clearTimers() { clearTimeout(startTimer); clearTimeout(stopTimer); }
    function message(text, offerKeyboard) {
      status.textContent = text;
      if (offerKeyboard) fallback.hidden = false;
    }
    function render(next) {
      state = next;
      var active = state !== 'idle';
      button.setAttribute('aria-pressed', String(active));
      button.textContent = state === 'starting' ? '取消启动' : state === 'listening' ? '停止语音输入' : state === 'stopping' ? '取消等待' : '语音输入';
      button.setAttribute('aria-label', button.textContent);
    }
    function abort(rec) { try { rec.abort(); } catch (error) {} }
    function retainPending() {
      if (pending) { options.onText(pending); pending = ''; received = true; return true; }
      return false;
    }
    function finish(text, offerKeyboard) {
      clearTimers();
      current = null;
      var unconfirmed = retainPending();
      render('idle');
      message(text || (received ? '语音输入已结束，文字已保留，请核对后再发送或保存。' : '没有识别到文字，可重试或使用键盘听写。'), offerKeyboard || !received);
      if (unconfirmed) status.textContent += ' 最后一段识别结果尚未确认，请检查。';
    }
    function cancel(text) {
      var rec = current;
      finish(text || '语音输入已取消，已有文字已保留。', false);
      if (rec) abort(rec);
    }
    function stop() {
      if (!current) return;
      if (state === 'starting' || state === 'stopping') { cancel(); return; }
      var rec = current;
      render('stopping');
      message('已请求停止，正在接收最后的文字…再次点击可取消等待。', false);
      clearTimeout(startTimer);
      // Some implementations never emit end after stop. Always release and reset.
      stopTimer = setTimeout(function () {
        if (current !== rec) return;
        finish('语音输入已结束，已有文字已保留。可检查文字，或使用键盘听写。', true);
        abort(rec);
      }, 1500);
      try { rec.stop(); } catch (error) { cancel('语音输入已结束，已有文字已保留。'); }
    }
    function start() {
      pending = ''; received = false;
      fallback.hidden = true;
      render('starting');
      message('正在启动语音输入，可再次点击取消。首次使用请允许麦克风权限。', false);
      var rec;
      try {
        if (options.beforeStart) options.beforeStart();
        rec = new Recognition();
        current = rec;
        rec.lang = 'zh-CN';
        rec.continuous = options.continuous !== false;
        rec.interimResults = true;
        rec.maxAlternatives = 1;
        var finalized = {};
        rec.onstart = function () {
          if (current !== rec) return;
          clearTimeout(startTimer);
          render('listening');
          message('正在聆听，说完请点“停止语音输入”。', false);
        };
        rec.onresult = function (event) {
          if (current !== rec) return;
          var interim = '';
          for (var i = 0; i < event.results.length; i++) {
            var result = event.results[i];
            var text = result[0].transcript || '';
            if (result.isFinal) {
              if (!finalized[i]) { finalized[i] = true; options.onText(text); received = received || Boolean(text); }
            } else interim += text;
          }
          pending = interim;
          if (interim) message('正在识别：' + interim, false);
          else if (state === 'listening') message('已记录，继续说话或点“停止语音输入”。', false);
        };
        rec.onerror = function (event) {
          if (current !== rec) return;
          var errors = {
            'service-not-allowed': '当前浏览器未提供可用的语音识别服务。可改用手机键盘上的麦克风听写。',
            'not-allowed': '麦克风权限未获允许，请检查浏览器或手机设置；也可使用键盘听写。',
            'audio-capture': '未能使用麦克风，请检查设备连接和权限，或使用键盘听写。',
            'network': '语音识别服务连接失败，可稍后重试，或使用键盘听写。',
            'no-speech': '没有听到清晰语音，可重试或使用键盘听写。',
            'language-not-supported': '当前浏览器的语音服务不支持中文，可使用键盘听写。',
            'aborted': '语音输入已取消，已有文字已保留。'
          };
          finish(errors[event.error] || '语音识别暂时不可用，已有文字已保留。可重试或使用键盘听写。', event.error !== 'aborted');
          abort(rec);
        };
        rec.onend = function () { if (current === rec) finish(); };
        startTimer = setTimeout(function () {
          if (current !== rec) return;
          finish('语音服务未响应，可重试或使用键盘听写。', true);
          abort(rec);
        }, 10000);
        rec.start();
      } catch (error) {
        finish('无法启动语音输入，已有文字已保留。可重试或使用键盘听写。', true);
        if (rec) abort(rec);
      }
    }
    button.addEventListener('click', function () { if (current) stop(); else start(); });
    keyboard.addEventListener('click', function () {
      if (current) cancel();
      message('在输入区点手机键盘上的麦克风开始听写；确认文字后再发送或保存。也可直接打字。', true);
      options.focus();
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden && current) cancel('页面已切换，语音输入已停止，已有文字已保留。');
    });
    window.addEventListener('pagehide', function () { if (current) cancel(); });
    render('idle');
    if (!Recognition || window.isSecureContext === false) {
      button.disabled = true;
      message(!Recognition ? '当前浏览器不支持网页语音识别，可使用手机键盘听写。' : '网页语音输入需要安全连接，请使用 HTTPS，或使用键盘听写。', true);
    }
    return {active:function () { return current !== null; },stop:stop,cancel:cancel};
  };
})();
