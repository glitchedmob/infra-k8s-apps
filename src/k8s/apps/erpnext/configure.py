#!/usr/bin/env python3
"""Reconcile only the managed ERPNext login settings, using site DB credentials."""

import contextlib
import fcntl
import hmac
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


BENCH = Path("/home/frappe/frappe-bench")
SITES = BENCH / "sites"
SETTINGS = Path("/settings/settings.json")
ROOT_KEYS = {"root_password", "root_login", "mariadb_root_password", "mariadb_root_login"}


def environment():
    site = os.environ.get("SITE_NAME", "finances.levizitting.com")
    # Native file backups use shell commands. Do not accept shell metacharacters.
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", site) or ".." in site:
        raise ValueError("Invalid site name")
    url = os.environ.get("SITE_URL", "https://finances.levizitting.com").rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != site or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Invalid site URL")
    # Frappe gives these precedence over site_config.json. Never silently use them.
    if any(key.startswith("FRAPPE_DB_") for key in os.environ):
        raise ValueError("Database overrides are not supported")
    return {
        "site": site,
        "url": url,
        "db_host": os.environ.get("DB_HOST", "erpnext-db"),
        "db_port": int(os.environ.get("DB_PORT", "3306")),
        "db_name": os.environ.get("DB_NAME", "erpnext"),
        "redis_cache": os.environ.get("REDIS_CACHE", "redis://erpnext-cache:6379"),
        "redis_queue": os.environ.get("REDIS_QUEUE", "redis://erpnext-queue:6379"),
        "socketio_port": int(os.environ.get("SOCKETIO_PORT", "9000")),
    }


def read_json(path):
    with path.open() as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Invalid JSON object")
    return value


