(function () {
  'use strict';
  var body = document.body;

  // Мобилно меню
  var menuBtn = document.querySelector('.menu-btn');
  var scrim = document.querySelector('.scrim');
  function setNav(open) { body.classList.toggle('nav-open', open); if (menuBtn) menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false'); }
  if (menuBtn) menuBtn.addEventListener('click', function () { setNav(!body.classList.contains('nav-open')); });
  if (scrim) scrim.addEventListener('click', function () { setNav(false); });
  var cur = document.querySelector('.sidebar a[aria-current="page"]');
  if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'center' });

  // Съдържание на страницата
  var toc = document.querySelector('.toc ul');
  var heads = Array.prototype.slice.call(document.querySelectorAll('main h2[id]'));
  if (toc && heads.length > 1) {
    heads.forEach(function (h) {
      var li = document.createElement('li'); var a = document.createElement('a');
      a.href = '#' + h.id; a.textContent = h.textContent; li.appendChild(a); toc.appendChild(li);
    });
    var links = toc.querySelectorAll('a');
    var onScroll = function () {
      var idx = 0;
      heads.forEach(function (h, i) { if (h.getBoundingClientRect().top < 140) idx = i; });
      links.forEach(function (l, i) { l.classList.toggle('active', i === idx); });
    };
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  } else if (toc) { toc.parentNode.style.display = 'none'; }

  // Копиране на команди
  document.querySelectorAll('pre').forEach(function (pre) {
    var b = document.createElement('button'); b.className = 'copy'; b.type = 'button'; b.textContent = 'Копирай';
    b.addEventListener('click', function () {
      var t = pre.querySelector('code') ? pre.querySelector('code').innerText : pre.innerText;
      var done = function () { b.textContent = 'Копирано'; setTimeout(function () { b.textContent = 'Копирай'; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(t.trim()).then(done, function () {});
      else { var ta = document.createElement('textarea'); ta.value = t.trim(); document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); done(); } catch (e) {} ta.remove(); }
    });
    pre.appendChild(b);
  });

  // Увеличаване на снимките
  var lb = document.getElementById('lb');
  document.querySelectorAll('figure.shot a').forEach(function (a) {
    a.addEventListener('click', function (e) {
      if (!lb || !lb.showModal) return;
      e.preventDefault();
      lb.querySelector('img').src = a.getAttribute('href');
      var cap = a.parentNode.querySelector('figcaption');
      lb.querySelector('img').alt = a.querySelector('img').alt;
      lb.querySelector('p').textContent = cap ? cap.textContent : '';
      lb.showModal();
    });
  });
  if (lb) {
    lb.addEventListener('click', function () { lb.close(); });
  }

  // Търсене
  var dlg = document.getElementById('search');
  var input = dlg && dlg.querySelector('input');
  var list = dlg && dlg.querySelector('.search-results');
  var index = window.GMSUN_INDEX || [];
  var sel = -1;
  function norm(s) { return (s || '').toLowerCase().replace(/ё/g, 'е'); }
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function hl(text, terms) {
    var out = esc(text);
    terms.forEach(function (t) { if (t.length < 2) return; out = out.replace(new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>'); });
    return out;
  }
  function snippet(text, term) {
    var i = norm(text).indexOf(term); if (i < 0) return text.slice(0, 140);
    var s = Math.max(0, i - 60); return (s > 0 ? '… ' : '') + text.slice(s, s + 170) + ' …';
  }
  function run() {
    var q = norm(input.value.trim()); list.innerHTML = ''; sel = -1;
    if (q.length < 2) { list.innerHTML = '<li class="search-empty">Въведете поне 2 букви — напр. „инвертор“, „Tailscale“, „оферта“, „бекъп“.</li>'; return; }
    var terms = q.split(/\s+/).filter(Boolean);
    var res = [];
    index.forEach(function (p) {
      p.s.forEach(function (sec) {
        var hay = norm(sec.h + ' ' + sec.t + ' ' + p.title);
        if (!terms.every(function (t) { return hay.indexOf(t) >= 0; })) return;
        var score = 0;
        terms.forEach(function (t) { if (norm(sec.h).indexOf(t) >= 0) score += 5; if (norm(p.title).indexOf(t) >= 0) score += 3; score += Math.min(3, norm(sec.t).split(t).length - 1); });
        res.push({ p: p, sec: sec, score: score });
      });
    });
    res.sort(function (a, b) { return b.score - a.score; });
    if (!res.length) { list.innerHTML = '<li class="search-empty">Няма резултати за „' + esc(input.value) + '“.</li>'; return; }
    res.slice(0, 30).forEach(function (r) {
      var li = document.createElement('li');
      li.innerHTML = '<a href="' + r.p.url + (r.sec.id ? '#' + r.sec.id : '') + '"><small>' + esc(r.p.title) + '</small><b>' + hl(r.sec.h, terms) + '</b><span>' + hl(snippet(r.sec.t, terms[0]), terms) + '</span></a>';
      list.appendChild(li);
    });
  }
  function openSearch() { if (!dlg) return; if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', ''); input.value = ''; run(); setTimeout(function () { input.focus(); }, 30); }
  document.querySelectorAll('[data-search]').forEach(function (b) { b.addEventListener('click', openSearch); });
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !/INPUT|TEXTAREA/.test(document.activeElement.tagName))) { e.preventDefault(); openSearch(); }
  });
  if (dlg) {
    input.addEventListener('input', run);
    input.addEventListener('keydown', function (e) {
      var items = list.querySelectorAll('a');
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); if (!items.length) return;
        sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items.forEach(function (a, i) { a.classList.toggle('sel', i === sel); });
        items[sel].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Escape') { e.preventDefault(); dlg.close(); }
      else if (e.key === 'Enter' && items.length) { e.preventDefault(); location.href = items[Math.max(sel, 0)].href; dlg.close(); }
    });
    dlg.querySelector('.search-close').addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    list.addEventListener('click', function (e) { if (e.target.closest('a')) dlg.close(); });
  }
})();
