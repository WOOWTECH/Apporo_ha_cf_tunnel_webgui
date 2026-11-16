"""Guided Apporo account and Security Access connection.

Same flow and platform API as the upstream WOOW add-on
(Woow_ha_cloudflare_tunnel_webgui 1.1.x), pointed at the Apporo platform
(www.apporo.ai): OAuth device authorization, per-route Access review, tunnel
binding, anonymous external checks and release. Only the add-on backend
handles OAuth tokens or tunnel credentials. The browser receives navigation
URLs and non-secret summaries through Ingress.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
import asyncio
from pathlib import Path
from urllib.parse import urlencode, urlparse

import aiohttp
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query

from ..instances import supervisor
from .. import metrics
from ..external_probe import probe as probe_hostname
from ..supervisor import SupervisorError

router = APIRouter(prefix="/api/paas", tags=["paas"])

PAAS_BASE_URL = "https://www.apporo.ai"
# Platform contract, not branding: the Apporo platform knows this connector by
# the same OAuth client id as the WOOW platform does, so the id stays as is.
CLIENT_ID = "woow-ha-smart-home"
# Shown in the Apporo portal as the device that holds the tunnel binding.
INSTANCE_LABEL = "Apporo CF Tunnel Web (HA add-on)"
SCOPES = "workspace:read security-access:read security-access:tunnel"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_pending: dict = {}
_connect_lock = asyncio.Lock()
_PROCESS_RUN_ID = str(uuid.uuid4())


def _api_base() -> str:
    # Override is for isolated contract tests and staging images. The shipped
    # add-on uses the fixed Apporo production origin, never a browser-provided
    # URL.
    return os.environ.get("PAAS_API_BASE", PAAS_BASE_URL).rstrip("/")


def _portal_path(workspace_id: int, access_id: int | None = None, tab: str = "overview") -> str:
    # The Apporo portal keeps the platform's /woow#/ client routes.
    if access_id is None:
        return f"{PAAS_BASE_URL}/woow#/workspace/{workspace_id}"
    if tab not in ("overview", "application", "access"):
        raise ValueError("Unsupported PaaS tab")
    return f"{PAAS_BASE_URL}/woow#/workspace/{workspace_id}/security-access/{access_id}/{tab}"


async def _form_post(path: str, form: dict) -> tuple[int, dict]:
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{_api_base()}{path}", data=form) as response:
                payload = await response.json(content_type=None)
                return response.status, payload if isinstance(payload, dict) else {}
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, "Failed to connect to the Apporo platform. Please try again later.") from exc


async def _access_token() -> str:
    state = _state()
    token = state.get("access_token")
    if token and state.get("expires_at", 0) > time.time() + 60:
        return token
    refresh = state.get("refresh_token")
    if not refresh:
        raise HTTPException(401, "Connect your Apporo account first.")
    status, payload = await _form_post(
        "/oauth2/token",
        {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": CLIENT_ID},
    )
    if status != 200 or not payload.get("access_token"):
        raise HTTPException(401, "Your Apporo authorization has expired. Please authorize again.")
    state.update(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or refresh,
        expires_at=time.time() + max(30, int(payload.get("expires_in") or 3600)),
    )
    _save_state(state)
    return state["access_token"]


async def _request(method: str, path: str) -> dict:
    token = await _access_token()
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, f"{_api_base()}{path}", headers={"Authorization": f"Bearer {token}"}
            ) as response:
                payload = await response.json(content_type=None)
                if response.status == 401:
                    raise HTTPException(401, "Your Apporo authorization has expired. Please authorize again.")
                if response.status == 403:
                    raise HTTPException(403, "You need to be an owner or admin of this workspace. "
                                             "Check your role in the Apporo portal.")
                if response.status == 409:
                    raise HTTPException(409, "This service is already bound to another device. "
                                             "Release that binding in the Apporo portal first.")
                if response.status >= 400 or not isinstance(payload, dict):
                    raise HTTPException(502, "The Apporo platform could not return the service right now. "
                                             "Please try again later.")
                return payload
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, "Failed to connect to the Apporo platform. Please try again later.") from exc


def _state_path() -> Path:
    return Path(os.environ.get("PAAS_LINK_STATE", "/data/paas-link.json"))


def _state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _save_state(value: dict) -> None:
    target = _state_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temporary = tempfile.mkstemp(prefix=".paas-link-", dir=target.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@router.get("/bootstrap")
async def bootstrap() -> dict:
    state = _state()
    return {
        "authorized": bool(state.get("refresh_token")),
        "portal_url": f"{PAAS_BASE_URL}/woow#/workspaces",
        "connection": state.get("connection"),
        "release_pending": bool(state.get("release_pending")),
    }


@router.post("/authorization")
async def start_authorization() -> dict:
    status, payload = await _form_post(
        "/oauth2/device_authorization", {"client_id": CLIENT_ID, "scope": SCOPES}
    )
    if status != 200:
        raise HTTPException(502, "The Apporo platform could not start the authorization. "
                                 "Please try again later.")
    device_code = payload.get("device_code")
    user_code = payload.get("user_code")
    verification_url = payload.get("verification_uri_complete") or payload.get("verification_uri")
    api_origin = urlparse(_api_base())
    verify_origin = urlparse(verification_url or "")
    if not (
        isinstance(device_code, str) and device_code
        and isinstance(user_code, str) and user_code
        and verify_origin.scheme == api_origin.scheme
        and verify_origin.netloc == api_origin.netloc
        and verify_origin.path == "/device"
    ):
        raise HTTPException(502, "The Apporo platform returned an invalid authorization response.")
    interval = max(5, int(payload.get("interval") or 5))
    expires_in = min(900, max(30, int(payload.get("expires_in") or 900)))
    _pending.clear()
    _pending.update(
        device_code=device_code,
        interval=interval,
        next_poll=time.monotonic() + interval,
        expires=time.monotonic() + expires_in,
    )
    return {
        "user_code": user_code,
        "verification_url": verification_url,
        "expires_in": expires_in,
        "interval": interval,
    }


@router.get("/authorization/status")
async def authorization_status() -> dict:
    if not _pending:
        return {"status": "authorized" if _state().get("refresh_token") else "idle"}
    now = time.monotonic()
    if now >= _pending["expires"]:
        _pending.clear()
        return {"status": "expired"}
    if now < _pending["next_poll"]:
        return {"status": "waiting"}
    _pending["next_poll"] = now + _pending["interval"]
    status, payload = await _form_post(
        "/oauth2/token",
        {"grant_type": DEVICE_GRANT, "device_code": _pending["device_code"], "client_id": CLIENT_ID},
    )
    if status != 200:
        error = payload.get("error")
        if error == "slow_down":
            _pending["interval"] += 5
            _pending["next_poll"] = now + _pending["interval"]
            return {"status": "waiting", "interval": _pending["interval"]}
        if error == "authorization_pending":
            return {"status": "waiting", "interval": _pending["interval"]}
        _pending.clear()
        return {"status": "denied" if error == "access_denied" else "expired"}
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
        _pending.clear()
        raise HTTPException(502, "The Apporo authorization result was incomplete. Please authorize again.")
    state = _state()
    state.update(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=time.time() + max(30, int(payload.get("expires_in") or 3600)),
    )
    _save_state(state)
    _pending.clear()
    return {"status": "authorized"}


@router.post("/authorization/revoke")
async def revoke_authorization() -> dict:
    state = _state()
    if state.get("connection") or state.get("release_pending"):
        raise HTTPException(409, "Stop the local connection and finish releasing the remote binding first.")
    refresh_token = state.get("refresh_token")
    if refresh_token:
        status, _ = await _form_post(
            "/oauth2/revoke", {"token": refresh_token, "client_id": CLIENT_ID}
        )
        if status != 200:
            raise HTTPException(502, "The Apporo platform has not confirmed the revocation yet. "
                                     "Please try again later.")
    for key in ("access_token", "refresh_token", "expires_at"):
        state.pop(key, None)
    _pending.clear()
    _save_state(state)
    return {"revoked": True}


@router.get("/workspaces")
async def workspaces() -> dict:
    data = await _request("GET", "/api/security-access/workspaces")
    return {"workspaces": [
        {"id": item["id"], "name": item["name"], "portal_url": _portal_path(item["id"])}
        for item in data.get("workspaces", [])
    ]}


@router.get("/workspaces/{workspace_id}/accesses")
async def accesses(workspace_id: int) -> dict:
    data = await _request("GET", f"/api/security-access/workspaces/{workspace_id}/accesses")
    return {"accesses": [
        {"id": item["id"], "name": item["name"], "state": item["state"],
         "plan_name": item.get("plan_name"), "portal_url": _portal_path(workspace_id, item["id"])}
        for item in data.get("accesses", [])
    ]}


def _review(access: dict) -> dict:
    issues: list[str] = []
    if access.get("state") != "active":
        issues.append("The service is not active yet or has been suspended. "
                      "Check its subscription in the Apporo portal.")
    subscription = access.get("subscription")
    if not isinstance(subscription, dict) or subscription.get("state") != "in_progress":
        issues.append("The subscription is not valid. Start or renew it in the Apporo portal.")
    if not access.get("tunnel_id"):
        issues.append("The tunnel has not been created yet. Finish the deployment in the Apporo portal.")
    connection = _state().get("connection") or {}
    if access.get("binding_state") != "unbound" and connection.get("access_id") != access.get("id"):
        issues.append("The service is bound to another device. "
                      "Release that binding in the Apporo portal first.")
    if access.get("binding_conflict") or (access.get("connector_count") or 0) > 1:
        issues.append("More than one connector was detected. Resolve the device-change conflict first.")
    routes = access.get("routes")
    if not isinstance(routes, list) or not routes:
        issues.append("No public hostname has been created yet. Add a route in the Apporo portal.")
        routes = []
    safe_routes = []
    public_routes = []
    for route in routes:
        host = route.get("hostname") or "Unnamed route"
        valid_target = bool(route.get("hostname")) and bool(route.get("service_url"))
        if not valid_target:
            issues.append(f"{host}: the public hostname or the internal service URL is missing. "
                          "Complete it in the Apporo portal.")
        public = route.get("is_protected") is False
        protected = False
        awaiting_publication = False
        if public:
            public_routes.append(host)
            if route.get("access_protection_lost") is not False:
                issues.append(f"{host}: the Access state has not settled yet. Check it in the Apporo portal.")
            # PaaS parks the origin at 503 during an unprotect transition.
            # A fresh connector may be required before it can release the
            # route, so allow that explicit public intent to be claimed.
            awaiting_publication = route.get("access_publish_pending") is True
            if route.get("access_publish_pending") is not True and route.get("access_publish_pending") is not False:
                issues.append(f"{host}: the publication state on the Apporo platform could not be confirmed. "
                              "Reload the service.")
        else:
            if route.get("is_protected") is not True:
                issues.append(f"{host}: the access mode could not be confirmed. "
                              "Check the route again in the Apporo portal.")
            if isinstance(subscription, dict) and subscription.get("ac_max_access_seats") == 0:
                issues.append(f"{host}: Access is enabled, but the plan has no Access seats. "
                              "Add seats, or turn off Access for this route in the Apporo portal.")
            policies = route.get("access_policies")
            allow = isinstance(policies, list) and any(
                p.get("decision") == "allow" and any(
                    rule.get("rule_type") in ("email_list", "email_domain") and rule.get("rule_value")
                    for rule in p.get("include", []))
                for p in policies
            )
            broad_access = not isinstance(policies, list) or any(
                p.get("decision") == "bypass" or (
                    p.get("decision") == "allow" and any(
                        rule.get("rule_type") in ("everyone", "ip_range", "country")
                        for rule in p.get("include", [])
                    )
                ) for p in (policies if isinstance(policies, list) else [])
            )
            login_ready = route.get("login_google") is True or route.get("login_email_otp") is True
            if not login_ready:
                issues.append(f"{host}: no login method is selected. "
                              "Select Email OTP or Google in the Apporo portal.")
            # A protected route still needs explicit access policy and login.
            declared = (
                valid_target and route.get("is_protected") is True
                and route.get("access_protection_lost") is False
                and not route.get("access_unresolved_idp_types")
                and login_ready and allow and not broad_access
            )
            protected = (
                declared and route.get("access_configuration_ready") is True
                and route.get("access_publish_pending") is False
            )
            # PaaS parks a protected origin at 503 until a live connector
            # enables Access publication. Do not deadlock that transition.
            awaiting_publication = (
                declared and not protected
                and route.get("access_publish_pending") is True
            )
            if not protected and not awaiting_publication:
                issues.append(f"{host}: Access protection or the allow list is not confirmed yet. "
                              "Set it up in the Apporo portal.")
        safe_routes.append({
            "hostname": route.get("hostname"), "service_url": route.get("service_url"),
            "public": public, "protected": protected,
            "awaiting_publication": awaiting_publication,
        })
    workspace_id = access.get("workspace_id")
    access_id = access.get("id")
    summary = {
        "id": access_id, "workspace_id": workspace_id, "name": access.get("name"), "state": access.get("state"),
        "subscription": {key: subscription.get(key) for key in (
            "state", "plan_name", "ac_max_access_seats", "ac_used_access_seats",
        )} if isinstance(subscription, dict) else None,
        "binding_state": access.get("binding_state"), "bound_instance_label": access.get("bound_instance_label"),
        "connector_count": access.get("connector_count"), "routes": safe_routes,
    }
    return {
        "ready": not issues,
        "issues": issues,
        "public_routes": public_routes,
        "awaiting_publication": any(r["awaiting_publication"] for r in safe_routes),
        "access": summary,
        "portal_access_url": _portal_path(workspace_id, access_id, "access"),
        "portal_routes_url": _portal_path(workspace_id, access_id, "application"),
    }


@router.get("/accesses/{access_id}/review")
async def review_access(access_id: int) -> dict:
    data = await _request("GET", f"/api/security-access/accesses/{access_id}")
    access = data.get("access")
    if not isinstance(access, dict) or access.get("id") != access_id:
        raise HTTPException(502, "The Apporo platform returned invalid service data.")
    return _review(access)


@router.get("/connection/status")
async def connection_status(probe: bool = Query(default=False)) -> dict:
    connection = _state().get("connection")
    if not connection:
        return {"connected": False}
    access_id = connection["access_id"]
    data = await _request("GET", f"/api/security-access/accesses/{access_id}/status")
    access = data.get("access")
    if not isinstance(access, dict) or access.get("id") != access_id:
        raise HTTPException(502, "The Apporo platform returned an invalid connection status.")
    reviewed = _review(access)
    tunnel = await metrics.tunnel_status()
    external = []
    if probe:
        external = await asyncio.gather(*(
            probe_hostname(route["hostname"])
            for route in reviewed["access"]["routes"]
        ))
    return {
        "connected": True,
        "subscription": reviewed["access"]["subscription"],
        "access_ready": reviewed["ready"] and not reviewed["public_routes"] and not reviewed["awaiting_publication"],
        "service_ready": reviewed["ready"],
        "public_routes": reviewed["public_routes"],
        "awaiting_publication": reviewed["awaiting_publication"],
        "issues": reviewed["issues"],
        "routes": reviewed["access"]["routes"],
        "tunnel_status": tunnel.status,
        "connector_count": access.get("connector_count"),
        "binding_conflict": bool(access.get("binding_conflict")),
        "checked_at": time.time(),
        "external_status": "checked" if probe else "not_checked",
        "external": external,
    }


@router.post("/accesses/{access_id}/connect")
async def connect_access(
    access_id: int, background: BackgroundTasks,
    allow_public_routes: bool = Body(default=False, embed=True),
) -> dict:
    async with _connect_lock:
        review = await review_access(access_id)
        if not review["ready"]:
            raise HTTPException(409, " ".join(review["issues"]))
        if review["public_routes"] and not allow_public_routes:
            raise HTTPException(409, "This service has public hostnames that are not protected by "
                                     "Cloudflare Access. Confirm them, then connect again.")
        state = _state()
        if state.get("release_pending"):
            raise HTTPException(409, "Finish releasing the previous service's binding, then connect again.")
        prior = state.get("connection") or {}
        if prior and prior.get("access_id") != access_id:
            raise HTTPException(409, "Disconnect the current service before you choose another one.")
        try:
            current_options = await supervisor.get_options()
        except SupervisorError as exc:
            raise HTTPException(502, "Could not read the add-on configuration. Please try again later.") from exc
        if current_options.get("tunnel_token") and not prior:
            raise HTTPException(409, "A manually configured tunnel token is already set. "
                                     "Review and remove it on the Config page first.")

        instance_uid = state.get("instance_uid") or str(uuid.uuid4())
        state["instance_uid"] = instance_uid
        _save_state(state)  # Persist before claim; retries must reuse the UID.
        query = urlencode({"instance_uid": instance_uid, "instance_label": INSTANCE_LABEL})
        token_path = f"/api/security-access/accesses/{access_id}/tunnel-token?{query}"
        release_path = f"/api/security-access/accesses/{access_id}/tunnel-binding?{urlencode({'instance_uid': instance_uid})}"
        credential = await _request("GET", token_path)
        tunnel_token = credential.get("tunnel_token")
        if not isinstance(tunnel_token, str) or not tunnel_token:
            if not prior:
                await _release_after_failed_connect(release_path, access_id)
            raise HTTPException(502, "The Apporo platform did not return a valid tunnel credential. "
                                     "Check whether a binding is still waiting to be released.")
        options = dict(current_options)
        options["tunnel_token"] = tunnel_token
        token_installed = False
        try:
            await supervisor.set_options(options)
            token_installed = True
            state["connection"] = {
                "access_id": access_id,
                "workspace_id": review["access"]["workspace_id"],
                "name": review["access"]["name"],
                "tunnel_id": credential.get("tunnel_id"),
            }
            _save_state(state)
        except (SupervisorError, OSError) as exc:
            if token_installed:
                try:
                    await supervisor.set_options(current_options)
                except SupervisorError as rollback_error:
                    # The token may still be installed. Keep PaaS bound so a
                    # second machine cannot claim it while this add-on may run.
                    raise HTTPException(
                        502, "The local settings could not be restored, so the remote binding is kept. "
                             "Check the add-on configuration and whether the add-on is running first."
                    ) from rollback_error
            if not prior:
                await _release_after_failed_connect(release_path, access_id)
            raise HTTPException(502, "The add-on configuration could not be written. Please try again; "
                                     "if it still fails, check the binding in the Apporo portal.") from exc
        background.add_task(supervisor.restart_self)
        return {"connected": True, "restarting": True, "connection": state["connection"]}


async def _release_after_failed_connect(path: str, access_id: int) -> None:
    try:
        await _request("DELETE", path)
    except HTTPException:
        # The user must see a warning if remote release cannot be confirmed.
        state = _state()
        state["release_pending"] = True
        state["pending_release_access_id"] = access_id
        _save_state(state)


@router.post("/disconnect")
async def disconnect(background: BackgroundTasks) -> dict:
    async with _connect_lock:
        state = _state()
        if not state.get("connection"):
            raise HTTPException(409, "There is no Apporo connection to disconnect.")
        try:
            options = await supervisor.get_options()
            state["release_pending"] = True
            # Saving options does not stop the current cloudflared process.
            # A release is safe only after this add-on process has restarted.
            state["stop_requested_by"] = _PROCESS_RUN_ID
            _save_state(state)
            # Clearing every local route prevents an old Local config from
            # starting a different public tunnel during the restart.
            options.pop("tunnel_token", None)
            options.update(external_hostname="", additional_hosts=[], nginx_proxy_manager=False)
            options.pop("catch_all_service", None)
            await supervisor.set_options(options)
        except (SupervisorError, OSError) as exc:
            raise HTTPException(502, "Could not stop the local tunnel. "
                                     "The remote binding is kept; please try again.") from exc
        background.add_task(supervisor.restart_self)
        return {"stopping": True, "release_pending": True}


@router.post("/disconnect/finish")
async def finish_disconnect() -> dict:
    async with _connect_lock:
        state = _state()
        connection = state.get("connection") or {}
        if not state.get("release_pending"):
            return {"released": True}
        access_id = state.get("pending_release_access_id") or connection.get("access_id")
        if not access_id:
            raise HTTPException(409, "The binding to release is unknown. Check it manually in the Apporo portal.")
        try:
            options = await supervisor.get_options()
        except SupervisorError as exc:
            raise HTTPException(502, "Could not confirm that the local tunnel has stopped. "
                                     "Try releasing the binding again later.") from exc
        if options.get("tunnel_token"):
            raise HTTPException(409, "A local tunnel token is still installed. Stop the local connection first.")
        if state.get("stop_requested_by"):
            if state["stop_requested_by"] == _PROCESS_RUN_ID:
                raise HTTPException(409, "Waiting for the add-on to restart and the tunnel to stop. "
                                         "Please try again shortly.")
            if (await metrics.tunnel_status()).metrics_reachable:
                raise HTTPException(409, "The tunnel process is still running, "
                                         "so the remote binding is not released yet.")
        instance_uid = state.get("instance_uid")
        if not instance_uid:
            raise HTTPException(409, "The original device ID is missing. "
                                     "Release the binding in the Apporo portal.")
        path = f"/api/security-access/accesses/{access_id}/tunnel-binding?{urlencode({'instance_uid': instance_uid})}"
        await _request("DELETE", path)
        state.pop("connection", None)
        state.pop("release_pending", None)
        state.pop("pending_release_access_id", None)
        state.pop("stop_requested_by", None)
        _save_state(state)
        return {"released": True}


async def reconcile_pending_disconnect() -> None:
    """Complete a previously requested release after the add-on restarts."""
    if not _state().get("release_pending"):
        return
    try:
        await finish_disconnect()
    except HTTPException:
        # Keep release_pending on disk so the UI can offer a retry.
        pass
