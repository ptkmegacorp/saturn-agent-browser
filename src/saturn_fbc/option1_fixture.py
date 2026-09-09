"""Controlled option-1 fixture: disposable vault + loopback HTTP login."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

AUTH_ROOT = Path("~/projects/saturn-auth")
FBC_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = FBC_ROOT / "fixtures"

HANDLE = "Sites/127.0.0.1--alice--fixture"
USERNAME = "alice"
LABEL = "fixture"


def _ensure_auth_on_path() -> None:
    root = str(AUTH_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


class _LoginHandler(BaseHTTPRequestHandler):
    expected_user = USERNAME
    expected_password = ""
    login_html = ""
    logged_in_html = ""
    continue_html = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        cookie = self.headers.get("Cookie") or ""
        authed = "saturn_fixture_session=ok" in cookie
        if path in ("/", "/login"):
            return self._html(200, self.login_html)
        if path == "/session":
            if not authed:
                return self._html(401, self.login_html.replace("<h1>", "<p id=\"login-error\">Sign in required</p><h1>"))
            return self._html(200, self.logged_in_html)
        if path == "/continue":
            if not authed:
                return self._html(401, "<p id=\"login-error\">Sign in required</p>")
            return self._html(200, self.continue_html)
        self.send_error(404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path != "/session":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        fields = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        user = (fields.get("username") or [""])[0]
        password = (fields.get("password") or [""])[0]
        ok = secrets.compare_digest(user, self.expected_user) and secrets.compare_digest(
            password, self.expected_password
        )
        if not ok:
            return self._html(401, self.login_html.replace("<h1>", "<p id=\"login-error\">Invalid login</p><h1>"))
        body = self.logged_in_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", "saturn_fixture_session=ok; Path=/; HttpOnly")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FixtureLoginWorld:
    """Disposable KeePass + Auth HTTP + loopback login page for option-1 tests."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="option1-fixture-")
        self.root = Path(self.tmp.name)
        self.entry_password = secrets.token_urlsafe(18)
        self.master_password = secrets.token_hex(16)
        self.kdbx = self.root / "fixture.kdbx"
        self.key_file = self.root / "fixture.key"
        self.store_path = self.root / "requests.json"
        self.callers_dir = self.root / "callers"
        self.fbc_token = secrets.token_hex(32)
        self.pi_token = secrets.token_hex(32)
        self.auth_base = ""
        self.origin = ""
        self.login_url = ""
        self.continue_url = ""
        self._auth_server = None
        self._login_server: ThreadingHTTPServer | None = None
        self._other_server: ThreadingHTTPServer | None = None
        self.other_origin = ""
        self._threads: list[threading.Thread] = []
        self.handle = HANDLE

    def start(self, *, in_process_auth: bool = True) -> None:
        _ensure_auth_on_path()
        os.environ["AGENT_KDBX"] = str(self.kdbx)
        os.environ["AGENT_VAULT_KEY_FILE"] = str(self.key_file)
        os.environ.pop("SATURN_AUTH_FBC_TOKEN_FILE", None)
        from saturn_fbc.config import load_config

        load_config.cache_clear()
        load_config()
        self._create_vault()
        self._start_login_http()
        if in_process_auth:
            os.environ["SATURN_AUTH_FIXTURE_VAULT"] = "1"
            os.environ["SATURN_AUTH_FBC_TOKEN"] = self.fbc_token
            self._start_auth_http()
            os.environ["SATURN_AUTH_URL"] = self.auth_base
        else:
            os.environ.pop("SATURN_AUTH_FIXTURE_VAULT", None)
            os.environ.pop("SATURN_AUTH_FBC_TOKEN", None)

    def stop(self) -> None:
        if self._auth_server is not None:
            self._auth_server.stop()
        if self._login_server is not None:
            self._login_server.shutdown()
            self._login_server.server_close()
            self._login_server = None
        if self._other_server is not None:
            self._other_server.shutdown()
            self._other_server.server_close()
            self._other_server = None
        os.environ.pop("SATURN_AUTH_FIXTURE_VAULT", None)
        os.environ.pop("SATURN_AUTH_FBC_TOKEN", None)
        os.environ.pop("SATURN_AUTH_URL", None)
        os.environ.pop("AGENT_KDBX", None)
        os.environ.pop("AGENT_VAULT_KEY_FILE", None)
        from saturn_fbc.config import load_config

        load_config.cache_clear()
        self.tmp.cleanup()

    def __enter__(self) -> FixtureLoginWorld:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def contract(self, *, run_id: str = "run-fixture"):
        from saturn_fbc.contract import AuthorityContract, ContractMode, CredentialSpec

        return AuthorityContract(
            task_id="task-fixture",
            run_id=run_id,
            mode=ContractMode.DRAFT,
            subgoal="login",
            origin_allowlist=["127.0.0.1"],
            allowed_actions=["click", "type", "navigate"],
            credential_policy="existing_only",
            credential_spec=CredentialSpec(
                domain="127.0.0.1",
                username=USERNAME,
                label=LABEL,
                handle=self.handle,
            ),
            success_checks=["#logged-in"],
        )

    def approve(self, request_id: str, operator: str = "fixture-operator") -> dict:
        return self._auth_json(
            "POST",
            f"/v1/requests/{request_id}/approve",
            self.pi_token,
            {},
            operator=operator,
        )

    def deny(self, request_id: str, operator: str = "fixture-operator") -> dict:
        return self._auth_json(
            "POST",
            f"/v1/requests/{request_id}/deny",
            self.pi_token,
            {"reason": "fixture_deny"},
            operator=operator,
        )

    def wait_request(self, request_id: str, *, wait_sec: int = 300) -> dict:
        return self._auth_json(
            "GET",
            f"/v1/requests/{request_id}?wait=1&wait_sec={wait_sec}",
            self.fbc_token,
            None,
            timeout=wait_sec + 5,
        )

    def store_blob(self) -> str:
        if not self.store_path.is_file():
            return ""
        return self.store_path.read_text(encoding="utf-8")

    def secret_leaked(self, *blobs: str) -> bool:
        needle = self.entry_password
        return any(needle and needle in blob for blob in blobs)

    def _create_vault(self) -> None:
        self.key_file.write_text(self.master_password + "\n", encoding="utf-8")
        self.key_file.chmod(0o600)
        created = subprocess.run(
            ["keepassxc-cli", "db-create", "-q", "-p", str(self.kdbx)],
            input=f"{self.master_password}\n{self.master_password}\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            raise RuntimeError(created.stderr.strip() or created.stdout.strip() or "db-create failed")
        from saturn_fbc.broker.vault import create_entry_with_password

        create_entry_with_password(
            "127.0.0.1",
            USERNAME,
            LABEL,
            self.entry_password,
            url="http://127.0.0.1",
        )

    def _start_login_http(self) -> None:
        handler = type(
            "LoginHandlerBound",
            (_LoginHandler,),
            {
                "expected_user": USERNAME,
                "expected_password": self.entry_password,
                "login_html": (FIXTURES / "login.html").read_text(encoding="utf-8"),
                "logged_in_html": (FIXTURES / "logged-in.html").read_text(encoding="utf-8"),
                "continue_html": (FIXTURES / "logged-in-continue.html").read_text(encoding="utf-8"),
            },
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._login_server = server
        self._threads.append(thread)
        port = server.server_address[1]
        self.origin = f"http://127.0.0.1:{port}"
        self.login_url = f"{self.origin}/login"
        self.continue_url = f"{self.origin}/continue"
        other = ThreadingHTTPServer(("127.0.0.1", 0), _BlankHandler)
        other_thread = threading.Thread(target=other.serve_forever, daemon=True)
        other_thread.start()
        self._other_server = other
        self._threads.append(other_thread)
        self.other_origin = f"http://127.0.0.1:{other.server_address[1]}"

    def _start_auth_http(self) -> None:
        from saturn_auth.callers import Caller
        from saturn_auth.httpd import AuthHTTPServer
        from saturn_auth.service import AuthService
        from saturn_auth.store import AuthStore

        store = AuthStore(self.store_path)
        service = AuthService(store)
        callers = [
            Caller("fbc", "saturn-fbc", frozenset({
                "health", "create", "get_own", "cancel", "consume", "report",
            }), self.fbc_token),
            Caller("pi", "saturn-pi", frozenset({
                "health", "list", "get", "approve", "deny",
            }), self.pi_token),
        ]
        server = AuthHTTPServer(service, host="127.0.0.1", port=0, callers=callers)
        self.auth_base = server.bind()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._auth_server = server
        self._threads.append(thread)

    def _auth_json(
        self,
        method: str,
        path: str,
        token: str,
        payload: dict | None,
        *,
        operator: str | None = None,
        timeout: float = 10,
    ) -> dict:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        if operator:
            headers["X-Saturn-Operator"] = operator
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.auth_base}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"ok": False, "error": body}
            parsed["http_status"] = err.code
            return parsed


class _BlankHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        body = (
            b"<html><body><p id='other'>other origin</p>"
            b"<input id='password' type='password' autocomplete='current-password'>"
            b"</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
