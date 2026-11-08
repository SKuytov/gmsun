#!/usr/bin/env python3
"""Сглобява ръководството gmsun в две версии: PHP (за SuperHosting) и статичен HTML.

    python3 build.py          ->  dist/php/   dist/html/   dist/gmsun-manual-php.zip   dist/gmsun-manual-html.zip
"""
from __future__ import annotations

import html
import json
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
VERSION = "1.0 · ноември 2026"
REPO = "https://github.com/SKuytov/gmsun"

GROUPS = [
    ("Начало", [
        ("index", "Начало", "Какво прави gmsun и как е организирано ръководството."),
        ("kak-raboti", "Как работи системата", "Компоненти, потоци на данните, роли и основни понятия."),
    ]),
    ("Сървър и достъп", [
        ("hardware", "Хардуер и интернет", "Какъв компютър е нужен и препоръчани модели."),
        ("instalacia", "Инсталация на сървъра", "Ubuntu Server, една команда, .env и първо стартиране."),
        ("dostap", "Отдалечен достъп и база данни", "Tailscale, HTTPS, pgAdmin и защитна стена."),
        ("android", "Android приложение", "Инсталиране на APK, адрес на сървъра, обновяване."),
    ]),
    ("Първоначална подготовка", [
        ("vhod", "Вход, потребители и език", "Вход, роли, смяна на парола, BG/EN."),
        ("nastroiki", "Настройки", "Фирма, ценообразуване, инженерни параметри, текстове, доставчици."),
        ("katalog", "Каталог и datasheets", "Артикули, цени, синхронизация с доставчика, документи."),
        ("excel", "Всички таблици в Excel", "Масова редакция на цени, срокове и спецификации."),
        ("aerocompact", "Конструкция AEROCOMPACT", "Типове покриви, системи и правила за количествата."),
    ]),
    ("Работа по проект", [
        ("proekt", "Нов проект, стъпки 1–2", "Клиент и обект, параметри, оглед на обекта, статуси."),
        ("pokriv", "Стъпка 3: Покрив и панели", "Снимка, ъгли, контур, препятствия, подреждане на модулите."),
        ("preporaka-modul", "Препоръка за модул", "Как системата избира най-подходящия модул за покрива."),
        ("vizualizacia-3d", "Визуализация и 3D", "Фотореалистична снимка и 3D модел за клиента."),
        ("oborudvane", "Стъпка 4: Оборудване", "Автоматични предложения, инвертори в паралел, батерии."),
        ("materiali", "Стъпка 5: Материали", "Автоматично проектиране на стрингове, кабели, защити, конструкция."),
        ("trud", "Стъпка 6: Труд и условия", "СМР по матрица или по мощност, срокове и гаранции."),
        ("oferta", "Стъпка 7: Оферта и документи", "Редове, версии, проверка, PDF, КСС, досие, запитвания."),
        ("porachki", "Стъпка 8: Поръчки и доставки", "Поръчки по доставчици, получаване, готовност."),
        ("dokumenti", "Стъпка 9: Документи", "Архив на проекта на вашия сървър."),
    ]),
    ("Общ преглед", [
        ("tablo", "Табло и Доставки", "Ежедневният преглед на фирмата."),
    ]),
    ("Поддръжка", [
        ("poddrajka", "Резервни копия и обновяване", "Бекъп, възстановяване, обновяване, команди."),
        ("problemi", "Отстраняване на проблеми", "Чести ситуации и как да ги решите."),
        ("vaprosi", "Въпроси и добри практики", "Съвети за точни оферти и ограничения на системата."),
        ("rechnik", "Речник", "Термини и съкращения."),
    ]),
]

CHAPTERS = []
for g, items in GROUPS:
    for slug, title, desc in items:
        CHAPTERS.append({"slug": slug, "title": title, "desc": desc, "group": g})
for i, c in enumerate(CHAPTERS):
    c["n"] = i  # 0 = начало

