#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本 (Manus 优化版)
=====================
- 增强：优化 reCAPTCHA iframe 定位逻辑，增加多层级查找
- 增强：提升音讯验证码识别的容错性，增加随机延迟模拟真人
- 修复：解决 "未找到验证码 Checkbox iframe" 的偶发问题
- 逻辑：阈值 25 小时，适配 8h 和 24h 账号
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
    """通过 innerText 获取纯文本，精准抓取信息"""
    server_id = "Unknown"
    expires_text = "Unknown"
    expires_sec = -1
    
    for _ in range(10):
        try:
            # 获取页面纯文本内容
            text_content = page.run_js("return document.body.innerText")
            
            # 1. 提取剩余时间 (XX:XX:XX)
            time_match = re.search(r"(\d{1,2}:\d{2}:\d{2})", text_content)
            if time_match:
                expires_text = time_match.group(1)
                expires_sec = parse_expires(expires_text)
                
                # 2. 提取服务器 ID (Renew server: bof5032)
                sid_match = re.search(r"Renew server:\s*([a-zA-Z0-9]+)", text_content, re.IGNORECASE)
                if sid_match:
                    server_id = sid_match.group(1)
                
                if server_id != "Unknown":
                    break
        except: pass
        time.sleep(2)
        
    return server_id, expires_text, expires_sec

