"""Server-side PDF (WeasyPrint). Arabic is shaped and laid out right-to-left by Pango.

Every dynamic value MUST go through `e()` (HTML escape): product, customer and company
names are user input. WeasyPrint is given no base URL and a fetcher that refuses every
request, so a crafted name can never make the server load a file or call a URL.
"""

import asyncio
from html import escape
from typing import Any

from fastapi import Response

_CSS = """
@page { size: A4; margin: 16mm 14mm; @bottom-center { content: counter(page) " / " counter(pages);
        font-size: 8pt; color: #777; } }
* { box-sizing: border-box; }
body { font-family: 'Noto Naskh Arabic', 'Noto Sans Arabic', 'Noto Sans', sans-serif;
       font-size: 10.5pt; color: #111; line-height: 1.5; }
h1 { font-size: 17pt; margin: 0; } h2 { font-size: 12pt; margin: 14pt 0 4pt; }
.muted { color: #666; font-size: 9pt; } .head { border-bottom: 2px solid #111; padding-bottom: 8pt;
         margin-bottom: 10pt; }
.row { display: flex; justify-content: space-between; gap: 12pt; }
table { width: 100%; border-collapse: collapse; margin-top: 6pt; }
th { text-align: start; font-size: 9pt; color: #555; border-bottom: 1px solid #999; padding: 4pt 3pt; }
td { padding: 4pt 3pt; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
.num { text-align: end; direction: ltr; white-space: nowrap; font-family: 'Noto Sans', sans-serif; }
.totals { width: 52%; margin-top: 8pt; }
.totals td { border: 0; padding: 2pt 3pt; } .totals .grand td { font-weight: bold; font-size: 12pt;
             border-top: 1px solid #111; }
.cards { display: flex; flex-wrap: wrap; gap: 6pt; }
.card { border: 1px solid #ccc; border-radius: 4pt; padding: 6pt 8pt; width: 31.8%; }
.card b { display: block; font-size: 12pt; direction: ltr; text-align: end; font-family: 'Noto Sans', sans-serif; }
.foot { margin-top: 14pt; text-align: center; color: #555; font-size: 9pt; }
"""


def e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _refuse(url: str, *args: Any, **kwargs: Any) -> dict:
    raise ValueError("external resources are disabled in PDFs")


def _render(body: str, lang: str) -> bytes:
    from weasyprint import HTML

    direction = "rtl" if lang == "ar" else "ltr"
    html = (
        f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )
    return HTML(string=html, url_fetcher=_refuse).write_pdf()


async def pdf_response(filename: str, body: str, lang: str) -> Response:
    data = await asyncio.to_thread(_render, body, lang)  # CPU work off the event loop
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
