<?php
// orders.php — Turtle Island
// CHANGES: Added StorePing integration (3 lines, marked with // STOREPING)
//
// Nothing else changes. If StorePing is down, checkout still works.

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/storeping.php';   // STOREPING: line 1 — include the notifier

$db = getDB();
$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'POST') {
    $body = getBody();

    $required = ['first_name', 'last_name', 'phone', 'address', 'city', 'province', 'postal_code', 'items'];
    foreach ($required as $field) {
        if (empty($body[$field])) jsonError("Missing required field: $field");
    }

    if (empty($body['items']) || !is_array($body['items'])) {
        jsonError('Cart is empty');
    }

    $total = 0;
    $sanitizedItems = [];
    foreach ($body['items'] as $item) {
        if (!isset($item['id'], $item['price'], $item['qty'])) continue;
        $stmt = $db->prepare("SELECT id, name, price, stock_status FROM products WHERE id = ?");
        $stmt->execute([$item['id']]);
        $product = $stmt->fetch();
        if (!$product || $product['stock_status'] !== 'in_stock') {
            jsonError("Product '{$item['name']}' is no longer available");
        }
        $qty = max(1, intval($item['qty']));
        $lineTotal = floatval($product['price']) * $qty;
        $total += $lineTotal;
        $sanitizedItems[] = [
            'id'    => $product['id'],
            'name'  => $product['name'],
            'price' => floatval($product['price']),
            'qty'   => $qty,
        ];
    }

    $orderNumber = generateOrderNumber();

    $stmt = $db->prepare("
        INSERT INTO orders (order_number, first_name, last_name, email, phone, address, city, province, postal_code, items, subtotal, total, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $orderNumber,
        trim($body['first_name']),
        trim($body['last_name']),
        trim($body['email'] ?? ''),
        trim($body['phone']),
        trim($body['address']),
        trim($body['city']),
        trim($body['province']),
        trim($body['postal_code']),
        json_encode($sanitizedItems),
        $total,
        $total,
        trim($body['notes'] ?? ''),
    ]);

    // STOREPING: line 2 + 3 — notify after successful insert
    $customerName = trim($body['first_name']) . ' ' . trim($body['last_name']);
    storeping_notify_order($orderNumber, $customerName, $total, count($sanitizedItems));

    jsonResponse(['success' => true, 'order_number' => $orderNumber, 'total' => $total]);
}

jsonError('Method not allowed', 405);
