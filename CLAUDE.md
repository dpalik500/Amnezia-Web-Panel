# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Amnezia Web Panel — a FastAPI web UI for managing VPN servers (AmneziaWG, WireGuard, Xray/XTLS-Reality, Telegram MTProxy, AmneziaDNS) over SSH. The panel connects to remote servers via SSH and manages Docker containers running VPN protocols.

## Commands

### Run locally
```bash
pip install -r requirements.txt
python app.py
# Accessible at http://localhost:5000 — default credentials: admin / admin
```

### Run with Docker
```bash
docker-compose up -d
# APP_PORT env var controls the port (default: 5000)
```

### Build standalone executable
CI builds (`.github/workflows/build.yml`) use PyInstaller for Linux/Windows/macOS. Trigger by pushing to main or creating a release tag.

## Architecture

### Core files
- **`app.py`** (~2300 lines) — FastAPI app, all HTTP routes, session auth, data loading/saving, i18n bootstrap
- **`ssh_manager.py`** — Paramiko SSH wrapper; all remote commands go through `SSHManager`
- **`awg_manager.py`**, **`wireguard_manager.py`**, **`xray_manager.py`**, **`telemt_manager.py`**, **`dns_manager.py`** — Protocol handlers; each implements a common interface (install, add_client, remove_client, toggle_client, get_clients, get_server_status, etc.)
- **`telegram_bot.py`** — Optional Telegram bot for user self-service

### Data layer
All state lives in `data/data.json` (no database). Schema:
```json
{ "servers": [], "users": [], "user_connections": [], "settings": {} }
```
Every mutation goes through `save_data_async()` + `DATA_LOCK` (asyncio.Lock) to avoid race conditions on concurrent requests.

### Request flow
1. Route handler loads `data.json` (via async lock)
2. Creates `SSHManager(host, port, user, password/key)`
3. Creates a protocol manager via `get_protocol_manager(ssh, protocol)`
4. Calls manager method (e.g., `add_client(...)`)
5. Updates in-memory data dict and calls `save_data_async()`

### Auth & roles
- PBKDF2-HMAC-SHA256 password hashing (salt stored as `salt$hash`)
- Starlette `SessionMiddleware`; session key `user_id`
- Four roles: `admin`, `support`, `helper`, `user` — checked per-route

### Templates & i18n
- Jinja2 templates in `templates/`; `base.html` is the master layout
- Translation JSONs in `translations/` (en, ru, fr, zh, fa)
- `_t(key)` lookup injected into template context by the `tpl()` helper in `app.py`
- Persian (`fa`) uses RTL layout via `dir="rtl"` on `<html>`

### Key design conventions
- `tpl(request, template_name, extra_ctx)` — always use this to render templates; it injects user object, settings, and translations automatically
- Protocol managers share method signatures — when adding a feature to one protocol, mirror it in others where applicable
- SSH commands are fire-and-forget strings executed via `SSHManager.execute()`; output is returned as stdout/stderr strings
- `SECRET_KEY` env var must be set for production (session security)
