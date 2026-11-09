import math
from datetime import datetime

def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs_price(spot, strike, expiry_dt, iv, opt_type, r=0.07):
    secs = max((expiry_dt - datetime.now()).total_seconds(), 60)
    T = secs / (365 * 24 * 3600)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if opt_type == "CE":
        p = spot * _cdf(d1) - strike * math.exp(-r * T) * _cdf(d2)
    else:
        p = strike * math.exp(-r * T) * _cdf(-d2) - spot * _cdf(-d1)
    return round(max(p, 0.05) / 0.05) * 0.05