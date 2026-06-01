"""
自动从浏览器提取 Mimo Cookies (远程调试协议方案)
支持 Edge 和 Chrome
"""
import os
import json
import time
import subprocess
import requests
from datetime import datetime


DEBUG_PORT = 9222

# 浏览器配置
BROWSERS = [
    {
        "name": "Edge",
        "process": "msedge.exe",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "user_data": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
    },
    {
        "name": "Chrome",
        "process": "chrome.exe",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "user_data": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
    },
]


def find_browser():
    """找到可用的浏览器"""
    for browser in BROWSERS:
        for path in browser["paths"]:
            if os.path.exists(path):
                return browser, path
    return None, None


def kill_browser(process_name):
    """关闭浏览器"""
    subprocess.run(["taskkill", "/F", "/IM", process_name], capture_output=True)
    time.sleep(1)


def start_browser_debug(browser, browser_path):
    """以调试模式启动浏览器"""
    subprocess.Popen([
        browser_path,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={browser['user_data']}",
        "--profile-directory=Default",
        "--remote-allow-origins=*",
        "https://platform.xiaomimimo.com/console/plan-manage",
    ])
    time.sleep(3)


def get_cookies_via_cdp() -> str:
    """通过 CDP 协议获取 cookies"""
    # 获取所有 tab
    resp = requests.get(f"http://localhost:{DEBUG_PORT}/json", timeout=5)
    tabs = resp.json()

    ws_url = None
    for tab in tabs:
        if "mimo" in tab.get("url", "").lower():
            ws_url = tab.get("webSocketDebuggerUrl")
            break

    if not ws_url:
        # 用第一个 tab
        ws_url = tabs[0].get("webSocketDebuggerUrl") if tabs else None

    if not ws_url:
        raise RuntimeError("无法获取调试连接")

    # 用 websocket 获取 cookies
    import websocket
    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({
        "id": 1,
        "method": "Network.getCookies",
        "params": {"urls": ["https://platform.xiaomimimo.com"]}
    }))
    result = json.loads(ws.recv())
    ws.close()

    cookies = result.get("result", {}).get("cookies", [])
    mimo_cookies = []
    for c in cookies:
        name = c["name"]
        value = c["value"].strip('"')
        if "serviceToken" in name:
            mimo_cookies.append(f'{name}="{value}"')
        else:
            mimo_cookies.append(f"{name}={value}")

    return "; ".join(mimo_cookies)


def update_config(cookies: str):
    """更新 config.json"""
    if os.name == 'nt':
        config_path = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "MiMoMonitor", "config.json")
    else:
        config_path = os.path.join(os.path.expanduser('~'), '.config', "MiMoMonitor", "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["mimo_cookies"] = cookies
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cookies 已更新")


if __name__ == "__main__":
    browser, browser_path = find_browser()
    if not browser:
        print("未找到 Edge 或 Chrome 浏览器")
        exit(1)

    try:
        print(f"使用 {browser['name']}...")
        kill_browser(browser["process"])
        start_browser_debug(browser, browser_path)

        # 等待调试端口就绪
        for i in range(15):
            try:
                resp = requests.get(f"http://localhost:{DEBUG_PORT}/json", timeout=1)
                if resp.status_code == 200:
                    break
            except:
                time.sleep(1)

        cookies = get_cookies_via_cdp()
        if cookies:
            update_config(cookies)
            print("成功！")
        else:
            print(f"未获取到 cookies，请先在 {browser['name']} 中登录 Mimo")
    except Exception as e:
        print(f"失败: {e}")
    finally:
        kill_browser(browser["process"])
