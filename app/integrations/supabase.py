"""Supabase Storage and Auth admin calls, made with the service role key (server only)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx

from app.services.ports import SignedUpload, UpstreamError

# Supabase signed upload URLs last two hours.
UPLOAD_URL_LIFETIME = timedelta(hours=2)


class _SupabaseClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, service_role_key: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        ok_statuses: tuple[int, ...] = (),
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                content=content,
                headers={**self._headers, **(headers or {})},
            )
        except httpx.HTTPError as error:
            raise UpstreamError(f"Supabase {method} {path} failed") from error
        if response.is_error and response.status_code not in ok_statuses:
            raise UpstreamError(f"Supabase {method} {path} answered {response.status_code}")
        return response


class SupabaseAvatarStorage(_SupabaseClient):
    """A public bucket: anyone can read the photos, only signed URLs can upload them."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, service_role_key: str, bucket: str) -> None:
        super().__init__(http, base_url, service_role_key)
        self._bucket = bucket

    def public_url(self, path: str) -> str:
        return f"{self._base_url}/storage/v1/object/public/{self._bucket}/{path}"

    async def create_upload_url(self, path: str) -> SignedUpload:
        response = await self._request("POST", f"/storage/v1/object/upload/sign/{self._bucket}/{path}")
        relative = response.json()["url"]  # "/object/upload/sign/<bucket>/<path>?token=..."
        token = parse_qs(urlsplit(relative).query)["token"][0]
        return SignedUpload(
            upload_url=f"{self._base_url}/storage/v1{relative}",
            token=token,
            expires_at=datetime.now(UTC) + UPLOAD_URL_LIFETIME,
        )

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        await self._request(
            "POST", f"/storage/v1/object/{self._bucket}/{path}", content=data, headers={"Content-Type": content_type}
        )

    async def delete(self, paths: Sequence[str]) -> None:
        await self._request("DELETE", f"/storage/v1/object/{self._bucket}", json={"prefixes": list(paths)})

    async def list_paths(self, prefix: str) -> list[str]:
        response = await self._request(
            "POST", f"/storage/v1/object/list/{self._bucket}", json={"prefix": prefix, "limit": 1000, "offset": 0}
        )
        return [f"{prefix}/{item['name']}" for item in response.json()]


class SupabaseIdentityAdmin(_SupabaseClient):
    async def delete_user(self, user_id: UUID) -> None:
        await self._request("DELETE", f"/auth/v1/admin/users/{user_id}", ok_statuses=(404,))
