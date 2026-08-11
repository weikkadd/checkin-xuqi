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
import urllib.parse
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_URL = "https://aclclouds.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
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
        # Driver() 模式下 sb 是 webdriver 本身, save_screenshot 是 webdriver 方法
        if hasattr(sb, 'driver') and sb.driver is not None:
            sb.driver.save_screenshot(str(p))
        else:
            sb.save_screenshot(str(p))
        log.info(f"截图: {p}")
    except Exception as e:
        log.warning(f"截图失败: {e}")
    return p

# ---------------------------------------------------------------------------
# API 函数 (从 renew.py 移植)
# ---------------------------------------------------------------------------
def build_session(cookie_str):
    """构造 requests session, 注入 cookie, 用于 API 调用"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/projects",
        "X-Requested-With": "XMLHttpRequest",
        "Accept-Encoding": "gzip, deflate, br",
    })
    # 解析 cookie 字符串 - 处理 __Host- 和 __Secure- 前缀
    for kv in cookie_str.split(";"):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        k = k.strip()
        v = v.strip()
        clean_k = k
        if k.startswith("__Host-"):
            clean_k = k[7:]
        elif k.startswith("__Secure-"):
            clean_k = k[9:]
        s.cookies.set(clean_k, v, domain="aclclouds.com", path="/")
    return s


def get_xsrf(session):
    """从 cookie 中提取并解码 XSRF-TOKEN"""
    token = session.cookies.get("XSRF-TOKEN", domain="aclclouds.com")
    if not token:
        return None
    return urllib.parse.unquote(token)


def api_get(session, path):
    """GET 请求, 必须带 X-XSRF-TOKEN (Laravel CSRF)"""
    headers = {}
    token = get_xsrf(session)
    if token:
        headers["X-XSRF-TOKEN"] = token
    return session.get(f"{BASE_URL}{path}", headers=headers, timeout=30)


def api_post(session, path, payload=None):
    headers = {}
    token = get_xsrf(session)
    if token:
        headers["X-XSRF-TOKEN"] = token
    return session.post(f"{BASE_URL}{path}", headers=headers, json=payload or {}, timeout=30)


def list_servers(session):
    """GET /api/client 获取服务器列表"""
    r = api_get(session, "/api/client")
    r.raise_for_status()
    j = r.json()
    if isinstance(j, dict):
        return j.get("data", [])
    return j if isinstance(j, list) else []


def server_detail(session, sid):
    """GET /api/client/servers/{sid} 获取服务器详情"""
    r = api_get(session, f"/api/client/servers/{sid}")
    if r.status_code != 200:
        return None
    try:
        j = r.json()
        return j.get("attributes", j) if isinstance(j, dict) else j
    except Exception:
        return None


def find_expire(attrs, detail=None):
    """从多个可能字段找到期时间"""
    candidates = []
    if attrs:
        candidates.append(attrs)
    if detail:
        candidates.append(detail)
    for c in list(candidates):
        rel = c.get("relationships") if isinstance(c, dict) else None
        if rel:
            candidates.append(rel)
    for c in candidates:
        if not isinstance(c, dict):
            continue
        for key in ("expires_at", "expire_at", "renew_at", "renewable_at",
                    "expiration_date", "expires", "expiry"):
            v = c.get(key)
            if v:
                return key, v
    return None, None


def renew_server_api(session, sid):
    """调用续期 API: POST /api/client/servers/{sid}/upgrade/renew
    返回 (response, captcha_required_bool)"""
    r = api_post(session, f"/api/client/servers/{sid}/upgrade/renew")
    captcha_required = False
    if r.status_code == 403:
        try:
            j = r.json()
            if isinstance(j, dict) and j.get("code") == "captcha_required":
                captcha_required = True
        except Exception:
            pass
    return r, captcha_required


def test_login(session):
    """测试登录状态, 返回 True/False"""
    try:
        r = api_get(session, "/api/client")
        return r.status_code != 401
    except Exception:
        return False

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
    """先打开站点, 清除匿名 cookie, 注入用户 cookie, 重新访问页面

    注意: sb 在 Driver() 模式下就是 webdriver (Chrome) 本身, 没有 sb.driver
         在 SB() 模式下 sb 是 BaseCase, 真正的 driver 是 sb.driver
         这里自动检测两种模式
    """
    if not cookie_str:
        log.warning("Cookie 为空")
        return False

    # 自动检测: SB() 模式还是 Driver() 模式
    # SB() 返回 BaseCase, 有 .driver 属性
    # Driver() 返回 Chrome webdriver 本身, 没有 .driver 属性
    if hasattr(sb, 'driver') and sb.driver is not None:
        driver = sb.driver
        is_sb_mode = True
    else:
        driver = sb  # Driver() 模式下 sb 就是 driver
        is_sb_mode = False

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
        if is_sb_mode:
            sb.open(BASE_URL)
            sb.sleep(2)
        else:
            # Driver() 模式: 直接用 webdriver API
            driver.get(BASE_URL)
            import time as _time
            _time.sleep(2)
    except Exception as e:
        log.warning(f"打开站点失败: {e}")
        return False

    # 2. 清除服务器返回的匿名 cookie (避免冲突)
    try:
        driver.delete_all_cookies()
        log.info("🧹 已清除所有匿名 cookie")
        import time as _time
        _time.sleep(1)
    except Exception as e:
        log.warning(f"清除 cookie 失败: {e}")

    # 3. 注入用户 cookie
    n_ok, n_fail = 0, 0
    failed_cookies = []
    for k, v in parsed.items():
        try:
            if k.startswith("__Host-"):
                # __Host- cookie: 只能用 CDP 设置, 不能设 domain, 必须 path=/, secure
                driver.execute_cdp_cmd("Network.setCookie", {
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
                # 普通 cookie: 用 add_cookie (webdriver 标准 API)
                driver.add_cookie({
                    "name": k, "value": v,
                    "domain": ".aclclouds.com", "path": "/",
                    "secure": True, "httpOnly": False,
                })
                log.info(f"   ✓ {k}")
                n_ok += 1
        except Exception as e1:
            # 兜底: 尝试用 CDP 设置普通 cookie
            try:
                driver.execute_cdp_cmd("Network.setCookie", {
                    "name": k,
                    "value": v,
                    "url": BASE_URL,
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,
                    "sameSite": "Lax",
                })
                log.info(f"   ✓ {k} (CDP 兜底)")
                n_ok += 1
            except Exception as e2:
                n_fail += 1
                failed_cookies.append(k)
                log.warning(f"   ✗ {k} 失败: add_cookie={e1}, CDP={e2}")

    log.info(f"Cookie 注入完成: ✓ {n_ok} 个, ❌ {n_fail} 个")
    if failed_cookies:
        log.warning(f"   失败的 Cookie: {failed_cookies}")

    # 4. 验证 cookie
    try:
        actual_cookies = driver.get_cookies()
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
        if is_sb_mode:
            sb.open(f"{BASE_URL}/dashboard")
            sb.sleep(3)
        else:
            driver.get(f"{BASE_URL}/dashboard")
            import time as _time
            _time.sleep(3)
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
    from seleniumbase import Driver

    CHROMIUM_ARGS = (
        f"--no-sandbox,--disable-dev-shm-usage,--disable-gpu,"
        f"--window-size=1280,720,--disable-blink-features=AutomationControlled,"
        f"--disable-infobars,--disable-popup-blocking"
    )

    if PROXY_URL and PROXY_URL != "socks5://127.0.0.1:1080":
        CHROMIUM_ARGS += f",--proxy-server={PROXY_URL}"

    try:
        # 注意: Driver() 不支持 SB() 的 test/xvfb 参数
        # - test=True 是 SB() 专有 (用于 test framework)
        # - xvfb=True 是 SB() 专有 (会自动启动 Xvfb)
        # Driver() 在 xvfb-run 环境下直接 headed=True 即可
        # window_size 直接传给 Driver, 避免后续 sb.set_window_size() 卡住

        # 第一步: 用 API 获取服务器列表 (快, 不用浏览器)
        log.info("📋 用 API 获取服务器列表...")
        session = build_session(cookie)

        if not test_login(session):
            log.error("❌ 登录失败: Cookie 已过期或无效")
            return {"name": name, "ok": False, "msg": "Cookie 过期",
                    "renewed": 0, "failed": 1}
        log.info("✅ API 登录验证通过")

        servers = list_servers(session)
        log.info(f"✅ API 获取到 {len(servers)} 台服务器")

        # 第二步: 筛选需要续期的服务器 (剩余 < 阈值)
        servers_to_renew = []
        for server in servers:
            attrs = server.get("attributes", {}) if isinstance(server, dict) else {}
            sid = attrs.get("id") or server.get("id") or attrs.get("slug")
            sname = attrs.get("name") or attrs.get("server_name") or sid
            if not sid:
                continue
            detail = server_detail(session, sid) or {}
            exp_key, exp_val = find_expire(attrs, detail)
            if not exp_val:
                log.info(f"  - {sname} (id={sid}) 无到期时间, 跳过")
                continue
            exp_dt = parse_iso(exp_val) if isinstance(exp_val, str) else None
            if not exp_dt:
                log.info(f"  - {sname} (id={sid}) 到期时间无法解析: {exp_val}, 跳过")
                continue
            now = datetime.now(timezone.utc)
            remaining_sec = (exp_dt - now).total_seconds()
            remaining_h = remaining_sec / 3600
            can_renew = remaining_h < RENEW_THRESHOLD_HOURS
            log.info(f"  - {sname} (id={sid}) 到期={exp_val} 剩余={fmt_remaining(remaining_sec)} can_renew={can_renew}")
            if can_renew:
                servers_to_renew.append({
                    "id": sid, "name": sname,
                    "remaining_sec": remaining_sec,
                    "expires_at": exp_val,
                })

        if not servers_to_renew:
            log.info("✅ 没有需要续期的服务器")
            # 返回成功, 并汇报最小剩余时间
            if servers:
                min_rem = min((s["remaining_sec"] for s in []
                              if servers), default=None)
            return {
                "name": name, "ok": True,
                "renewed": 0, "failed": 0,
                "skipped": len(servers),
                "msg": f"全部 {len(servers)} 台服务器剩余时间充足, 无需续期",
            }

        log.info(f"📋 需要续期 {len(servers_to_renew)} 台: {[s['name'] for s in servers_to_renew]}")

        # 第三步: 启动浏览器走 Turnstile + 续期
        with Driver(
            browser="chrome",
            uc=True,
            headed=True,
            headless=False,
            chromium_arg=CHROMIUM_ARGS,
            window_size="1280,720",
        ) as sb:
            # 注入 Cookie
            log.info("🍪 注入 Cookie...")
            if not inject_cookies(sb, cookie):
                return {"name": name, "ok": False, "msg": "Cookie 注入失败",
                        "renewed": 0, "failed": len(servers_to_renew)}

            # 对每个服务器执行续期
            success_count = 0
            fail_count = 0
            results_detail = []
            for srv in servers_to_renew:
                log.info(f"")
                log.info(f"{'='*40}")
                log.info(f"🔄 开始续期: {srv['name']} (id={srv['id']})")
                log.info(f"   剩余: {fmt_remaining(srv['remaining_sec'])}")
                log.info(f"{'='*40}")

                # 3.1 打开服务器页面 (会触发 CF Turnstile)
                srv_url = f"{BASE_URL}/server/{srv['id']}"
                try:
                    sb.get(srv_url)
                    log.info(f"📍 已打开: {srv_url}")
                    human_wait(3, 5)
                except Exception as e:
                    log.warning(f"打开页面失败: {e}")

                # 3.2 处理 CF Turnstile (如果有)
                # 用 CDP 点击预设位置, 复用 gaming4free 的方案
                # 这里简化: 等待页面加载完, 检查是否还在挑战页
                try:
                    title = sb.title or ""
                    if "just a moment" in title.lower() or "checking" in title.lower():
                        log.info("🎯 检测到 CF 挑战页, 尝试点击 checkbox...")
                        # 用 CDP 在预设位置点击 (CF Turnstile 复选框位置)
                        for pos in [(192, 360), (640, 331), (128, 331), (640, 360)]:
                            try:
                                # 用 JS 模拟点击 (CDP Input.dispatchMouseEvent 比较复杂, 这里用 JS click)
                                sb.execute_script(f"""
                                    var el = document.elementFromPoint({pos[0]}, {pos[1]});
                                    if (el) el.click();
                                """)
                                log.info(f"   点击 ({pos[0]}, {pos[1]})")
                                time.sleep(3)
                                title = sb.title or ""
                                if "just a moment" not in title.lower() and "checking" not in title.lower():
                                    log.info("✅ CF 验证通过")
                                    break
                            except Exception:
                                continue
                except Exception as e:
                    log.warning(f"CF 处理失败: {e}")

                # 3.3 找续期按钮并点击
                try:
                    # 找 "Renew" / "续期" 按钮
                    btn = sb.execute_script("""
                        var btns = document.querySelectorAll('button, a.btn, [role="button"]');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].innerText || '').toLowerCase();
                            if (t.indexOf('renew') !== -1 || t.indexOf('续期') !== -1 ||
                                t.indexOf('extend') !== -1) {
                                return btns[i];
                            }
                        }
                        return null;
                    """)
                    if btn:
                        log.info(f"✅ 找到续期按钮: {btn.get('innerText', '')[:50]}")
                        # 用 JS 点击 (Driver 模式下 sb.execute_script 直接用)
                        sb.execute_script("arguments[0].click();", btn)
                        log.info("🖱️ 已点击续期按钮")
                        human_wait(3, 5)
                    else:
                        log.warning("⚠️ 未找到续期按钮, 尝试直接调用 API")
                except Exception as e:
                    log.warning(f"找按钮失败: {e}")

                # 3.4 调用续期 API (浏览器已通过 CF, 复用 session 的 cookie)
                try:
                    r, captcha = renew_server_api(session, srv["id"])
                    if r.status_code == 200:
                        log.info(f"✅ 续期 API 调用成功 (HTTP 200)")
                        success_count += 1
                        results_detail.append({
                            "name": srv["name"], "id": srv["id"],
                            "ok": True, "msg": "续期 API 调用成功",
                        })
                    elif captcha:
                        log.warning(f"⚠️ API 返回 captcha_required, 尝试用浏览器 fetch 调用 (复用浏览器 CF token)")
                        # 用浏览器的 fetch 调用 (能复用 CF token)
                        try:
                            fetch_result = sb.execute_script(f"""
                                return fetch('/api/client/servers/{srv["id"]}/upgrade/renew', {{
                                    method: 'POST',
                                    headers: {{
                                        'X-XSRF-TOKEN': decodeURIComponent(
                                            (document.cookie.match(/XSRF-TOKEN=([^;]+)/) || [])[1] || ''
                                        ),
                                        'Content-Type': 'application/json',
                                        'Accept': 'application/json'
                                    }}
                                }}).then(r => r.text());
                            """)
                            log.info(f"浏览器 fetch 结果: {str(fetch_result)[:300]}")
                            success_count += 1
                            results_detail.append({
                                "name": srv["name"], "id": srv["id"],
                                "ok": True, "msg": "浏览器 fetch 调用",
                            })
                        except Exception as e2:
                            log.error(f"❌ 浏览器 fetch 也失败: {e2}")
                            fail_count += 1
                            results_detail.append({
                                "name": srv["name"], "id": srv["id"],
                                "ok": False, "msg": f"captcha + fetch 失败: {e2}",
                            })
                    else:
                        log.error(f"❌ 续期 API 失败: HTTP {r.status_code} - {r.text[:200]}")
                        fail_count += 1
                        results_detail.append({
                            "name": srv["name"], "id": srv["id"],
                            "ok": False, "msg": f"HTTP {r.status_code}: {r.text[:100]}",
                        })
                except Exception as e:
                    log.error(f"❌ 调用续期 API 异常: {e}")
                    fail_count += 1
                    results_detail.append({
                        "name": srv["name"], "id": srv["id"],
                        "ok": False, "msg": f"异常: {e}",
                    })

                # 截图保存
                screenshot(sb, f"renew_{srv['id']}")
                human_wait(2, 4)

            log.info(f"")
            log.info(f"📊 账号 {name} 续期汇总:")
            log.info(f"   ✅ 成功: {success_count}")
            log.info(f"   ❌ 失败: {fail_count}")
            return {
                "name": name, "ok": fail_count == 0,
                "renewed": success_count, "failed": fail_count,
                "servers": results_detail,
            }

    except Exception as e:
        log.exception(f"账号 {name} 异常: {e}")
        return {"name": name, "ok": False, "msg": f"异常: {e}",
                "renewed": 0, "failed": 1}

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
            res = {"name": acc["name"], "ok": False, "msg": f"异常: {e}",
                   "renewed": 0, "failed": 1}
            tg(f"🎮 ACLClouds 续期通知\n\n⚠️ 账号 {acc['name']} 崩溃\n📊 {e}")
        all_results.append(res)

        # 关键修复: 每个账号处理完都发 TG 通知 (成功/失败都发)
        # 之前只在失败时发, 成功时用户不知道发生了什么
        if "servers" in res and res["servers"]:
            # 有具体服务器结果 (进入了浏览器续期流程)
            detail_lines = []
            for s in res["servers"]:
                mark = "✅" if s.get("ok") else "❌"
                detail_lines.append(f"{mark} {s['name']}: {s.get('msg', '')[:60]}")
            detail_text = "\n".join(detail_lines)
            if res.get("renewed", 0) > 0 and res.get("failed", 0) == 0:
                # 全部成功
                msg = (
                    f"🎮 ACLClouds 续期通知\n\n"
                    f"✅ 续期成功\n"
                    f"👤 账号: {res['name']}\n"
                    f"📊 续期 {res['renewed']} 台服务器:\n"
                    f"{detail_text}"
                )
            else:
                # 部分或全部失败
                msg = (
                    f"🎮 ACLClouds 续期通知\n\n"
                    f"⚠️ 部分失败\n"
                    f"👤 账号: {res['name']}\n"
                    f"✅ 成功: {res.get('renewed', 0)} | ❌ 失败: {res.get('failed', 0)}\n"
                    f"{detail_text}"
                )
            log.info(msg)
            tg(msg)
        elif res.get("ok"):
            # 成功但无需续期 (剩余时间充足)
            msg = (
                f"🎮 ACLClouds 续期通知\n\n"
                f"ℹ️ 无需续期\n"
                f"👤 账号: {res['name']}\n"
                f"📊 {res.get('msg', '所有服务器剩余时间充足')}\n"
                f"⏭️ 跳过: {res.get('skipped', 0)} 台"
            )
            log.info(msg)
            tg(msg)
        elif not res.get("ok"):
            # 整个账号失败 (如 Cookie 过期)
            msg = (
                f"🎮 ACLClouds 续期通知\n\n"
                f"❌ 账号 {res['name']} 失败\n"
                f"📊 {res.get('msg', '未知错误')}"
            )
            log.info(msg)
            tg(msg)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("用户中断")
    except Exception as e:
        log.exception(f"未捕获异常: {e}")
        tg(f"🎮 ACLClouds 续期通知\n\n💥 脚本崩溃\n📊 {e}")
        sys.exit(1)