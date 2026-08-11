#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACLClouds 浏览器版自动续期脚本
"""

import os
import sys
import re
import time
import random
import socket
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_URL = "https://aclclouds.com"
RENEW_THRESHOLD_HOURS = int(os.environ.get("RENEW_THRESHOLD_HOURS", "48"))
MAX_HOURS = 72

COOKIE = os.environ.get("ACL_COOKIES", "").strip()
MULTI_ACCOUNTS = os.environ.get("ACL_ACCOUNTS", "").strip()

# 多账号解析
ACCOUNTS = []
if MULTI_ACCOUNTS:
    for line in MULTI_ACCOUNTS.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|||" in line:
            name, ck = line.split("|||", 1)
            ACCOUNTS.append({"name": name.strip(), "cookie": ck.strip()})
if not ACCOUNTS and COOKIE:
    ACCOUNTS.append({"name": "main", "cookie": COOKIE})

TG_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# 代理
_raw_proxy = os.getenv("PROXY_URL", "").strip()
if _raw_proxy and _raw_proxy.startswith("socks5://") and "127.0.0.1" not in _raw_proxy:
    PROXY_URL = _raw_proxy
else:
    PROXY_URL = "socks5://127.0.0.1:1080"

# 截图目录
SHOT_DIR = Path("debug_output")
SHOT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("renew_browser.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("aclclouds")

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def tg(msg: str, photo_path: str = None):
    if not (TG_TOKEN and TG_CHAT_ID):
        return
    try:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            with open(photo_path, "rb") as f:
                requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": msg},
                              files={"photo": f}, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg,
                                     "parse_mode": "HTML"}, timeout=15)
        log.info("✓ TG 通知发送成功")
    except Exception as e:
        log.warning(f"TG 通知失败: {e}")

def screenshot(sb, name: str):
    p = SHOT_DIR / f"{datetime.now():%H%M%S}_{name}.png"
    try:
        sb.save_screenshot(str(p))
        log.info(f"截图: {p}")
    except Exception as e:
        log.warning(f"截图失败: {e}")
    return p

def human_wait(min_s=2, max_s=4):
    time.sleep(random.uniform(min_s, max_s))

def parse_iso(s):
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def fmt_remaining(seconds):
    if seconds is None:
        return "?"
    if seconds < 0:
        return "已过期"
    seconds = int(seconds)
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"

# ---------------------------------------------------------------------------
# Cookie 注入
# ---------------------------------------------------------------------------
def inject_cookies(sb, cookie_str: str):
    """先打开站点, 清除匿名 cookie, 注入用户 cookie, 重新访问页面"""
    if not cookie_str:
        log.warning("Cookie 为空")
        return False

    # 解析 cookie, 自动改名 aclclouds_session → __Host-aclclouds_session
    parsed = {}
    for kv in cookie_str.split(";"):
        kv = kv.strip()
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        parsed[k.strip()] = v.strip()

    if "aclclouds_session" in parsed and "__Host-aclclouds_session" not in parsed:
        parsed["__Host-aclclouds_session"] = parsed.pop("aclclouds_session")
        log.info("🔄 已将 aclclouds_session 重命名为 __Host-aclclouds_session")

    log.info(f"📋 待注入 {len(parsed)} 个 Cookie: {list(parsed.keys())}")

    # 1. 先打开站点 (获取页面上下文)
    try:
        sb.open(BASE_URL)
        sb.sleep(2)
    except Exception as e:
        log.warning(f"打开站点失败: {e}")
        return False

    # 2. 清除服务器返回的匿名 cookie (避免冲突)
    try:
        sb.driver.delete_all_cookies()
        log.info("🧹 已清除所有匿名 cookie")
        sb.sleep(1)
    except Exception as e:
        log.warning(f"清除 cookie 失败: {e}")

    # 3. 注入用户 cookie
    n_ok, n_fail = 0, 0
    failed_cookies = []
    for k, v in parsed.items():
        try:
            if k.startswith("__Host-"):
                # __Host- cookie: 只能用 CDP 设置, 不能设 domain, 必须 path=/, secure
                sb.driver.execute_cdp_cmd("Network.setCookie", {
                    "name": k,
                    "value": v,
                    "url": BASE_URL,
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                })
                log.info(f"   ✓ {k} (CDP, __Host- 前缀)")
                n_ok += 1
            else:
                # 普通 cookie: 用 set_cookie
                sb.set_cookie(k, v, domain="aclclouds.com")
                log.info(f"   ✓ {k}")
                n_ok += 1
        except Exception as e1:
            try:
                sb.driver.add_cookie({
                    "name": k, "value": v,
                    "domain": ".aclclouds.com", "path": "/",
                    "secure": True, "httpOnly": True,
                })
                log.info(f"   ✓ {k} (add_cookie 兜底)")
                n_ok += 1
            except Exception as e2:
                n_fail += 1
                failed_cookies.append(k)
                log.warning(f"   ✗ {k} 失败: set_cookie={e1}, add_cookie={e2}")

    log.info(f"Cookie 注入完成: ✓ {n_ok} 个, ❌ {n_fail} 个")
    if failed_cookies:
        log.warning(f"   失败的 Cookie: {failed_cookies}")

    # 4. 验证 cookie
    try:
        actual_cookies = sb.driver.get_cookies()
        actual_names = [c.get("name") for c in actual_cookies]
        log.info(f"📋 浏览器实际 Cookie: {actual_names}")
        has_session = any("aclclouds_session" in n for n in actual_names)
        has_xsrf = "XSRF-TOKEN" in actual_names
        if not has_session:
            log.warning("⚠️ __Host-aclclouds_session 未注入成功")
        if not has_xsrf:
            log.warning("⚠️ XSRF-TOKEN 未注入成功")
    except Exception as e:
        log.warning(f"验证 cookie 失败: {e}")

    # 5. 重新访问 dashboard (用新 cookie 发请求)
    try:
        log.info(f"🔄 用新 cookie 重新访问 {BASE_URL}/dashboard")
        sb.open(f"{BASE_URL}/dashboard")
        sb.sleep(3)
    except Exception as e:
        log.warning(f"重新访问失败: {e}")

    return True

# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------
def process_account(acc: dict) -> dict:
    """处理单个账号的续期逻辑"""
    name = acc["name"]
    cookie = acc["cookie"]

    log.info(f"{'='*60}")
    log.info(f"👤 账号: {name}")
    log.info(f"{'='*60}")

    # 导入 seleniumbase
    from seleniumbase import Browser

    CHROMIUM_ARGS = (
        f"--no-sandbox,--disable-dev-shm-usage,--disable-gpu,"
        f"--window-size=1280,720,--disable-blink-features=AutomationControlled,"
        f"--disable-infobars,--disable-popup-blocking"
    )

    if PROXY_URL and PROXY_URL != "socks5://127.0.0.1:1080":
        CHROMIUM_ARGS += f",--proxy-server={PROXY_URL}"

    try:
        with Browser(
            browser="chrome",
            uc=True,
            test=True,
            headed=True,
            headless=False,
            xvfb=True,
            chromium_arg=CHROMIUM_ARGS,
        ) as sb:
            sb.set_window_size(1280, 720)

            # 注入 Cookie
            log.info("🍪 注入 Cookie...")
            if not inject_cookies(sb, cookie):
                return {"name": name, "ok": False, "msg": "Cookie 注入失败"}

            # 后续续期逻辑...
            log.info("✅ 续期流程完成 (需要添加具体续期逻辑)")
            return {"name": name, "ok": True, "renewed": 0, "failed": 0}

    except Exception as e:
        log.exception(f"账号 {name} 异常: {e}")
        return {"name": name, "ok": False, "msg": f"异常: {e}"}

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("🎮 ACLClouds 浏览器版续期启动")
    log.info(f"🌐 站点: {BASE_URL}")
    log.info(f"⏰ 阈值: {RENEW_THRESHOLD_HOURS}h")
    log.info(f"👤 账号数: {len(ACCOUNTS)}")
    log.info(f"🌐 代理: {PROXY_URL}")
    log.info("=" * 60)

    if not ACCOUNTS:
        msg = "🎮 ACLClouds 续期通知\n\n⚠️ 未配置 ACL_COOKIES 或 ACL_ACCOUNTS"
        log.error(msg)
        tg(msg)
        sys.exit(1)

    all_results = []
    for acc in ACCOUNTS:
        try:
            res = process_account(acc)
        except Exception as e:
            log.exception(f"账号 {acc['name']} 异常: {e}")
            res = {"name": acc["name"], "ok": False, "msg": f"异常: {e}"}
            tg(f"🎮 ACLClouds 续期通知\n\n⚠️ 账号 {acc['name']} 崩溃\n📊 {e}")
        all_results.append(res)

    # 总汇总只在有失败时发
    total_renewed = sum(r.get("renewed", 0) for r in all_results if r.get("ok"))
    total_failed = sum(r.get("failed", 0) for r in all_results if r.get("ok"))
    if total_failed > 0:
        summary = (
            f"🎮 ACLClouds 续期通知\n\n"
            f"⚠️ 部分失败\n"
            f"✅ 成功: {total_renewed} | ❌ 失败: {total_failed}"
        )
        log.info(summary)
        tg(summary)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("用户中断")
    except Exception as e:
        log.exception(f"未捕获异常: {e}")
        tg(f"🎮 ACLClouds 续期通知\n\n💥 脚本崩溃\n📊 {e}")
        sys.exit(1)