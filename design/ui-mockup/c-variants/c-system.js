(function () {
  document.documentElement.classList.add('js');

  var collection = document.getElementById('variants-collection');
  var layoutBtns = document.querySelectorAll('[data-layout-btn]');
  var focusBtns = document.querySelectorAll('[data-focus-btn]');
  var variantBlocks = document.querySelectorAll('[data-variant-id]');

  function readParams() {
    try {
      return new URLSearchParams(window.location.search);
    } catch (e) {
      return new URLSearchParams();
    }
  }

  function writeParam(key, val, defaultVal) {
    try {
      var params = readParams();
      if (!val || val === defaultVal) {
        params.delete(key);
      } else {
        params.set(key, val);
      }
      var qs = params.toString();
      var next = window.location.pathname + (qs ? '?' + qs : '') + window.location.hash;
      window.history.replaceState(null, '', next);
    } catch (e) {
      /* file:// environments without replaceState support ignore URL sync safely */
    }
  }

  function applyLayout(mode) {
    var nextMode = mode === 'grid' ? 'grid' : 'stack';
    if (collection) {
      collection.setAttribute('data-layout', nextMode);
    }
    layoutBtns.forEach(function (btn) {
      var active = btn.getAttribute('data-layout-btn') === nextMode;
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    writeParam('layout', nextMode, 'stack');
  }

  function applyFocus(targetId) {
    var valid = ['c0', 'c1', 'c2', 'c3'].indexOf(targetId) >= 0 ? targetId : 'all';
    variantBlocks.forEach(function (block) {
      var id = block.getAttribute('data-variant-id');
      block.hidden = valid !== 'all' && id !== valid;
    });
    focusBtns.forEach(function (btn) {
      var active = btn.getAttribute('data-focus-btn') === valid;
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    if (valid !== 'all' && collection) {
      collection.setAttribute('data-layout', 'stack');
    }
    writeParam('focus', valid, 'all');
  }

  layoutBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyFocus('all');
      applyLayout(btn.getAttribute('data-layout-btn'));
    });
  });

  focusBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyFocus(btn.getAttribute('data-focus-btn'));
    });
  });

  /* C1: Multi-company / team filter & open-day cell picker */
  var orgBtns = document.querySelectorAll('[data-org-filter]');
  var matrixTable = document.getElementById('c1-matrix-table');
  var pickBtns = document.querySelectorAll('.cell-pick-btn');
  var pickReadout = document.getElementById('c1-selection-readout');

  orgBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var org = btn.getAttribute('data-org-filter');
      orgBtns.forEach(function (b) {
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      if (matrixTable) {
        matrixTable.querySelectorAll('tbody tr[data-org]').forEach(function (row) {
          row.hidden = org !== 'all' && row.getAttribute('data-org') !== org;
        });
      }
      writeParam('org', org, 'all');
    });
  });

  function updatePickReadout() {
    if (!pickReadout) return;
    var selected = [];
    pickBtns.forEach(function (btn) {
      if (btn.getAttribute('aria-pressed') === 'true') {
        selected.push(btn.getAttribute('data-day-label'));
      }
    });
    if (!selected.length) {
      pickReadout.textContent = '내 행의 빈 날짜 셀을 눌러 일괄 신청 대상을 선택할 수 있습니다.';
    } else {
      pickReadout.textContent = '선택된 신청 예정일: ' + selected.join(', ') + ' (합계 ' + (selected.length * 8) + 'h 전일 기준)';
    }
  }

  pickBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var next = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', next ? 'true' : 'false');
      btn.textContent = next ? '선택 8h' : '신청 가능';
      updatePickReadout();
    });
  });

  /* C2: Live SHIM leave deduction calculator & honest validation (data-endpoint="") */
  var c2Form = document.getElementById('c2-leave-form');
  var c2Start = document.getElementById('c2-start');
  var c2End = document.getElementById('c2-end');
  var c2Deductive = document.getElementById('c2-deductive');
  var c2Reason = document.getElementById('c2-reason');
  var c2Calc = document.getElementById('c2-calc-hours');
  var c2Help = document.getElementById('c2-form-help');

  function toMinutes(hhmm) {
    if (!hhmm) return null;
    var parts = hhmm.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  function computeDeduction() {
    if (!c2Start || !c2End || !c2Deductive || !c2Calc) return { ok: true, hours: 8 };
    var sVal = c2Start.value;
    var eVal = c2End.value;
    var deductive = c2Deductive.checked;

    if (!sVal && !eVal) {
      c2Calc.textContent = deductive ? '8h (시간 생략 전일 자동 적용, 점심 1h 제외)' : '0h (비차감 전일, 사유 입력 필수)';
      return { ok: true, hours: deductive ? 8 : 0 };
    }
    if (!sVal || !eVal) {
      c2Calc.textContent = '입력 확인 필요 (시작과 종료 시각을 함께 지정하세요)';
      return { ok: false, field: !sVal ? c2Start : c2End, msg: '시작 시각과 종료 시각을 모두 선택하거나, 전일 신청 시 두 항목을 모두 비워 두세요.' };
    }
    var sMin = toMinutes(sVal);
    var eMin = toMinutes(eVal);
    if (eMin <= sMin) {
      c2Calc.textContent = '시간 범위 오류';
      return { ok: false, field: c2End, msg: '종료 시각은 시작 시각보다 뒤여야 합니다.' };
    }
    var overlapLunch = Math.max(0, Math.min(eMin, 780) - Math.max(sMin, 720));
    var netHours = (eMin - sMin - overlapLunch) / 60;
    var labelHours = deductive ? netHours + 'h 차감 (점심 겹침 ' + (overlapLunch / 60) + 'h 제외)' : '0h (비차감 일정, 실제 부재 ' + netHours + 'h)';
    c2Calc.textContent = labelHours;
    return { ok: true, hours: deductive ? netHours : 0 };
  }

  [c2Start, c2End, c2Deductive].forEach(function (el) {
    if (el) el.addEventListener('change', computeDeduction);
  });

  if (c2Form) {
    c2Form.addEventListener('submit', function (e) {
      e.preventDefault();
      [c2Start, c2End, c2Reason].forEach(function (f) {
        if (f) f.removeAttribute('aria-invalid');
      });
      if (c2Help) c2Help.classList.remove('is-error');

      var calc = computeDeduction();
      if (!calc.ok) {
        if (calc.field) {
          calc.field.setAttribute('aria-invalid', 'true');
          calc.field.focus();
        }
        if (c2Help) {
          c2Help.classList.add('is-error');
          c2Help.textContent = calc.msg;
        }
        return;
      }

      if (c2Deductive && !c2Deductive.checked && c2Reason && !c2Reason.value.trim()) {
        c2Reason.setAttribute('aria-invalid', 'true');
        c2Reason.focus();
        if (c2Help) {
          c2Help.classList.add('is-error');
          c2Help.textContent = '비차감 신청(공가, 출장 등)은 사유를 반드시 입력해야 합니다.';
        }
        return;
      }

      if (!c2Form.getAttribute('data-endpoint') && c2Help) {
        c2Help.textContent = '연결된 서버 엔드포인트가 없는 시안 화면입니다. 입력값과 차감 계산 규칙만 검증했습니다.';
      }
    });
  }

  /* C2: Pending self-cancel with immediate Undo */
  var pendingRow = document.getElementById('c2-pending-row');
  var cancelBtn = document.getElementById('c2-cancel-btn');
  var undoRow = document.getElementById('c2-undo-row');
  var undoBtn = document.getElementById('c2-undo-btn');

  if (cancelBtn && pendingRow && undoRow) {
    cancelBtn.addEventListener('click', function () {
      pendingRow.hidden = true;
      undoRow.hidden = false;
      if (undoBtn) undoBtn.focus();
    });
  }
  if (undoBtn && pendingRow && undoRow) {
    undoBtn.addEventListener('click', function () {
      undoRow.hidden = true;
      pendingRow.hidden = false;
      if (cancelBtn) cancelBtn.focus();
    });
  }

  /* C3: Keyboard-accessible tablist & 4-state data region preview */
  var c3Tabs = document.querySelectorAll('[data-c3-tab]');
  var c3Panels = document.querySelectorAll('[data-c3-panel]');
  var c3StateBtns = document.querySelectorAll('[data-c3-state]');
  var c3Views = document.querySelectorAll('[data-c3-view]');

  function activateC3Tab(tabName, moveFocus) {
    c3Tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-c3-tab') === tabName;
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.setAttribute('tabindex', active ? '0' : '-1');
      if (active && moveFocus) tab.focus();
    });
    c3Panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-c3-panel') !== tabName;
    });
    writeParam('tab', tabName, 'pending');
  }

  c3Tabs.forEach(function (tab, idx) {
    tab.addEventListener('click', function () {
      activateC3Tab(tab.getAttribute('data-c3-tab'), false);
    });
    tab.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault();
      var nextIdx = e.key === 'ArrowRight' ? (idx + 1) % c3Tabs.length : (idx - 1 + c3Tabs.length) % c3Tabs.length;
      activateC3Tab(c3Tabs[nextIdx].getAttribute('data-c3-tab'), true);
    });
  });

  function applyC3State(stateName) {
    var target = ['full', 'loading', 'empty', 'error'].indexOf(stateName) >= 0 ? stateName : 'full';
    c3StateBtns.forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-c3-state') === target ? 'true' : 'false');
    });
    c3Views.forEach(function (view) {
      view.hidden = view.getAttribute('data-c3-view') !== target;
    });
    writeParam('state', target, 'full');
  }

  c3StateBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyC3State(btn.getAttribute('data-c3-state'));
    });
  });

  var rejectForm = document.getElementById('c3-reject-form');
  var rejectReason = document.getElementById('c3-reject-reason');
  var rejectHelp = document.getElementById('c3-reject-help');

  if (rejectForm && rejectReason && rejectHelp) {
    rejectForm.addEventListener('submit', function (e) {
      e.preventDefault();
      rejectReason.removeAttribute('aria-invalid');
      rejectHelp.classList.remove('is-error');
      if (!rejectReason.value.trim()) {
        rejectReason.setAttribute('aria-invalid', 'true');
        rejectReason.focus();
        rejectHelp.classList.add('is-error');
        rejectHelp.textContent = '반려 처리 시 신청자에게 전달할 사유를 입력해야 합니다.';
        return;
      }
      if (!rejectForm.getAttribute('data-endpoint')) {
        rejectHelp.textContent = '서버 미연결 시안입니다. 반려 사유 필수 입력 검증만 확인했습니다.';
      }
    });
  }

  /* Restore initial URL state if present */
  var initParams = readParams();
  if (initParams.get('layout')) applyLayout(initParams.get('layout'));
  if (initParams.get('focus')) applyFocus(initParams.get('focus'));
  if (initParams.get('tab')) activateC3Tab(initParams.get('tab'), false);
  if (initParams.get('state')) applyC3State(initParams.get('state'));
})();
