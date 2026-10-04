"""
Tests para Web Push (roadmap #7)
- Endpoints /push/* (auth, upsert por endpoint, IDOR en unsubscribe)
- Smoke test: send_push nunca lanza
"""

import base64

from app.models.push_subscription import PushSubscription
from app.services.push_service import (
    _generate_vapid_pair,
    send_push,
)


SUBSCRIPTION = {
    "endpoint": "https://push.example.com/user/abc",
    "keys": {
        "p256dh": "BNIB1234567890abcdef",
        "auth": "authsecret123",
    },
    "user_agent": "test-agent",
}


class TestVapidKeys:
    def test_generate_pair_roundtrip(self):
        """La pareja generada es base64url válido y from_raw deriva la misma pública."""
        from py_vapid import Vapid, b64urlencode
        from cryptography.hazmat.primitives import serialization

        public_b64, private_b64 = _generate_vapid_pair()
        # 65 bytes (punto no comprimido) -> 87 chars sin padding; 32 bytes -> 43
        assert len(public_b64) == 87
        assert len(private_b64) == 43
        v = Vapid.from_raw(private_b64.encode("ascii"))
        derived = b64urlencode(
            v.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint,
            )
        )
        assert derived == public_b64

    def test_public_key_endpoint(self, client, auth_headers):
        resp = client.get("/api/v1/push/vapid-public-key", headers=auth_headers)
        assert resp.status_code == 200
        key = resp.json()["publicKey"]
        assert len(key) == 87

    def test_public_key_requires_auth(self, client):
        resp = client.get("/api/v1/push/vapid-public-key")
        assert resp.status_code in (401, 403)


class TestSubscribe:
    def test_subscribe_creates_subscription(self, client, auth_headers, db):
        resp = client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=auth_headers)
        assert resp.status_code == 200
        rows = db.query(PushSubscription).all()
        assert len(rows) == 1
        assert rows[0].endpoint == SUBSCRIPTION["endpoint"]
        assert rows[0].user_id is not None

    def test_subscribe_upserts_by_endpoint(self, client, auth_headers, db):
        client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=auth_headers)
        client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=auth_headers)
        rows = db.query(PushSubscription).all()
        assert len(rows) == 1

    def test_subscribe_different_endpoints(self, client, auth_headers, db):
        client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=auth_headers)
        other = dict(SUBSCRIPTION, endpoint="https://push.example.com/user/def")
        client.post("/api/v1/push/subscribe", json=other, headers=auth_headers)
        assert db.query(PushSubscription).count() == 2

    def test_unsubscribe_removes_own(self, client, auth_headers, db):
        client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=auth_headers)
        body = {"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "", "auth": ""}}
        resp = client.request("DELETE", "/api/v1/push/subscribe", json=body, headers=auth_headers)
        assert resp.status_code == 200
        assert db.query(PushSubscription).count() == 0

    def test_unsubscribe_cannot_remove_others(self, client, regular_user, second_user, db):
        from tests.conftest import _auth
        owner = _auth(regular_user)
        intruder = _auth(second_user)
        client.post("/api/v1/push/subscribe", json=SUBSCRIPTION, headers=owner)
        body = {"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "", "auth": ""}}
        client.request("DELETE", "/api/v1/push/subscribe", json=body, headers=intruder)
        assert db.query(PushSubscription).count() == 1


class TestSendPush:
    def test_send_push_never_raises(self):
        # Sin suscripciones (y sin BD real en este proceso): debe tragar cualquier error
        send_push(99999, "Título", "Cuerpo", "/manga/1")
