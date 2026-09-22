<?php

require '/app/www/vendor/autoload.php';
$app = require '/app/www/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

$user = App\Models\User::where('email', getenv('ADMIN_EMAIL'))->firstOrFail();
$user->tokens()->updateOrCreate(
    ['name' => 'isp-scheduler'],
    [
        'token' => hash('sha256', getenv('SCHEDULER_API_TOKEN')),
        'abilities' => ['speedtests:run'],
    ],
);
