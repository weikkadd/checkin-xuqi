#!/usr/bin/env python3
"""
ACLClouds (aclclouds.com) 自动续期脚本
- 通过 Cookie 注入调用 Pelican 风格 API
- 免费服务到期前 2 天可续期 / Minecraft 免费服务到期前 2 小时可续期
- 默认阈值 48h, 命中则调用 POST /api/client/servers/{id}/upgrade/renew
- 不需要浏览器 / 不需要代理 / 不触发 Turnstile
"""

import os
import sys
import json
import time
import urllib.parse
from datetime import datetime, timezone

import requests

# ==================== 配置 ====================
BASE_URL = "https://aclclouds.com"  # 注意：不是 dash.aclclouds.com
RENEW_THRESHOLD_HOURS = int(os.environ.get("RENEW_THRESHOLD_HOURS", "48"))

# Cookie: 完整的浏览器 Cookie 字符串，必须包含 XSRF-TOKEN 和 aclclouds_session
COOKIE = os.environ.get("ACL_COOKIES", "").strip()

# TG 通知
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()

# 多账号支持 (可选), 格式: name1|||cookie1\nname2|||cookie2
MULTI_ACCOUNTS = os.environ.get("ACL_ACCOUNTS", "").strip()

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


# ==================== 工具函数 ====================
def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg):
    print(msg, flush=True)


def send_tg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    except Exception as e:
        log(f"⚠️ TG 推送失败: {e}")


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


def build_session(cookie_str):
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
        # 移除 __Host- 和 __Secure- 前缀（requests 不支持这些前缀）
        clean_k = k
        if k.startswith("__Host-"):
            clean_k = k[7:]  # 移除 "__Host-" (7个字符)
        elif k.startswith("__Secure-"):
            clean_k = k[9:]  # 移除 "__Secure-" (9个字符)
        
        # 设置 domain 为 aclclouds.com
        s.cookies.set(clean_k, v, domain="aclclouds.com", path="/")
    
    # 调试: 打印设置的 Cookie
    log(f"🔍 Session 中设置了 {len(s.cookies)} 个 Cookie:")
    for cookie in s.cookies:
        log(f"   - {cookie.name} = {cookie.value[:30]}...")
    
    return s


def get_xsrf(session):
    """从 cookie 中提取并解码 XSRF-TOKEN"""
    token = session.cookies.get("XSRF-TOKEN", domain="aclclouds.com")
    if not token:
        return None
    return urllib.parse.unquote(token)


def api_get(session, path):
    # 关键修复: GET 请求也必须带 X-XSRF-TOKEN 头
    # Laravel 框架对所有 /api/* 路径都验证 CSRF (不只 POST)
    # 之前只 POST 带 token, GET 没带, 导致服务器返回 401 (误报 Cookie 过期)
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
    # ACLClouds 用 GET /api/client 列表服务器
    # 响应: { data: [ { object: "server", attributes: {...} } ], meta: {...} }
    r = api_get(session, "/api/client")
    r.raise_for_status()
    j = r.json()
    if isinstance(j, dict):
        return j.get("data", [])
    return j if isinstance(j, list) else []


def server_detail(session, sid):
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
    # 也查 relationships
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


def renew_server(session, sid):
    """调用续期 API, 返回 (response, captcha_required_bool)"""
    r = api_post(session, f"/api/client/servers/{sid}/upgrade/renew")
    captcha_required = False
    if r.status_code == 403:
        try:
            j = r.json()
            if isinstance(j, dict) and j.get("code") == "captcha_required":
                captcha_required = True
        except:
            pass
    return r, captcha_required


