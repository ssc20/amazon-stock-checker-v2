# Amazon Stock Checker v2

A Playwright + Docker app that checks Amazon product pages for restocks and sends notifications.

Built for tracking Beyblade drops, but it works for any Amazon ASIN list.

---

## Quick Start

```bash
# 1. Go to project directory
cd amazon-stock-checker

# 2. Create config
mkdir -p config
cp config.example.json config/config.json
# Edit config/config.json with your Telegram bot token, chat ID, and ASINs

# 3. Build and run
docker compose up -d --build

# 4. Check logs
docker logs -f amazon-stock-checker
```

Requirements: Docker + Docker Compose.

Optional (remote host/NAS): copy this folder to your target machine first, then run the same commands there.

---

## Architecture

```
amazon-stock-checker/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point and poll loop
│   ├── config.py               # Typed config (dataclass) with validation
│   ├── state.py                # Stock state + cookie persistence
│   ├── browser.py              # Playwright lifecycle, stealth, warmup
│   ├── checker.py              # Product page parsing + stock detection
│   ├── debug.py                # Screenshot/HTML capture on errors
│   ├── captcha_solvers/
│   │   └── __init__.py         # Solver protocol + registry
│   └── notifiers/
│       ├── __init__.py         # Notifier protocol + registry
│       ├── telegram.py         # Telegram implementation
│       └── discord.py          # Discord stub (TODO)
├── config/                     # Mounted volume
│   ├── config.json             # Your config
│   ├── state.json              # Auto-generated
│   ├── cookies.json            # Auto-generated
│   └── debug/                  # Error screenshots
├── Dockerfile
├── docker-compose.yml
├── config.example.json
├── requirements.txt
└── README.md
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `main.py` | Poll loop, wiring everything together |
| `config.py` | Loads JSON config into typed `Config` + `Product` dataclasses |
| `state.py` | `StateManager` (per-ASIN state) + `CookieManager` (browser cookies) |
| `browser.py` | `BrowserManager`: launch, stealth, context rotation, warmup |
| `checker.py` | `check_product()`: navigate, handle CAPTCHA, parse stock status |
| `debug.py` | `capture()` — save screenshot + HTML on errors |
| `captcha_solvers/` | `CaptchaSolver` protocol + `SoftCaptchaSolver` (button-click) |
| `notifiers/` | `Notifier` protocol + `TelegramNotifier` |

---

## Extending
Current TODO items are listed below.

### Add a New Notifier (e.g., Discord, Pushover, SMS)

1. Create `src/notifiers/my_notifier.py`
2. Implement the `Notifier` protocol:
   ```python
   class MyNotifier:
       def send(self, message: str) -> bool: ...
       def send_startup(self, products, domain) -> bool: ...
       def send_restock(self, product, result) -> bool: ...
       def send_error(self, product, error, error_count) -> bool: ...
   ```
3. Add a config field in `config.py`
4. Wire it into `build_notifiers()` in `src/notifiers/__init__.py`

### Add a New CAPTCHA Solver

1. Create a class with `detect(page) -> bool` and `solve(page) -> bool`
2. Add it to the `SOLVERS` list in `src/captcha_solvers/__init__.py`
3. Solvers are tried in order; put the most common one first

### Add a New Retailer (e.g., Best Buy, Walmart)

`checker.py` currently uses Amazon-specific selectors. To support other retailers:

1. Define a `RetailerParser` protocol with `build_url()` and `parse_stock()` methods
2. Create `src/parsers/amazon.py`, `src/parsers/bestbuy.py`, etc.
3. Add a `retailer` field to the `Product` config
4. Route to the correct parser in `check_product()`

### Add Proxy Rotation

1. Set `proxy_url` in config (or a list of proxies)
2. Pass to `BrowserManager`; there is already a TODO placeholder in `start()`
3. Rotate proxy on context rotation

---

## Telegram Bot Setup

1. Message **@BotFather** on Telegram → `/newbot` → follow prompts
2. Copy the bot token
3. Send any message to your new bot
4. Get your chat ID:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Find `"chat":{"id":123456789}`

---

## Config Reference

```json
{
    "telegram_bot_token": "required",
    "telegram_chat_id": "required",
    "discord_webhook_url": "",

    "amazon_domain": "amazon.ca",

    "poll_high_priority_min_seconds": 25,
    "poll_high_priority_max_seconds": 35,
    "poll_interval_min_seconds": 45,
    "poll_interval_max_seconds": 60,

    "warmup_every_n_cycles": 20,
    "proxy_url": null,

    "products": [
        {
            "asin": "B0DCZFNB3C",
            "label": "PS5 Slim",
            "priority": "high"
        }
    ]
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `telegram_bot_token` | *required* | Bot token from @BotFather |
| `telegram_chat_id` | *required* | Your Telegram chat ID |
| `discord_webhook_url` | `""` | Discord webhook URL (TODO) |
| `amazon_domain` | `amazon.ca` | Amazon domain to monitor |
| `poll_high_priority_min_seconds` | `25` | Min cycle interval (high-priority) |
| `poll_high_priority_max_seconds` | `35` | Max cycle interval (high-priority) |
| `poll_interval_min_seconds` | `45` | Min cycle interval (normal) |
| `poll_interval_max_seconds` | `60` | Max cycle interval (normal) |
| `warmup_every_n_cycles` | `20` | Homepage warmup frequency |
| `proxy_url` | `null` | Proxy server URL (TODO) |
| `products[].asin` | *required* | Amazon ASIN |
| `products[].label` | ASIN | Friendly name for logs/alerts |
| `products[].priority` | `"normal"` | `"high"` or `"normal"` |

Config is hot-reloaded every cycle, so no restart is needed.

---

## Anti-Detection

| Feature | Module |
|---------|--------|
| Stealth JS (webdriver, Chrome runtime, WebGL) | `browser.py` |
| Random viewport + User-Agent per context | `browser.py` |
| Cookie persistence across restarts | `state.py` |
| Homepage warmup every N cycles | `browser.py` |
| Human-like mouse/scroll jitter | `browser.py` |
| Randomized timing (~15s jitter) | `main.py` |
| Auto context rotation on 3+ errors | `main.py` |
| Soft CAPTCHA auto-solve | `captcha_solvers/` |

---

## Resource Usage

About 300-500 MB RAM (Chromium), with low CPU use between checks. `shm_size: 512mb` in docker-compose is required or Chromium may crash.

---

## Tips

- **1-Click Buy** on Amazon can be very fast after a Telegram alert
- **Telegram on smartwatch** helps with reaction time
- **Start conservative** with default intervals, then tighten if no 503s after a day
- **Multiple domains**: run two containers with separate configs
- **Debug screenshots** in `/config/debug/` show exactly what Amazon returned
