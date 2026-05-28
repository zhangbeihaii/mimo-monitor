import requests


def get_balance(api_key: str) -> dict:
    """查询DeepSeek账户余额和token用量"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    resp = requests.get("https://api.deepseek.com/user/balance", headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