LOGO = ('<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#26211b"/>'
        '<circle cx="16" cy="13" r="5.2" fill="#f2b632"/>'
        '<g stroke="#f2b632" stroke-width="1.6" stroke-linecap="round"><path d="M16 4.5v2M8.2 8.2l1.4 1.4M23.8 8.2l-1.4 1.4M5.5 14h2M24.5 14h2"/></g>'
        '<path d="M7 26l3-6h12l3 6z" fill="#3f6fb0"/><path d="M13.5 20l-1 6M18.5 20l1 6M8.5 23h15" stroke="#26211b" stroke-width=".9"/></svg>')
FAVICON = "data:image/svg+xml," + LOGO.replace('aria-hidden="true"', 'xmlns="http://www.w3.org/2000/svg"').replace("#", "%23").replace('"', "'")

TRANSLIT = dict(zip("абвгдежзийклмнопрстуфхцчшщъьюя", ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sht", "a", "", "yu", "ya"]))


def slugify(text: str) -> str:
    t = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60] or "s"


def strip_tags(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


IMG_SIZES: dict[str, tuple[int, int]] = {}


def figure(m: re.Match) -> str:
    parts = m.group(1).split("|")
    name = parts[0].strip()
    cap = parts[1].strip() if len(parts) > 1 else ""
    cls = parts[2].strip() if len(parts) > 2 else ""
    w, h = IMG_SIZES[name]
    alt = html.escape(strip_tags(cap) or name, quote=True)
    return (f'<figure class="shot {cls}"><a href="img/{name}.webp"><img src="img/{name}.webp" width="{w}" height="{h}" '
            f'alt="{alt}" loading="lazy" decoding="async"></a>' + (f"<figcaption>{cap}</figcaption>" if cap else "") + "</figure>")


def render_content(slug: str, ext: str) -> tuple[str, list[dict]]:
    raw = (SRC / "content" / f"{slug}.html").read_text(encoding="utf-8")
    raw = re.sub(r"\[\[img:(.+?)\]\]", figure, raw)
    if "[[chapters]]" in raw:
        cards = []
        for g, items in GROUPS:
            if g == "Начало":
                continue
            cards.append(f"<h3>{g}</h3><div class=\"chapters\">")
            for s, t, d in items:
                n = next(x["n"] for x in CHAPTERS if x["slug"] == s)
                cards.append(f'<a href="{s}.{ext}"><span class="n">{n:02d}</span><b>{t}</b><span class="d">{d}</span></a>')
            cards.append("</div>")
        raw = raw.replace("[[chapters]]", "\n".join(cards))
    raw = re.sub(r"<table>", '<div class="table-wrap"><table>', raw)
    raw = re.sub(r"</table>", "</table></div>", raw)
    raw = re.sub(r'href="@([a-z0-9-]+)(#[^"]*)?"', lambda m: f'href="{m.group(1)}.{ext}{m.group(2) or ""}"', raw)
    raw = raw.replace('href="index.' + ext + '"', 'href="index.' + ext + '"')

    used = set()

    def add_id(m: re.Match) -> str:
        attrs, inner = m.group(1), m.group(2)
        if "id=" in attrs:
            return m.group(0)
        base = slugify(strip_tags(inner))
        i, sid = 2, base
        while sid in used:
            sid = f"{base}-{i}"; i += 1
        used.add(sid)
        return f'<h2{attrs} id="{sid}">{inner}</h2>'

    raw = re.sub(r"<h2([^>]*)>(.*?)</h2>", add_id, raw, flags=re.S)

    # индекс за търсене: секции по h2
    sections = []
    pieces = re.split(r'(<h2[^>]*id="[^"]+"[^>]*>.*?</h2>)', raw, flags=re.S)
    cur = {"id": "", "h": "", "t": ""}
    for p in pieces:
        m = re.match(r'<h2[^>]*id="([^"]+)"[^>]*>(.*?)</h2>', p, flags=re.S)
        if m:
            sections.append(cur)
            cur = {"id": m.group(1), "h": strip_tags(m.group(2)), "t": ""}
        else:
            cur["t"] += " " + strip_tags(p)
    sections.append(cur)
    out = []
    for s in sections:
        s["t"] = s["t"].strip()[:4000]
        if s["t"] or s["h"]:
            out.append(s)
    return raw, out


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400..700&family=Onest:wght@500..800&family=JetBrains+Mono:wght@400;600;700&subset=cyrillic&display=swap" rel="stylesheet">')

MENU_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>'
SEARCH_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'


def head_html(title: str, desc: str) -> str:
    return f"""<!doctype html>
<html lang="bg">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#f7f4ee">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:locale" content="bg_BG">
<link rel="icon" href="{FAVICON}">
{FONTS}
<link rel="stylesheet" href="assets/style.css?v=1">
</head>
"""


def top_html(home: str) -> str:
    return f"""<body>
<a class="skip" href="#main">Към съдържанието</a>
<header class="top">
  <button class="menu-btn" type="button" aria-label="Меню" aria-expanded="false" aria-controls="sidebar">{MENU_ICON}</button>
  <a class="brand" href="{home}">{LOGO}<span>gmsun <small>Ръководство на потребителя</small></span></a>
  <span class="spacer"></span>
  <button class="search-btn" type="button" data-search aria-label="Търсене в ръководството">{SEARCH_ICON}<span class="lbl">Търсене в ръководството</span><kbd>Ctrl K</kbd></button>
  <a class="top-link" href="{REPO}" target="_blank" rel="noopener">GitHub</a>
</header>
<div class="scrim"></div>
<div class="layout">
"""


def sidebar_html(ext: str, current: str) -> str:
    out = ['<nav class="sidebar" id="sidebar" aria-label="Глави">']
    for g, items in GROUPS:
        out.append(f"<h2>{g}</h2><ul>")
        for slug, title, _ in items:
            c = next(x for x in CHAPTERS if x["slug"] == slug)
            n = f'{c["n"]:02d}' if c["n"] else "—"
            cur = ' aria-current="page"' if slug == current else ""
            out.append(f'<li><a href="{slug}.{ext}"{cur}><span class="n">{n}</span><span>{title}</span></a></li>')
        out.append("</ul>")
    out.append("</nav>")
    return "\n".join(out)


def pager_html(ext: str, idx: int) -> str:
    prev = CHAPTERS[idx - 1] if idx > 0 else None
    nxt = CHAPTERS[idx + 1] if idx + 1 < len(CHAPTERS) else None
    s = '<nav class="pager" aria-label="Предишна и следваща глава">'
    if prev:
        s += f'<a class="prev" href="{prev["slug"]}.{ext}"><small>Предишна</small>{prev["title"]}</a>'
    if nxt:
        s += f'<a class="next" href="{nxt["slug"]}.{ext}"><small>Следваща</small>{nxt["title"]}</a>'
    return s + "</nav>"


def tail_html(year_expr: str) -> str:
    return f"""<footer class="foot"><span>gmsun — система за оферти и проекти на фотоволтаични централи · Ръководство {VERSION}</span><span>© {year_expr} GM SUN · <a href="{REPO}" target="_blank" rel="noopener">Изходен код</a></span></footer>
"""


DIALOGS = f"""<dialog class="search" id="search" aria-label="Търсене">
  <div class="search-head">{SEARCH_ICON}<input type="search" placeholder="Търсене: инвертор, Tailscale, оферта, бекъп …" aria-label="Търсене" autocomplete="off"><button type="button" class="search-close">Esc</button></div>
  <ul class="search-results"></ul>
</dialog>
<dialog class="lb" id="lb"><img src="" alt=""><p></p><button type="button" aria-label="Затвори">×</button></dialog>
<script src="search-index.js?v=1" defer></script>
<script src="assets/app.js?v=1" defer></script>
</body>
</html>
"""


def page_body(c: dict, content: str) -> str:
    crumb = "" if c["slug"] == "index" else f'<p class="crumb">{c["group"]} · {c["n"]:02d}</p>'
    return f"""<div class="content-wrap">
<main id="main">
{crumb}
{content}
"""


def build_static(contents: dict[str, str]) -> Path:
    out = DIST / "html"
    for c in CHAPTERS:
        title = "gmsun — Ръководство на потребителя" if c["slug"] == "index" else f'{c["title"]} — gmsun Ръководство'
        page = (head_html(title, html.escape(c["desc"])) + top_html("index.html") + sidebar_html("html", c["slug"]) +
                page_body(c, contents[c["slug"] + ".html"]) + pager_html("html", c["n"]) + tail_html("2026") +
                '</main>\n<aside class="toc" aria-label="На тази страница"><h2>На тази страница</h2><ul></ul></aside>\n</div>\n</div>\n' + DIALOGS)
        (out / f'{c["slug"]}.html').write_text(page, encoding="utf-8")
    return out


def php_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_php(contents: dict[str, str]) -> Path:
    out = DIST / "php"
    inc = out / "includes"
    inc.mkdir(parents=True, exist_ok=True)
    # chapters.php — единственият източник на навигацията в PHP версията
    rows = []
    for g, items in GROUPS:
        it = ",\n".join(f"    [{php_str(s)}, {php_str(t)}, {php_str(d)}]" for s, t, d in items)
        rows.append(f"  {php_str(g)} => [\n{it}\n  ]")
    (inc / "chapters.php").write_text("<?php\n// Глави на ръководството (група => [slug, заглавие, описание])\n$GROUPS = [\n" + ",\n".join(rows) + "\n];\n"
        "$CHAPTERS = [];\nforeach ($GROUPS as $g => $items) { foreach ($items as $it) { $CHAPTERS[] = ['slug' => $it[0], 'title' => $it[1], 'desc' => $it[2], 'group' => $g]; } }\n"
        "function gm_index($slug) { global $CHAPTERS; foreach ($CHAPTERS as $i => $c) { if ($c['slug'] === $slug) return $i; } return 0; }\n"
        "function e($s) { return htmlspecialchars($s, ENT_QUOTES, 'UTF-8'); }\n", encoding="utf-8")

    head = head_html("<?= e($PAGE_TITLE) ?>", "<?= e($CH['desc']) ?>")
    top = top_html("index.php")
    sidebar = """<nav class="sidebar" id="sidebar" aria-label="Глави">
<?php foreach ($GROUPS as $g => $items): ?>
<h2><?= e($g) ?></h2><ul>
<?php foreach ($items as $it): $i = gm_index($it[0]); ?>
<li><a href="<?= e($it[0]) ?>.php"<?= $it[0] === $SLUG ? ' aria-current="page"' : '' ?>><span class="n"><?= $i ? sprintf('%02d', $i) : '—' ?></span><span><?= e($it[1]) ?></span></a></li>
<?php endforeach; ?>
</ul>
<?php endforeach; ?>
</nav>"""
    header_php = ("<?php\nrequire_once __DIR__ . '/chapters.php';\n$IDX = gm_index($SLUG);\n$CH = $CHAPTERS[$IDX];\n"
                  "$PAGE_TITLE = $SLUG === 'index' ? 'gmsun — Ръководство на потребителя' : $CH['title'] . ' — gmsun Ръководство';\n"
                  "header('Content-Type: text/html; charset=utf-8');\n?>\n" + head + top + sidebar + """
<div class="content-wrap">
<main id="main">
<?php if ($SLUG !== 'index'): ?><p class="crumb"><?= e($CH['group']) ?> · <?= sprintf('%02d', $IDX) ?></p><?php endif; ?>
""")
    (inc / "header.php").write_text(header_php, encoding="utf-8")
    footer_php = """<nav class="pager" aria-label="Предишна и следваща глава">
<?php if ($IDX > 0): $p = $CHAPTERS[$IDX - 1]; ?><a class="prev" href="<?= e($p['slug']) ?>.php"><small>Предишна</small><?= e($p['title']) ?></a><?php endif; ?>
<?php if ($IDX + 1 < count($CHAPTERS)): $n = $CHAPTERS[$IDX + 1]; ?><a class="next" href="<?= e($n['slug']) ?>.php"><small>Следваща</small><?= e($n['title']) ?></a><?php endif; ?>
</nav>
""" + tail_html("<?= date('Y') ?>") + '</main>\n<aside class="toc" aria-label="На тази страница"><h2>На тази страница</h2><ul></ul></aside>\n</div>\n</div>\n' + DIALOGS
    (inc / "footer.php").write_text(footer_php, encoding="utf-8")
    for c in CHAPTERS:
        body = contents[c["slug"] + ".php"]
        (out / f'{c["slug"]}.php').write_text(f"<?php $SLUG = {php_str(c['slug'])}; require __DIR__ . '/includes/header.php'; ?>\n{body}\n<?php require __DIR__ . '/includes/footer.php'; ?>\n", encoding="utf-8")
    (inc / ".htaccess").write_text("Require all denied\n", encoding="utf-8")
    (out / ".htaccess").write_text("""# gmsun — Ръководство (Apache / SuperHosting)
DirectoryIndex index.php index.html
AddDefaultCharset UTF-8
Options -Indexes

<IfModule mod_mime.c>
  AddType image/webp .webp
</IfModule>

<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css application/javascript image/svg+xml
</IfModule>

<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType image/webp "access plus 30 days"
  ExpiresByType text/css "access plus 7 days"
  ExpiresByType application/javascript "access plus 7 days"
</IfModule>
""", encoding="utf-8")
    return out


README = """gmsun — Ръководство на потребителя ({kind})
===============================================

Качване в SuperHosting (cPanel):
1. Влезте в https://www.superhosting.bg -> Моят профил -> cPanel -> „Файлов мениджър“ (File Manager).
2. Отворете public_html (или папката на домейна/поддомейна).
3. Създайте папка, напр. „rakovodstvo“ (по-добре латиница, без интервали).
4. Влезте в нея -> „Качване“ (Upload) -> изберете този ZIP архив.
5. Маркирайте архива -> „Разархивиране“ (Extract) -> в текущата папка. След това може да изтриете ZIP-а.
6. Отворете https://вашият-домейн.bg/rakovodstvo/

{extra}
Съдържание: {n} глави, вградено търсене (Ctrl K), снимки от реалното приложение, печат (Ctrl P).
Изходен код на системата: https://github.com/SKuytov/gmsun
"""


def main():
    for f in (SRC / "img").glob("*.webp"):
        IMG_SIZES[f.stem] = Image.open(f).size
    if DIST.exists():
        shutil.rmtree(DIST)
    contents = {}
    index = {"php": [], "html": []}
    for c in CHAPTERS:
        for ext in ("php", "html"):
            body, secs = render_content(c["slug"], ext)
            contents[f'{c["slug"]}.{ext}'] = body
            index[ext].append({"url": f'{c["slug"]}.{ext}', "title": c["title"], "s": secs})
    for kind in ("php", "html"):
        out = DIST / kind
        out.mkdir(parents=True)
        shutil.copytree(SRC / "assets", out / "assets")
        shutil.copytree(SRC / "img", out / "img")
        (out / "search-index.js").write_text("window.GMSUN_INDEX=" + json.dumps(index[kind], ensure_ascii=False) + ";\n", encoding="utf-8")
    build_static(contents)
    build_php(contents)
    (DIST / "html" / ".htaccess").write_text("DirectoryIndex index.html\nAddDefaultCharset UTF-8\nOptions -Indexes\n<IfModule mod_mime.c>\n  AddType image/webp .webp\n</IfModule>\n", encoding="utf-8")
    extras = {"php": "Изисква PHP 7.4 или по-нов (SuperHosting по подразбиране е PHP 8.x). Папката includes/ е защитена от директен достъп.\n",
              "html": "Чист HTML без PHP — работи на всеки хостинг и дори отворен локално (index.html).\n"}
    for kind in ("php", "html"):
        out = DIST / kind
        (out / "PROCHETI-ME.txt").write_text(README.format(kind="PHP версия" if kind == "php" else "HTML версия", extra=extras[kind], n=len(CHAPTERS)), encoding="utf-8")
        zp = DIST / f"gmsun-manual-{kind}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(out))
        print(zp.name, zp.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
