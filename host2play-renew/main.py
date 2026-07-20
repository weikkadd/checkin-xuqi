#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本
=====================
- 使用 DrissionPage 自动化浏览器操作
- 支持代理配置（家宽代理 / WARP）
- 支持 reCAPTCHA 音频验证码识别
- 支持多账号批量续期
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
PAGE_TIMEOUT = 180
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
    prefix = "\U0001f3ae <b>host2play</b>\n"
    if "host2play" not in msg.lower():
        msg = prefix + msg
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_notification": silent,
            },
            timeout=10,
        )
    except Exception:
        pass


def parse_expires(text: str) -> int:
    if not text:
        return -1
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return -1


def get_server_info(page):
    server_id = "Unknown"
    expires_text = "Unknown"
    expires_sec = -1

    for attempt in range(10):
        try:
            text_content = page.run_js("return document.body.innerText")
            time_match = re.search(r"(\d{1,2}:\d{2}:\d{2})", text_content)
            if time_match:
                expires_text = time_match.group(1)
                expires_sec = parse_expires(expires_text)
                sid_match = re.search(r"Renew server:\s*([a-zA-Z0-9\-]+)", text_content, re.IGNORECASE)
                if sid_match:
                    server_id = sid_match.group(1)
                if server_id == "Unknown":
                    sid_match2 = re.search(r"Server:\s*([a-zA-Z0-9\-]+)", text_content, re.IGNORECASE)
                    if sid_match2:
                        server_id = sid_match2.group(1)
                if server_id != "Unknown":
                    break
        except Exception:
            pass
        time.sleep(2)

    return server_id, expires_text, expires_sec


def debug_dump(page, label=""):
    try:
        shot_path = SHOT_DIR / f"debug_{label}_{int(time.time())}.png"
        page.get_screenshot(path=str(shot_path))
        log.info(f"调试截图已保存: {shot_path}")
    except Exception:
        pass
    try:
        src_path = SHOT_DIR / f"debug_src_{label}_{int(time.time())}.txt"
        src_path.write_text(page.html[:20000], encoding="utf-8")
        log.info(f"页面源码已保存: {src_path} (前20000字符)")
        
        # 保存所有按钮信息
        btns_path = SHOT_DIR / f"debug_btns_{label}_{int(time.time())}.txt"
        all_buttons = page.eles('css:button')
        btn_info = []
        for i, btn in enumerate(all_buttons):
            try:
                text = btn.text[:50] if btn.text else "no text"
                cls = btn.attr("class") or ""
                disp = btn.is_displayed()
                hid = btn.is_hidden()
                btn_info.append(f"  btn[{i}]: text='{text}' class='{cls}' displayed={disp} hidden={hid}")
            except Exception:
                pass
        btns_path.write_text("\n".join(btn_info), encoding="utf-8")
        log.info(f"按钮列表已保存: {btns_path} ({len(all_buttons)}个按钮)")
    except Exception as e:
        log.warning(f"保存调试信息失败: {e}")