def process_account(cookie_str, threshold_hours):
    """处理单个账号的续期逻辑"""
    log("=" * 60)
    log("🎮 ACLClouds 自动续期")
    log(f"⏰ {now_str()}")
    log(f"⚙️ 续期阈值: {threshold_hours}h")
    log("=" * 60)
    
    session = build_session(cookie_str)
    
    # 测试登录状态
    log("\n🔍 测试登录状态...")
    try:
        test_r = api_get(session, "/api/client")
        if test_r.status_code == 401:
            log(f"❌ 登录失败: Cookie 已过期或无效 (HTTP 401)")
            # 关键诊断: 检查 XSRF token 是否被正确设置
            xsrf = get_xsrf(session)
            if not xsrf:
                log("⚠️ XSRF-TOKEN 未找到! 请确认 Cookie 包含 'XSRF-TOKEN=xxx'")
            else:
                log(f"✅ XSRF-TOKEN 已设置 (前 20 字符): {xsrf[:20]}...")
            # 检查 session cookie 是否存在
            sess = session.cookies.get("aclclouds_session", domain="aclclouds.com")
            if not sess:
                log("⚠️ aclclouds_session Cookie 未找到!")
                log("   检查 ACL_COOKIES Secret 是否包含 'aclclouds_session=' 或 '__Host-aclclouds_session='")
            else:
                log(f"✅ aclclouds_session 已设置 (前 20 字符): {sess[:20]}...")
            log(f"   服务器响应: {test_r.text[:300]}")
            return {"servers": [], "success": 0, "skipped": 0, "failed": 1, "error": "401 Unauthorized"}
        if test_r.status_code != 200:
            log(f"⚠️ 登录测试返回 HTTP {test_r.status_code}")
            log(f"   响应: {test_r.text[:300]}")
            return {"servers": [], "success": 0, "skipped": 0, "failed": 1, "error": f"HTTP {test_r.status_code}"}
        log("✅ 登录成功")
    except Exception as e:
        log(f"❌ 登录测试失败: {e}")
        return {"servers": [], "success": 0, "skipped": 0, "failed": 1, "error": str(e)}
    
    # 获取服务器列表
    log("\n📋 获取服务器列表...")
    servers = list_servers(session)
    log(f"✅ API 获取到 {len(servers)} 台服务器")
    
    results = {
        "servers": [],
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }
    
    # 遍历每个服务器
    for server in servers:
        attrs = server.get("attributes", {})
        sid = attrs.get("id") or server.get("id") or attrs.get("slug")
        
        if not sid:
            log(f"⚠️ 跳过: 无法获取服务器 ID")
            results["failed"] += 1
            continue
        
        name = attrs.get("name") or f"Server-{sid}"
        log(f"\n🖥️ 处理服务器: {name} (id={sid})")
        
        # 获取到期时间
        expire_key, expire_val = find_expire(attrs)
        if not expire_val:
            detail = server_detail(session, sid)
            expire_key, expire_val = find_expire(attrs, detail)
        
        expires_at = parse_iso(expire_val) if expire_val else None
        if not expires_at:
            log(f"⚠️ 无法解析到期时间: {expire_val}")
            results["skipped"] += 1
            continue
        
        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
        remaining_hours = remaining / 3600
        
        log(f"📅 到期时间: {expires_at.strftime('%Y-%m-%dT%H:%M:%S+02:00')}")
        log(f"⏰ 剩余时间: {fmt_remaining(remaining)} ({remaining_hours:.1f}h)")
        
        # 检查是否需要续期
        threshold_seconds = threshold_hours * 3600
        if remaining > threshold_seconds:
            log(f"✅ 剩余 {remaining_hours:.1f}h >= {threshold_hours}h, 跳过")
            results["skipped"] += 1
            continue
        
        # 执行续期
        log(f"🔄 开始续期...")
        r, captcha_required = renew_server(session, sid)
        
        if r.status_code == 200:
            log(f"✅ 续期成功!")
            results["success"] += 1
        elif r.status_code == 403 and captcha_required:
            log(f"⚠️ 需要验证码 (Turnstile), 请手动处理")
            results["failed"] += 1
        else:
            log(f"❌ 续期失败: HTTP {r.status_code}")
            try:
                j = r.json()
                log(f"   错误: {json.dumps(j, ensure_ascii=False)}")
            except:
                log(f"   响应: {r.text[:200]}")
            results["failed"] += 1
        
        results["servers"].append({
            "id": sid,
            "name": name,
            "remaining_hours": remaining_hours,
            "success": r.status_code == 200,
        })
    
    return results


def main():
    accounts = []
    
    # 解析多账号配置
    if MULTI_ACCOUNTS:
        for line in MULTI_ACCOUNTS.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|||" in line:
                name, ck = line.split("|||", 1)
                accounts.append({"name": name.strip(), "cookie": ck.strip()})
    
    if not accounts and COOKIE:
        accounts.append({"name": "main", "cookie": COOKIE})
    
    if not accounts:
        log("❌ 未配置 ACL_COOKIES 或 ACL_ACCOUNTS")
        send_tg("❌ 未配置 ACL_COOKIES 或 ACL_ACCOUNTS")
        sys.exit(1)
    
    log(f"📋 共 {len(accounts)} 个账号待处理\n")
    
    total_results = {
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }
    
    for acc in accounts:
        log(f"\n{'='*60}")
        log(f"👤 账号: {acc['name']}")
        log(f"{'='*60}")
        
        try:
            result = process_account(acc["cookie"], RENEW_THRESHOLD_HOURS)
            total_results["success"] += result.get("success", 0)
            total_results["skipped"] += result.get("skipped", 0)
            total_results["failed"] += result.get("failed", 0)
        except Exception as e:
            log(f"❌ 账号 {acc['name']} 异常: {e}")
            total_results["failed"] += 1
            send_tg(f"❌ 账号 {acc['name']} 处理失败: {e}")
    
    # 汇总通知
    msg = f"🎮 *ACLClouds 自动续期*\n\n"
    msg += f"⏰ {now_str()}\n\n"
    msg += f"📊 总服务器: {total_results['success'] + total_results['skipped'] + total_results['failed']}\n"
    msg += f"✅ 成功: {total_results['success']} | ⏭️ 跳过: {total_results['skipped']} | ❌ 失败: {total_results['failed']}"
    
    log(f"\n{msg}")
    send_tg(msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n用户中断")
    except Exception as e:
        log(f"❌ 未捕获异常: {e}")
        import traceback
        traceback.print_exc()
        send_tg(f"❌ 脚本崩溃: {e}")
        sys.exit(1)
