<?php
// contact.php — Turtle Island (with StorePing integration)
// CHANGES: Added StorePing notification for contact form (3 lines marked // STOREPING)
// Everything else is identical. If StorePing is down, email still sends fine.

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/storeping.php';   // STOREPING line 1

if ($_SERVER['REQUEST_METHOD'] !== 'POST') jsonError('Method not allowed', 405);

$body     = getBody();
$required = ['first_name', 'last_name', 'email', 'subject', 'message'];
foreach ($required as $f) {
    if (empty($body[$f])) jsonError("Missing: $f");
}

// Send email (configure your Hostinger email settings)
$to      = 'info@yourdomain.com';
$subject = 'Contact Form: ' . htmlspecialchars($body['subject']);
$message = "From: {$body['first_name']} {$body['last_name']}\n";
$message .= "Email: {$body['email']}\n\n";
$message .= "Message:\n{$body['message']}";
$headers  = "From: noreply@yourdomain.com\r\nReply-To: {$body['email']}";

mail($to, $subject, $message, $headers);

// STOREPING line 2+3 — notify owner on Telegram instantly
storeping_notify_event('contact_form', [
    'name'    => trim($body['first_name']) . ' ' . trim($body['last_name']),
    'email'   => trim($body['email']),
    'subject' => trim($body['subject']),
]);

jsonResponse(['success' => true]);
