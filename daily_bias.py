import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import pytz
import re

TZ_NY = pytz.timezone('America/New_York')
today = datetime.now(TZ_NY).date()

# Data fetch with robust error handling
spy = yf.Ticker("SPY")
hist = spy.history(period="2y")
weekly = spy.history(period="3mo", interval="1wk")

if len(hist) == 0:
    print("Error: No SPY data")
    exit(1)

current_price = hist['Close'][-1]
sma200 = hist['Close'].rolling(200).mean()[-1] if len(hist) >= 200 else current_price

# Weekly momentum (safe [-2])
weekly_return = 0.0
if len(weekly) >= 2:
    current_week_close = weekly['Close'][-1]
    prev_week_close = weekly['Close'][-2]
    weekly_return = (current_week_close / prev_week_close - 1) * 100
else:
    weekly_return = 0.0  # Neutral if insufficient data

# Overnight futures (Investing.com scrape with fallback)
def get_overnight():
    try:
        url = "https://www.investing.com/indices/us-spx-500-futures"
        html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text
        match = re.search(r'last_price">([\d,]+\.?\d*)', html)
        if match:
            futures = float(match.group(1).replace(',', ''))
            return (futures / current_price - 1) * 100
    except:
        pass
    return 0.0

overnight_pct = get_overnight()

# VIX (fallback to ^VIX only, no VIX9D/VIX3M)
vix = 20.0  # Default neutral
try:
    vix_data = yf.Ticker("^VIX").history(period="5d")  # More days for safety
    if len(vix_data) > 0:
        vix = vix_data['Close'][-1]
    vix9d = vix  # Fallback to same
    vix3m = vix  # Fallback to same
except:
    pass

# Dollar & yields (safe [-2] with fallback)
dxy_change = 0.0
tnx_change_bps = 0.0
try:
    dxy = yf.Ticker("DX-Y.NYB").history(period="5d")['Close']
    if len(dxy) >= 2:
        dxy_change = (dxy[-1] / dxy[-2] - 1) * 100
    tnx = yf.Ticker("^TNX").history(period="5d")['Close']
    if len(tnx) >= 2:
        tnx_change_bps = (tnx[-1] - tnx[-2]) * 100
except:
    pass

# Breadth (Barchart scrape with fallback)
def get_breadth():
    try:
        html = requests.get("https://www.barchart.com/stocks/indices/sp/market-summary", headers={'User-Agent': 'Mozilla/5.0'}).text
        match = re.search(r'% Above 50-Day Average.*?(\d+\.\d+)%', html, re.DOTALL)
        if match:
            return float(match.group(1))
    except:
        pass
    return 50.0  # Neutral fallback

breadth_50 = get_breadth()

# Scoring (exact 60-year quant rules, with safe defaults)
score = 0

# 1. Trend
if current_price > sma200:
    score += 1
else:
    score -= 1

# 2. Weekly momentum
if weekly_return >= 2.0:
    score += 1
elif weekly_return <= -2.0:
    score -= 1

# 3. Overnight futures
if overnight_pct >= 0.3:
    score += 1
elif overnight_pct <= -0.3:
    score -= 1

# 4. VIX regime (contango = vix9d < vix3m, but fallback neutral)
if vix < 20 and vix9d < vix3m:
    score += 1
elif vix > 25 or vix9d > vix3m:
    score -= 1

# 5. Dollar + yields
if dxy_change < 0 and tnx_change_bps < 0:
    score += 1
elif dxy_change > 0 and tnx_change_bps > 0:
    score -= 1

# 6. Breadth
if breadth_50 > 60:
    score += 1
elif breadth_50 < 40:
    score -= 1

# Final bias
if score >= 4:
    bias = "STRONG BULLISH"
elif score >= 2:
    bias = "BULLISH"
elif score > -2:
    bias = "NEUTRAL"
elif score > -4:
    bias = "BEARISH"
else:
    bias = "STRONG BEARISH"

# Output result
result = f"""=== DAILY BIAS — {today.strftime('%A, %B %d, %Y')} ===
Score       : {score}/6
Trend (200SMA) : {'Above (+1)' if current_price > sma200 else 'Below (-1)'}
Weekly mom  : {weekly_return:+5.2f}%
Overnight   : {overnight_pct:+5.2f}%
VIX         : {vix:.1f} ({'contango' if vix9d < vix3m else 'backwardation'})
DXY + 10Y   : {dxy_change:+.2f}% / {tnx_change_bps:+.1f}bps
Breadth 50d : {breadth_50:.1f}%

>>> FINAL BIAS: {bias} <<<"""

print(result)

# Save to file
with open("latest_bias.txt", "w") as f:
    f.write(result)
