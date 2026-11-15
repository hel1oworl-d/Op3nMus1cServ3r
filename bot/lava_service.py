import hmac
import hashlib
import json
import aiohttp
import config

LAVA_API_URL = "https://api.lava.ru/business/invoice"

def generate_signature(data: dict) -> str:
    """Генерация HMAC SHA256 подписи по документации Lava Business API."""
    json_bytes = json.dumps(data, separators=(',', ':')).encode("utf-8")
    return hmac.new(config.LAVA_SECRET_KEY.encode("utf-8"), json_bytes, hashlib.sha256).hexdigest()

async def create_invoice(amount: float, order_id: str, comment: str) -> dict | None:
    """POST /business/invoice/create"""
    if not config.LAVA_PROJECT_ID or not config.LAVA_SECRET_KEY:
        return None

    payload = {
        "sum": float(amount),
        "orderId": str(order_id),
        "shopId": config.LAVA_PROJECT_ID,
        "comment": comment,
        "expirePeriod": 300
    }
    signature = generate_signature(payload)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Signature": signature
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{LAVA_API_URL}/create", json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("status") == 200 and data.get("data"):
                    return data["data"]
                return None
        except Exception:
            return None

async def check_invoice_status(invoice_id: str, order_id: str) -> str | None:
    """POST /business/invoice/status"""
    if not config.LAVA_PROJECT_ID or not config.LAVA_SECRET_KEY:
        return None

    payload = {
        "shopId": config.LAVA_PROJECT_ID,
        "orderId": str(order_id),
        "invoiceId": str(invoice_id)
    }
    signature = generate_signature(payload)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Signature": signature
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{LAVA_API_URL}/status", json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("status") == 200:
                    status_val = data.get("data", {}).get("status")
                    return str(status_val).lower() if status_val else None
                return None
        except Exception:
            return None
