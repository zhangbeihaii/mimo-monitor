import requests
import time
import calendar
from urllib.parse import quote


BASE_URL = "https://platform.xiaomimimo.com"


def _headers(cookies: str) -> dict:
    return {
        "Cookie": cookies,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-timezone": "Asia/Shanghai",
        "origin": BASE_URL,
        "Referer": f"{BASE_URL}/console/plan-manage",
    }


def _extract_cookie(cookies: str, name: str) -> str:
    """从cookie字符串中提取指定name的值"""
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part[len(name) + 1:].strip().strip('"')
    return ""


def get_usage(cookies: str) -> dict:
    """查询Mimo套餐token用量

    Returns:
        {
            "plan_used", "plan_limit", "plan_percent",
            "comp_used", "comp_limit", "comp_percent",
        }
    """
    resp = requests.get(
        f"{BASE_URL}/api/v1/tokenPlan/usage",
        headers=_headers(cookies),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "未知错误"))

    usage_items = data.get("data", {}).get("usage", {}).get("items", [])

    plan = next((i for i in usage_items if i["name"] == "plan_total_token"), {})
    comp = next((i for i in usage_items if i["name"] == "compensation_total_token"), {})

    return {
        "plan_used": plan.get("used", 0),
        "plan_limit": plan.get("limit", 0),
        "plan_percent": plan.get("percent", 0),
        "comp_used": comp.get("used", 0),
        "comp_limit": comp.get("limit", 0),
        "comp_percent": comp.get("percent", 0),
    }


def get_plan_detail(cookies: str) -> dict:
    """查询套餐详情（有效期等）

    Returns:
        {"plan_name", "period_end", "expired", "auto_renew"}
    """
    resp = requests.get(
        f"{BASE_URL}/api/v1/tokenPlan/detail",
        headers=_headers(cookies),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "未知错误"))

    d = data.get("data", {})
    return {
        "plan_name": d.get("planName", ""),
        "period_end": d.get("currentPeriodEnd", ""),
        "expired": d.get("expired", False),
        "auto_renew": d.get("enableAutoRenew", False),
    }


def get_history(cookies: str, year: int = 0, month: int = 0) -> dict:
    """查询历史用量，按模型返回每日数据

    Returns:
        {
            "mimo-v2.5-pro": [(timestamp, total_tokens), ...],
            "mimo-v2.5": [(timestamp, total_tokens), ...],
            ...
        }
    """
    if year == 0 or month == 0:
        now = time.localtime()
        year, month = now.tm_year, now.tm_mon

    ph = _extract_cookie(cookies, "api-platform_ph")
    url = f"{BASE_URL}/api/v1/usage/token-plan/list"
    if ph:
        url += f"?api-platform_ph={quote(ph)}"

    resp = requests.post(
        url,
        headers=_headers(cookies),
        json={"year": year, "month": month},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(data.get("message", "未知错误"))

    records = data.get("data", [])

    # 按模型分组
    models = {}
    for rec in records:
        date_str = rec.get("date", "")
        model = rec.get("model", "unknown")
        total = rec.get("totalToken", 0)
        if not date_str:
            continue
        ts = time.mktime(time.strptime(date_str[:10], "%Y-%m-%d"))
        if model not in models:
            models[model] = {}
        models[model][ts] = total

    # 转为排序列表
    result = {}
    for model, daily in models.items():
        result[model] = sorted(daily.items())

    return result
