'use strict';
/* ROB RUN patch status page. Polls /api/state (read only). No inline code, no HTML from data: text nodes only. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var state = null;
  var offset = 0;
  var selected = { kind: 'role', role: 'battle', auto: true };
  var filter = 'all';
  var lastKey = '';
  var misses = 0;

  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'text') node.textContent = attrs[k];
      else if (k === 'class') node.className = attrs[k];
      else if (k === 'css') Object.keys(attrs[k]).forEach(function (prop) { node.style[prop] = attrs[k][prop]; });
      else node.setAttribute(k, attrs[k]);
    });
    function add(child) {
      if (child == null) return;
      if (Array.isArray(child)) { child.forEach(add); return; }
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    for (var i = 2; i < arguments.length; i++) add(arguments[i]);
    return node;
  }

  var PATHS = {
    check: 'M3.5 8.5l3 3 6-7',
    cross: 'M4 4l8 8M12 4l-8 8',
    retry: 'M13 8a5 5 0 1 1-1.6-3.7M13 2.5v3h-3',
    ring: 'M8 2.5a5.5 5.5 0 1 0 5.5 5.5',
    relay: 'M2.5 5.5h9l-2.5-2.5M13.5 10.5h-9l2.5 2.5',
    dash: 'M4 8h8'
  };
  function icon(name, spin) {
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('class', 'ico' + (spin ? ' spin' : ''));
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('d', PATHS[name]);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.8');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  function dur(s) {
    if (s == null || isNaN(s)) return '-';
    if (s < 100) return s.toFixed(1) + ' s';
    return Math.floor(s / 60) + ' min ' + ('0' + Math.floor(s % 60)).slice(-2) + ' s';
  }
  function clock(t) {
    var d = new Date(t * 1000);
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) + ':' + ('0' + d.getSeconds()).slice(-2);
  }
  function nowS() { return Date.now() / 1000 + offset; }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  var OUT = {
    direct: { tone: 'ok', icon: 'check', text: 'Connected directly' },
    repaired: { tone: 'accent', icon: 'relay', text: 'Repaired by patch' },
    failed: { tone: 'bad', icon: 'cross', text: 'Did not connect' },
    joining: { tone: 'warn', icon: 'ring', text: 'Joining', spin: true }
  };
  var STATE_TEXT = {
    connected: ['check', 'Connected'], connecting: ['ring', 'Connecting'], authorizing: ['ring', 'Authorizing'],
    retrying: ['retry', 'Retrying'], idle: ['dash', 'Not connected']
  };

  function connectOrigin(j) { return j.connect_t0 || j.started; }
  function joinTime(j) {
    var origin = connectOrigin(j);
    return j.connected_at ? j.connected_at - origin : (j.ended || nowS()) - origin;
  }

  /* ---- sections ---- */
  function renderHeader(s) {
    document.getElementById('version').textContent = 'v' + s.tool.version;
    var pill = document.getElementById('tool-state');
    var tone = { armed: 'ok', connected: 'accent', testing: 'accent', error: 'bad', limit: 'warn', waiting: 'warn' }[s.tool.status] || '';
    pill.setAttribute('data-tone', tone);
    pill.textContent = s.tool.label;
    document.getElementById('game-state').textContent = s.game_running === true ? 'Game running' : s.game_running === false ? 'Game not running' : 'Checking game';
  }

  function figure(value, label, tone, hint) {
    var f = el('div', { class: 'figure', 'data-tone': tone }, el('b', { text: String(value) }), el('span', { text: label }));
    if (hint) f.appendChild(el('small', { text: hint }));
    return f;
  }
  function renderCounts(s) {
    var c = s.counts, t = s.totals, box = document.getElementById('counts');
    box.replaceChildren(
      figure(c.connected + ' of ' + c.total, 'servers connected', 'ok', 'account, region, battle'),
      figure(c.connecting, 'connecting', 'accent'),
      figure(c.retrying, 'retrying', 'warn'),
      figure(t.repaired, plural(t.repaired, 'join repaired', 'joins repaired'), 'accent', 'by the patch'),
      figure(t.failed_attempts, 'failed attempts', 'bad', 'this session')
    );
  }

  function renderLanes(s) {
    var list = document.getElementById('lanes');
    var relayOn = s.relay.routes > 0;
    var items = ['user', 'region_user', 'battle'].map(function (key) {
      var r = s.roles[key];
      var st = STATE_TEXT[r.status] || STATE_TEXT.idle;
      var label = el('span', { class: 'link-label' }, icon(st[0], r.status === 'connecting' || r.status === 'authorizing'), st[1]);
      var sub = '';
      var last = r.attempts[r.attempts.length - 1];
      if (r.status === 'connecting' || r.status === 'authorizing') sub = last ? 'attempt ' + last.n + ' for ' : '';
      if (r.status === 'retrying') sub = plural(r.attempts.filter(function (a) { return a.outcome === 'failed'; }).length, 'failed attempt', 'failed attempts');
      if (r.status === 'connected') sub = r.rtt ? r.rtt + ' ms' : '';
      var subNode = el('span', { class: 'link-sub' + (sub.slice(-5) === ' for ' ? ' live' : ''), text: sub });
      if (sub.slice(-5) === ' for ' && last) {
        subNode.setAttribute('data-since', String(last.t0));
        subNode.setAttribute('data-prefix', sub);
      }
      var link = el('div', { class: 'link', 'data-state': r.status }, label, subNode);
      if (key === 'battle') link.appendChild(el('span', { class: 'relay', 'data-on': String(relayOn) }, icon('relay'), relayOn ? ' Patch relay forwarding' : ' Patch relay standby'));
      var where = r.ip ? r.ip + ':' + r.port : 'waiting for the game';
      var server = el('div', { class: 'node' }, r.name, el('small', { text: (r.host ? r.host + '  ' : '') + where }));
      var button = el('button', { class: 'lane', type: 'button', 'aria-pressed': String(selected.kind === 'role' && selected.role === key), 'data-key': 'lane-' + key },
        el('div', { class: 'lane-row' }, el('div', { class: 'node you', text: 'This PC' }), link, server));
      button.addEventListener('click', function () { selected = { kind: 'role', role: key, auto: false }; draw(true); });
      return el('li', null, button);
    });
    list.replaceChildren.apply(list, items);
  }

  function attemptRows(attempts, origin, span, now) {
    return attempts.slice(-12).map(function (a) {
      var t1 = a.t1 || now;
      var left = Math.max(0, (a.t0 - origin) / span * 100);
      var width = Math.max((t1 - a.t0) / span * 100, 0.6);
      width = Math.min(width, 100 - left);
      var word = { failed: 'failed', ok: 'connected', handshake: 'handshake', trying: 'trying', abandoned: 'cancelled' }[a.outcome] || a.outcome;
      var ico = { failed: 'cross', ok: 'check', handshake: 'ring', trying: 'ring' }[a.outcome];
      var bar = el('div', { class: 'bar', 'data-o': a.outcome, 'data-t0': String(a.t0), css: { left: left.toFixed(2) + '%', width: width.toFixed(2) + '%' } }, ico ? icon(ico) : null, word + ' ' + dur(t1 - a.t0));
      return el('div', { class: 'attempt' }, el('span', { class: 'lbl', text: 'try ' + a.n }), el('div', { class: 'track' }, bar));
    });
  }

  var MARK_TEXT = { trial: 'patch started a repair', proposal: 'sent an edited proposal', reply: 'server replied', connected: 'connected through the relay', retry_limit: 'retry limit reached' };

  function currentJoin(s) {
    if (selected.kind === 'join') {
      var found = s.joins.filter(function (j) { return j.id === selected.id; })[0];
      if (found) return found;
    }
    return s.joins[0] || null;
  }

  function renderDetail(s) {
    var box = document.getElementById('detail');
    var now = s.now;
    if (selected.kind === 'role' && selected.role !== 'battle') {
      var r = s.roles[selected.role];
      var origin = r.attempts.length ? r.attempts[0].t0 : now;
      var end = r.attempts.reduce(function (m, a) { return Math.max(m, a.t1 || now); }, origin);
      var span = Math.max(end - origin, 4);
      box.replaceChildren(
        el('h2', { text: r.name + ': attempts' }),
        el('div', { class: 'detail-head muted', text: (r.host || 'waiting for the game') + (r.ip ? '  ' + r.ip + ':' + r.port : '') }),
        r.attempts.length ? el.apply(null, ['div', { class: 'attempts' }].concat(attemptRows(r.attempts, origin, span, now))) : el('p', { class: 'empty', text: 'No attempts recorded yet.' })
      );
      return;
    }
    var j = currentJoin(s);
    if (!j) {
      box.replaceChildren(el('h2', { text: 'Battle server: attempts' }), el('p', { class: 'empty', text: 'No battle join yet. It appears the moment you enter a battle.' }));
      return;
    }
    var o = OUT[j.outcome] || OUT.joining;
    var origin2 = connectOrigin(j);
    var end2 = Math.max(j.ended || now, j.connected_at || 0, j.attempts.reduce(function (m, a) { return Math.max(m, a.t1 || now); }, origin2));
    var span2 = Math.max(end2 - origin2, 5);
    var head = el('div', { class: 'detail-head' },
      el('span', { class: 'res', 'data-t': j.outcome }, icon(o.icon, o.spin), o.text),
      el('span', { class: 'mono muted', text: (j.host || '') + (j.ip ? '  ' + j.ip + ':' + j.port : '') }),
      el('span', { class: 'muted', text: plural(j.attempts.length, 'attempt', 'attempts') + ', ' + (j.connected_at ? 'connected after ' + dur(j.connected_at - origin2) : 'not connected after ' + dur(joinTime(j))) + (j.end_reason ? ', ended: ' + j.end_reason : '') }));
    var rows = attemptRows(j.attempts, origin2, span2, now);
    // patch marks as ticks on every track, plus a plain list underneath
    var marks = j.marks.filter(function (m) { return m.kind !== 'baseline'; });
    rows.forEach(function (row) {
      var track = row.querySelector('.track');
      marks.forEach(function (m) {
        var x = (m.t - origin2) / span2 * 100;
        if (x >= 0 && x <= 100) track.appendChild(el('span', { class: 'tick', css: { left: x.toFixed(2) + '%' }, title: MARK_TEXT[m.kind] || m.kind }));
      });
    });
    var events = el('ul', { class: 'events' });
    if (marks.length) marks.forEach(function (m) {
      events.appendChild(el('li', null, el('span', { class: 't', text: '+' + (m.t - origin2).toFixed(1) + ' s' }), MARK_TEXT[m.kind] || m.kind));
    });
    else events.appendChild(el('li', { class: 'muted', text: j.outcome === 'direct' ? 'The patch was not needed for this join.' : 'The patch did nothing for this join.' }));
    var shown = el('h2', { text: 'Battle join #' + j.id });
    box.replaceChildren(shown, head, el.apply(null, ['div', { class: 'attempts' }].concat(rows)), events);
  }

  function renderHistory(s) {
    var table = document.getElementById('joins');
    var filters = [['all', 'All'], ['stalled', 'Stalled'], ['repaired', 'Repaired'], ['kicked', 'Kicked']];
    var seg = document.getElementById('filters');
    seg.replaceChildren.apply(seg, filters.map(function (f) {
      var b = el('button', { class: 'btn', type: 'button', 'aria-pressed': String(filter === f[0]), 'data-key': 'f-' + f[0], text: f[1] });
      b.addEventListener('click', function () { filter = f[0]; draw(true); });
      return b;
    }));
    var rows = s.joins.filter(function (j) {
      if (filter === 'repaired') return j.outcome === 'repaired';
      if (filter === 'kicked') return j.end_reason === 'kicked';
      if (filter === 'stalled') return j.outcome === 'failed' || j.outcome === 'repaired' || j.attempts.some(function (a) { return a.outcome === 'failed'; });
      return true;
    });
    var cur = currentJoin(s);
    var head = el('thead', null, el('tr', null, ['Join', 'Time', 'Server', 'Result', 'Attempts', 'To connect', 'Ended'].map(function (h) { return el('th', { scope: 'col', text: h }); })));
    var body = el('tbody');
    rows.forEach(function (j) {
      var o = OUT[j.outcome] || OUT.joining;
      var btn = el('button', { class: 'rowbtn', type: 'button', 'data-key': 'j-' + j.id, text: '#' + j.id });
      btn.addEventListener('click', function () { selected = { kind: 'join', id: j.id, auto: false }; draw(true); });
      var tr = el('tr', { 'aria-selected': String(!!cur && cur.id === j.id && selected.kind === 'join') },
        el('td', null, btn), el('td', { class: 'mono', text: clock(j.started) }), el('td', { class: 'mono', text: j.host || '-' }),
        el('td', null, el('span', { class: 'res', 'data-t': j.outcome }, icon(o.icon, o.spin), o.text)),
        el('td', { text: String(j.attempts.length) }), el('td', { class: 'mono', text: j.connected_at ? dur(j.connected_at - connectOrigin(j)) : '-' }),
        el('td', { text: j.end_reason || (j.outcome === 'joining' ? 'in progress' : '-') }));
      body.appendChild(tr);
    });
    table.replaceChildren(head, body);
    if (!rows.length) table.appendChild(el('caption', { class: 'empty', text: 'No joins match this filter yet.' }));
  }

  function summary(s) {
    var j = currentJoin(s);
    if (!j) return 'No battle join recorded yet.';
    var o = OUT[j.outcome] || OUT.joining, origin = connectOrigin(j);
    var lines = ['ROB RUN join #' + j.id + ' on ' + (j.host || 'unknown server') + (j.ip ? ' (' + j.ip + ':' + j.port + ')' : '') + ': ' + o.text.toLowerCase() +
      ', ' + plural(j.attempts.length, 'attempt', 'attempts') + (j.connected_at ? ', connected ' + dur(j.connected_at - origin) + ' after the first attempt' : ', never connected') + (j.end_reason ? ', ended: ' + j.end_reason : '') + '.'];
    j.attempts.forEach(function (a) { lines.push('  try ' + a.n + ': ' + a.outcome + ' ' + dur((a.t1 || s.now) - a.t0)); });
    j.marks.filter(function (m) { return m.kind !== 'baseline'; }).forEach(function (m) { lines.push('  patch +' + (m.t - origin).toFixed(1) + ' s: ' + (MARK_TEXT[m.kind] || m.kind)); });
    lines.push('Patch ' + s.tool.version + '. Page reads connection lines only; no tokens.');
    return lines.join('\n');
  }

  /* ---- drawing ---- */
  function draw(force) {
    if (!state) return;
    var focus = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute('data-key');
    var copy = JSON.parse(JSON.stringify(state));
    copy.now = 0;
    var key = JSON.stringify(copy) + JSON.stringify(selected) + filter;
    if (!force && key === lastKey) return;
    lastKey = key;
    if (selected.auto && selected.kind !== 'role') selected = { kind: 'role', role: 'battle', auto: true };
    renderHeader(state);
    renderCounts(state);
    renderLanes(state);
    renderDetail(state);
    renderHistory(state);
    if (focus) {
      var again = document.querySelector('[data-key="' + focus + '"]');
      if (again) again.focus();
    }
  }

  function tick() {
    if (!state) return;
    var live = document.querySelectorAll('.link-sub[data-since]');
    for (var i = 0; i < live.length; i++) {
      var since = parseFloat(live[i].getAttribute('data-since'));
      live[i].textContent = live[i].getAttribute('data-prefix') + dur(nowS() - since);
    }
    var trying = document.querySelectorAll('.bar[data-o="trying"]');
    for (var k = 0; k < trying.length; k++) trying[k].lastChild.textContent = 'trying ' + dur(nowS() - parseFloat(trying[k].getAttribute('data-t0') || nowS()));
  }

  function poll() {
    fetch('/api/state', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (s) {
      misses = 0;
      offset = s.now - Date.now() / 1000;
      state = s;
      document.getElementById('stale').hidden = true;
      try { draw(false); } catch (e) { console.error('draw failed', e); }
    }, function () {
      misses += 1;
      if (misses >= 3) document.getElementById('stale').hidden = false;
    });
  }

  /* theme: follows the system until the viewer picks one */
  function setTheme(name) { document.documentElement.setAttribute('data-theme', name); }
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  var saved = null;
  try { saved = window.localStorage.getItem('robrun-theme'); } catch (e) { saved = null; }
  setTheme(saved || (media && media.matches ? 'light' : 'dark'));
  document.getElementById('theme').addEventListener('click', function () {
    var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    setTheme(next);
    try { window.localStorage.setItem('robrun-theme', next); } catch (e) { /* storage may be blocked */ }
  });

  document.getElementById('copy').addEventListener('click', function () {
    if (!state) return;
    var done = document.getElementById('copied');
    var text = summary(state);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done.textContent = 'Copied.'; }, function () { done.textContent = 'Copy was blocked by the browser.'; });
    } else {
      done.textContent = 'Copy is not available here.';
    }
    setTimeout(function () { done.textContent = ''; }, 2500);
  });

  poll();
  setInterval(poll, 1000);
  setInterval(tick, 250);
})();
