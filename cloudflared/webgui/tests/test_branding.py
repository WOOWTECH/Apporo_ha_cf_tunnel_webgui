"""What makes this fork Apporo's: the platform it calls, the device label it
registers there, the platform contract it keeps unchanged, and messages in English.
"""
import ast
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.main import app
from backend.routers import paas

BACKEND = Path(__file__).resolve().parent.parent / "backend"
# CJK ideographs, plus CJK and full-width punctuation such as ，；：。
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


def _sources():
    return sorted(BACKEND.rglob("*.py"))


def _strings(node):
    return [part for part in ast.walk(node)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)]


def _user_messages():
    """The literal parts of every HTTPException detail and review issue."""
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "HTTPException":
                parts = node.args[1:] + [k.value for k in node.keywords if k.arg == "detail"]
            elif (isinstance(func, ast.Attribute) and func.attr == "append"
                  and isinstance(func.value, ast.Name) and func.value.id == "issues"):
                parts = node.args
            else:
                continue
            for part in parts:
                for constant in _strings(part):
                    yield path, constant


def _where(path, node):
    return f"{path.relative_to(BACKEND.parent)}:{node.lineno}: {node.value[:60]!r}"


@pytest.fixture()
def no_pending_authorization():
    yield
    paas._pending.clear()


def test_platform_is_apporo(monkeypatch):
    monkeypatch.delenv("PAAS_API_BASE", raising=False)
    assert paas.PAAS_BASE_URL == "https://www.apporo.ai"
    assert paas._api_base() == "https://www.apporo.ai"
    assert paas._portal_path(7) == "https://www.apporo.ai/woow#/workspace/7"
    assert paas.INSTANCE_LABEL == "Apporo CF Tunnel Web (HA add-on)"
    assert app.title == "Apporo CF Tunnel Web"


def test_oauth_contract_is_the_platform_one():
    # The Apporo platform knows this connector by the same client id as WOOW's.
    assert paas.CLIENT_ID == "woow-ha-smart-home"
    assert paas.SCOPES == "workspace:read security-access:read security-access:tunnel"
    assert paas.DEVICE_GRANT == "urn:ietf:params:oauth:grant-type:device_code"


@pytest.mark.asyncio
@pytest.mark.parametrize("verification,accepted", [
    ("https://www.apporo.ai/device?user_code=ABCD-EFGH", True),
    ("https://aiot.woowtech.io/device?user_code=ABCD-EFGH", False),
    ("https://www.apporo.ai.evil.test/device?user_code=ABCD-EFGH", False),
])
async def test_device_page_must_be_on_the_apporo_platform(
        monkeypatch, no_pending_authorization, verification, accepted):
    monkeypatch.delenv("PAAS_API_BASE", raising=False)

    async def fake_post(path, form):
        assert path == "/oauth2/device_authorization"
        return 200, {"device_code": "PRIVATE_DEVICE_CODE", "user_code": "ABCD-EFGH",
                     "verification_uri_complete": verification, "expires_in": 900, "interval": 5}

    monkeypatch.setattr(paas, "_form_post", fake_post)
    if accepted:
        assert (await paas.start_authorization())["verification_url"] == verification
    else:
        with pytest.raises(HTTPException) as info:
            await paas.start_authorization()
        assert info.value.status_code == 502


def test_backend_strings_are_english():
    found = [_where(path, node) for path in _sources()
             for node in _strings(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
             if CJK.search(node.value)]
    assert not found, "\n".join(found)


def test_messages_name_apporo_not_paas_or_woow():
    messages = list(_user_messages())
    # The scan must see the messages at all, or it would pass vacuously.
    assert any(node.value == "Connect your Apporo account first." for _, node in messages)
    found = [_where(path, node) for path, node in messages
             if re.search(r"PaaS|WOOW|Woow", node.value)]
    assert not found, "\n".join(found)


def test_backend_never_names_the_woow_platform():
    hits = [str(path.relative_to(BACKEND.parent)) for path in _sources()
            if "woowtech.io" in path.read_text(encoding="utf-8")]
    assert not hits
