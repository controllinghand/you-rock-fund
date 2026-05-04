# Mac Mini Setup Guide — You Rock Club

This guide walks You Rock Club members through setting up a Mac Mini as a dedicated, always-on YRVI trading machine. Follow these steps in order from initial macOS setup through a verified reboot test.

---

## Recommended Hardware

| Component | Spec | Notes |
|-----------|------|-------|
| Computer | Mac Mini M4 (Apple Silicon) | M4 Pro (48GB) is ideal but base M4 works fine |
| RAM | 16GB minimum | Base config is fine for YRVI |
| Storage | 256GB SSD | Base config is fine |
| Network | Ethernet (recommended) | More reliable than WiFi |
| UPS | Battery backup ~$75 | Highly recommended — prevents power-outage reboots |

> 💡 Check Amazon weekly — the M4 Mac Mini regularly goes on sale for $469–499. MicroCenter sometimes has it for $399 in store.

---

## One-Time Setup Hardware

You will need the following physical hardware to complete the initial setup. After setup is complete, you can manage the Mac Mini entirely via Screen Sharing (remote desktop) from another Mac, or via a VNC client from a Windows PC — none of this hardware is needed day-to-day.

| Item | Notes |
|------|-------|
| Monitor with HDMI input | The Mac Mini has an HDMI port. If your monitor only has DisplayPort or VGA, you'll need an adapter. A cheap 1080p monitor works fine. |
| HDMI cable | Usually included with monitors, otherwise ~$10 |
| USB keyboard | Any USB or Bluetooth keyboard |
| USB mouse | Any USB or Bluetooth mouse |

> 💡 Once Screen Sharing is configured (Phase 2), you can disconnect all of this and control the Mac Mini remotely forever after — from a Mac via Finder, or from a Windows PC using a free VNC client like RealVNC Viewer.

---

## Phase 1 — macOS Initial Setup

When you first power on the Mac Mini, follow these decisions at each setup screen:

### Apple Account
- **Skip signing in to Apple ID** — select "Set Up Later" or "Skip"
- This machine is a dedicated server and doesn't need iCloud, App Store sync, or any Apple services

### Location Services
- **Turn off** — not needed for a trading server

### Time Zone
- Select **closest city** (Los Angeles for Pacific time)

### Mac Analytics
- **Uncheck everything** and skip

### FileVault
- **Do NOT enable FileVault**
- FileVault requires a manual password entry after every reboot or power outage, which means YRVI won't auto-restart unattended
- Your IBKR credentials are protected by macOS Keychain regardless of FileVault

### Automatic Software Updates
- Turn on **Download new updates when available**
- Turn on **Install Security Responses and system files**
- Leave **Install macOS updates** OFF — a major OS update should not reboot your machine mid-trading day

---

## Phase 2 — macOS System Settings

### Enable Screen Sharing (Remote Access)
1. System Settings → General → Sharing → Screen Sharing → **On**
2. Set **Allow access for: Only these users → Administrators**
3. Leave "Anyone may request permission" and "VNC viewers may control with password" **Off**

You can now connect from another Mac on the same network via Finder sidebar or **Go → Connect to Server → `vnc://[MAC_MINI_IP]`**

> 💡 Both machines must be on the same network. Ethernet on both is most reliable.

### Enable Automatic Login
1. System Settings → Users & Groups (search "automatic" in Settings search bar)
2. Set **Automatically log in as: [your admin user]**
3. Enter your password to confirm

This ensures the Mac Mini logs itself in automatically after a power outage or reboot — no one needs to be present.

> ⚠️ Automatic Login is only available when FileVault is disabled. This is why we skip FileVault above.

### Optional: Prevent Display Sleep
- System Settings → Energy → set display sleep to **Never**
- The Mac Mini runs headless — no display needed after initial setup

---

## Phase 3 — Developer Tools

Open Terminal and run these commands in order.

### 1. Xcode Command Line Tools
```bash
xcode-select --install
```
A popup will appear — click **Install** (not "Get Xcode"). Takes a few minutes.

