from conftest import merchant


async def test_login_rejects_wrong_password(client):
    await client.post("/auth/register", json={"email": "a@example.com", "password": "correct horse battery"})
    r = await client.post("/auth/token", data={"username": "a@example.com", "password": "wrong password!!"})
    assert r.status_code == 401


async def test_short_password_rejected(client):
    r = await client.post("/auth/register", json={"email": "b@example.com", "password": "short"})
    assert r.status_code == 422


async def test_protected_route_needs_token(client):
    assert (await client.get("/invoices")).status_code == 401
    assert (await client.get("/invoices", headers={"Authorization": "Bearer nonsense"})).status_code == 401


async def test_refresh_rotates_and_reuse_revokes_family(client):
    await client.post("/auth/register", json={"email": "c@example.com", "password": "correct horse battery"})
    first = (await client.post("/auth/token", data={"username": "c@example.com", "password": "correct horse battery"})).json()
    second = await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    # Replaying the first token looks like theft: refused, and the newer token dies with it.
    assert (await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": second.json()["refresh_token"]})).status_code == 401


async def test_access_token_cannot_be_used_as_refresh(client):
    h = await merchant(client)
    token = h["Authorization"].split()[1]
    assert (await client.post("/auth/refresh", json={"refresh_token": token})).status_code == 401
