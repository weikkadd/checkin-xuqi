#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本
=====================
- 修复：GitHub Actions 环境下浏览器启动失败问题 (Headless + No-Sandbox)
- 逻辑：保持原有的续期流程和时间逻辑不变
"""

import os
import sys
import time
import json
import random
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ==========================================================
# 配置
# ==========================================================

# 续期页面 URL（从环境变量读取）
RENEW_URL = os.getenv("H2P_RENEW_URL", "")

# Cookie 字符串
COOKIE_STR = os.getenv("H2P_COOKIE", "")

# WARP 代理
WARP_PROXY = os.getenv("WARP_PROXY", "")

# 续期参数
MAX_RETRY = 5
PAGE_TIMEOUT = 60

# TG 通知
TG_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# 东八区时区
TZ_CN = timezone(timedelta(hours=8))

def now_cn():
    return datetime.now(TZ_CN)

# ==========================================================
# 文件
# ==========================================================

ROOT = Path(__file__).parent
SHOT_DIR = ROOT / "output" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================================
# 日志
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("renew.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("host2play")

# ==========================================================
# TG 通知
# ==========================================================

def tg(msg: str, silent: bool = False):
    """Telegram 通知"""
    prefix = "🎮 <b>host2play</b>\n"
    if "host2play" not in msg.lower():
        msg = prefix + msg
    if not TG_TOKEN or not TG_CHAT_ID:
        log.info(f"📧 TG 通知（未配置）: {msg[:80]}")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_notification": silent,
            },
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            log.info(f"✅ TG 通知发送成功")
        else:
            log.warning(f"⚠️ TG 通知失败: {resp.text[:200]}")
    except Exception as e:
        log.warning(f"❌ TG 通知异常: {e}")

# ==========================================================
# 工具
# ==========================================================

def screenshot(page, name: str):
    """保存截图"""
    p = SHOT_DIR / f"{datetime.now():%H%M%S}_{name}.png"
    try:
        page.get_screenshot(str(p), full_page=True)
        log.info(f"截图: {p}")
    except Exception as e:
        log.warning(f"截图失败: {e}")
    return p

def parse_expires(text: str) -> int:
    """解析 'Expires in: 07:57:29' 返回秒数"""
    import re
    if not text:
        return -1
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return -1

def get_expires_seconds(page) -> int:
    """从页面获取剩余秒数"""
    try:
        text = page.html or ""
        import re
        m = re.search(r"Expires\s*in[:\s]*</[^>]+>\s*(\d{1,2}:\d{2}:\d{2})", text, re.IGNORECASE)
        if m:
            sec = parse_expires(m.group(1))
            if sec > 0:
                log.info(f"剩余时间: {m.group(1)} → {sec}s")
                return sec
        body = page.ele('tag:body').text if page.ele('tag:body') else ""
        for line in body.split("\n"):
            if "expires" in line.lower() or ":" in line:
                sec = parse_expires(line)
                if 60 < sec < 86400 * 30:
                    log.info(f"剩余时间 [body] = {line.strip()} → {sec}s")
                    return sec
    except Exception as e:
        log.warning(f"提取剩余时间失败: {e}")
    return -1

# ==========================================================
# reCAPTCHA 音频识别
# ==========================================================

def solve_recaptcha_audio(page) -> bool:
    try:
        import speech_recognition as sr
        import pydub
    except ImportError:
        log.error("❌ 未安装 speech_recognition 或 pydub")
        return False

    log.info("🤖 开始处理 reCAPTCHA...")

    try:
        checkbox_iframe = page.ele('css:iframe[src*="recaptcha/api2/banchor"]', timeout=10)
        if checkbox_iframe:
            page.switch_to.frame(checkbox_iframe)
            time.sleep(1)
            checkbox = page.ele('css:.recaptcha-checkbox-checkmark', timeout=5)
            if checkbox:
                checkbox.click()
                log.info("✅ 点击了 reCAPTCHA checkbox")
                time.sleep(3)
            page.switch_to.main_frame()
    except Exception as e:
        log.warning(f"点击 checkbox 失败: {e}")

    time.sleep(2)
    try:
        page.switch_to.frame(checkbox_iframe)
        checkbox_class = page.ele('css:.recaptcha-checkbox').attr('class') or ''
        page.switch_to.main_frame()
        if 'recaptcha-checkbox-checked' in checkbox_class:
            log.info("✅ reCAPTCHA 直接通过")
            return True
    except:
        pass

    log.info("🔄 reCAPTCHA 弹出挑战，尝试音频识别...")

    for attempt in range(MAX_RETRY):
        log.info(f"🎵 音频识别尝试 {attempt + 1}/{MAX_RETRY}")
        try:
            challenge_iframe = page.ele('css:iframe[src*="recaptcha/api2/bframe"]', timeout=10)
            if not challenge_iframe:
                iframes = page.eles('css:iframe[src*="recaptcha"]')
                if len(iframes) >= 2: challenge_iframe = iframes[1]
            if not challenge_iframe: continue

            page.switch_to.frame(challenge_iframe)
            audio_btn = page.ele('css:.rc-button-audio', timeout=5)
            if audio_btn:
                audio_btn.click()
                time.sleep(3)
            else:
                page.switch_to.main_frame()
                continue

            audio_link = page.ele('css:.rc-audiochallenge-tdownload-link', timeout=5)
            if not audio_link:
                page.switch_to.main_frame()
                continue

            audio_url = audio_link.attr('href')
            audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)

            wav_file = SHOT_DIR / f"audio_{attempt}.wav"
            audio_segment = pydub.AudioSegment.from_mp3(str(audio_file))
            audio_segment.export(str(wav_file), format="wav")

            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            log.info(f"✅ 音频识别结果: '{text}'")

            input_box = page.ele('css:#audio-response', timeout=5)
            if input_box:
                input_box.input(text)
                time.sleep(1)
            
            verify_btn = page.ele('css:#recaptcha-verify-button', timeout=5)
            if not verify_btn: verify_btn = page.ele('css:.rc-button-goog-default', timeout=3)
            if verify_btn:
                verify_btn.click()
                time.sleep(3)

            page.switch_to.main_frame()
            time.sleep(2)
            
            page.switch_to.frame(checkbox_iframe)
            checkbox_class = page.ele('css:.recaptcha-checkbox').attr('class') or ''
            page.switch_to.main_frame()
            if 'recaptcha-checkbox-checked' in checkbox_class:
                log.info("🎉 reCAPTCHA 音频识别成功！")
                return True
        except Exception as e:
            log.warning(f"尝试 {attempt+1} 失败: {e}")
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

# ==========================================================
# 主流程
# ==========================================================

def run_one(label: str, renew_url: str, cookie_str: str):
    from DrissionPage import ChromiumPage, ChromiumOptions

    log.info("\n" + "=" * 60)
    log.info(f"👤 账号: {label}")
    log.info(f"续期 URL: {renew_url}")
    log.info("=" * 60)

    co = ChromiumOptions()
    co.headless()  # ★ 关键：适配 GitHub Actions
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=en-US')
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

        old_sec = get_expires_seconds(page)
        renew_btn = page.ele('text:Renew server', timeout=10)
        if not renew_btn: renew_btn = page.ele('css:button', timeout=5)
        if not renew_btn: return {"label": label, "ok": False, "msg": "未找到 Renew 按钮"}

        renew_btn.click()
        time.sleep(3)

        if solve_recaptcha_audio(page):
            time.sleep(2)
            renew_modal_btn = page.ele('css:button.purple', timeout=5)
            if renew_modal_btn:
                renew_modal_btn.click()
                time.sleep(5)
            
            page.get(renew_url)
            time.sleep(5)
            new_sec = get_expires_seconds(page)
            if new_sec > old_sec:
                return {"label": label, "ok": True, "old": f"{old_sec//3600}h", "new": f"{new_sec//3600}h"}
        
        return {"label": label, "ok": False, "msg": "续期未成功"}
    except Exception as e:
        return {"label": label, "ok": False, "msg": f"异常: {e}"}
    finally:
        try: page.quit()
        except: pass

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

def run():
    accounts = collect_accounts()
    if not accounts: return False
    results = [run_one(label, url, ck) for label, url, ck in accounts]
    
    ok_count = sum(1 for r in results if r.get("ok"))
    summary = [f"🎮 <b>host2play 续期</b>", f"⏰ {now_cn():%Y-%m-%d %H:%M:%S} (北京)", "", f"📊 总账号: {len(results)} | ✅ {ok_count} | ❌ {len(results)-ok_count}", ""]
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        summary.append(f"👤 <b>{r['label']}</b>: {status} {r.get('msg', '成功')}")
    
    final_msg = "\n".join(summary)
    log.info("\n" + final_msg)
    tg(final_msg)
    return all(r.get("ok") for r in results)

if __name__ == "__main__":
    if run(): sys.exit(0)
    else: sys.exit(1)