def atomic_write(path, content, mode=0o600):
    """Replace a complete file on the shared volume, never truncate it in place."""
    fd, temporary = tempfile.mkstemp(prefix=".erpnext-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_settings():
    from cryptography.fernet import Fernet

    settings = read_json(SETTINGS)
    for key in ("adminPassword", "databasePassword", "encryptionKey"):
        if not isinstance(settings.get(key), str) or not settings[key]:
            raise ValueError("Missing managed credential")
    Fernet(settings["encryptionKey"].encode("ascii"))
    oidc = settings["oidc"]
    for key in ("clientId", "clientSecret", "issuerUrl"):
        if not isinstance(oidc.get(key), str) or not oidc[key]:
            raise ValueError("Missing OIDC setting")
    issuer = urlsplit(oidc["issuerUrl"])
    if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.password or issuer.query or issuer.fragment:
        raise ValueError("Invalid OIDC issuer")
    social = settings["socialLogin"]
    if social["providerId"] != "zitadel" or social["providerName"] != "Zitadel" or social["signUps"] != "Deny":
        raise ValueError("Unexpected managed provider")
    if settings["disableSignup"] is not True or social["scope"] != "openid profile email":
        raise ValueError("Unexpected signup policy or scope")
    for key in ("authorizeUrl", "tokenUrl", "userinfoUrl"):
        endpoint = social[key]
        parsed = urlsplit(endpoint)
        if not endpoint.startswith("/") or endpoint.startswith("//") or parsed.netloc or parsed.scheme or parsed.fragment:
            raise ValueError("Invalid OIDC endpoint")
    return settings


def incomplete_marker(env):
    return SITES / (".erpnext-" + env["site"] + ".incomplete")


@contextlib.contextmanager
def deployment_lock():
    """All three scripts share a persistent advisory lock on the RWX volume."""
    fd = os.open(SITES / ".erpnext-bootstrap.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextlib.contextmanager
def quiet_output():
    """Discard upstream output, including subprocess output and exception details."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    previous_logging = logging.root.manager.disable
    previous_streaming = os.environ.get("FRAPPE_STREAM_LOGGING")
    os.environ["FRAPPE_STREAM_LOGGING"] = "1"
    logging.disable(sys.maxsize)
    try:
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for target, descriptor in zip((1, 2), saved):
            os.dup2(descriptor, target)
            os.close(descriptor)
        logging.disable(previous_logging)
        if previous_streaming is None:
            os.environ.pop("FRAPPE_STREAM_LOGGING", None)
        else:
            os.environ["FRAPPE_STREAM_LOGGING"] = previous_streaming


def site_config(env, settings=None):
    """Reject partial sites and credential drift before any managed writes."""
    from cryptography.fernet import Fernet

    if incomplete_marker(env).exists():
        raise ValueError("Incomplete bootstrap requires operator review")
    config = read_json(SITES / env["site"] / "site_config.json")
    common_path = SITES / "common_site_config.json"
    common = read_json(common_path) if common_path.exists() else {}
    merged = common | config
    if ROOT_KEYS.intersection(merged):
        raise ValueError("Root credentials must not be in site configuration")
    if merged.get("extra_config"):
        raise ValueError("External configuration hooks are not supported")
    for key in ("db_name", "db_password", "encryption_key"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError("Incomplete site configuration")
    Fernet(config["encryption_key"].encode("ascii"))
    if (
        merged.get("db_type", "mariadb") != "mariadb"
        or merged.get("db_host", "127.0.0.1") != env["db_host"]
        or int(merged.get("db_port", 3306)) != env["db_port"]
        or merged.get("db_socket")
        or config["db_name"] != env["db_name"]
        or merged.get("db_user", config["db_name"]) != env["db_name"]
    ):
        raise ValueError("Site database connection differs from deployment")
    if settings is not None:
        for actual, expected in (
            (config["db_password"], settings["databasePassword"]),
            (config["encryption_key"], settings["encryptionKey"]),
        ):
            if not hmac.compare_digest(actual.encode(), expected.encode()):
                raise ValueError("Site credentials differ from deployment")
    return config


@contextlib.contextmanager
def connected_site(env, settings=None, require_erpnext=True):
    import frappe

    site_config(env, settings)
    os.chdir(SITES)
    try:
        frappe.init(env["site"], sites_path=str(SITES))
        frappe.connect()
        apps = frappe.get_installed_apps()
        if "frappe" not in apps or (require_erpnext and "erpnext" not in apps):
            raise ValueError("Site installation is incomplete")
        if not frappe.db.exists("User", "Administrator"):
            raise ValueError("Site installation is incomplete")
        yield frappe
    except BaseException:
        if getattr(frappe.local, "db", None):
            frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


@contextlib.contextmanager
def private_database_commands():
    """Keep native Frappe import/dump passwords out of child process argv.

    Frappe 16 get_command normally emits --password. Its native callers import
    the function at call time, so scope this adapter to this bootstrap process.
    """
    import frappe
    import frappe.database

    original = frappe.database.get_command
    with tempfile.TemporaryDirectory(prefix="erpnext-client-", dir="/tmp") as directory:
        def get_command(socket=None, host=None, port=None, user=None, password=None,
                        db_name=None, extra=None, dump=False):
            if frappe.conf.db_type != "mariadb":
                raise ValueError("Only MariaDB is supported")
            executable, arguments, name = original(
                socket=socket, host=host, port=port, user=user, password=None,
                db_name=db_name, extra=extra, dump=dump,
            )
            if password is not None:
                if "\0" in password:
                    raise ValueError("Invalid database credential")
                escaped = password.replace("\\", "\\\\").replace('"', '\\"')
                escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
                fd, path = tempfile.mkstemp(prefix="client-", suffix=".cnf", dir=directory)
                with os.fdopen(fd, "w") as stream:
                    stream.write('[client]\npassword="' + escaped + '"\n')
                arguments.insert(0, "--defaults-extra-file=" + path)
            return executable, arguments, name

        frappe.database.get_command = get_command
        try:
            yield
        finally:
            frappe.database.get_command = original


def reconcile_locked(env, settings):
    """Caller must hold deployment_lock and quiet_output."""
    with connected_site(env, settings) as frappe:
        provider = settings["socialLogin"]
        oidc = settings["oidc"]
        values = {
            "social_login_provider": "Custom",
            "provider_name": provider["providerName"],
            "enable_social_login": 1,
            "client_id": oidc["clientId"],
            "base_url": oidc["issuerUrl"].rstrip("/"),
            "custom_base_url": 1,
            "authorize_url": provider["authorizeUrl"],
            "access_token_url": provider["tokenUrl"],
            "api_endpoint": provider["userinfoUrl"],
            "redirect_url": "/api/method/frappe.integrations.oauth2_logins.custom/zitadel",
            "auth_url_data": json.dumps({"response_type": "code", "scope": provider["scope"]}, sort_keys=True),
            "user_id_property": "sub",
            "sign_ups": "Deny",
        }
        exists = frappe.db.exists("Social Login Key", "zitadel")
        doc = frappe.get_doc("Social Login Key", "zitadel") if exists else frappe.new_doc("Social Login Key")
        # These are set-only-once fields. Refuse to take over a different key.
        if exists and (doc.social_login_provider != "Custom" or doc.provider_name != "Zitadel"):
            raise ValueError("Managed provider identity conflict")
        changed = False
        for key, value in values.items():
            if doc.get(key) != value:
                doc.set(key, value)
                changed = True
        if not exists or not hmac.compare_digest(
            (doc.get_password("client_secret", raise_exception=False) or "").encode(),
            oidc["clientSecret"].encode(),
        ):
            doc.client_secret = oidc["clientSecret"]
            changed = True
        if not exists:
            doc.insert(ignore_permissions=True)
            if doc.name != "zitadel":
                raise ValueError("Unexpected managed provider identity")
        elif changed:
            doc.save(ignore_permissions=True)
        website = frappe.get_single("Website Settings")
        if website.disable_signup != 1:
            website.disable_signup = 1
            website.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.clear_cache()


def configure_site():
    """Importable entry point. Never expose upstream exception text or secrets."""
    try:
        with quiet_output(), deployment_lock():
            env = environment()
            reconcile_locked(env, load_settings())
    except BaseException:
        raise RuntimeError("ERPNext configuration failed; check prerequisites and credential consistency") from None


if __name__ == "__main__":
    try:
        configure_site()
    except BaseException:
        sys.stderr.write("ERPNext configuration failed; check prerequisites and credential consistency.\n")
        sys.exit(1)
