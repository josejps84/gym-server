import httpx


async def test_privacy_policy_in_both_languages(client: httpx.AsyncClient) -> None:
    spanish = await client.get("/privacy")
    assert spanish.status_code == 200
    assert spanish.headers["content-type"].startswith("text/html")
    assert "Política de privacidad" in spanish.text
    assert "[Contacto pendiente]" in spanish.text
    assert "$" not in spanish.text

    english = await client.get("/privacy", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert "Privacy policy" in english.text
    assert "Privacy policy" in (await client.get("/privacy", params={"lang": "en"})).text
    assert (await client.get("/privacy", params={"lang": "fr"})).status_code == 422


async def test_email_links_land_on_a_page_that_opens_the_app(client: httpx.AsyncClient) -> None:
    page = await client.get("/auth/callback", params={"code": "abc"})
    assert page.status_code == 200
    assert "Correo confirmado" in page.text
    assert 'href="com.gymtracker.app://auth-callback"' in page.text
    assert "$" not in page.text.replace("${", "")
    assert "Email confirmed" in (await client.get("/auth/callback", params={"lang": "en"})).text
