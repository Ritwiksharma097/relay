<?php
// maintenance_check.php — Turtle Island
// Drop this into your api/ folder.
// Add one line to the TOP of api/config.php:
//
//   require_once __DIR__ . '/maintenance_check.php';
//
// That's it. When owner sends /maintenance on via Telegram,
// this file reads the StorePing API and shows a maintenance page.
// When they send /maintenance off, site is back to normal.
// No deploy needed. No file editing. Just a Telegram message.

define('STOREPING_MAINTENANCE_URL',
    rtrim(STOREPING_URL ?? 'https://your-storeping-domain.com', '/') .
    '/maintenance/' . (STOREPING_SLUG ?? 'turtle-island')
);

function is_maintenance_mode(): bool {
    // Cache in a temp file for 30 seconds so we don't hit the API on every request
    $cache_file = sys_get_temp_dir() . '/storeping_maintenance_' . (STOREPING_SLUG ?? 'default');
    $cache_ttl  = 30; // seconds

    if (file_exists($cache_file) && (time() - filemtime($cache_file)) < $cache_ttl) {
        return trim(file_get_contents($cache_file)) === 'on';
    }

    // Fetch from StorePing API
    $ctx = stream_context_create(['http' => [
        'timeout'       => 2,
        'ignore_errors' => true,
        'header'        => 'Authorization: Bearer ' . (STOREPING_SECRET ?? ''),
    ]]);

    $result = @file_get_contents(STOREPING_MAINTENANCE_URL, false, $ctx);
    $data   = $result ? json_decode($result, true) : null;
    $status = ($data['maintenance'] ?? 'off') === 'on' ? 'on' : 'off';

    // Write cache
    file_put_contents($cache_file, $status);

    return $status === 'on';
}

// Only block non-API requests during maintenance
$request_uri = $_SERVER['REQUEST_URI'] ?? '';
$is_api      = strpos($request_uri, '/api/') !== false;

if (!$is_api && is_maintenance_mode()) {
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    header('Retry-After: 3600');
    echo '<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Turtle Island — Under Maintenance</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0a0a0a;
      color: #fff;
      font-family: "Jost", sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      text-align: center;
      padding: 2rem;
    }
    .container { max-width: 480px; }
    h1 {
      font-family: "Cinzel", serif;
      font-size: 1.5rem;
      letter-spacing: 0.2em;
      color: #c9a84c;
      margin-bottom: 1.5rem;
      text-transform: uppercase;
    }
    p { color: #9ca3af; line-height: 1.8; font-size: 0.95rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Under Maintenance</h1>
    <p>We\'re making some improvements.<br>We\'ll be back shortly. Thank you for your patience.</p>
  </div>
</body>
</html>';
    exit;
}
