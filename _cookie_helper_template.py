# -*- coding: utf-8 -*-
"""
Mimo Cookie 提取助手 — 以管理员权限运行
使用 rookiepy 读取 Edge v130+ 的 app-bound 加密 cookies
"""
import os
import sys
import traceback

# === 占位符（由主脚本替换） ===
RESULT_FILE = r"@RESULT_FILE@"
LOG_FILE = RESULT_FILE + ".log"

log_lines = []
MIMO_DOMAINS = ["xiaomimimo.com", "xiaomi.com", "mi.com"]
REQUIRED_COOKIES = {
    "serviceToken", "api-platform_serviceToken",
    "api-platform_ph", "api-platform_slh",
    "userId", "xiaomichatbot_ph",
}


def log(msg):
    log_lines.append(str(msg))


def main():
    log("helper started")

    try:
        import rookiepy
        log("rookiepy imported")

        # 用 rookiepy 获取 mimo cookies（需要管理员权限）
        cookies = rookiepy.edge(domains=MIMO_DOMAINS)
        log(f"found {len(cookies)} cookies")

        # 格式化为 "name=value; name2=value2" 格式
        seen = set()
        parts = []
        for c in cookies:
            name = c["name"]
            if name not in REQUIRED_COOKIES or name in seen:
                continue
            value = c["value"].strip('"')
            seen.add(name)
            if "servicetoken" in name.lower():
                parts.append(f'{name}="{value}"')
            else:
                parts.append(f"{name}={value}")
            log(f"  {name} = {value[:30]}...")

        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write("; ".join(parts))
        log("OK")

    except Exception:
        log(traceback.format_exc())
        log("FAIL")
    finally:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))


if __name__ == "__main__":
    main()
