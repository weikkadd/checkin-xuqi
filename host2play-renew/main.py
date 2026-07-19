#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本 (渲染增强版)
=====================
- 修复：针对 Headless 模式下动态内容加载慢导致的 Unknown 问题
- 优化：增强对 Expires 时间和 Server ID 的捕获逻辑
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
    """增强版：动态等待并抓取服务器信息"""
    server_id = "Unknown"
    expires_text = "Unknown"
    expires_sec = -1
    
    # 循环等待页面内容加载 (最多等待 20 秒)
    for _ in range(10):
        html = page.html
        # 1. 尝试匹配时间格式 (XX:XX:XX)
        time_match = re.search(r"(\d{1,2}:\d{2}:\d{2})", html)
        if time_match:
            expires_text = time_match.group(1)
            expires_sec = parse_expires(expires_text)
            
            # 2. 尝试匹配服务器 ID (Renew server: XXXX)
            sid_match = re.search(r"Renew server:\s*([a-zA-Z0-9]+)", html, re.IGNORECASE)
            if sid_match:
                server_id = sid_match.group(1)
            else:
                # 备选：从 h2 标签提取
                h2 = page.ele('tag:h2', timeout=1)
                if h2 and ":" in h2.text:
                    server_id = h2.text.split(":")[-1].strip()
            
            if server_id != "Unknown":
                break
        time.sleep(2)
        
    return server_id, expires_text, expires_sec

# ==========================================================
# reCAPTCHA 音频识别
# ==========================================================
def solve_recaptcha_audio(page) -> bool:
    try:
        import speech_recognition as sr
        import pydub
    except: return False
    log.info("🤖 开始处理 reCAPTCHA...")
    checkbox_iframe = page.ele('css:iframe[src*="recaptcha/api2/banchor"]', timeout=15)
    if not checkbox_iframe: return False
    try:
        page.switch_to.frame(checkbox_iframe)
        checkbox = page.ele('css:.recaptcha-checkbox-checkmark', timeout=5)
        if checkbox: checkbox.click()
        page.switch_to.main_frame()
    except: pass
    time.sleep(5)
    for attempt in range(MAX_RETRY):
        try:
            challenge_iframe = page.ele('css:iframe[src*="recaptcha/api2/bframe"]', timeout=10)
            if not challenge_iframe:
                iframes = page.eles('css:iframe[src*="recaptcha"]')
                if len(iframes) >= 2: challenge_iframe = iframes[1]
            if not challenge_iframe: continue
            page.switch_to.frame(challenge_iframe)
            audio_btn = page.ele('css:.rc-button-audio', timeout=5)
            if audio_btn: audio_btn.click()
            else: 
                page.switch_to.main_frame()
                continue
            time.sleep(5)
            audio_link = page.ele('css:.rc-audiochallenge-tdownload-link', timeout=5)
            if not audio_link:
                page.switch_to.main_frame()
                continue
            audio_url = audio_link.attr('href')
            audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)
            wav_file = SHOT_DIR / f"audio_{attempt}.wav"
            pydub.AudioSegment.from_mp3(str(audio_file)).export(str(wav_file), format="wav")
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                text = recognizer.recognize_google(recognizer.record(source))
            input_box = page.ele('css:#audio-response', timeout=5)
            if input_box:
                input_box.input(text)
                verify_btn = page.ele('css:#recaptcha-verify-button', timeout=5)
                if not verify_btn: verify_btn = page.ele('css:.rc-button-goog-default', timeout=3)
                if verify_btn: verify_btn.click()
            page.switch_to.main_frame()
            time.sleep(3)
            return True
        except:
            page.switch_to.main_frame()
    return False

def inject_cookies(page, cookie_str: str):
    if not cookie_str: return
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            try: page.set.cookies({k.strip(): v.strip()})
            except: pass

def run_one(label: str, renew_url: str, cookie_str: str):
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    co.headless()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--user-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
    page = ChromiumPage(co)
    page.set.timeouts(PAGE_TIMEOUT)
    try:
        page.get(renew_url)
        time.sleep(5)
        if cookie_str:
            inject_cookies(page, cookie_str)
            page.get(renew_url)
            time.sleep(5)
        
        server_id, old_time, old_sec = get_server_info(page)
        log.info(f"👤 账号: {label} | 🆔 伺服器: {server_id} | ⏱️ 剩余: {old_time}")

        if 0 < old_sec > RENEW_THRESHOLD_SECONDS:
            h = old_sec // 3600
            return {"label": label, "sid": server_id, "ok": True, "msg": f"跳过 ({h}h)", "new": f"{h}h"}

        renew_btn = page.ele('text:Renew server', timeout=10)
        if not renew_btn: renew_btn = page.ele('css:button', timeout=5)
        if not renew_btn: return {"label": label, "sid": server_id, "ok": False, "msg": "未找到 Renew 按钮"}
        
        renew_btn.click()
        time.sleep(5)
        if solve_recaptcha_audio(page):
            time.sleep(5)
            renew_modal_btn = page.ele('css:button.purple', timeout=5)
            if renew_modal_btn: renew_modal_btn.click()
            time.sleep(10)
            page.get(renew_url)
            _, new_time, new_sec = get_server_info(page)
            if new_sec > old_sec:
                return {"label": label, "sid": server_id, "ok": True, "old": old_time, "new": new_time}
        return {"label": label, "sid": server_id, "ok": False, "msg": "续期未成功"}
    except Exception as e:
        return {"label": label, "sid": "Error", "ok": False, "msg": f"异常: {e}"}
    finally:
        try: page.quit()
        except: pass

def run():
    accounts = collect_accounts()
    if not accounts: return False
    results = [run_one(label, url, ck) for label, url, ck in accounts]
    ok_count = sum(1 for r in results if r.get("ok"))
    summary = [f"🎮 <b>host2play 续期</b>", f"⏰ {now_cn():%Y-%m-%d %H:%M:%S} (北京)", "", f"📊 总账号: {len(results)} | ✅ {ok_count} | ❌ {len(results)-ok_count}", ""]
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        sid = r.get("sid", "Unknown")
        summary.append(f"👤 <b>{r['label']}</b> ({sid}): {status} {r.get('msg', '成功') if not r.get('new') else r['new']}")
    tg("\n".join(summary))
    return all(r.get("ok") for r in results)

def collect_accounts():
    accounts = []
    multi = os.getenv("H2P_ACCOUNTS", "").strip()
    if multi:
        for line in multi.splitlines():
            parts = line.strip().split("|||")
            if len(parts) >= 3: accounts.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    if not accounts and RENEW_URL and COOKIE_STR:
        accounts.append(("main", RENEW_URL, COOKIE_STR))
    return accounts

if __name__ == "__main__":
    if run(): sys.exit(0)
    else: sys.exit(1)
