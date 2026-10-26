"""Email: Resend's HTTP API, or nothing when no key is configured."""

import logging

import httpx

from app.services.ports import UpstreamError

log = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


class ResendMailer:
    def __init__(self, http: httpx.AsyncClient, api_key: str, sender: str) -> None:
        self._http = http
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sender = sender

    async def send(self, to: str, subject: str, text: str) -> None:
        body = {"from": self._sender, "to": [to], "subject": subject, "text": text}
        try:
            response = await self._http.post(RESEND_URL, json=body, headers=self._headers)
        except httpx.HTTPError as error:
            raise UpstreamError("Resend failed") from error
        if response.is_error:
            raise UpstreamError(f"Resend answered {response.status_code}")


class NoMailer:
    async def send(self, to: str, subject: str, text: str) -> None:
        log.info("Email not sent (no RESEND_API_KEY): %s", subject)