### 2. Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. Add Homebrew to PATH (required on Apple Silicon)
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile && eval "$(/opt/homebrew/bin/brew shellenv)"
```

Verify:
```bash
brew --version
```

### 4. Install Core Tools
```bash
brew install git gh python node
```

### 5. Set Up SSH Key and GitHub Auth
```bash
ssh-keygen -t ed25519 -C "your@email.com"
```
Hit Enter through all prompts (default location, no passphrase).

Then authenticate with GitHub:
```bash
gh auth login
```
Choose: **GitHub.com → SSH → Yes → Login with a web browser** — this uploads your SSH key to GitHub automatically.

---

## Phase 4 — Docker Desktop

1. Download **Docker Desktop for Mac (Apple Silicon)** from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Drag Docker to Applications and open it
3. Accept the license agreement
4. At setup: select **Use recommended settings** → Finish
5. Skip the Docker account sign-in (click Skip)

### Configure Auto-Start
Docker Desktop → Settings (⚙️) → General:
- ✅ **Start Docker Desktop when you sign in to your computer**
- ✅ **Open Docker Dashboard when Docker Desktop starts**

### Verify Docker Works
```bash
docker run hello-world
```
Should print "Hello from Docker!"

---

## Phase 5 — Clone YRVI and Run Setup

### Clone the Repo
```bash
cd ~ && git clone git@github.com:controllinghand/you_rock_fund.git
cd you_rock_fund
```

### Register the Upgrade URL Scheme (one-time)
```bash
bash scripts/yrvi-register-url-scheme.sh
```
This registers `yrvi://upgrade` so the dashboard Upgrade button can open Terminal directly for one-click upgrades. Run it once after cloning; re-run it if you move the repo.

### Run Paper Trading Setup
```bash
./setup_docker.sh --paper
```

On first run you will be prompted for:
- Your **IBKR paper trading password** (stored in macOS Keychain)
- Your **Render screener API secret** (stored in macOS Keychain)

On subsequent runs, secrets are pulled from Keychain silently — no re-entry needed.

### What Setup Does
The script runs 6 steps automatically:
1. Verifies Docker is running
2. Pulls secrets from Keychain and writes ephemeral secret files
3. Validates your `.env.compose` config
4. Builds and starts all 4 containers (ib_gateway, api, scheduler, web)
5. Installs a login item so containers restart automatically after every reboot
6. Installs the YRVI Startup desktop app

### Watch IB Gateway Log In
```bash
docker compose --env-file .env.compose logs -f ib_gateway
```
Wait for **"Login has completed"** — takes 30–90 seconds.

### Open the Dashboard
```
http://localhost:3000
```

You should see all status indicators green: **Gateway • Scheduler • IBKR**

---

## Phase 6 — Switch to Live Trading

Once you've validated paper trading works for a full week:

```bash
./setup_docker.sh --live
```

> ⚠️ Only one YRVI instance can connect to an IBKR account at a time. If you have YRVI running on another machine (laptop, Windows PC), you must shut it down before starting live trading on the Mac Mini. The Mac Mini should be your permanent home for live trading going forward.

---

## Phase 7 — Reboot Test

Always test a full reboot before considering setup complete:

```bash
sudo reboot
```

After the Mac Mini restarts:
1. It should boot straight to the desktop (no password prompt) — confirms automatic login works
2. Docker Desktop should open automatically
3. YRVI containers should start within 60 seconds
4. Dashboard at `http://localhost:3000` should show all green

If IB Gateway needs a moment, run:
```bash
docker compose --env-file .env.compose logs -f ib_gateway
```
And wait for "Login has completed".

---

## Ongoing Operations

### Pre-flight Check (anytime)
```bash
bash ~/you_rock_fund/startup.sh
```
Or double-click **YRVI Startup** on your Desktop.

### Container Status
```bash
docker compose --env-file .env.compose ps
```

### View Logs
```bash
docker compose --env-file .env.compose logs -f scheduler   # trades
docker compose --env-file .env.compose logs -f ib_gateway  # gateway login
docker compose --env-file .env.compose logs -f api         # dashboard API
```

### Re-run Setup (after reboot, if needed)
```bash
cd ~/you_rock_fund && ./setup_docker.sh --paper
```
Secrets are pulled from Keychain automatically — no passwords needed.

### Rotating a Secret (e.g. changed IBKR password)
1. Open **Keychain Access.app**
2. Search for `YRVI`
3. Delete the relevant entry (e.g. `YRVI_TWS_PAPER`)
4. Re-run `./setup_docker.sh --paper` — you will be prompted for the new value

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Existing session detected" in gateway log | Another machine is connected to the same IBKR paper account. Shut it down first. |
| Containers don't start after reboot | Open Docker Desktop manually and wait for "Engine running", then run `./setup_docker.sh --paper` |
| Dashboard shows Gateway red | Run `docker compose --env-file .env.compose logs -f ib_gateway` and check for errors |
| Secret files missing error | Run `./setup_docker.sh --paper` — it will re-pull secrets from Keychain |
| IB Gateway needs 2FA | Set `VNC_SERVER_PASSWORD` in `.env.compose`, recreate gateway, connect via Finder → Go → Connect to Server → `vnc://localhost:5900` |

---

## Total Setup Cost

| Item | Cost |
|------|------|
| Mac Mini M4 (16GB/256GB) | ~$499 |
| UPS battery backup | ~$75 |
| Ethernet cable | ~$10 |
| **Total** | **~$584 one time** |

vs $3,500+/week potential income = **ROI in first week** 💰

---

*You Rock Club — YRVI Mac Mini Setup Guide*
