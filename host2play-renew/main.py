#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本 (Manus 优化版)
=====================
- 增强：支持带认证的家宽代理 (PROXY_URL)，自动解析并过滤特殊参数
- 增强：增加 IP 检查逻辑，确保代理生效
- 增强：优化 reCAPTCHA iframe 定位逻辑，增加多层级查找
- 增强：提升音讯验证码识别的容错性，增加随机延迟模拟真人
"""

import os
import sys
import time
import json
import random
import logging
import requests
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ==========================================================
# 配置
# ==========================================================
RENEW_URL = os.getenv("H2P_RENEW_URL", "")
COOKIE_STR = os.getenv("H2P_COOKIE", "")
WARP_PROXY = os.getenv("WARP_PROXY", "")
PROXY_URL = os.getenv("PROXY_URL", "")
RENEW_THRESHOLD_SECONDS = 25 * 3600

MAX_RETRY = 5
PAGE_TIMEOUT = 60
TG_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
TZ_CN = timezone(timedelta(hours=8))

def now_cn():
    return datetime.now(TZ_CN)

ROOT = Path(__file__).parent
SHOT_DIR = ROOT / "output" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("host2play")

# ==========================================================
# 工具函数
# ==========================================================
def tg(msg: str, silent: bool = False):
    prefix = "🎮 <b>host2play</b>\n"
    if "host2play" not in msg.lower(): msg = prefix + msg
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_notification": silent},
            timeout=10,
         )
    except: pass

def parse_expires(text: str) -> int:
    if not text: return -1
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if m: return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return -1

def get_server_info(page):
    server_id = "Unknown"
    expires_text = "Unknown"
    expires_sec = -1
    for _ in range(10):
        try:
            text_content = page.run_js("return document.body.innerText")
            time_match = re.search(r"(\d{1,2}:\d{2}:\d{2})", text_content)
            if time_match:
                expires_text = time_match.group(1)
                expires_sec = parse_expires(expires_text)
                sid_match = re.search(r"Renew server:\s*([a-zA-Z0-9]+)", text_content, re.IGNORECASE)
                if sid_match: server_id = sid_match.group(1)
                if server_id != "Unknown": break
        except: pass
        time.sleep(2)
    return server_id, expires_text, expires_sec

def solve_recaptcha_audio(page) -> bool:
    try:
        import speech_recognition as sr
        import pydub
    except ImportError:
        log.error("❌ 缺少依赖: SpeechRecognition 或 pydub")
        return False
    
    log.info("🤖 开始处理 reCAPTCHA...")
    checkbox_iframe = None
    selectors = ['css:iframe[src*="recaptcha/api2/banchor"]', 'css:iframe[title*="reCAPTCHA"]', 'xpath://iframe[contains(@src, "anchor")]']
    for selector in selectors:
        checkbox_iframe = page.ele(selector, timeout=10)
        if checkbox_iframe: break
    if not checkbox_iframe: 
        if page.ele('css:.recaptcha-checkbox-checkmark', timeout=2): log.info("💡 发现直接存在的 Checkbox")
        else: return False
    
    try:
        if checkbox_iframe: page.switch_to.frame(checkbox_iframe)
        checkbox = page.ele('css:.recaptcha-checkbox-checkmark', timeout=5)
        if checkbox:
            checkbox.click()
            time.sleep(random.uniform(2, 4))
        page.switch_to.main_frame()
    except: page.switch_to.main_frame()

    time.sleep(3)
    for attempt in range(MAX_RETRY):
        try:
            challenge_iframe = None
            c_selectors = ['css:iframe[src*="recaptcha/api2/bframe"]', 'xpath://iframe[contains(@src, "bframe")]']
            for cs in c_selectors:
                challenge_iframe = page.ele(cs, timeout=5)
                if challenge_iframe: break
            if not challenge_iframe:
                iframes = page.eles('css:iframe[src*="recaptcha"]')
                if len(iframes) >= 2: challenge_iframe = iframes[1]
            if not challenge_iframe: return True

            page.switch_to.frame(challenge_iframe)
            audio_btn = page.ele('css:#recaptcha-audio-button', timeout=5)
            if not audio_btn: audio_btn = page.ele('css:.rc-button-audio', timeout=2)
            if audio_btn: 
                audio_btn.click()
                time.sleep(random.uniform(3, 5))
            
            audio_link = page.ele('css:.rc-audiochallenge-tdownload-link', timeout=5)
            if not audio_link:
                if "自动查询" in page.html or "automated queries" in page.html:
                    log.error("🚫 IP 被 Google 拦截")
                    page.switch_to.main_frame(); return False
                page.switch_to.main_frame(); continue

            audio_url = audio_link.attr('href')
            audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)
            
            wav_file = SHOT_DIR / f"audio_{attempt}.wav"
            pydub.AudioSegment.from_mp3(str(audio_file)).export(str(wav_file), format="wav")
            
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="en-US")
            
            log.info(f"✅ 识别结果: {text}")
            input_box = page.ele('css:#audio-response', timeout=5)
            if input_box:
                input_box.input(text)
                time.sleep(1)
                verify_btn = page.ele('css:#recaptcha-verify-button', timeout=5)
                if verify_btn: verify_btn.click()
            
            page.switch_to.main_frame()
            time.sleep(3)
            if not page.ele('css:iframe[src*="recaptcha/api2/bframe"]', timeout=3): return True
        except Exception as e:
            log.warning(f"⚠️ 尝试 {attempt+1} 失败: {e}")
            page.switch_to.main_frame(); time.sleep(2)
    return False

def inject_cookies(page, cookie_str: str):
    if not cookie_str: return
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            try: page.set.cookies({k.strip(): v.strip()})
            except: pass

def create_proxy_auth_extension(proxy_url):
    import zipfile
    if "@" not in proxy_url: return None
    try:
        base_url = proxy_url.split("?")[0]
        scheme = base_url.split("://")[0] if "://" in base_url else "http"
        content = base_url.split("://")[1] if "://" in base_url else base_url
        auth_part, addr_part = content.split("@")
        proxy_user, proxy_pass = auth_part.split(":")
        addr_split = addr_part.split(":")
        proxy_host = addr_split[0]
        proxy_port = addr_split[1] if len(addr_split) > 1 else ("1080" if "socks" in scheme else "8080")
        scheme = "socks5" if "socks" in scheme else "http"
        log.info(f"🔧 代理解析: {scheme}://{proxy_host}:{proxy_port}")
    except: return None

    manifest_json = json.dumps({
        "version": "1.0.0", "manifest_version": 2, "name": "Chrome Proxy",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": { "scripts": ["background.js"] }, "minimum_chrome_version":"22.0.0"
    })
    background_js = """
    var config = { mode: "fixed_servers", rules: { singleProxy: { scheme: "%s", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    chrome.webRequest.onAuthRequired.addListener(function(details) {
        return { authCredentials: { username: "%s", password: "%s" } };
    }, {urls: ["<all_urls>"]}, ['blocking']);
    """ % (scheme, proxy_host, proxy_port, proxy_user, proxy_pass)
    
    plugin_path = ROOT / "proxy_auth_plugin.zip"
    with zipfile.ZipFile(str(plugin_path), 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return str(plugin_path)

def run_one(label: str, renew_url: str, cookie_str: str):
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    co.headless()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    
    if PROXY_URL:
        if "@" in PROXY_URL:
            plugin = create_proxy_auth_extension(PROXY_URL)
            if plugin: 
                co.add_extension(plugin)
            else:
                # 即使有 @ 但解析失败，也尝试直接设置
                co.set_argument(f'--proxy-server={PROXY_URL}')
        else:
            # 直接使用启动参数设置代理，绕过 DrissionPage 的 SOCKS 限制
            co.set_argument(f'--proxy-server={PROXY_URL}')
    elif WARP_PROXY:
        co.set_argument(f'--proxy-server={WARP_PROXY}')

    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
    
    page = ChromiumPage(co)
    page.set.timeouts(PAGE_TIMEOUT)
    try:
        try:
            page.get("https://api.ip.sb/ip", timeout=10)
            log(f"📍 当前出口 IP: {page.run_js('return document.body.innerText').strip()}")
        except: pass

        log(f"🌐 正在访问: {renew_url}")
        page.get(renew_url)
        time.sleep(5)
        if cookie_str:
            inject_cookies(page, cookie_str)
            page.get(renew_url)
            time.sleep(8)
        
        server_id, old_time, old_sec = get_server_info(page)
        log(f"👤 账号: {label} | 🆔: {server_id} | ⏱️: {old_time}")

        if old_sec > RENEW_THRESHOLD_SECONDS:
            return {"label": label, "sid": server_id, "ok": True, "msg": f"跳过 ({old_sec//3600}h)", "new": f"{old_sec//3600}h"}

        renew_btn = None
        for sel in ['text:Renew server', 'css:button.purple', 'xpath://button[contains(text(), "Renew")]']:
            renew_btn = page.ele(sel, timeout=5)
            if renew_btn: break
        if not renew_btn: 
            page.get_screenshot(path=str(SHOT_DIR / f"error_{label}.png"))
            return {"label": label, "sid": server_id, "ok": False, "msg": "未找到按钮"}
        
        renew_btn.click()
        time.sleep(5)
        if solve_recaptcha_audio(page):
            time.sleep(3)
            renew_confirm = page.ele('css:button.purple', timeout=5)
            if renew_confirm and renew_confirm.is_displayed():
                renew_confirm.click()
                time.sleep(10)
            page.get(renew_url)
            time.sleep(5)
            _, new_time, new_sec = get_server_info(page)
            if new_sec > old_sec: return {"label": label, "sid": server_id, "ok": True, "old": old_time, "new": new_time}
        return {"label": label, "sid": server_id, "ok": False, "msg": "流程未完成"}
    except Exception as e: return {"label": label, "sid": "Error", "ok": False, "msg": f"异常: {e}"}
    finally:
        try: page.quit()
        except: pass

def run():
    accounts = collect_accounts()
    if not accounts: return False
    results = []
    for label, url, ck in accounts:
        results.append(run_one(label, url, ck))
        time.sleep(random.uniform(5, 10))
    ok_count = sum(1 for r in results if r.get("ok"))
    summary = [f"🎮 <b>host2play 续期</b>", f"⏰ {now_cn():%Y-%m-%d %H:%M:%S}", "", f"📊 总账号: {len(results)} | ✅ {ok_count} | ❌ {len(results)-ok_count}", ""]
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        summary.append(f"👤 <b>{r['label']}</b> ({r.get('sid', 'Unknown')}): {status} {r.get('msg', '成功') if not r.get('new') else r['new']}")
    tg("\n".join(summary))
    return all(r.get("ok") for r in results)

def collect_accounts():
    accounts = []
    multi = os.getenv("H2P_ACCOUNTS", "").strip()
    if multi:
        for line in multi.splitlines():
            parts = line.strip().split("|||")
            if len(parts) >= 3: accounts.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    if not accounts and RENEW_URL and COOKIE_STR: accounts.append(("main", RENEW_URL, COOKIE_STR))
    return accounts

if __name__ == "__main__":
    if run(): sys.exit(0)
    else: sys.exit(1)