def solve_recaptcha_audio(page) -> bool:
    """解决 reCAPTCHA 音频验证码 - DrissionPage 4.x 兼容版"""
    try:
        import speech_recognition as sr
        import pydub
    except ImportError:
        log.error("缺少依赖: SpeechRecognition 或 pydub")
        return False

    log.info("开始处理 reCAPTCHA...")

    recaptcha_frame = None

    # 方法1：通过 src 属性查找
    log.info("尝试通过 src 属性查找 reCAPTCHA iframe...")
    recaptcha_frame = page.get_frame('@src*="recaptcha"')
    if recaptcha_frame:
        log.info(f"找到 reCAPTCHA iframe")
    else:
        log.info("尝试通过 title 属性查找 reCAPTCHA iframe...")
        recaptcha_frame = page.get_frame('@title*="recaptcha"')
        if recaptcha_frame:
            log.info("找到 reCAPTCHA iframe (via title)")
        else:
            log.info("尝试遍历所有 iframe...")
            all_frames = page.eles('css:iframe')
            log.info(f"页面中共找到 {len(all_frames)} 个 iframe")
            for idx, fr in enumerate(all_frames):
                src = fr.attr("src") or ""
                title = fr.attr("title") or ""
                log.info(f"  iframe[{idx}] src={src[:60]} title={title[:30]}")
                if "recaptcha" in src.lower() or "recaptcha" in title.lower():
                    recaptcha_frame = fr
                    log.info(f"手动匹配到 reCAPTCHA iframe[{idx}]")
                    break

    if not recaptcha_frame:
        log.error("未找到任何 reCAPTCHA iframe")
        debug_dump(page, "no_recaptcha_frame")
        return False

    # 在 iframe 内找到并点击 checkbox
    checkbox_found = False
    try:
        for sel in ['css:.recaptcha-checkbox-checkmark', 'css:.recaptcha-checkbox-input', 'css:input[type="checkbox"]']:
            try:
                cb = recaptcha_frame.ele(sel, timeout=5)
                if cb:
                    log.info(f"在 iframe 中找到 checkbox: {sel}")
                    cb.click()
                    checkbox_found = True
                    log.info("已点击 checkbox")
                    break
            except Exception as e:
                log.warning(f"选择器 {sel} 失败: {e}")
                continue

        if not checkbox_found:
            try:
                cb = recaptcha_frame.ele('@role="checkbox"', timeout=5)
                if cb:
                    cb.click()
                    checkbox_found = True
                    log.info("通过 role=checkbox 点击成功")
            except Exception as e:
                log.warning(f"role=checkbox 失败: {e}")
    except Exception as e:
        log.error(f"操作 iframe 内元素失败: {e}")
        debug_dump(page, "iframe_click_fail")
        return False

    if not checkbox_found:
        log.info("未找到 checkbox，可能已自动通过")
        time.sleep(3)
        return True

    time.sleep(random.uniform(3, 6))

    # 处理 reCAPTCHA 挑战（音频验证码）
    for attempt in range(MAX_RETRY):
        log.info(f"第 {attempt + 1} 次尝试 reCAPTCHA 挑战...")
        debug_dump(page, f"challenge_start_{attempt}")

        challenge_frame = None
        log.info("尝试查找 challenge iframe (bframe)...")
        challenge_frame = page.get_frame('@src*="bframe"')
        if challenge_frame:
            log.info("找到 challenge iframe (bframe)")
        else:
            all_frames = page.eles('css:iframe')
            for fr in all_frames:
                src = fr.attr("src") or ""
                if "recaptcha" in src.lower() and "bframe" in src.lower():
                    challenge_frame = fr
                    log.info(f"找到 challenge iframe: {src[:60]}")
                    break

        if not challenge_frame:
            log.info("未找到 challenge iframe，假设已通过验证")
            return True

        # 在 challenge iframe 中点击音频按钮
        audio_btn = None
        audio_selectors = [
            '@id="recaptcha-audio-button"',
            '.rc-button-audio',
            '@aria-label="Audio CAPTCHA"',
        ]
        for sel in audio_selectors:
            try:
                audio_btn = challenge_frame.ele(sel, timeout=5)
                if audio_btn:
                    log.info(f"找到音频按钮: {sel}")
                    break
            except Exception:
                pass

        if audio_btn:
            audio_btn.click()
            log.info("已点击音频按钮")
            time.sleep(random.uniform(3, 5))
        else:
            log.info("未找到音频按钮")

        # 下载音频文件
        audio_link = None
        audio_selectors = [
            '.rc-audiochallenge-tdownload-link',
            '@href*="audio"',
        ]
        for sel in audio_selectors:
            try:
                audio_link = challenge_frame.ele(sel, timeout=5)
                if audio_link:
                    log.info(f"找到音频下载链接: {sel}")
                    break
            except Exception:
                pass

        if not audio_link:
            log.warning(f"未找到音频下载链接，重试...")
            debug_dump(page, f"no_audio_link_{attempt}")
            time.sleep(2)
            continue

        # 下载音频
        audio_url = audio_link.attr("href")
        audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
        try:
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)
            log.info(f"音频已下载: {len(resp.content)} bytes")
        except Exception as e:
            log.warning(f"下载音频失败: {e}")
            continue

        # 转换为 WAV
        wav_file = SHOT_DIR / f"audio_{attempt}.wav"
        try:
            pydub.AudioSegment.from_mp3(str(audio_file)).export(str(wav_file), format="wav")
            log.info("音频已转换为 WAV")
        except Exception as e:
            log.warning(f"WAV 转换失败: {e}")
            continue

        # 语音识别
        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language="en-US")
            log.info(f"识别结果: {text}")
        except Exception as e:
            log.warning(f"语音识别失败: {e}")
            continue

        # 输入答案并提交
        try:
            input_box = challenge_frame.ele('@id="audio-response"', timeout=5)
            if input_box:
                input_box.input(text)
                log.info(f"已输入答案: {text}")
                time.sleep(1)

                verify_btn = challenge_frame.ele('@id="recaptcha-verify-button"', timeout=5)
                if verify_btn:
                    verify_btn.click()
                    log.info("已点击验证按钮")
                else:
                    for vs in ['.rc-button-default', '@aria-label="Verify"']:
                        try:
                            vb = challenge_frame.ele(vs, timeout=3)
                            if vb:
                                vb.click()
                                log.info(f"通过 {vs} 点击验证按钮")
                                break
                        except Exception:
                            pass
        except Exception as e:
            log.warning(f"输入验证失败: {e}")

        time.sleep(5)

        # 检查验证是否通过
        try:
            remaining_challenge = page.get_frame('@src*="bframe"')
            if not remaining_challenge:
                log.info("reCAPTCHA 验证通过")
                return True
            else:
                log.info("仍有 challenge iframe，继续下一轮尝试")
        except Exception as e:
            log.warning(f"检查验证状态失败: {e}")
            return True

    log.error("reCAPTCHA 音频识别全部失败")
    debug_dump(page, "final_fail")
    return False


