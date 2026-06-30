from app.connectors.common.auth import AuthConfig


def test_auth_basic():
    a = AuthConfig(auth_type="basic", credentials={"username": "alice", "password": "s3cr3t"})
    assert a.auth_type == "basic"
    assert a.get("username") == "alice"
    assert a.get("password") == "s3cr3t"


def test_auth_api_key():
    a = AuthConfig(auth_type="api_key", credentials={"key": "ck_abc", "secret": "cs_xyz"})
    assert a.get("key") == "ck_abc"
    assert a.get("secret") == "cs_xyz"


def test_auth_none():
    a = AuthConfig(auth_type="none")
    assert a.credentials == {}
    assert a.get("anything") is None


def test_auth_get_missing_key_returns_default():
    a = AuthConfig(auth_type="basic", credentials={"username": "bob"})
    assert a.get("password") is None
    assert a.get("password", "fallback") == "fallback"


def test_auth_oauth2():
    a = AuthConfig(
        auth_type="oauth2",
        credentials={
            "access_token": "tok_abc",
            "refresh_token": "ref_xyz",
            "expires_at": 9999999999.0,
        },
    )
    assert a.get("access_token") == "tok_abc"
    assert a.get("expires_at") == 9999999999.0
