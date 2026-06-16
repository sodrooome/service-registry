import os
from dotenv import load_dotenv

load_dotenv()

# default headers for the health check request to downstream services, you can modify this as needed
# this is used for bypassing the CloudFlare protection which gives you 403 forbidden if you don't have the correct headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# downstream services that you want to monitor the health, you can register it here or through the API
DOWNSTREAM_SERVICES = {
    "Maukerja-Server": os.getenv("MAUKERJA_SERVER"),
    "V3-API-BE": os.getenv("V3_API_BE"),
    "BE-Chat-Health": os.getenv("BE_CHAT_HEALTH"),
    "FE-Chat-Health-Node-Proxy": os.getenv("FE_CHAT_HEALTH_NODE_PROXY"),
    "FE-Chat-Health-Apache-Proxy": os.getenv("FE_CHAT_HEALTH_APACHE_PROXY"),
}
