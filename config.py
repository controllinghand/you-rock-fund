import os
from dotenv import load_dotenv

load_dotenv()

# ── You Rock Volatility Income Fund ──────────────────────────
IBKR_HOST      = os.environ["IBKR_HOST"]
IBKR_PORT      = int(os.environ["IBKR_PORT"])   # 7497 = paper, 7496 = live
IBKR_CLIENT_ID = int(os.environ["IBKR_CLIENT_ID"])
ACCOUNT        = os.environ["ACCOUNT"]

# Fund parameters
TOTAL_FUND_BUDGET   = 250_000    # total capital to deploy ← change this anytime
TARGET_PER_POSITION = 50_000     # target per position
MAX_PER_POSITION    = 70_000     # never exceed this per position
NUM_POSITIONS       = 5          # top N targets
WEEKLY_INCOME_GOAL  = 0.01       # 1% per week

# Risk management
STOP_LOSS_PCT    = 0.10          # sell stock if 10% below assignment strike

# Execution
EXECUTE_HOUR_PST = 10            # 10AM PST Monday
EXECUTE_MINUTE   = 0

# Screener API
RENDER_URL    = os.environ["RENDER_URL"]
RENDER_SECRET = os.environ["RENDER_SECRET"]
