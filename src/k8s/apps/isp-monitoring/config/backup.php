<?php

// VACUUM INTO creates a consistent online snapshot, including committed WAL data.
$directory = sys_get_temp_dir().'/isp-backup-'.bin2hex(random_bytes(8));
mkdir($directory, 0700);
$database = $directory.'/database.sqlite';
try {
    $pdo = new PDO('sqlite:/config/database.sqlite');
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->exec('PRAGMA busy_timeout = 30000');
    $pdo->exec('VACUUM INTO '.$pdo->quote($database));
    passthru('tar -C '.escapeshellarg($directory).' -cf - database.sqlite', $status);
} finally {
    if (file_exists($database)) {
        unlink($database);
    }
    rmdir($directory);
}
exit($status);
