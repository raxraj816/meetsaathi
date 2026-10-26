"""Recipient view of a shared recap (M23, UNI-024): a static, script-free HTML page.

Everything is escaped; the page loads nothing external, cannot be framed, is never indexed or cached, and sends no
referrer. Invalid, expired, revoked and deleted links all return the same 404 so nothing leaks about a token.
"""
from __future__ import annotations

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..errors import ApiError
from ..memory.sharing import read_share

router = APIRouter(include_in_schema=False)

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}

SECTIONS = (("decisions", "Decisions"), ("actions", "Actions"), ("questions", "Open questions & risks"), ("notes", "Notes"))
STATUS = {"PROPOSED": "Proposed", "DISCUSSED": "Discussed", "ACCEPTED": "Accepted", "REJECTED": "Rejected", "DEFERRED": "Deferred",
          "SUPERSEDED": "Superseded", "UNRESOLVED": "Unresolved"}

STYLE = """
:root{color-scheme:light dark;--bg:#F5FAF9;--fg:#142630;--muted:#51636F;--card:#FFFFFF;--line:#D5E3E1;--accent:#087968;--warn:#9C6000}
@media (prefers-color-scheme:dark){:root{--bg:#0B1A26;--fg:#F0F8F8;--muted:#A0B8C6;--card:#132839;--line:#24435A;--accent:#70E6D0;--warn:#FFCF8A}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:680px;margin:0 auto;padding:24px 16px 48px}h1{font-size:26px;line-height:1.25;margin:4px 0 8px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.meta{color:var(--muted);font-size:14px;margin:0 0 16px}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin:12px 0}
h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}ul{margin:0;padding-left:20px}li{margin:6px 0}
.tag{color:var(--muted);font-size:13px}.notice{border-left:3px solid var(--accent);padding:8px 12px;color:var(--muted);font-size:14px}
.stale{border-left-color:var(--warn)}footer{color:var(--muted);font-size:13px;margin-top:24px}
"""


def _e(v) -> str:
    return html.escape(str(v or ""), quote=True)


def render(share: dict) -> str:
    s = share["snapshot"] or {}
    parts = [f'<p class="eyebrow">MeetSaathi · shared recap</p><h1>{_e(s.get("title"))}</h1>',
             f'<p class="meta">{_e(s.get("date"))} · {_e((s.get("context") or "").title())}</p>']
    if share.get("notice"):
        parts.append(f'<p class="notice stale">{_e(share["notice"])}</p>')
    if s.get("summary"):
        parts.append('<section class="card"><h2>Summary</h2>' + "".join(f"<p>{_e(t)}</p>" for t in s["summary"]) + "</section>")
    for key, title in SECTIONS:
        items = s.get(key) or []
        if not items:
            continue
        lis = []
        for it in items:
            tags = [STATUS.get(it.get("status"), "") if it.get("status") else "", it.get("owner") or "", it.get("label") or ""]
            tag = " · ".join(t for t in tags if t)
            lis.append(f"<li>{_e(it.get('text'))}" + (f' <span class="tag">· {_e(tag)}</span>' if tag else "") + "</li>")
        parts.append(f'<section class="card"><h2>{_e(title)}</h2><ul>{"".join(lis)}</ul></section>')
    parts.append(f'<p class="notice">{_e(s.get("notice"))}</p>')
    parts.append(f'<footer>This link expires {_e(str(share["expires_at"])[:16].replace("T", " "))} UTC and can be revoked by its owner.</footer>')
    return _page(_e(s.get("title")) or "Shared recap", "".join(parts))


def _page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{title} · MeetSaathi</title><style>{STYLE}</style></head>'
            f"<body><main>{body}</main></body></html>")


GONE = _page("Link unavailable", '<p class="eyebrow">MeetSaathi</p><h1>This link isn\'t available.</h1>'
             '<p class="meta">It may have expired or been revoked by the person who shared it.</p>')


@router.get("/s/{token}", response_class=HTMLResponse)
async def shared_page(token: str):
    if len(token) > 128:
        return HTMLResponse(GONE, status_code=404, headers=SECURITY_HEADERS)
    try:
        share = await read_share(token)
    except ApiError:
        return HTMLResponse(GONE, status_code=404, headers=SECURITY_HEADERS)
    return HTMLResponse(render(share), headers=SECURITY_HEADERS)
