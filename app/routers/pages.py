"""Public HTML pages: the privacy policy and where the email links land."""

from html import escape
from pathlib import Path
from string import Template
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import HTMLResponse

from app.dependencies import ContainerDep

router = APIRouter(tags=["pages"])

Language = Literal["es", "en"]
LANGUAGES: tuple[Language, ...] = ("es", "en")
PRIVACY_UPDATED = {"es": "26 de octubre de 2026", "en": "October 26, 2026"}
# The app's deep link (NATIVE_REDIRECT in gym-app's SupabaseAuthGateway).
APP_AUTH_URL = "com.giimme.app://auth-callback"
_NO_CONTACT = {"es": "[Contacto pendiente]", "en": "[Contact pending]"}
_DIR = Path(__file__).parent.parent / "pages"


def _templates(name: str) -> dict[str, Template]:
    return {lang: Template((_DIR / f"{name}_{lang}.html").read_text()) for lang in LANGUAGES}


_PRIVACY = _templates("privacy")
_AUTH_CALLBACK = _templates("auth_callback")

LangQuery = Annotated[Language | None, Query()]
AcceptLanguage = Annotated[str, Header()]


def _language(lang: Language | None, accept_language: str) -> Language:
    """Spanish unless asked or the browser prefers English."""
    return lang or ("en" if accept_language.lower().startswith("en") else "es")


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(c: ContainerDep, lang: LangQuery = None, accept_language: AcceptLanguage = "") -> HTMLResponse:
    """Public page the app and the stores link to."""
    language = _language(lang, accept_language)
    contact = escape(c.settings.privacy_contact) or _NO_CONTACT[language]
    return HTMLResponse(_PRIVACY[language].substitute(updated=PRIVACY_UPDATED[language], contact=contact))


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(lang: LangQuery = None, accept_language: AcceptLanguage = "") -> HTMLResponse:
    """Where the confirmation and password emails land: on the phone it hands the code to the app,
    elsewhere it explains what to do (the code only works in the app that asked for it)."""
    language = _language(lang, accept_language)
    return HTMLResponse(_AUTH_CALLBACK[language].substitute(app_url=APP_AUTH_URL))
