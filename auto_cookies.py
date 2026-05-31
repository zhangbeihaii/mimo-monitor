"""
自动从 Edge 提取 Mimo Cookies (远程调试协议方案)
需要先关闭 Edge，再以调试模式重启
"""
import os
import json
import time
import subprocess
import requests
from datetime import datetime


DEBUG_PORT = 9222


def kill_edge():
    """关闭 Edge"""
    subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
    time.sleep(1)


def start_edge_debug():
    """以调试模式启动 Edge"""
    edge_path = None
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(p):
            edge_path = p
            break
    if not edge_path:
        raise FileNotFoundError("找不到 Edge")

    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    subprocess.Popen([
        edge_path,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={user_data}",
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
    try:
        kill_edge()
        start_edge_debug()
        cookies = get_cookies_via_cdp()
        if cookies:
            update_config(cookies)
            print("成功！")
        else:
            print("未获取到 cookies，请先在 Edge 中登录 Mimo")
    except Exception as e:
        print(f"失败: {e}")
    finally:
        # 恢复正常 Edge
        kill_edge()
        time.sleep(1)
        edge_path = None
        for p in [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.exists(p):
                edge_path = p
                break
        if edge_path:
            user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
            subprocess.Popen([edge_path, f"--user-data-dir={user_data}", "--profile-directory=Default"])
