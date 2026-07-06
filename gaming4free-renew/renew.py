#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gaming4free 自动续期脚本（GHA + WARP + seleniumbase UC mode）
================================================================
- 使用 seleniumbase UC mode 反检测
- 走 Cloudflare WARP SOCKS5 出口（CF 自家 IP，几乎必过 Turnstile）
- 自动识别续期按钮，循环点击至 48h 上限
- 点击前后剩余时间对比，确保真成功
- 失败自动截图 + Telegram 通知
"""
import os
import re
import sys
import time
import json
import random
import socket
import smtplib
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置区
# ---------------------------------------------------------------------------
SITE_URL       = os.getenv("GF_SITE_URL", "https://gaming4free.zapto.org/")
LOGIN_URL      = os.getenv("GF_LOGIN_URL", "")          # 如有独立登录页填这里，否则留空
USERNAME       = os.getenv("MC_USERNAME", "")           # Minecraft 用户名（用于登录）
PASSWORD       = os.getenv("MC_PASSWORD", "")           # 密码（如需）
COOKIE_STR     = os.getenv("GF_COOKIE", "")             # 备用：直接注入 cookie
WARP_PROXY     = "socks5://127.0.0.1:40000"

MAX_HOURS      = 48            # 续期上限 48 小时（页面显示 'cap 48h'）
ADD_MINUTES    = 90            # 每次点击 +90 分钟
COOLDOWN_SEC   = 180           # 冷却 3 分钟（页面显示 expires 2-5min）
MAX_CLICKS     = 30            # 单次运行最大点击次数（防死循环）
PAGE_TIMEOUT   = 60            # 单页操作超时
TURNSTILE_WAIT = 90            # Turnstile 等待上限

TG_TOKEN       = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID     = os.getenv("TG_CHAT_ID", "")

SHOT_DIR       = Path("screenshots")
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
        logging.FileHandler("renew.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("renew")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def tg(msg: str):
    """Telegram 通知（失败不影响主流程）"""
    if not (TG_TOKEN and TG_CHAT_ID):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"TG 通知失败: {e}")


def parse_remaining_seconds(text: str) -> int:
    """
    从页面文本中解析剩余时间，返回秒数。
    支持 '48h 30m', '47:30:00', '2d 5h', '90 min' 等
    """
    if not text:
        return -1
    t = text.lower().strip()
    total = 0

    # 优先匹配 HH:MM:SS 或 MM:SS
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", t)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    # 匹配 'Xd Xh Xm Xs' 或 'Xh Xm'
    for unit, mult in [("d", 86400), ("day", 86400),
                        ("h", 3600),  ("hour", 3600),
                        ("m", 60),    ("min", 60), ("minute", 60),
                        ("s", 1),     ("sec", 1)]:
        m = re.search(rf"(\d+)\s*{unit}", t)
        if m:
            total += int(m.group(1)) * mult
    return total if total > 0 else -1


def human_sleep(a: float = 0.5, b: float = 1.5):
    """模拟人类反应时间"""
    time.sleep(random.uniform(a, b))


def screenshot(sb, name: str):
    """保存截图，返回路径"""
    p = SHOT_DIR / f"{datetime.now():%H%M%S}_{name}.png"
    try:
        sb.save_screenshot(str(p))
        log.info(f"截图: {p}")
    except Exception as e:
        log.warning(f"截图失败: {e}")
    return p


# ---------------------------------------------------------------------------
# 续期核心
# ---------------------------------------------------------------------------
def get_remaining_seconds(sb) -> int:
    """从页面提取剩余时间，返回秒数（-1 表示无法识别）

    gaming4free 实际页面布局：
    - 文本格式：'06:13:39 remaining' / 'expires 01:48' / 'cap 48h'
    - 优先匹配包含 'remaining' 的那行（这才是真正的剩余时间）
    """
    try:
        # 优先用 JS 直接抓含 'remaining' 关键词的元素文本
        # 注意：seleniumbase UC mode 用 CDP，不允许顶层 return，必须用纯表达式
        try:
            txt = sb.execute_script("""
            (function(){
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const t = (el.textContent || '').trim();
                    if (el.children.length <= 2 && /remaining/i.test(t) && /\\d{1,2}:\\d{2}/.test(t)) {
                        return t;
                    }
                }
                return '';
            })()
            """)
            if txt:
                sec = parse_remaining_seconds(txt)
                if sec > 0:
                    log.info(f"剩余时间 [JS remaining] = {txt} → {sec}s ({sec//3600}h {(sec%3600)//60}m)")
                    return sec
        except Exception:
            pass

        # 常见选择器，按优先级尝试
        selectors = [
            "#timeleft", ".timeleft", ".time-left",
            "#remaining", ".remaining", ".countdown",
            '[class*="time"]', '[id*="time"]',
            '[class*="remain"]', '[id*="remain"]',
        ]
        for sel in selectors:
            try:
                txt = sb.get_text(sel) if sb.is_element_visible(sel) else ""
                sec = parse_remaining_seconds(txt)
                if sec > 0:
                    log.info(f"剩余时间 [{sel}] = {txt} → {sec}s ({sec//3600}h {(sec%3600)//60}m)")
                    return sec
            except Exception:
                continue

        # 兜底：整页文本提取
        body_text = sb.get_text("body")
        # 优先找包含 'remaining' 的行
        for line in body_text.split("\n"):
            if "remaining" in line.lower():
                sec = parse_remaining_seconds(line)
                if 60 < sec < MAX_HOURS * 3600 + 3600:
                    log.info(f"剩余时间 [remaining line] = {line.strip()} → {sec}s")
                    return sec
        # 再找 'expires' 的行
        for line in body_text.split("\n"):
            if "expires" in line.lower():
                sec = parse_remaining_seconds(line)
                if 60 < sec < MAX_HOURS * 3600 + 3600:
                    log.info(f"剩余时间 [expires line] = {line.strip()} → {sec}s")
                    return sec
        return -1
    except Exception as e:
        log.warning(f"提取剩余时间失败: {e}")
        return -1


def get_cooldown_seconds(sb) -> int:
    """从页面提取 'expires MM:SS' 冷却剩余秒数（-1 表示无冷却）

    gaming4free 冷却中页面会显示 'expires 04:45' 表示还需等 4 分 45 秒才能再次续期
    """
    try:
        # 优先用 JS 找包含 'expires' 关键词的元素文本
        try:
            txt = sb.execute_script("""
            (function(){
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.children.length > 0) continue;  // 只看叶子节点
                    const t = (el.textContent || '').trim();
                    if (/^expires\\s+\\d{1,2}:\\d{2}(:\\d{2})?$/i.test(t)) {
                        return t;
                    }
                }
                // 兜底：在所有元素里找
                for (const el of all) {
                    const t = (el.textContent || '').trim();
                    if (/expires\\s+\\d{1,2}:\\d{2}/i.test(t) && el.children.length <= 2) {
                        return t;
                    }
                }
                return '';
            })()
            """)
            if txt:
                # 提取 MM:SS 或 HH:MM:SS
                import re
                m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", txt)
                if m:
                    if m.group(3):  # HH:MM:SS
                        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                    else:  # MM:SS
                        sec = int(m.group(1)) * 60 + int(m.group(2))
                    log.info(f"冷却剩余 [expires] = {txt} → {sec}s")
                    return sec
        except Exception:
            pass

        # 兜底：整页文本找
        body_text = sb.get_text("body")
        for line in body_text.split("\n"):
            if "expires" in line.lower():
                import re
                m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", line)
                if m:
                    if m.group(3):
                        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                    else:
                        sec = int(m.group(1)) * 60 + int(m.group(2))
                    if 0 < sec < 3600:  # 冷却一般不会超过 1 小时
                        log.info(f"冷却剩余 [body line] = {line.strip()} → {sec}s")
                        return sec
        return -1
    except Exception as e:
        log.warning(f"提取冷却时间失败: {e}")
        return -1


def click_renew_button(sb) -> bool:
    """找到并点击续期按钮，返回是否点到了"""
    candidates = [
        # gaming4free 实际按钮文字：+ 90 min
        'button:contains("+ 90 min")',
        'button:contains("90 min")',
        'button:contains("+90")',
        # 兼容其它文字
        'button:contains("Renew")',
        'button:contains("Extend")',
        'button:contains("续期")',
        'button:contains("增加")',
        'a:contains("+ 90 min")',
        'a:contains("Renew")',
        # 选择器兜底
        "#renew", ".renew", ".btn-renew",
        'button[class*="renew"]', 'a[class*="renew"]',
        'button[class*="extend"]', 'a[class*="extend"]',
    ]

    # 备用方案：通过 JS 找包含 "90 min" 或 "+90" 文字的所有可点击元素（已废弃，改用下面的终极兜底）
    # 保留变量供参考
    _js_find_button_doc = "已改用 execute_script 内联 IIFE，详见下方兜底逻辑"
    for sel in candidates:
        try:
            if sb.is_element_visible(sel):
                # 模拟人类阅读
                human_sleep(1.0, 2.5)
                # 滚到可视区
                sb.scroll_to(sel)
                human_sleep(0.3, 0.8)
                # UC mode 推荐用 .click()，必要时用 js click
                try:
                    sb.click(sel, timeout=8)
                except Exception:
                    sb.execute_script(
                        "document.querySelector(arguments[0]).click();", sel
                    )
                log.info(f"✅ 点击续期按钮 [{sel}]")
                return True
        except Exception:
            continue

    # 终极兜底：用 JS 直接找包含 "90 min" 的可点击元素并点击
    # 注意：UC mode 用 CDP，不允许顶层 return，必须用纯表达式
    try:
        clicked = sb.execute_script("""
        (function(){
            const all = document.querySelectorAll('button, a, [role="button"], .btn, input[type="button"], input[type="submit"]');
            for (const el of all) {
                const t = (el.textContent || el.value || '').trim();
                if (/\\+?\\s*90\\s*min/i.test(t) || /renew|extend|续期/i.test(t)) {
                    el.scrollIntoView({block:'center'});
                    el.click();
                    return t;
                }
            }
            return '';
        })()
        """)
        if clicked:
            log.info(f"✅ JS 兜底点击续期按钮 [{clicked}]")
            return True
    except Exception as e:
        log.warning(f"JS 兜底点击失败: {e}")

    log.warning("❌ 未找到续期按钮")
    return False


def handle_turnstile(sb) -> bool:
    """处理 Cloudflare Turnstile，返回是否检测到并尝试通过"""
    try:
        # Turnstile iframe 选择器
        iframe_sel = 'iframe[src*="challenges.cloudflare.com"]'
        if not sb.is_element_present(iframe_sel):
            log.info("未检测到 Turnstile iframe，跳过")
            return True

        log.info("🔄 检测到 Cloudflare Turnstile，等待自动通过（UC mode + WARP 大概率自动过）...")
        screenshot(sb, "turnstile_appear")

        # 等待最多 TURNSTILE_WAIT 秒，每秒检查一次
        for i in range(TURNSTILE_WAIT):
            # 检测 Turnstile 是否已通过：响应 input 有值
            try:
                val = sb.execute_script(
                    """(function(){
                        let el = document.querySelector('[name="cf-turnstile-response"]');
                        if (!el) el = document.querySelector('input[name*="turnstile"]');
                        return el ? el.value : '';
                    })()"""
                )
                if val and len(val) > 20:
                    log.info(f"✅ Turnstile 已通过 ({i}s)")
                    return True
            except Exception:
                pass

            # 尝试点击 iframe 内的复选框（UC mode 允许跨 iframe）
            try:
                if i == 3:  # 出现后等 3 秒再尝试点击
                    sb.switch_to_frame(iframe_sel)
                    try:
                        if sb.is_element_visible('input[type="checkbox"]'):
                            sb.click('input[type="checkbox"]', timeout=3)
                            log.info("点击 Turnstile checkbox")
                    except Exception:
                        pass
                    finally:
                        sb.switch_to_default_content()
            except Exception:
                pass

            time.sleep(1)

        log.warning(f"⚠️ Turnstile {TURNSTILE_WAIT}s 未通过")
        screenshot(sb, "turnstile_timeout")
        return False
    except Exception as e:
        log.warning(f"Turnstile 处理异常: {e}")
        return False


def inject_cookies(sb):
    """如果提供了 cookie 字符串，注入到当前域名"""
    if not COOKIE_STR:
        return
    log.info("注入自定义 cookie ...")
    for item in COOKIE_STR.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            try:
                sb.set_cookie(k, v)
            except Exception:
                pass


def do_login(sb):
    """登录逻辑（如有）"""
    if not USERNAME:
        log.info("未配置 MC_USERNAME，跳过登录")
        return
    log.info(f"尝试登录用户: {USERNAME}")

    # 通用登录表单选择器
    user_selectors = ['input[name="username"]', 'input[name="user"]',
                       'input[name="mc_username"]', 'input[type="text"]',
                       'input[id*="user"]', 'input[name="email"]']
    pass_selectors = ['input[name="password"]', 'input[type="password"]']
    submit_selectors = ['button[type="submit"]', 'input[type="submit"]',
                         'button:contains("Login")', 'button:contains("登录")',
                         'button:contains("Sign in")']

    # 用户名
    for sel in user_selectors:
        try:
            if sb.is_element_visible(sel):
                sb.type(sel, USERNAME, timeout=5)
                break
        except Exception:
            continue
    # 密码
    if PASSWORD:
        for sel in pass_selectors:
            try:
                if sb.is_element_visible(sel):
                    sb.type(sel, PASSWORD, timeout=5)
                    break
            except Exception:
                continue
    # 提交
    for sel in submit_selectors:
        try:
            if sb.is_element_visible(sel):
                human_sleep(0.5, 1.2)
                sb.click(sel, timeout=5)
                log.info("登录表单已提交")
                time.sleep(3)
                return
        except Exception:
            continue


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run():
    from seleniumbase import SB

    log.info("=" * 60)
    log.info("gaming4free 续期启动")
    log.info(f"WARP 代理: {WARP_PROXY}")
    log.info(f"目标站点: {SITE_URL}")
    log.info(f"MC 用户:  {USERNAME or '(未配置)'}")
    log.info("=" * 60)

    # 预检 WARP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("127.0.0.1", 40000))
        s.close()
        log.info("✅ WARP SOCKS5 端口 40000 可用")
    except Exception:
        log.error("❌ WARP 端口 40000 不可达，请检查 WARP 启动状态")
        tg("❌ gaming4free 续期失败：WARP 代理未就绪")
        sys.exit(1)

    # UC mode 启动
    # 注意：seleniumbase SB() 不支持 ignore_certificate_errors / disable_cookies / localized
    # 这些参数会引发 TypeError。改用 chromium_arg 传递浏览器启动参数。
    with SB(
        browser="chrome",                        # seleniumbase 叫 chrome，不是 chromium
        uc=True,                                # undetected chromedriver
        headless=False,                          # Xvfb 下跑非 headless，反检测更强
        xvfb=True,                               # 自动用 Xvfb 虚拟显示
        incognito=False,
        agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        chromium_arg="--ignore-certificate-errors",
        proxy=WARP_PROXY,
        ad_block=False,                          # 别开 ad block，可能误杀 Turnstile
        locale_code="en",
    ) as sb:

        sb.set_window_size(1280, 800)
        sb.driver.set_page_load_timeout(PAGE_TIMEOUT)

        # Step 1: 打开站点
        try:
            sb.open(SITE_URL)
            sb.sleep(3)
        except Exception as e:
            log.error(f"打开站点失败: {e}")
            screenshot(sb, "open_fail")
            tg(f"❌ gaming4free 续期失败：站点打不开\n{e}")
            return

        # Step 2: 处理 CF 5 秒盾（如有）+ 等 JS 渲染
        # UC mode + WARP 通常会自动过 CF，但要给足时间
        log.info("等待 CF 盾 + 页面 JS 渲染（最长 60s）...")
        cf_keywords = ["just a moment", "checking your browser", "attention required",
                       "verifying you are human", "ddos protection", "cf-browser-verification"]
        for i in range(60):
            try:
                body_lower = sb.get_text("body").lower() if sb.is_element_present("body") else ""
            except Exception:
                body_lower = ""
            # 如果还看到 CF 验证关键词，继续等
            if any(kw in body_lower for kw in cf_keywords):
                if i % 5 == 0:
                    log.info(f"⏳ CF 盾未过 ({i}s)，继续等...")
                time.sleep(1)
                continue
            # 如果页面有了 gaming4free 的关键标志（说明已进入），就停
            if any(kw in body_lower for kw in ["gaming4free", "console", "remaining",
                                                  "active session", "+ 90 min", "90 min"]):
                log.info(f"✅ 页面已加载完成 ({i}s)")
                break
            time.sleep(1)

        # 再额外等 3 秒让 JS 完全渲染
        sb.sleep(3)

        # Step 3: 注入 cookie / 登录
        inject_cookies(sb)
        if LOGIN_URL:
            sb.open(LOGIN_URL)
            sb.sleep(2)
            do_login(sb)
            sb.open(SITE_URL)
            sb.sleep(2)

        screenshot(sb, "dashboard")

        # Step 4: 主循环 - 反复点击续期直到接近 8h 上限
        click_count = 0
        last_sec = get_remaining_seconds(sb)
        if last_sec > 0:
            log.info(f"初始剩余: {last_sec}s ({last_sec//3600}h {(last_sec%3600)//60}m)")
        else:
            log.info("初始剩余: 未识别")

        while click_count < MAX_CLICKS:
            # 接近上限就停（剩 30 分钟以内就停，避免溢出）
            if last_sec > 0 and last_sec >= (MAX_HOURS * 3600 - 1800):
                log.info(f"🎉 已接近 {MAX_HOURS}h 上限，停止续期")
                break

            # Step 4.1: 点击续期按钮
            if not click_renew_button(sb):
                # 没找到按钮 - 可能是冷却中（按钮被替换成 "Go Always-On" 或类似）
                # 检查 expires 时间，自动等到冷却结束
                cooldown_left = get_cooldown_seconds(sb)
                if cooldown_left > 0:
                    wait_sec = cooldown_left + 10  # 多等 10s 保险
                    log.info(f"⏳ 续期按钮未出现，检测到冷却中 expires={cooldown_left}s，等待 {wait_sec}s")
                    screenshot(sb, f"cooldown_{click_count}")
                    # 分段等，每 30s 打一次日志
                    for i in range(0, wait_sec, 30):
                        time.sleep(min(30, wait_sec - i))
                        log.info(f"  冷却等待剩 {wait_sec - i - 30}s")
                    sb.refresh()
                    sb.sleep(3)
                    # 重新检测页面就绪
                    for _ in range(30):
                        try:
                            body_lower = sb.get_text("body").lower()
                            if any(kw in body_lower for kw in ["remaining", "90 min", "console"]):
                                break
                        except Exception:
                            pass
                        time.sleep(1)
                    last_sec = get_remaining_seconds(sb)
                    continue
                else:
                    screenshot(sb, f"no_btn_{click_count}")
                    log.warning("本次未找到按钮，且无冷却提示，刷新重试")
                    sb.refresh()
                    sb.sleep(3)
                    last_sec = get_remaining_seconds(sb)
                    click_count += 1
                    continue

            # Step 4.2: 处理可能出现的 Turnstile
            human_sleep(1.0, 2.0)
            handle_turnstile(sb)

            # Step 4.3: 等待响应
            human_sleep(3.0, 5.0)
            sb.sleep(2)

            # Step 4.4: 对比时间
            new_sec = get_remaining_seconds(sb)
            delta = new_sec - last_sec if new_sec > 0 and last_sec > 0 else 0
            log.info(f"点击 #{click_count+1}: {last_sec}s → {new_sec}s (Δ={delta}s)")

            if new_sec > last_sec or (last_sec <= 0 and new_sec > 0):
                click_count += 1
                log.info(f"✅ 续期成功 (累计 {click_count} 次)")
                screenshot(sb, f"success_{click_count}")
                last_sec = new_sec
            else:
                log.warning(f"⚠️ 续期可能失败，时间未增加")
                screenshot(sb, f"fail_{click_count}")
                # 失败一次重试刷新
                sb.refresh()
                sb.sleep(3)
                last_sec = get_remaining_seconds(sb)
                click_count += 1   # 计入尝试次数

            # Step 4.5: 冷却
            if last_sec > 0 and last_sec >= (MAX_HOURS * 3600 - 1800):
                break
            log.info(f"⏳ 冷却 {COOLDOWN_SEC}s ...")
            for i in range(COOLDOWN_SEC, 0, -30):
                log.info(f"  剩 {i}s")
                time.sleep(min(30, i))

        # 收尾
        final_sec = get_remaining_seconds(sb)
        h, m = final_sec // 3600, (final_sec % 3600) // 60
        msg = (f"✅ gaming4free 续期完成\n"
               f"成功点击: {click_count} 次\n"
               f"最终剩余: {h}h {m}m")
        log.info(msg)
        tg(msg)
        screenshot(sb, "final")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("用户中断")
    except Exception as e:
        log.exception(f"❌ 未捕获异常: {e}")
        tg(f"❌ gaming4free 续期崩溃\n{e}")
        sys.exit(1)
