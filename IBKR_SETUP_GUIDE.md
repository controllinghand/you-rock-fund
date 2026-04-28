# 📋 IBKR Account Setup Guide for YRVI

A complete walkthrough for setting up your Interactive Brokers account to run the You Rock Volatility Income Fund system.

---

## Overview

**Interactive Brokers (IBKR)** is the brokerage we use to execute trades. It offers:
- Direct market access with very low commissions (~$0.65/contract for options)
- A robust API (`ib_insync`) that YRVI uses to place orders automatically
- Both paper (simulated) and live trading accounts

**What to expect:**
- Account approval takes **2–3 business days**
- Start with a **free paper trading account** — no deposit required
- Paper accounts come with $1M virtual cash (we'll reset to $250K)
- You can run the full YRVI system on paper trading while you wait for live approval

---

## Step 1 — Create Your Account

1. Go to **https://www.interactivebrokers.com**
2. Click **"Open Account"** in the top right
3. Select **"Individual Account"**
4. Enter your email address and create a strong password
5. Check your inbox and click the verification link

> **Tip:** Use the same email you want associated with this account long-term — it's hard to change later.

---

## ⚠️ CRITICAL: Choose IBKR Pro (NOT Lite)

During signup IBKR will ask you to choose between two account tiers. **This is the most important choice in the entire setup.**

| | IBKR Lite | IBKR Pro |
|---|-----------|----------|
| Commissions | $0 (free trades) | ~$0.65/contract |
| API access | ❌ **None** | ✅ **Full access** |
| YRVI compatible | ❌ **Will not work** | ✅ **Required** |

### **You MUST select IBKR Pro.**

YRVI is fully automated — it connects to IBKR via API to place every order. IBKR Lite has no API access, which means **the automation cannot place any trades.**

**The commission cost is negligible:**

| | Amount |
|---|--------|
| Options commission | ~$0.65 per contract |
| Typical week (50 contracts sold) | ~$32 in commissions |
| Typical weekly premium collected | $3,500+ |
| Commission as % of income | **< 1%** ✅ |

**If you accidentally selected IBKR Lite:**
1. Log into the IBKR portal → **Account → Account Type**
2. Request an upgrade to **IBKR Pro**
3. Upgrade takes 1–2 business days to process

---

## Step 2 — Personal Information

Fill in your details as prompted. Here's what to expect:

| Field | What to enter |
|-------|--------------|
| Legal name | Exactly as it appears on your government ID |
| Address | Your current residential address |
| Phone number | A number you can receive calls/SMS on for 2FA |
| Date of birth | Your actual DOB |
| SSN | Full SSN for US citizens (required for tax reporting) |
| Country of citizenship | United States |

**Employment status** — choose the option that best describes you:
- Employed, Self-employed, Retired, or Student are all fine
- If employed, you'll be asked your employer's name and your job title

**Financial information** — IBKR uses these to assess suitability. Recommended ranges for YRVI:

| Field | Recommended range |
|-------|------------------|
| Annual income | $100,000 – $200,000 |
| Net worth (total) | $500,000 – $1,000,000 |
| Liquid net worth | $250,000 – $500,000 |

> These should reflect your actual financial situation. IBKR uses them to determine account eligibility, not to verify income for a loan.

---

## Step 3 — Trading Experience ⭐ CRITICAL

**This section determines whether you get options trading approval.** Answer conservatively and you'll be denied. Be accurate about what you know.

Recommended answers for the YRVI strategy:

| Asset class | Experience | Knowledge level |
|-------------|-----------|----------------|
| Stocks / ETFs | 3+ years | Good |
| Options | 3+ years | Good |
| Bonds | 1–2 years | Limited (fine to leave low) |

**Investment objective:** Income

**Trading frequency:** Weekly

**Average trade size:** $25,000 – $100,000

> **Why this matters:** IBKR uses your stated experience to decide your options approval level. Level 2 is what we need (see Step 5). Stating "no experience" with options will result in denial.

---

## Step 4 — Account Configuration ⭐ CRITICAL

> **Reminder:** Make sure you selected **IBKR Pro** during signup. IBKR Lite has no API access and YRVI will not work with it. See the [IBKR Pro warning above](#️-critical-choose-ibkr-pro-not-lite) if you're unsure.

**Account type: CASH**

YRVI sells **cash-secured puts** — meaning the full capital to buy the shares is held in your account as collateral. You do **not** need margin for this strategy, and using a cash account avoids margin calls and interest charges.

| Setting | Value | Why |
|---------|-------|-----|
| Account type | **CASH** | CSPs require cash collateral, not margin |
| Base currency | USD | All positions are in US equities |

**Trading permissions to request:**

| Permission | Required? |
|-----------|-----------|
| ✅ US Stocks & ETFs | Yes — needed for stock assignments |
| ✅ US Options (Level 2) | Yes — required for selling CSPs and CCs |
| ❌ Margin | No — cash account only |
| ❌ Futures | No |
| ❌ Forex | No |

> If you accidentally select a margin account during signup, contact IBKR support to convert it to a cash account before depositing funds.

---

## Step 5 — Options Level 2 Approval

**Level 2 options** is the minimum required to run YRVI. It authorizes:

| Strategy | Allowed at Level 2 |
|----------|-------------------|
| ✅ Cash-secured puts (CSPs) | Yes — core YRVI strategy |
| ✅ Covered calls (CCs) | Yes — wheel strategy after assignment |
| ❌ Naked puts/calls | No — and we don't want these anyway |
| ❌ Multi-leg spreads | No |

**If your options trading request is denied:**

1. Call IBKR client services: **1-877-442-2757** (US)
2. Tell them: *"I want to sell cash-secured puts and covered calls only. I understand these require the full cash collateral to be held in the account and there is no naked exposure."*
3. They will frequently approve manually after a brief conversation
4. You can also re-apply through the portal after updating your trading experience

---

## Step 6 — Identity Verification

IBKR is required by law to verify your identity. Have these ready:

**Required documents:**
- **Government-issued photo ID** — driver's license or passport
- **Proof of address** — utility bill, bank statement, or government letter dated within 90 days

**Upload tips:**
- Take photos in good lighting with no glare
- Make sure all four corners of the document are visible
- The name and address must be clearly legible
- Blurry or cropped photos are the #1 cause of approval delays

> Documents are reviewed within 1–2 business days. You'll receive an email when your account is approved.

---

### Step 7 — Fund Your Account (Optional for Paper Trading)

**Paper Trading — $0 required** ✅
You can start paper trading immediately with NO real money.
IBKR gives you $1M in virtual cash to practice with.
This is how we recommend everyone starts with YRVI.

**Live Trading — when you're ready**
When you're confident in the system and want to use real money:
- Minimum: any amount (no IBKR minimum for cash accounts)
- YRVI is designed for $250,000 deployed capital
- You can start smaller and scale up as you get comfortable
- Transfer options:
  * ACH transfer (free, 3-5 days)
  * Wire transfer (faster, small fee)
  * ACATS transfer from another broker

💡 Pro Tip: Run paper trading for at least 4-8 weeks before
using real money. The system needs to prove itself first!

---

## Step 8 — Enable Paper Trading

While waiting for live account approval, set up paper trading to test the full YRVI system:

1. Log into **https://www.interactivebrokers.com/portal**
2. Go to **Account → Settings → Paper Trading Account**
3. Click **"Create Paper Trading Account"**
4. Your paper account is created with **$1,000,000** virtual cash

**Reset paper account to $250,000 for accurate YRVI testing:**
1. Log into the paper trading account at **https://paper.interactivebrokers.com**
2. Go to **Account → Account Settings → Reset Paper Trading Account**
3. Set the balance to **$250,000**

> Paper trading uses real market data and real order routing logic — the only difference is no real money changes hands. Run YRVI in paper mode for at least 4 weeks before going live.

---

## Step 9 — Find Your Credentials for YRVI

After your account is set up, gather these values for your `.env` file:

**`IBKR_USERNAME`**
- This is your IBKR login username (the one you created in Step 1)
- It's typically your email address or a short username you chose

**`IBKR_PASSWORD`**
- Your IBKR login password

**`ACCOUNT`**
- Log into the IBKR portal → **Account → Account Summary**
- Your account number is listed at the top
- Live accounts start with **`U`** (e.g., `U12345678`)
- Paper accounts start with **`DU`** (e.g., `DU12345678`)

```env
# For paper trading
IBKR_USERNAME=your_ibkr_username
IBKR_PASSWORD=your_ibkr_password
ACCOUNT=DU12345678
IBKR_PORT=4002          # 4002 = paper trading

# For live trading (when ready)
ACCOUNT=U12345678
IBKR_PORT=4001          # 4001 = live trading
```

---

## Step 10 — Install and Configure YRVI

> **Docker (recommended):** `setup_docker.sh` handles everything — IB Gateway runs inside a container automatically. Manual IB Gateway installation is not needed.

### Docker Setup (Recommended)

1. Install **[Rancher Desktop](https://rancherdesktop.io)** and enable the dockerd (moby) engine in Preferences → Container Engine.

2. ⚠️ **Configure Rancher Desktop to auto-start** — this is required so Docker is running before YRVI containers start after a reboot:
   - Open Rancher Desktop → **Preferences → Application**
   - Check ✅ **Automatically start at login**
   - Check ✅ **Start in background**
   - Click **Apply**

3. Run the one-command setup:
   ```bash
   git clone https://github.com/controllinghand/you_rock_fund.git you_rock_fund
   cd you_rock_fund
   bash setup_docker.sh
   ```

See [CONTAINERIZATION.md](CONTAINERIZATION.md) for the full guide including credentials, 2FA, and troubleshooting.

### Manual / Legacy Setup (macOS only)

If you're using the original launchd-based setup instead of Docker:

1. Go to: **https://www.interactivebrokers.com/en/trading/ibgateway-stable.php**
2. Click **"Download IB Gateway Stable"** — choose the correct macOS version:
   - **Apple Silicon (M4/M3/M2/M1):** `arm64` / Apple Silicon build
   - **Intel Mac:** `x64` / Intel build
3. Run the `.dmg` installer — the default install location is fine
4. Run `bash setup_ibc.sh` — this configures IB Gateway to launch automatically via launchd

> **IB Gateway vs TWS:** YRVI uses IB Gateway, not Trader Workstation (TWS). They serve the same API but IB Gateway is lightweight and headless — better for automated trading. Use IB Gateway ports: **4002** (paper) and **4001** (live).

---

---

## Preparing for Live Trading

Once you've run paper trading for at least 4 weeks and are ready to use real money, follow these steps to switch YRVI to live trading via the dashboard.

### Step 1 — Open a Live IBKR Account

If you've only been using a paper trading account, you'll need a funded live account:

1. Log into **https://www.interactivebrokers.com/portal**
2. Go to **Account → Open Additional Account** (or apply during your original signup)
3. Deposit funds via ACH (free, 3–5 days) or wire transfer
4. Confirm you have **Level 2 options approval** on the live account (same as paper)

> Your live account number starts with **`U`** (e.g., `U12345678`). Paper accounts start with `DU`.

### Step 2 — Add Live Credentials to .env

Open your `.env` file and add the live-specific credentials at the bottom:

```env
IBKR_USERNAME_LIVE=your_live_ibkr_username
IBKR_PASSWORD_LIVE=your_live_ibkr_password
ACCOUNT_LIVE=U12345678
```

These are kept separate from your paper credentials (`IBKR_USERNAME`, `IBKR_PASSWORD`, `ACCOUNT`) so you can switch back and forth safely.

> **Security note:** Your `.env` file is excluded from git (never uploaded to GitHub). Keep it on your local machine only.

### Step 3 — Restart YRVI

After editing `.env`, restart the YRVI API so it picks up the new environment variables:

```bash
# In the YRVI app, use the restart option
# Or from terminal:
launchctl stop com.yourockfund.api
launchctl start com.yourockfund.api
```

### Step 4 — Switch to Live in the Dashboard

1. Open the YRVI dashboard → **Settings**
2. Click **"Switch to Live"**
3. The dashboard checks that all three live credentials are set
4. If any are missing, a warning is shown with exactly which variables to add
5. If all credentials are configured, a confirmation modal shows your account number (masked) — type `CONFIRM` to proceed

When you confirm, YRVI automatically:
- Updates IB Gateway configuration with your live credentials
- Restarts IB Gateway pointed at port 4001 (live)
- Posts a Discord alert (if webhook is enabled)

> You do **not** need to manually edit `ibc_config.ini` or restart IB Gateway — the dashboard handles it.

---

## Common Issues & Solutions

| Problem | Solution |
|---------|----------|
| Options trading denied | Call IBKR (1-877-442-2757), explain CSP/CC strategy — they often approve manually |
| Account stuck "In Review" | Upload clearer ID photos; check spam folder for document requests |
| Can't find account number | Portal → Account → Account Summary (top of page) |
| Paper account not showing | Wait 24 hours after live account approval; may need to enable via portal |
| 2FA / authentication issues | Install the **IBKR Mobile** app and use it for login authentication |
| Wire transfer not credited | Call IBKR with your wire confirmation number — usually credited same day |
| Options order rejected | Verify your account has Level 2 options; check available cash collateral |

---

## ⚠️ Important Notes

- **Never share your password.** YRVI stores credentials only in your local `.env` file, which is excluded from git (never uploaded to GitHub).
- **Start with paper trading** for at least 4 weeks to validate the system before risking real capital.
- **Only use money you can afford to have tied up.** CSPs tie up collateral for the duration of the contract (typically 1 week). Stop losses are set at 10% below strike — this is the maximum per-position loss in a bad week.
- **Keep IB Gateway running.** YRVI connects to IB Gateway to place orders. If IB Gateway is closed, trades won't execute. With Docker, `setup_docker.sh` handles this automatically. With the legacy launchd setup, `setup_ibc.sh` configures it to start automatically on login.
- **Keep Rancher Desktop set to auto-start** (Docker setup only). If Rancher Desktop is not configured to start at login, Docker won't be available when YRVI containers try to restart after a reboot. Set this in Preferences → Application → ✅ Automatically start at login + ✅ Start in background.

---

## Timeline

| Day | Action |
|-----|--------|
| Day 1 | Submit IBKR application, upload ID documents |
| Day 2–3 | IBKR reviews and approves account |
| Day 3 | Install Rancher Desktop; enable auto-start (Preferences → Application) |
| Day 3 | Run `bash setup_docker.sh` — builds containers and installs login item |
| Day 3 | Paper trading begins via IB Gateway container |
| Week 1–4 | Run full YRVI system in paper mode, review results each Monday |
| Week 4–8 | Fund live account, switch `IBKR_PORT=4001`, go live |