def inject_cookies(page, cookie_str: str):
    if not cookie_str:
        return
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                page.set.cookies({k.strip(): v.strip()})
            except Exception:
                pass


def create_proxy_auth_extension(proxy_url):
    import zipfile

    if "@" not in proxy_url:
        return None
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
        log.info(f"代理解析: {scheme}://{proxy_host}:{proxy_port}")
    except Exception:
        return None

    manifest_json = json.dumps(
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy",
                "tabs",
                "unlimitedStorage",
                "storage",
                "<all_urls>",
                "webRequest",
                "webRequestBlocking",
            ],
            "background": {"scripts": ["background.js"]},
            "minimum_chrome_version": "22.0.0",
        }
    )
    background_js = """
    var config = { mode: "fixed_servers", rules: { singleProxy: { scheme: "%s", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    chrome.webRequest.onAuthRequired.addListener(function(details) {
        return { authCredentials: { username: "%s", password: "%s" } };
    }, {urls: ["<all_urls>"]}, ['blocking']);
    """ % (scheme, proxy_host, proxy_port, proxy_user, proxy_pass)

    plugin_path = ROOT / "proxy_auth_plugin.zip"
    with zipfile.ZipFile(str(plugin_path), "w") as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return str(plugin_path)


def run_one(label: str, renew_url: str, cookie_str: str):
    """执行单个账号的续期"""
    from DrissionPage import ChromiumPage, ChromiumOptions

    co = ChromiumOptions()
    co.headless()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--disable-extensions")
    co.set_argument("--disable-background-timer-throttling")
    co.set_argument("--disable-renderer-backgrounding")
    co.set_argument("--disable-backgrounding-occluded-windows")
    co.set_user_agent(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    if PROXY_URL:
        if "@" in PROXY_URL:
            plugin = create_proxy_auth_extension(PROXY_URL)
            if plugin:
                co.add_extension(plugin)
            else:
                co.set_argument(f"--proxy-server={PROXY_URL}")
        else:
            co.set_argument(f"--proxy-server={PROXY_URL}")
    elif WARP_PROXY:
        co.set_argument(f"--proxy-server={WARP_PROXY}")

    page = ChromiumPage(co)
    page.set.timeouts(PAGE_TIMEOUT)

    try:
        # 检查出口 IP
        try:
            page.get("https://api.ip.sb/ip", timeout=15)
            ip = page.run_js("return document.body.innerText").strip()
            log.info(f"当前出口 IP: {ip}")
        except Exception as e:
            log.warning(f"IP检查失败: {e}")

        log.info(f"正在访问: {renew_url}")
        page.get(renew_url)
        time.sleep(5)

        # 注入 Cookie
        if cookie_str:
            log.info("注入 Cookie...")
            inject_cookies(page, cookie_str)
            page.get(renew_url)
            time.sleep(10)

        # 获取服务器信息
        server_id, old_time, old_sec = get_server_info(page)
        log.info(f"账号: {label} | 服务器: {server_id} | 剩余: {old_time} ({old_sec}秒)")

        # 如果剩余时间足够，跳过
        if old_sec > RENEW_THRESHOLD_SECONDS:
            return {
                "label": label,
                "sid": server_id,
                "ok": True,
                "msg": f"跳过 (剩余 {old_sec // 3600}h)",
                "new": f"{old_sec // 3600}h",
            }

        # 查找续期按钮
        renew_btn = None
        btn_texts = ["Renew server", "Renew", "Extend", "Continue"]
        for btn_text in btn_texts:
            try:
                renew_btn = page.ele(f"text:{btn_text}", timeout=5)
                if renew_btn:
                    log.info(f"找到续期按钮: text:{btn_text}")
                    break
            except Exception:
                pass
        
        if not renew_btn:
            try:
                renew_btn = page.ele('css:button.purple', timeout=5)
                if renew_btn:
                    log.info("找到紫色续期按钮")
            except Exception:
                pass
        
        if not renew_btn:
            try:
                renew_btn = page.ele('xpath://button[contains(text(), "Renew")]', timeout=5)
                if renew_btn:
                    log.info("找到续期按钮 (xpath)")
            except Exception:
                pass

        if not renew_btn:
            page.get_screenshot(path=str(SHOT_DIR / f"error_{label}_no_btn.png"))
            log.error("未找到续期按钮")
            debug_dump(page, "no_renew_btn")
            return {"label": label, "sid": server_id, "ok": False, "msg": "未找到按钮"}

        log.info("点击续期按钮...")
        renew_btn.click()
        
        # 等待 reCAPTCHA 出现
        log.info("等待 reCAPTCHA 出现...")
        time.sleep(10)

        # 处理 reCAPTCHA
        captcha_passed = solve_recaptcha_audio(page)
        if captcha_passed:
            log.info("reCAPTCHA 通过，等待续期请求提交...")
            
            # 保存当前页面状态
            debug_dump(page, "after_captcha")
            
            # 关键改动：reCAPTCHA 通过后，**再次点击续期按钮**
            # 因为第一次点击可能只触发了 reCAPTCHA，没有真正提交
            log.info("重新查找并点击续期按钮以提交续期请求...")
            time.sleep(3)
            
            renew_btn2 = None
            for btn_text in ["Renew server", "Renew", "Extend", "Continue"]:
                try:
                    renew_btn2 = page.ele(f"text:{btn_text}", timeout=5)
                    if renew_btn2:
                        log.info(f"找到续期按钮（第二次）: text:{btn_text}")
                        break
                except Exception:
                    pass
            
            if not renew_btn2:
                try:
                    renew_btn2 = page.ele('css:button.purple', timeout=5)
                    if renew_btn2:
                        log.info("找到紫色续期按钮（第二次）")
                except Exception:
                    pass
            
            if renew_btn2:
                log.info("再次点击续期按钮...")
                renew_btn2.click()
                log.info("等待续期处理...")
                time.sleep(20)
            else:
                log.info("未找到续期按钮，等待页面自动处理...")
                time.sleep(20)
            
            # 保存最终状态
            debug_dump(page, "after_final_wait")

            # 刷新页面同步状态
            log.info("刷新页面同步状态...")
            page.get(renew_url)
            time.sleep(10)

            # 检查新时间
            _, new_time, new_sec = get_server_info(page)
            log.info(f"新时间: {new_time} ({new_sec}秒), 旧时间: {old_time} ({old_sec}秒)")

            if new_sec > old_sec:
                return {
                    "label": label,
                    "sid": server_id,
                    "ok": True,
                    "old": old_time,
                    "new": new_time,
                }
            else:
                log.warning(f"时间未增加: {old_sec} -> {new_sec}")
                debug_dump(page, "time_not_increased")
                return {"label": label, "sid": server_id, "ok": False, "msg": f"时间未增加 ({old_sec}s -> {new_sec}s)"}
        else:
            log.warning("reCAPTCHA 未能通过")
            return {"label": label, "sid": server_id, "ok": False, "msg": "reCAPTCHA 流程未完成"}

    except Exception as e:
        log.error(f"运行异常: {e}")
        return {"label": label, "sid": "Error", "ok": False, "msg": f"异常: {e}"}
    finally:
        try:
            page.quit()
        except Exception:
            pass


def collect_accounts():
    """收集账号配置"""
    accounts = []
    multi = os.getenv("H2P_ACCOUNTS", "").strip()
    if multi:
        for line in multi.splitlines():
            parts = line.strip().split("|||")
            if len(parts) >= 3:
                accounts.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

    if not accounts and RENEW_URL and COOKIE_STR:
        accounts.append(("main", RENEW_URL, COOKIE_STR))

    return accounts


def run():
    """主运行函数"""
    accounts = collect_accounts()
    if not accounts:
        log.error("未找到任何账号配置")
        return False

    results = []
    for label, url, ck in accounts:
        log.info(f"========== 开始处理账号: {label} ==========")
        results.append(run_one(label, url, ck))
        time.sleep(random.uniform(5, 10))

    ok_count = sum(1 for r in results if r.get("ok"))
    summary = [
        "\U0001f3ae <b>host2play 续期</b>",
        f"\u23f0 {now_cn():%Y-%m-%d %H:%M:%S}",
        "",
        f"\U0001f4ca 总账号: {len(results)} | \u2705 {ok_count} | \u274c {len(results) - ok_count}",
        "",
    ]
    default_msg = "成功"
    for r in results:
        status = "\u2705" if r.get("ok") else "\u274c"
        if r.get("new"):
            summary.append(f"\U0001f464 <b>{r['label']}</b> ({r.get('sid', 'Unknown')}): {status} {r['new']}")
        else:
            summary.append(f"\U0001f464 <b>{r['label']}</b> ({r.get('sid', 'Unknown')}): {status} {r.get('msg', default_msg)}")

    tg("\n".join(summary))
    return all(r.get("ok") for r in results)


if __name__ == "__main__":
    if run():
        sys.exit(0)
    else:
        sys.exit(1)
