"""Tests de la sesión aiohttp compartida de Anilist (roadmap #10).

Antes de #10, cada query creaba y cerraba una ClientSession nueva
(conexión TCP+TLS por petición). Ahora se reutiliza un pool de conexiones.
"""
import asyncio

from app.services.anilist import AnilistService


def test_session_shared_within_loop():
    """La misma ClientSession se reutiliza entre llamadas en el mismo loop."""
    async def scenario():
        svc = AnilistService()
        s1 = svc._get_session()
        s2 = svc._get_session()
        assert s1 is s2
        assert not s1.closed

        await svc.close()
        assert s1.closed
        assert svc._session is None

        # Tras close() se crea una sesión nueva
        s3 = svc._get_session()
        assert s3 is not s1
        assert not s3.closed
        await svc.close()

    asyncio.run(scenario())


def test_session_recreated_on_loop_change():
    """Si cambia el event loop (tests con distintos loops), la sesión se recrea."""
    svc = AnilistService()

    async def first_loop():
        return svc._get_session()

    s1 = asyncio.run(first_loop())

    async def second_loop():
        s2 = svc._get_session()
        assert s2 is not s1
        assert not s2.closed
        await svc.close()

    asyncio.run(second_loop())


class _FakeResponse:
    status = 200

    async def json(self):
        return {"data": {"ok": True}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Sustituye a aiohttp.ClientSession para verificar el comportamiento."""
    closed = False

    def post(self, *args, **kwargs):
        return _FakeResponse()

    async def close(self):
        self.closed = True


def test_execute_query_reuses_session():
    """_execute_query NO cierra la sesión tras cada query (pool persistente)."""
    async def scenario():
        svc = AnilistService()
        fake = _FakeSession()
        svc._session = fake
        svc._session_loop = asyncio.get_running_loop()

        r1 = await svc._execute_query("query A", {})
        r2 = await svc._execute_query("query B", {})
        assert r1 == {"data": {"ok": True}}
        assert r2 == {"data": {"ok": True}}
        # El código antiguo (async with ClientSession()) dejaría closed=True
        assert fake.closed is False
        assert svc._session is fake

    asyncio.run(scenario())


def test_close_is_idempotent():
    """close() sin sesión creada no lanza."""
    async def scenario():
        svc = AnilistService()
        await svc.close()
        await svc.close()

    asyncio.run(scenario())