# ==========================================================
# reCAPTCHA 音频识别
# ==========================================================
def solve_recaptcha_audio(page) -> bool:
    try:
        import speech_recognition as sr
        import pydub
    except ImportError:
        log.error("❌ 缺少依赖: SpeechRecognition 或 pydub，请检查 requirements.txt")
        return False
    
    log.info("🤖 开始处理 reCAPTCHA...")
    
    # 1. 寻找 Checkbox Iframe (增加多重匹配)
    checkbox_iframe = None
    selectors = [
        'css:iframe[src*="recaptcha/api2/banchor"]',
        'css:iframe[title*="reCAPTCHA"]',
        'xpath://iframe[contains(@src, "anchor")]'
    ]
    
    for selector in selectors:
        checkbox_iframe = page.ele(selector, timeout=10)
        if checkbox_iframe: break
        
    if not checkbox_iframe: 
        log.warning("❌ 未找到验证码 Checkbox iframe，尝试直接查找页面元素...")
        # 兜底：如果找不到 iframe，可能是已经加载或结构异常
        if page.ele('css:.recaptcha-checkbox-checkmark', timeout=2):
            log.info("💡 发现直接存在的 Checkbox 元素")
        else:
            return False
    
    try:
        if checkbox_iframe:
            page.switch_to.frame(checkbox_iframe)
        
        checkbox = page.ele('css:.recaptcha-checkbox-checkmark', timeout=5)
        if checkbox:
            log.info("🖱️ 点击 Checkbox")
            checkbox.click()
            time.sleep(random.uniform(2, 4))
        
        page.switch_to.main_frame()
    except Exception as e:
        log.warning(f"❌ 点击 Checkbox 失败: {e}")
        page.switch_to.main_frame()

    time.sleep(3)
    
    # 2. 检查是否直接通过
    # 如果 checkbox 勾选了，通常不需要后续音频验证
    
    # 3. 尝试识别音轨
    for attempt in range(MAX_RETRY):
        try:
            # 寻找挑战框 Iframe
            challenge_iframe = None
            c_selectors = [
                'css:iframe[src*="recaptcha/api2/bframe"]',
                'xpath://iframe[contains(@src, "bframe")]',
                'css:iframe[title*="验证码挑战"]'
            ]
            for cs in c_selectors:
                challenge_iframe = page.ele(cs, timeout=5)
                if challenge_iframe: break
            
            if not challenge_iframe:
                # 尝试通过 index 寻找第二个 recaptcha iframe
                iframes = page.eles('css:iframe[src*="recaptcha"]')
                if len(iframes) >= 2: challenge_iframe = iframes[1]
            
            if not challenge_iframe:
                log.info("✅ 未发现挑战框，可能已直接通过")
                return True

            page.switch_to.frame(challenge_iframe)
            
            # 点击音频按钮
            audio_btn = page.ele('css:#recaptcha-audio-button', timeout=5)
            if not audio_btn: audio_btn = page.ele('css:.rc-button-audio', timeout=2)
            
            if audio_btn: 
                log.info(f"🎵 切换到音频验证 (尝试 {attempt+1})")
                audio_btn.click()
                time.sleep(random.uniform(3, 5))
            else: 
                # 检查是否已经处于音频模式
                if not page.ele('css:#audio-response', timeout=2):
                    page.switch_to.main_frame()
                    continue

            # 获取音频下载链接
            audio_link = page.ele('css:.rc-audiochallenge-tdownload-link', timeout=5)
            if not audio_link:
                # 检查是否被拦截 (如：您的计算机或网络可能正在发送自动查询)
                if "自动查询" in page.html or "automated queries" in page.html:
                    log.error("🚫 IP 被 Google 拦截，无法获取音频验证码")
                    page.switch_to.main_frame()
                    return False
                page.switch_to.main_frame()
                continue

            audio_url = audio_link.attr('href')
            audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)
            
            # 转换为 WAV (SpeechRecognition 需求)
            wav_file = SHOT_DIR / f"audio_{attempt}.wav"
            try:
                pydub.AudioSegment.from_mp3(str(audio_file)).export(str(wav_file), format="wav")
            except Exception as e:
                log.error(f"❌ 音频转换失败 (可能缺少 ffmpeg): {e}")
                page.switch_to.main_frame()
                return False
            
            # 语音识别
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="en-US")
            
            log.info(f"✅ 识别结果: {text}")
            
            # 输入识别结果
            input_box = page.ele('css:#audio-response', timeout=5)
            if input_box:
                input_box.input(text)
                time.sleep(1)
                verify_btn = page.ele('css:#recaptcha-verify-button', timeout=5)
                if not verify_btn: verify_btn = page.ele('css:.rc-button-goog-default', timeout=3)
                if verify_btn: 
                    verify_btn.click()
                    log.info("🔘 点击验证按钮")
            
            page.switch_to.main_frame()
            time.sleep(3)
            
            # 检查是否验证成功 (挑战框消失)
            if not page.ele('css:iframe[src*="recaptcha/api2/bframe"]', timeout=3):
                log.info("🎉 reCAPTCHA 验证成功")
                return True
                
        except Exception as e:
            log.warning(f"⚠️ 识别尝试 {attempt+1} 失败: {e}")
            page.switch_to.main_frame()
            time.sleep(2)
            
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
    """为带认证的代理创建临时插件"""
    import zipfile
    if "@" not in proxy_url: return None
    
    try:
        auth_part, addr_part = proxy_url.split("://")[1].split("@")
        proxy_user, proxy_pass = auth_part.split(":")
        proxy_host, proxy_port = addr_part.split(":")
    except: return None

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": { "scripts": ["background.js"] },
        "minimum_chrome_version":"22.0.0"
    }
    """
    background_js = """
    var config = {
        mode: "fixed_servers",
        rules: {
            singleProxy: {
                scheme: "http",
                host: "%s",
                port: parseInt(%s)
            },
            bypassList: ["localhost"]
        }
    };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }
    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        {urls: ["<all_urls>"]},
        ['blocking']
    );
    """ % (proxy_host, proxy_port, proxy_user, proxy_pass)
    
    plugin_path = ROOT / f"proxy_auth_plugin.zip"
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
    
    # 代理设置
    if PROXY_URL:
        if "@" in PROXY_URL:
            log.info(f"🌐 使用带认证的代理: {PROXY_URL.split('@')[1]}")
            plugin = create_proxy_auth_extension(PROXY_URL)
            if plugin: co.add_extension(plugin)
            else: co.set_proxy(PROXY_URL)
        else:
            log.info(f"🌐 使用代理: {PROXY_URL}")
            co.set_proxy(PROXY_URL)
    elif WARP_PROXY:
        log.info(f"🌐 使用 WARP 代理: {WARP_PROXY}")
        co.set_proxy(WARP_PROXY)

    # 反爬参数
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
    
    page = ChromiumPage(co)
    page.set.timeouts(PAGE_TIMEOUT)
    try:
        log.info(f"🌐 正在访问: {renew_url}")
        page.get(renew_url)
        time.sleep(5)
        
        if cookie_str:
            inject_cookies(page, cookie_str)
            page.get(renew_url)
            time.sleep(8)
        
        server_id, old_time, old_sec = get_server_info(page)
        log.info(f"👤 账号: {label} | 🆔 伺服器: {server_id} | ⏱️ 剩余: {old_time}")

        if old_sec > RENEW_THRESHOLD_SECONDS:
            h = old_sec // 3600
            log.info(f"⏭️ 剩余时间充足 ({h}h)，跳过续期")
            return {"label": label, "sid": server_id, "ok": True, "msg": f"跳过 ({h}h)", "new": f"{h}h"}

        # 寻找续期按钮
        renew_btn = None
        btn_selectors = ['text:Renew server', 'css:button.purple', 'xpath://button[contains(text(), "Renew")]']
        for sel in btn_selectors:
            renew_btn = page.ele(sel, timeout=5)
            if renew_btn: break
            
        if not renew_btn: 
            # 截图留证
            page.get_screenshot(path=str(SHOT_DIR / f"error_{label}.png"))
            return {"label": label, "sid": server_id, "ok": False, "msg": "未找到 Renew 按钮"}
        
        log.info("🖱️ 点击 Renew server 按钮")
        renew_btn.click()
        time.sleep(5)
        
        # 处理验证码
        if solve_recaptcha_audio(page):
            time.sleep(3)
            # 再次寻找确认按钮 (有时点击验证后会自动触发，有时需要再点一次页面上的 Renew)
            renew_confirm = page.ele('css:button.purple', timeout=5)
            if renew_confirm and renew_confirm.is_displayed():
                log.info("🔘 点击最终确认按钮")
                renew_confirm.click()
                time.sleep(10)
            
            # 刷新页面验证结果
            page.get(renew_url)
            time.sleep(5)
            _, new_time, new_sec = get_server_info(page)
            if new_sec > old_sec:
                log.info(f"✨ 续期成功! 新剩余时间: {new_time}")
                return {"label": label, "sid": server_id, "ok": True, "old": old_time, "new": new_time}
            else:
                log.warning("❓ 验证码通过但时间未增加")
        
        return {"label": label, "sid": server_id, "ok": False, "msg": "续期流程未完成"}
    except Exception as e:
        log.error(f"💥 运行异常: {e}")
        return {"label": label, "sid": "Error", "ok": False, "msg": f"异常: {e}"}
    finally:
        try: page.quit()
        except: pass

def run():
    accounts = collect_accounts()
    if not accounts: 
        log.error("❌ 未找到任何账号配置，请检查 Secrets")
        return False
        
    results = []
    for label, url, ck in accounts:
        res = run_one(label, url, ck)
        results.append(res)
        time.sleep(random.uniform(5, 10)) # 账号间增加间隔
        
    ok_count = sum(1 for r in results if r.get("ok"))
    summary = [f"🎮 <b>host2play 续期</b>", f"⏰ {now_cn():%Y-%m-%d %H:%M:%S}", "", f"📊 总账号: {len(results)} | ✅ {ok_count} | ❌ {len(results)-ok_count}", ""]
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
            if not line.strip(): continue
            parts = line.strip().split("|||")
            if len(parts) >= 3: 
                accounts.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
            elif len(parts) == 2:
                accounts.append((f"server-{len(accounts)+1}", parts[0].strip(), parts[1].strip()))
                
    if not accounts and RENEW_URL and COOKIE_STR:
        accounts.append(("main", RENEW_URL, COOKIE_STR))
    return accounts

if __name__ == "__main__":
    success = run()
    if success: sys.exit(0)
    else: sys.exit(1)
