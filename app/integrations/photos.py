"""Downloads sign-in providers' profile photos (only from hosts provider_photo_url accepts)."""

import httpx

from app.services.ports import UpstreamError

MAX_PHOTO_BYTES = 1_000_000


class HttpPhotoFetcher:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def fetch(self, url: str) -> tuple[bytes, str]:
        try:
            # No redirects: the URL was checked, wherever it would redirect to was not.
            async with self._http.stream("GET", url, follow_redirects=False, timeout=5) as response:
                if response.status_code != 200:
                    raise UpstreamError(f"Photo download answered {response.status_code}")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_PHOTO_BYTES:
                        raise UpstreamError("Photo is too big")
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
        except httpx.HTTPError as error:
            raise UpstreamError("Photo download failed") from error
        return bytes(data), content_type
