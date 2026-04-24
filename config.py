import os
from dotenv import load_dotenv

load_dotenv()

# ── You Rock Volatility Income Fund ──────────────────────────
IBKR_HOST      = os.environ["IBKR_HOST"]
IBKR_PORT      = int(os.environ["IBKR_PORT"])   # IB Gateway: 4002 = paper, 4001 = live
IBKR_CLIENT_ID = int(os.environ["IBKR_CLIENT_ID"])
ACCOUNT        = os.environ["ACCOUNT"]

# Fund parameters
TOTAL_FUND_BUDGET   = 250_000    # total capital to deploy ← change this anytime
TARGET_PER_POSITION = 50_000     # target per position
MAX_PER_POSITION    = 70_000     # never exceed this per position
NUM_POSITIONS       = 5          # top N targets
WEEKLY_INCOME_GOAL  = 0.01       # 1% per week

# IBKR client IDs — each module gets its own to allow concurrent connections
IBKR_CLIENT_ID_WHEEL = 2        # wheel_manager.py
IBKR_CLIENT_ID_RISK  = 3        # risk_manager.py

# Execution
EXECUTE_HOUR_PST = 10            # 10AM PST Monday
EXECUTE_MINUTE   = 0

# Screener API
RENDER_URL    = os.environ["RENDER_URL"]
RENDER_SECRET = os.environ["RENDER_SECRET"]
