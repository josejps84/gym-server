from html import escape
from pathlib import Path
from string import Template
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import HTMLResponse

from app.dependencies import ContainerDep

router = APIRouter(tags=["legal"])

PRIVACY_UPDATED = {"es": "26 de octubre de 2026", "en": "October 26, 2026"}
_LEGAL = Path(__file__).parent.parent / "legal"
_PAGES = {lang: Template((_LEGAL / f"privacy_{lang}.html").read_text()) for lang in PRIVACY_UPDATED}
_NO_CONTACT = {"es": "[Contacto pendiente]", "en": "[Contact pending]"}


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(
    c: ContainerDep,
    lang: Annotated[Literal["es", "en"] | None, Query()] = None,
    accept_language: Annotated[str, Header()] = "",
) -> HTMLResponse:
    """Public page the app and the stores link to. Spanish unless asked or the browser prefers English."""
    lang = lang or ("en" if accept_language.lower().startswith("en") else "es")
    contact = escape(c.settings.privacy_contact) or _NO_CONTACT[lang]
    return HTMLResponse(_PAGES[lang].substitute(updated=PRIVACY_UPDATED[lang], contact=contact))
