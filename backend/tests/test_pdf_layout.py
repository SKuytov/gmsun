"""PDF pagination guards: the totals, a section header row and the signatures must never be orphaned on a page."""
from pathlib import Path

import pytest

weasyprint = pytest.importorskip("weasyprint")

CSS = (Path(__file__).resolve().parents[1] / "app" / "templates" / "_doc.css").read_text(encoding="utf-8")


def _doc(n: int) -> str:
    rows = ""
    for i in range(n):
        if i % 6 == 0:
            rows += f"<tr class=section><td>S</td><td>SEC{i}</td><td></td></tr>"
        rows += f"<tr><td>{i}</td><td>Item{i}<span class=sub>x</span></td><td>1</td></tr>"
    return (f"<html><head><style>{CSS}</style></head><body><table class=lines><thead><tr><th>#</th><th>n</th><th>q</th></tr></thead>"
            f"<tbody>{rows}</tbody></table><div class=totals-wrap><table class=totals><tr class=grand><td>TOTAL</td><td class=r>2</td></tr>"
            f"</table></div><div class=terms><h3>T</h3><p>{'line<br>' * n}</p></div><div class=sign><div>SIGNA<b>x</b></div><div>SIGNB</div></div></body></html>")


def _tokens(page) -> list[str]:
    out: list[str] = []

    def walk(b):
        t = (getattr(b, "text", None) or "").strip()
        if t and "{{" not in t and "}}" not in t and "/" not in t:
            out.append(t)
        for c in getattr(b, "children", None) or []:
            walk(c)

    walk(page._page_box)
    return out


def test_no_orphans_at_any_table_length():
    bad = []
    for n in range(10, 66):
        pages = [_tokens(p) for p in weasyprint.HTML(string=_doc(n)).render().pages]
        for i, toks in enumerate(pages):
            if i and toks and toks[0] in ("TOTAL", "SIGNA"):
                bad.append((n, i, toks[0]))
            secs = [j for j, x in enumerate(toks) if x.startswith("SEC")]
            if secs and not any(x.startswith("Item") for x in toks[secs[-1]:]):
                bad.append((n, i, "section"))
    assert not bad, bad


def _spec_doc(n: int, fit: int) -> str:
    rows = ""
    for i in range(n):
        if i % 6 == 0:
            rows += f"<tr class=section><td>S</td><td>SEC{i}</td><td></td></tr>"
        rows += f"<tr><td>{i}</td><td>Item{i}<span class=sub>x</span></td><td>1</td></tr>"
    return (f"<html><head><style>{CSS}</style></head><body class='fit-{fit}'><h2 id=spec-start>Spec</h2><table class=lines><tbody>{rows}</tbody></table>"
            f"<div class=totals-wrap id=spec-end><table class=totals><tr class=grand><td>TOTAL</td><td class=r>2</td></tr></table></div>"
            f"<h2>Next</h2><p>tail</p></body></html>")


def test_short_spillover_is_squeezed_onto_one_page():
    from app.services.pdf import _fit_specification, _spec_span

    squeezed = 0
    for n in range(28, 48):
        base = _spec_span(weasyprint.HTML(string=_spec_doc(n, 0)).render())
        fitted = _spec_span(_fit_specification(lambda f: weasyprint.HTML(string=_spec_doc(n, f)).render()))
        assert fitted[1] - fitted[0] <= base[1] - base[0]          # never worse
        if base[1] > base[0] and base[2] <= 0.15:                   # a couple of rows spilled
            assert fitted[1] - fitted[0] == base[1] - base[0] - 1, (n, base, fitted)  # the short tail page is saved
            squeezed += 1
    assert squeezed, "no spill-over case was exercised"
