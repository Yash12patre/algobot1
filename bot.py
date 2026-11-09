import os
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = (os.getenv("DHAN_CLIENT_ID") or "").strip()
ACCESS_TOKEN = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
BASE_URL = "https://api.dhan.co/v2"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()],
)

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "access-token": ACCESS_TOKEN,
        "client-id": CLIENT_ID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504],
                  allowed_methods=["GET"])  # never auto-retry POSTs (orders!)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

def diagnose_connection(session: requests.Session) -> bool:
    if not CLIENT_ID or not ACCESS_TOKEN:
        logging.error("DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN missing in .env")
        return False

    url = f"{BASE_URL}/fundlimit"  # Trading API, no Data API subscription needed
    logging.info(f"GET {url}")
    try:
        r = session.get(url, timeout=15)
    except requests.exceptions.SSLError as e:
        logging.error(f"TLS error (antivirus HTTPS scanning / old OpenSSL?): {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Connection dropped before any response (network/firewall/VPN): {e}")
        return False
    except requests.exceptions.Timeout:
        logging.error("Request timed out")
        return False

    logging.info(f"Status: {r.status_code}")
    if r.ok:
        logging.info(f"Connected. Funds response: {r.json()}")
        return True

    # Dhan returns a JSON error body; log it instead of guessing the cause
    logging.error(f"API error {r.status_code}: {r.text}")
    if r.status_code == 401:
        logging.error("Token invalid or expired. Regenerate it in web.dhan.co > Profile > Access DhanHQ APIs.")
    return False

def check_ltp(session: requests.Session) -> None:
    """Needs the Data API subscription. Reliance NSE_EQ id = 2885."""
    r = session.post(f"{BASE_URL}/marketfeed/ltp", json={"NSE_EQ": [2885]}, timeout=15)
    logging.info(f"LTP status {r.status_code}: {r.text}")

if __name__ == "__main__":
    s = make_session()
    if diagnose_connection(s):
        check_ltp(s)