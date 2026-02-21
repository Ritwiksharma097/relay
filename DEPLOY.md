# StorePing — Deploy Guide
# Your VPS (interactxp user) + Turtle Island on Hostinger

---

## PART 1 — VPS Setup (do this once)

### 1. SSH in as interactxp
```bash
ssh interactxp@15.235.166.58
```

### 2. Upload the project
On your LOCAL machine (new terminal):
```bash
scp -r /path/to/storeping-v2 interactxp@15.235.166.58:~/storeping
```
Then back on the VPS:
```bash
cd ~/storeping
```

### 3. Create your .env file
```bash
cp .env.example .env
nano .env
```
Fill in:
- `DB_PASS` — make something strong, e.g. `openssl rand -hex 32`
- `BOT_TOKEN` — from @BotFather on Telegram
- `API_SECRET` — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`

### 4. Start everything
```bash
docker compose up -d
```
Check it's running:
```bash
docker compose ps
docker compose logs bot
```
You should see: `✅ StorePing bot starting`

### 5. Register Turtle Island as a client
```bash
docker compose exec bot python setup_client.py
```
Enter:
- Store name: `Turtle Island`
- Store slug: `turtle-island`
- Timezone: `America/Toronto`
- Currency: `$`

**Save the output.** It gives you:
- `STOREPING_SLUG` and `STOREPING_SECRET` → for storeping.php on Hostinger
- `/start turtle-island <secret>` → for the Telegram bot

### 6. Set up nginx + SSL (so URL is clean, no :8000)
```bash
sudo apt install nginx certbot python3-certbot-nginx -y

# Copy nginx config
sudo cp nginx.conf /etc/nginx/sites-available/storeping

# Edit it — change your-domain.com to your actual domain or VPS IP
sudo nano /etc/nginx/sites-available/storeping

# Enable it
sudo ln -s /etc/nginx/sites-available/storeping /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# If you have a domain, get SSL (free):
sudo certbot --nginx -d your-domain.com
```
If you're using just an IP (no domain), skip certbot and use `http://` in storeping.php with `CURLOPT_SSL_VERIFYPEER => false`.

---

## PART 2 — Hostinger (Turtle Island site)

### 1. Upload these files to the `api/` folder:
- `storeping.php`
- `maintenance_check.php`

### 2. Edit storeping.php
```php
define('STOREPING_URL',    'https://your-domain.com');  // your VPS URL
define('STOREPING_SLUG',   'turtle-island');
define('STOREPING_SECRET', 'the-secret-from-setup_client');
```

### 3. Replace orders.php with orders_with_storeping.php
Just rename/replace. The only difference is 3 lines at the bottom.

### 4. Replace contact.php with contact_with_storeping.php
Same — 3 extra lines. Email still sends, now Telegram also pings.

### 5. Add maintenance check to config.php
At the very top of `api/config.php`, add this ONE line:
```php
require_once __DIR__ . '/maintenance_check.php';
```
Edit `maintenance_check.php` — fill in STOREPING_URL and STOREPING_SLUG at the top.

---

## PART 3 — Connect the Telegram bot

### 1. Find your Telegram chat ID
- Open Telegram
- Message your bot (the one you made with @BotFather)
- Visit: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
- Find the `"id"` inside `"chat"` — that's your chat_id

### 2. Link the bot to Turtle Island
In your Telegram chat with the bot, send:
```
/start turtle-island YOUR_SECRET_HERE
```
(Use the exact command from setup_client.py output)

You should get: ✅ Linked! This chat will now receive notifications for Turtle Island

### 3. Test it
Place a test order on the website.
You should receive a Telegram message within 1-2 seconds.

---

## PART 4 — Day to day commands

```
/today          → today's orders and revenue
/week           → last 7 days
/month          → last 30 days  
/orders         → 5 most recent orders
/maintenance on → put site in maintenance mode
/maintenance off → bring site back online
/help           → all commands
```

---

## Troubleshooting

**Bot not receiving messages:**
```bash
docker compose logs bot --tail 50
```

**API not receiving from Hostinger:**
```bash
docker compose logs api --tail 50
```
Also check that your VPS firewall allows port 80/443:
```bash
sudo ufw allow 80
sudo ufw allow 443
```

**Restart everything:**
```bash
docker compose restart
```

**Add a second client later:**
```bash
docker compose exec bot python setup_client.py
```
