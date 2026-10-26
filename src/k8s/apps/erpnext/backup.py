#!/usr/bin/env python3
"""K8up PreBackupPod command. Stdout is exactly one completed tar.gz archive.

The native logical database dump and file archives are taken sequentially,
without maintenance mode. They are not a coordinated point-in-time snapshot.
The archive contains credentials and the encryption key. Protect the repository.
"""

import contextlib
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

from configure import (
    connected_site,
    deployment_lock,
    environment,
    private_database_commands,
    quiet_output,
)


def generate_archive(directory, env):
    """Use native Frappe outputs, but never its persistent sites/backups path."""
    from frappe.utils.backups import BackupGenerator

    native = directory / "native"
    native.mkdir(mode=0o700)
    paths = {
        "database.sql.gz": native / "database.sql.gz",
        "public-files.tar": native / "public-files.tar",
        "private-files.tar": native / "private-files.tar",
        "site_config.json": native / "site_config.json",
    }
    with connected_site(env) as frappe, private_database_commands():
        backup = BackupGenerator(
            db_name=frappe.conf.db_name,
            user=frappe.conf.db_user,
            password=frappe.conf.db_password,
            db_type=frappe.conf.db_type,
            db_host=frappe.conf.db_host,
            db_port=frappe.conf.db_port,
            db_socket=frappe.conf.db_socket,
            backup_path=str(native),
            backup_path_db=str(paths["database.sql.gz"]),
            backup_path_files=str(paths["public-files.tar"]),
            backup_path_private_files=str(paths["private-files.tar"]),
            backup_path_conf=str(paths["site_config.json"]),
            ignore_conf=True,  # Full DB, even if site backup exclusions exist.
            compress_files=False,
            verbose=False,
        )
        # Do not call get_backup: it can reuse older dumps, email links, or
        # generate/persist a separate native backup-encryption key. K8up owns
        # repository encryption. These methods produce native restore inputs.
        backup.take_dump()
        backup.copy_site_config()
        # Native backup_files suppresses tar's "file changed as we read it"
        # failure. Record command failures so K8up retries rather than silently
        # accepting a file archive whose command returned a nonzero status.
        execute = frappe.utils.execute_in_shell
        failed = False

        def checked_execute(*args, **kwargs):
            nonlocal failed
            try:
                return execute(*args, **kwargs)
            except BaseException:
                failed = True
                raise

        frappe.utils.execute_in_shell = checked_execute
        try:
            backup.backup_files()
        finally:
            frappe.utils.execute_in_shell = execute
        if failed:
            raise ValueError("Native file backup did not complete cleanly")
        for path in paths.values():
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                raise ValueError("Native backup output is missing")
        archive_path = directory / "erpnext.tar.gz"
        with tarfile.open(archive_path, "w:gz", compresslevel=6) as archive:
            for name, path in paths.items():
                archive.add(path, arcname=env["site"] + "/" + name, recursive=False)
        os.chmod(archive_path, 0o600)
        # Leave no transaction open while streaming the completed archive.
        frappe.db.rollback()
    return archive_path


def main():
    # Preserve a separate binary output descriptor. Keep fd 1 pointed at
    # /dev/null even during interpreter shutdown, when upstream atexit hooks
    # might otherwise append text to the archive.
    output = os.fdopen(os.dup(1), "wb")
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
    os.environ.pop("DB_ROOT_PASSWORD", None)
    try:
        with output, quiet_output(), deployment_lock():
            env = environment()
            # Explicit /tmp avoids TMPDIR resolving onto the sites volume.
            with tempfile.TemporaryDirectory(prefix="erpnext-backup-", dir="/tmp") as temporary:
                archive = generate_archive(Path(temporary), env)
                # No bytes leave the pod until every native backup and the
                # enclosing archive have completed successfully.
                with archive.open("rb") as stream:
                    shutil.copyfileobj(stream, output, length=1024 * 1024)
                output.flush()
        return 0
    except BaseException:
        with contextlib.suppress(OSError):
            output.close()
        sys.stderr.write("ERPNext backup failed; check prerequisites and backup storage.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
