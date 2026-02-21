<?php
// storeping.php — StorePing Notifier
// Drop this file into your site's api/ folder.
// Then call storeping_notify_order() right after a successful order INSERT.
//
// Setup:
//   1. Set STOREPING_URL to your VPS API address
//   2. Set STOREPING_SLUG to your store slug (e.g. "turtle-island")
//   3. Set STOREPING_SECRET to your API secret

define('STOREPING_URL',    'https://your-vps-ip-or-domain:8000');
define('STOREPING_SLUG',   'turtle-island');
define('STOREPING_SECRET', 'your-api-secret-here');


/**
 * Notify StorePing of a new order.
 * Call this right after your order INSERT succeeds.
 *
 * @param string $orderNumber  e.g. "TI-ABC12345"
 * @param string $customerName e.g. "Jane Smith"
 * @param float  $total        e.g. 79.99
 * @param int    $itemCount    number of line items
 */
function storeping_notify_order(string $orderNumber, string $customerName, float $total, int $itemCount = 1): void {
    $payload = json_encode([
        'order_number'  => $orderNumber,
        'customer_name' => $customerName,
        'total'         => $total,
        'item_count'    => $itemCount,
        'received_at'   => time(),
    ]);

    _storeping_post('/event/' . STOREPING_SLUG . '/order', $payload);
}


/**
 * Notify StorePing of any other event.
 *
 * @param string $eventType  e.g. "low_stock", "contact_form"
 * @param array  $payload    extra data for this event
 */
function storeping_notify_event(string $eventType, array $payload = []): void {
    $body = json_encode([
        'event_type' => $eventType,
        'payload'    => $payload,
    ]);

    _storeping_post('/event/' . STOREPING_SLUG . '/generic', $body);
}


/**
 * Internal: fire-and-forget HTTP POST to StorePing API.
 * Uses cURL with a short timeout so it never slows down your site.
 * Errors are silently ignored — StorePing failing should never break checkout.
 */
function _storeping_post(string $endpoint, string $jsonBody): void {
    $url = rtrim(STOREPING_URL, '/') . $endpoint;

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER  => true,
        CURLOPT_POST            => true,
        CURLOPT_POSTFIELDS      => $jsonBody,
        CURLOPT_TIMEOUT         => 3,           // max 3 seconds — never block checkout
        CURLOPT_CONNECTTIMEOUT  => 2,
        CURLOPT_HTTPHEADER      => [
            'Content-Type: application/json',
            'Authorization: Bearer ' . STOREPING_SECRET,
        ],
        CURLOPT_SSL_VERIFYPEER  => true,        // keep SSL verification on in production
    ]);

    curl_exec($ch);
    curl_close($ch);
    // No error handling — StorePing is optional, checkout always completes
}
