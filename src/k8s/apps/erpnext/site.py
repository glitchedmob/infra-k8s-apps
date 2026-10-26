#!/usr/bin/env python3
"""One-shot site bootstrap/migration hook. Never force, reinstall, or rotate keys."""

import os
import re
import subprocess
import sys

from configure import (
    BENCH,
    ROOT_KEYS,
    SITES,
    atomic_write,
    connected_site,
    deployment_lock,
    environment,
    incomplete_marker,
    load_settings,
    private_database_commands,
    quiet_output,
    read_json,
    reconcile_locked,
    site_config,
    write_json,
)


def configure_bench(env):
    path = SITES / "common_site_config.json"
    common = read_json(path) if path.exists() else {}
    if ROOT_KEYS.intersection(common) or common.get("extra_config"):
        raise ValueError("Unsafe common configuration")
    common.update({
        "db_host": env["db_host"],
        "db_port": env["db_port"],
        "db_type": "mariadb",
        "redis_cache": env["redis_cache"],
        "redis_queue": env["redis_queue"],
        "redis_socketio": env["redis_queue"],
        "socketio_port": env["socketio_port"],
    })
    write_json(path, common)
    apps_path = SITES / "apps.txt"
    apps = apps_path.read_text().splitlines() if apps_path.exists() else []
    for app in ("frappe", "erpnext"):
        if app not in apps:
            apps.append(app)
    atomic_write(apps_path, "\n".join(apps) + "\n", mode=0o644)


def bench(env, command):
    # Only the site name and a fixed command enter argv. Root credentials are
    # never inherited by bench, and upstream output may contain SQL or secrets.
    child_env = os.environ.copy()
    child_env.pop("DB_ROOT_PASSWORD", None)
    child_env["FRAPPE_STREAM_LOGGING"] = "1"
    subprocess.run(
        [str(BENCH / "env/bin/python"), "-m", "frappe.utils.bench_helper",
         "frappe", "--site", env["site"], command],
        cwd=SITES, env=child_env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )


def check_database_is_absent(env, root_password):
    """Check before the upstream installer can create users or drop an empty DB.

    A preexisting DB or DB account with no matching site directory is not proof
    of an empty installation. Leave it alone, including after a partial retry.
    """
    import frappe
    import frappe.database

    os.chdir(SITES)
    root = None
    try:
        frappe.init(env["site"], sites_path=str(SITES), new_site=True)
        root = frappe.database.get_db(
            host=env["db_host"], port=env["db_port"], user="root",
            password=root_password, cur_db_name=None,
        )
        if root.sql("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (env["db_name"],)):
            raise ValueError("Database already exists without a complete site")
        if root.sql("SELECT User FROM mysql.user WHERE User=%s", (env["db_name"],)):
            raise ValueError("Database account already exists without a complete site")
    finally:
        if root is not None:
            root.close()
        frappe.destroy()


def create_site(env, settings, root_password):
    import frappe
    from frappe.database.db_manager import DbManager
    from frappe.installer import install_app, install_db, make_site_dirs

    if not root_password:
        raise ValueError("New sites require a database root credential")
    check_database_is_absent(env, root_password)
    marker = incomplete_marker(env)
    atomic_write(marker, "Incomplete site creation. Operator review is required before retry.\n")
    site_path = SITES / env["site"]
    site_path.mkdir()  # Deliberately no exist_ok, and no cleanup on failure.
    config = {
        "db_type": "mariadb",
        "db_host": env["db_host"],
        "db_port": env["db_port"],
        "db_name": env["db_name"],
        "db_user": env["db_name"],
        "db_password": settings["databasePassword"],
        "encryption_key": settings["encryptionKey"],
        "host_name": env["url"],
    }
    # Seed the real per-site key before install_db or any Password field save.
    write_json(site_path / "site_config.json", config)

    # Frappe 16's create_user interpolates the password into SQL. Parameterize
    # this one operation so generated credentials can contain quotes safely.
    original_create_user = DbManager.create_user

    def create_user(manager, user, password, host=None):
        manager.db.sql(
            "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
            (user, host or manager.get_current_host(), password),
        )

    try:
        frappe.init(env["site"], sites_path=str(SITES))
        make_site_dirs()
        DbManager.create_user = create_user
        try:
            with private_database_commands():
                # Same installer sequence as new-site, without its interactive
                # rollback callbacks or absent-directory check after key seeding.
                install_db(
                    root_login="root", root_password=root_password,
                    db_name=env["db_name"], db_user=env["db_name"],
                    db_password=settings["databasePassword"], db_type="mariadb",
                    db_host=env["db_host"], db_port=env["db_port"],
                    admin_password=settings["adminPassword"], site_config=config,
                    force=False, verbose=False, mariadb_user_host_login_scope="%",
                )
                install_app("frappe", verbose=False, force=False)
                install_app("erpnext", verbose=False, force=False)
            if not {"frappe", "erpnext"}.issubset(frappe.get_installed_apps()):
                raise ValueError("Site installation did not complete")
            frappe.db.commit()
        finally:
            DbManager.create_user = original_create_user
    finally:
        frappe.destroy()
    # Keep this marker on ANY failure. Native app installation commits schema
    # in stages and cannot be undone safely by a generic bootstrap retry.
    marker.unlink()


def ensure_erpnext(env, settings):
    with connected_site(env, settings, require_erpnext=False) as frappe:
        if "erpnext" in frappe.get_installed_apps():
            return False
        if frappe.db.exists("DocType", "Company"):
            raise ValueError("Possible partial ERPNext installation requires operator review")
        from frappe.installer import install_app

        marker = incomplete_marker(env)
        atomic_write(marker, "Incomplete ERPNext installation. Operator review is required before retry.\n")
        with private_database_commands():
            install_app("erpnext", verbose=False, force=False)
        if "erpnext" not in frappe.get_installed_apps():
            raise ValueError("ERPNext installation did not complete")
        frappe.db.commit()
        marker.unlink()
        return True


def bootstrap():
    # Remove root credentials before importing Frappe or launching any child.
    root_password = os.environ.pop("DB_ROOT_PASSWORD", None)
    try:
        with quiet_output(), deployment_lock():
            env = environment()
            if not re.fullmatch(r"[A-Za-z0-9_]+", env["db_name"]):
                raise ValueError("Invalid database name")
            settings = load_settings()
            if incomplete_marker(env).exists():
                raise ValueError("Incomplete bootstrap requires operator review")
            path = SITES / env["site"]
            exists = path.exists()
            if exists:
                # Verify the old connection before updating the common config.
                site_config(env, settings)
                with connected_site(env, settings, require_erpnext=False):
                    pass
            configure_bench(env)
            if not exists:
                create_site(env, settings, root_password)
            else:
                config = site_config(env, settings)
                config["host_name"] = env["url"]
                write_json(path / "site_config.json", config)
            root_password = None
            # Use the supported bench CLI rather than duplicating migrations.
            bench(env, "migrate")
            if ensure_erpnext(env, settings):
                bench(env, "migrate")
            bench(env, "enable-scheduler")
            reconcile_locked(env, settings)
    except BaseException:
        raise RuntimeError("ERPNext bootstrap failed; check prerequisites, credential consistency, and incomplete markers") from None


if __name__ == "__main__":
    try:
        bootstrap()
    except BaseException:
        sys.stderr.write("ERPNext bootstrap failed; check prerequisites, credential consistency, and incomplete markers.\n")
        sys.exit(1)
