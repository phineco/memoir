/* Questions suggest a topic; they never replace a writer's text or identity. */
(function () {
  'use strict';
  window.initWritingPrompts = function (options) {
    var form = document.getElementById('write-form');
    var modes = document.getElementById('recording-mode');
    if (!form || !modes) return;
    var narrator = form.elements.narrator_person_id;
    var narratorChosen = false;
    var prompt = document.getElementById('writing-prompt');
    var status = document.getElementById('writing-question-status');
    function sync() {
      var accompany = form.elements.recording_mode.value === 'accompany';
      document.getElementById('recording-mode-help').textContent = accompany
        ? '边听边记，讲述的人可在“补充人物与时间”中选择；暂时没有人物也可以先保存。'
        : '写下自己的回忆，也可以记录身边的人和事。';
      if (accompany) document.getElementById('story-details').open = true;
      var chosen = Array.from(modes.parentNode.querySelectorAll('[data-writing-question]')).find(function (button) { return button.dataset.writingQuestion === prompt.value; });
      status.textContent = chosen ? '可以从这个问题开始：' + chosen.dataset.questionText + ' 原有标题和正文会保留。' : '';
    }
    narrator.addEventListener('change', function () { narratorChosen = true; });
    modes.addEventListener('change', function () {
      if (!narratorChosen) {
        if (form.elements.recording_mode.value === 'accompany' && narrator.value === options.selfNarrator) narrator.value = '';
        else if (form.elements.recording_mode.value === 'self' && !narrator.value) narrator.value = options.selfNarrator;
      }
      sync();
    });
    form.querySelectorAll('[data-writing-question]').forEach(function (button) {
      button.addEventListener('click', function () {
        prompt.value = button.dataset.writingQuestion;
        if (!form.elements.topic.value.trim()) form.elements.topic.value = button.dataset.questionText;
        sync();
        document.getElementById('writing-questions').open = false;
        form.dispatchEvent(new Event('input', {bubbles:true}));
        options.focus();
      });
    });
    // Browser recovery restores the whole form; do not infer or overwrite its narrator.
    form.addEventListener('change', sync);
    sync();
  };
})();
