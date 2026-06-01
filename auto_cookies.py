"""
自动从浏览器提取 Mimo Cookies (静默方案 v2)
直接读取浏览器 Cookie 数据库，无需启动/关闭浏览器
支持 Edge 和 Chrome，零弹窗、零进程干扰

策略:
  1. 直接读 Cookie DB (如果浏览器没锁文件)
  2. 复制后读取
  3. 以管理员运行子脚本通过 shadowcopy 读取 (仅首次需 UAC 确认)
"""
import os
import sys
import json
import shutil
import sqlite3
import tempfile
import base64
import ctypes
import ctypes.wintypes as wt
import subprocess
from datetime import datetime

# 修复 OpenSSL legacy provider 问题
os.environ["CRYPTOGRAPHY_OPENSSL_NO_LEGACY"] = "1"


MIMO_DOMAIN = "xiaomimimo.com"

# ---------- Windows DPAPI ----------

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_decrypt(encrypted: bytes) -> bytes:
    blob_in = DATA_BLOB(len(encrypted),
                        ctypes.create_string_buffer(encrypted, len(encrypted)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise ctypes.WinError()
    data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return data


# ---------- AES-GCM (用 cryptography 库) ----------

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def aes_gcm_decrypt(nonce: bytes, ciphertext: bytes, tag: bytes, key: bytes, aad: bytes = None) -> bytes:
    """AES-GCM 解密"""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext + tag, aad)


def get_encryption_key(user_data_dir: str) -> bytes:
    local_state = os.path.join(user_data_dir, "Local State")
    with open(local_state, "r", encoding="utf-8") as f:
        data = json.load(f)
    encrypted_key = base64.b64decode(data["os_crypt"]["encrypted_key"])
    return dpapi_decrypt(encrypted_key[5:])


def decrypt_cookie_value(encrypted: bytes, aes_key: bytes = None, host: str = "") -> str:
    if not encrypted:
        return ""
    if encrypted[:3] in (b"v10", b"v20") and aes_key:
        raw = encrypted[3:]
        nonce = raw[:12]
        tag = raw[-16:]
        ciphertext = raw[12:-16]
        # v20 需要 hostname 作为 AAD
        aad = host.encode("utf-8") if encrypted[:3] == b"v20" and host else None
        return aes_gcm_decrypt(nonce, ciphertext, tag, aes_key, aad).decode("utf-8")
    try:
        return dpapi_decrypt(encrypted).decode("utf-8")
    except Exception:
        return ""


# ---------- 浏览器 Cookie 读取 ----------

BROWSER_DATA = {
    "Edge": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
    "Chrome": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
}


def _find_cookie_db(user_data: str) -> str:
    candidates = [
        os.path.join(user_data, "Default", "Cookies"),
        os.path.join(user_data, "Default", "Network", "Cookies"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    for item in os.listdir(user_data):
        for sub in ("", "Network"):
            candidate = os.path.join(user_data, item, sub, "Cookies")
            if os.path.isfile(candidate):
                return candidate
    return ""


def _extract_cookies_from_db(cookie_db: str, user_data: str) -> str:
    """从 Cookie 数据库提取 mimo cookies"""
    aes_key = None
    try:
        aes_key = get_encryption_key(user_data)
    except Exception:
        pass

    conn = sqlite3.connect(cookie_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE ?",
        (f"%{MIMO_DOMAIN}%",)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return ""

    parts = []
    for host, name, enc_val in rows:
        value = decrypt_cookie_value(enc_val, aes_key, host=host)
        if not value:
            continue
        if "servicetoken" in name.lower():
            parts.append(f'{name}="{value}"')
        else:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def _try_direct_read(cookie_db: str, user_data: str) -> str:
    """方法1: 直接用 sqlite3 只读模式打开"""
    uri = "file:" + cookie_db.replace("\\", "/")
    for opts in ["?mode=ro", "?mode=ro&nolock=1", "?mode=ro&immutable=1"]:
        try:
            conn = sqlite3.connect(uri + opts, uri=True)
            cur = conn.cursor()
            cur.execute("SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE ?",
                        (f"%{MIMO_DOMAIN}%",))
            rows = cur.fetchall()
            conn.close()
            if rows:
                aes_key = None
                try:
                    aes_key = get_encryption_key(user_data)
                except Exception:
                    pass
                parts = []
                for host, name, enc_val in rows:
                    value = decrypt_cookie_value(enc_val, aes_key, host=host)
                    if value:
                        if "servicetoken" in name.lower():
                            parts.append(f'{name}="{value}"')
                        else:
                            parts.append(f"{name}={value}")
                return "; ".join(parts)
        except Exception:
            continue
    return ""


def _try_copy_read(cookie_db: str, user_data: str) -> str:
    """方法2: 复制数据库后读取"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        shutil.copy2(cookie_db, tmp.name)
        return _extract_cookies_from_db(tmp.name, user_data)
    except Exception:
        return ""
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _find_python() -> str:
    """找到系统 Python 解释器（打包后 sys.executable 指向 EXE，不是 Python）"""
    # 1. 如果没被打包，直接用 sys.executable
    if not getattr(sys, 'frozen', False):
        return sys.executable

    # 2. 试 py launcher（Windows Python Launcher）
    try:
        r = subprocess.run(["py", "-3", "-c", "import sys; print(sys.executable)"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            path = r.stdout.strip()
            if os.path.exists(path):
                return path
    except Exception:
        pass

    # 3. 试 PATH 里的 python
    for cmd in ("python", "python3"):
        try:
            r = subprocess.run([cmd, "-c", "import sys; print(sys.executable)"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                path = r.stdout.strip()
                if os.path.exists(path):
                    return path
        except Exception:
            continue

    # 4. 常见安装路径
    for p in (
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python39", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python310", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe"),
        r"C:\Python39\python.exe",
        r"C:\Python310\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python312\python.exe",
    ):
        if os.path.exists(p):
            return p

    return ""


def _try_admin_read(cookie_db: str, user_data: str) -> str:
    """方法3: 以管理员权限运行 rookiepy 解密 v130+ app-bound cookies"""
    result_file = os.path.join(tempfile.gettempdir(), "mimo_cookies_result.txt")
    log_file = result_file + ".log"
    helper_script = os.path.join(tempfile.gettempdir(), "mimo_cookie_helper.py")

    # 从模板生成 helper 脚本
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "_cookie_helper_template.py")
    if not os.path.exists(template_path):
        return ""

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    helper_content = template.replace("@RESULT_FILE@", result_file)

    with open(helper_script, "w", encoding="utf-8") as f:
        f.write(helper_content)

    # 清理旧文件
    for p in (result_file, log_file):
        try:
            os.unlink(p)
        except Exception:
            pass

    # 以管理员运行 helper
    try:
        import time
        python_exe = _find_python()
        if not python_exe:
            return ""
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas",
            python_exe,
            f'"{helper_script}"',
            None, 1  # SW_SHOWNORMAL — UAC 弹窗需要可见
        )
        if ret <= 32:
            return ""

        # 等待结果文件出现
        for _ in range(60):
            time.sleep(0.5)
            if os.path.exists(result_file):
                break
        else:
            return ""

        time.sleep(0.3)
        with open(result_file, "r", encoding="utf-8") as f:
            result = f.read().strip()

        return result
    except Exception:
        return ""


def read_browser_cookies(browser_name: str, user_data: str) -> str:
    """静默读取浏览器 cookies — 依次尝试 3 种方法"""
    cookie_db = _find_cookie_db(user_data)
    if not cookie_db:
        raise FileNotFoundError(f"未找到 {browser_name} 的 Cookie 数据库")

    # 方法1: 直接读
    result = _try_direct_read(cookie_db, user_data)
    if result:
        return result

    # 方法2: 复制后读
    result = _try_copy_read(cookie_db, user_data)
    if result:
        return result

    # 方法3: 管理员权限读
    result = _try_admin_read(cookie_db, user_data)
    if result:
        return result

    raise RuntimeError(f"无法读取 {browser_name} 的 Cookies (文件被锁定)")


def update_config(cookies: str):
    if os.name == "nt":
        config_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "MiMoMonitor", "config.json"
        )
    else:
        config_path = os.path.join(
            os.path.expanduser("~"), ".config", "MiMoMonitor", "config.json"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["mimo_cookies"] = cookies
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cookies 已更新")


def get_cookies_silent() -> str:
    errors = []
    for name, data_dir in BROWSER_DATA.items():
        if not os.path.isdir(data_dir):
            continue
        try:
            cookies = read_browser_cookies(name, data_dir)
            if cookies:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 从 {name} 获取成功")
                return cookies
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise RuntimeError("获取失败:\n" + "\n".join(errors))


if __name__ == "__main__":
    try:
        cookies = get_cookies_silent()
        if cookies:
            update_config(cookies)
            print("成功！")
        else:
            print("未获取到 Cookies，请先在浏览器中登录 Mimo")
    except Exception as e:
        print(f"失败: {e}")
