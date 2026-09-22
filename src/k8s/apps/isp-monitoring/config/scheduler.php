<?php

function saveSchedule(string $path, array $state): void
{
    $json = json_encode($state, JSON_THROW_ON_ERROR)."\n";
    $file = fopen($path.'.tmp', 'w');
    if ($file === false || fwrite($file, $json) !== strlen($json) || !fflush($file) || !fsync($file)) {
        throw new RuntimeException('Could not persist ISP schedule');
    }
    fclose($file);
    if (!rename($path.'.tmp', $path)) {
        throw new RuntimeException('Could not replace ISP schedule');
    }
}

$path = '/config/isp-scheduler.json';
$lock = fopen('/config/isp-scheduler.lock', 'c');
if ($lock === false) {
    throw new RuntimeException('Could not open ISP scheduler lock');
}
if (!flock($lock, LOCK_EX | LOCK_NB)) {
    exit(0);
}

$now = time();
$window = intdiv($now, 43200) * 43200; // Midnight/noon UTC, unaffected by DST.
$state = is_file($path) ? json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR) : null;
if ($state !== null && (!is_array($state)
    || !is_int($state['window'] ?? null)
    || !is_int($state['runAt'] ?? null)
    || !is_bool($state['attempted'] ?? null))) {
    throw new RuntimeException('Invalid ISP schedule; refusing to choose another test time');
}

if ($state === null || $state['window'] < $window) {
    // On first startup, choose from the minutes remaining in this window.
    $state = [
        'window' => $window,
        'runAt' => random_int(intdiv($now, 60), intdiv($window + 43200, 60) - 1) * 60,
        'attempted' => false,
    ];
    saveSchedule($path, $state);
    echo 'Next ISP speed test: '.gmdate('Y-m-d\TH:i:s\Z', $state['runAt'])."\n";
}

if ($state['window'] !== $window || $state['attempted'] || $now < $state['runAt']) {
    exit(0);
}

// Claim before dispatch: a crash may miss a test, but must not dispatch it twice.
$state['attempted'] = true;
saveSchedule($path, $state);
require '/app/www/vendor/autoload.php';
$app = require '/app/www/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
App\Actions\Ookla\RunSpeedtest::run(scheduled: true);
echo 'Dispatched ISP speed test at '.gmdate('Y-m-d\TH:i:s\Z', $now)."\n";
