#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host2play 自动续期脚本
=====================
- DrissionPage 真实浏览器
- Cookie 注入登录
- reCAPTCHA v2 音频识别（方案 B）
- TG 通知（北京时间）
- 截图诊断
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

# WARP 代理（fscarmen/warp-on-actions 已启用系统级 WARP，Chrome 直连即可走 WARP）
# 不需要再设置 Chrome 代理，否则 DrissionPage 会拒绝 socks5 协议
WARP_PROXY = os.getenv("WARP_PROXY", "")  # 留空 = 不用代理，走系统 WARP

# 续期参数
MAX_RETRY = 5          # reCAPTCHA 最多重试次数
PAGE_TIMEOUT = 60      # 页面超时

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
    # HH:MM:SS
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    # MM:SS
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return -1

def get_expires_seconds(page) -> int:
    """从页面获取剩余秒数"""
    try:
        text = page.html or ""
        # 找 "Expires in:" 后面的时间
        import re
        m = re.search(r"Expires\s*in[:\s]*</[^>]+>\s*(\d{1,2}:\d{2}:\d{2})", text, re.IGNORECASE)
        if m:
            sec = parse_expires(m.group(1))
            if sec > 0:
                log.info(f"剩余时间: {m.group(1)} → {sec}s")
                return sec
        # 兜底：整页文本
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
    """用音频模式识别 reCAPTCHA v2

    流程:
    1. 找到 reCAPTCHA checkbox iframe
    2. 点击 checkbox
    3. 如果直接通过 → 返回 True
    4. 如果弹挑战 → 切换音频模式
    5. 下载音频 → SpeechRecognition 识别
    6. 输入结果 → 验证
    """
    try:
        import speech_recognition as sr
        import pydub
    except ImportError:
        log.error("❌ 未安装 speech_recognition 或 pydub")
        return False

    log.info("🤖 开始处理 reCAPTCHA...")

    # 1. 找到 reCAPTCHA checkbox iframe
    try:
        checkbox_iframe = page.ele('css:iframe[src*="recaptcha/api2/banchor"]', timeout=10)
        if not checkbox_iframe:
            # 兜底：找所有 recaptcha iframe
            iframes = page.eles('css:iframe[src*="recaptcha"]')
            if iframes:
                checkbox_iframe = iframes[0]
    except Exception:
        checkbox_iframe = None

    if not checkbox_iframe:
        log.warning("⚠️ 未找到 reCAPTCHA checkbox iframe")
        screenshot(page, "no_recaptcha")
        return False

    # 2. 切换到 checkbox iframe 并点击
    try:
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
        try:
            page.switch_to.main_frame()
        except:
            pass

    # 3. 检测是否直接通过（checkbox 变绿）
    time.sleep(2)
    try:
        page.switch_to.frame(checkbox_iframe)
        checkbox_class = page.ele('css:.recaptcha-checkbox').attr('class') or ''
        page.switch_to.main_frame()
        if 'recaptcha-checkbox-checked' in checkbox_class:
            log.info("✅ reCAPTCHA 直接通过（checkbox 变绿）")
            return True
    except:
        try:
            page.switch_to.main_frame()
        except:
            pass

    # 4. 没直接通过，需要处理挑战
    log.info("🔄 reCAPTCHA 弹出挑战，尝试音频识别...")

    for attempt in range(MAX_RETRY):
        log.info(f"🎵 音频识别尝试 {attempt + 1}/{MAX_RETRY}")

        # 找到挑战 iframe
        try:
            challenge_iframe = page.ele('css:iframe[src*="recaptcha/api2/bframe"]', timeout=10)
            if not challenge_iframe:
                iframes = page.eles('css:iframe[src*="recaptcha"]')
                if len(iframes) >= 2:
                    challenge_iframe = iframes[1]
        except Exception:
            challenge_iframe = None

        if not challenge_iframe:
            log.warning("⚠️ 未找到挑战 iframe")
            screenshot(page, f"no_challenge_{attempt}")
            time.sleep(2)
            continue

        # 切换到挑战 iframe
        try:
            page.switch_to.frame(challenge_iframe)
        except Exception as e:
            log.warning(f"切换挑战 iframe 失败: {e}")
            continue

        # 5. 点击音频按钮
        try:
            audio_btn = page.ele('css:.rc-button-audio', timeout=5)
            if not audio_btn:
                # 兜底：找带耳机图标的按钮
                audio_btn = page.ele('css:button[title="音频挑战"]', timeout=3)
            if audio_btn:
                audio_btn.click()
                log.info("✅ 点击了音频按钮")
                time.sleep(3)
            else:
                log.warning("⚠️ 未找到音频按钮")
                screenshot(page, f"no_audio_btn_{attempt}")
                page.switch_to.main_frame()
                continue
        except Exception as e:
            log.warning(f"点击音频按钮失败: {e}")
            try:
                page.switch_to.main_frame()
            except:
                pass
            continue

        # 6. 下载音频文件
        try:
            audio_link = page.ele('css:.rc-audiochallenge-tdownload-link', timeout=5)
            if not audio_link:
                log.warning("⚠️ 未找到音频下载链接")
                screenshot(page, f"no_audio_link_{attempt}")
                page.switch_to.main_frame()
                continue

            audio_url = audio_link.attr('href')
            log.info(f"📥 音频 URL: {audio_url[:80]}...")

            # 下载音频
            audio_file = SHOT_DIR / f"audio_{attempt}.mp3"
            resp = requests.get(audio_url, timeout=30)
            audio_file.write_bytes(resp.content)
            log.info(f"✅ 音频下载: {audio_file} ({len(resp.content)} bytes)")

        except Exception as e:
            log.warning(f"下载音频失败: {e}")
            try:
                page.switch_to.main_frame()
            except:
                pass
            continue

        # 7. 识别音频
        try:
            # 转换 mp3 → wav
            wav_file = SHOT_DIR / f"audio_{attempt}.wav"
            audio_segment = pydub.AudioSegment.from_mp3(str(audio_file))
            audio_segment.export(str(wav_file), format="wav")
            log.info(f"✅ 转换 WAV: {wav_file}")

            # SpeechRecognition 识别
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_file)) as source:
                audio_data = recognizer.record(source)

            # 用 Google Web Speech API 识别
            text = recognizer.recognize_google(audio_data)
            log.info(f"✅ 音频识别结果: '{text}'")

        except sr.UnknownValueError:
            log.warning("⚠️ 音频识别失败（无法理解音频）")
            text = ""
        except sr.RequestError as e:
            log.warning(f"⚠️ 识别服务错误: {e}")
            text = ""
        except Exception as e:
            log.warning(f"识别异常: {e}")
            text = ""

        if not text:
            # 识别失败，刷新换一道
            try:
                refresh_btn = page.ele('css:button[title="重新获取音频挑战"]', timeout=3)
                if not refresh_btn:
                    refresh_btn = page.ele('css:.rc-button-reload', timeout=3)
                if refresh_btn:
                    refresh_btn.click()
                    log.info("🔄 刷新音频挑战")
                    time.sleep(3)
            except:
                pass
            try:
                page.switch_to.main_frame()
            except:
                pass
            continue

        # 8. 输入识别结果
        try:
            input_box = page.ele('css:#audio-response', timeout=5)
            if not input_box:
                input_box = page.ele('css:.rc-audiochallenge-response', timeout=3)
            if input_box:
                input_box.clear()
                input_box.input(text)
                log.info(f"✅ 输入识别结果: '{text}'")
                time.sleep(1)
            else:
                log.warning("⚠️ 未找到输入框")
        except Exception as e:
            log.warning(f"输入失败: {e}")

        # 9. 点击验证按钮
        try:
            verify_btn = page.ele('css:button[disabled=""]', timeout=2)
            if not verify_btn:
                verify_btn = page.ele('css:.rc-button-goog-default', timeout=3)
            if verify_btn:
                verify_btn.click()
                log.info("✅ 点击了验证按钮")
                time.sleep(3)
        except Exception as e:
            log.warning(f"点击验证按钮失败: {e}")

        # 10. 检测是否通过
        try:
            page.switch_to.main_frame()
        except:
            pass

        time.sleep(3)

        # 检测 checkbox 是否变绿
        try:
            page.switch_to.frame(checkbox_iframe)
            checkbox_class = page.ele('css:.recaptcha-checkbox').attr('class') or ''
            page.switch_to.main_frame()
            if 'recaptcha-checkbox-checked' in checkbox_class:
                log.info("🎉 reCAPTCHA 音频识别成功！")
                return True
        except:
            try:
                page.switch_to.main_frame()
            except:
                pass

        log.warning(f"⚠️ 第 {attempt + 1} 次尝试失败，重试...")
        screenshot(page, f"recaptcha_fail_{attempt}")

    log.error(f"❌ reCAPTCHA {MAX_RETRY} 次尝试都失败")
    return False

# ==========================================================
# Cookie 注入
# ==========================================================

def inject_cookies(page) -> bool:
    """注入 cookie 到当前域名"""
    if not COOKIE_STR:
        log.warning("⚠️ 未配置 H2P_COOKIE")
        return False

    log.info(f"注入 cookie（{COOKIE_STR.count(';')+1} 项）...")
    injected = 0
    for item in COOKIE_STR.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        try:
            page.set.cookies({k: v})
            injected += 1
        except Exception as e:
            log.warning(f"  cookie [{k}] 注入失败: {e}")

    log.info(f"✅ 注入 {injected} 个 cookie")
    return True

# ==========================================================
# 主流程
# ==========================================================

def run():
    from DrissionPage import ChromiumPage, ChromiumOptions

    if not RENEW_URL:
        log.error("❌ 未配置 H2P_RENEW_URL")
        tg("❌ <b>续期失败</b>\n⚠️ 未配置 H2P_RENEW_URL")
        return False

    log.info("=" * 60)
    log.info("host2play 续期启动")
    log.info(f"续期 URL: {RENEW_URL}")
    log.info(f"TG_BOT_TOKEN: {'✅ 已配置' if TG_TOKEN else '❌ 未配置'}")
    log.info(f"TG_CHAT_ID: {'✅ 已配置' if TG_CHAT_ID else '❌ 未配置'}")
    log.info("=" * 60)

    # TG 启动通知
    tg(f"🚀 <b>host2play 续期启动</b>\n"
       f"⏰ {now_cn():%Y-%m-%d %H:%M:%S} (北京时间)\n"
       f"🌐 WARP: 已就绪", silent=True)

    # 配置浏览器
    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    co.set_argument('--lang=en-US')
    co.set_argument('--user-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
    # WARP 代理：fscarmen/warp-on-actions 已启用系统级 WARP（全局代理）
    # Chrome 直接连网就走 WARP，不需要再设置 Chrome 代理
    # 如果 WARP_PROXY 有值，用 Chrome --proxy-server（但 DrissionPage 不支持 socks5）
    if WARP_PROXY and not WARP_PROXY.startswith("socks"):
        co.set_argument(f'--proxy-server={WARP_PROXY}')
        log.info(f"🌐 使用代理: {WARP_PROXY}")
    else:
        log.info("🌐 走系统级 WARP（fscarmen/warp-on-actions 已启用）")

    page = ChromiumPage(co)
    page.set.timeouts(PAGE_TIMEOUT)

    try:
        # 1. 打开续期页面
        log.info("🌐 打开续期页面...")
        page.get(RENEW_URL)
        time.sleep(5)

        # 2. 注入 cookie 并刷新
        if COOKIE_STR:
            inject_cookies(page)
            log.info("🔄 刷新让 cookie 生效...")
            page.get(RENEW_URL)
            time.sleep(5)

        screenshot(page, "dashboard")

        # 3. 检测是否登录成功
        body_text = page.ele('tag:body').text if page.ele('tag:body') else ""
        if "Renew server" not in body_text and "Expires in" not in body_text:
            log.warning("⚠️ 可能未登录或页面未加载")
            screenshot(page, "not_logged_in")
            tg(f"⚠️ <b>续期失败</b>\n⏰ {now_cn():%H:%M:%S} (北京)\n⚠️ 页面未加载或 cookie 失效")
            return False

        # 4. 获取初始剩余时间
        old_sec = get_expires_seconds(page)
        if old_sec > 0:
            log.info(f"初始剩余: {old_sec}s ({old_sec//3600}h {(old_sec%3600)//60}m)")
            tg(f"📊 <b>当前剩余时间</b>\n⏳ {old_sec//3600}h {(old_sec%3600)//60}m", silent=True)
        else:
            log.info("初始剩余: 未识别")

        # 5. 点击 Renew server 按钮
        log.info("🖱️ 点击 Renew server 按钮...")
        try:
            renew_btn = page.ele('text:Renew server', timeout=10)
            if not renew_btn:
                renew_btn = page.ele('css:button', timeout=5)
            if renew_btn:
                renew_btn.click()
                log.info("✅ 点击了 Renew server 按钮")
                time.sleep(3)
            else:
                log.warning("⚠️ 未找到 Renew server 按钮")
                screenshot(page, "no_renew_btn")
                return False
        except Exception as e:
            log.warning(f"点击 Renew 按钮失败: {e}")
            screenshot(page, "click_fail")
            return False

        # 6. 处理 reCAPTCHA
        screenshot(page, "before_recaptcha")
        log.info("🤖 检测 reCAPTCHA...")

        recaptcha_passed = solve_recaptcha_audio(page)

        if not recaptcha_passed:
            log.error("❌ reCAPTCHA 未通过")
            screenshot(page, "recaptcha_failed")
            tg(f"❌ <b>续期失败</b>\n⏰ {now_cn():%H:%M:%S} (北京)\n⚠️ reCAPTCHA 未通过")
            return False

        # 7. reCAPTCHA 通过后，点击 Renew（弹窗里的紫色按钮）
        log.info("🖱️ 点击弹窗里的 Renew 按钮...")
        time.sleep(2)
        try:
            # 弹窗里的 Renew 按钮（紫色）
            renew_modal_btn = page.ele('css:button.purple', timeout=5)
            if not renew_modal_btn:
                # 兜底：找所有按钮里文字是 Renew 的
                btns = page.eles('css:button')
                for btn in btns:
                    if 'renew' in (btn.text or '').lower():
                        renew_modal_btn = btn
                        break
            if renew_modal_btn:
                renew_modal_btn.click()
                log.info("✅ 点击了弹窗 Renew 按钮")
                time.sleep(5)
            else:
                log.warning("⚠️ 未找到弹窗 Renew 按钮，可能已自动续期")
        except Exception as e:
            log.warning(f"点击弹窗 Renew 按钮失败: {e}")

        # 8. 检测续期是否成功
        screenshot(page, "after_renew")
        time.sleep(3)

        # 刷新页面看新时间
        page.get(RENEW_URL)
        time.sleep(5)

        new_sec = get_expires_seconds(page)
        screenshot(page, "final")

        if new_sec > old_sec:
            delta = new_sec - old_sec
            log.info(f"✅ 续期成功！{old_sec}s → {new_sec}s (Δ=+{delta}s)")
            tg(f"✅ <b>续期成功</b>\n"
               f"⏰ {now_cn():%H:%M:%S} (北京)\n"
               f"⏳ 剩余: {old_sec//3600}h {(old_sec%3600)//60}m → {new_sec//3600}h {(new_sec%3600)//60}m\n"
               f"➕ 增加: {delta//3600}h {(delta%3600)//60}m")
            return True
        elif new_sec > 0:
            log.warning(f"⚠️ 续期可能失败，时间未增加（{old_sec}s → {new_sec}s）")
            tg(f"⚠️ <b>续期可能失败</b>\n"
               f"⏰ {now_cn():%H:%M:%S} (北京)\n"
               f"⏳ 当前剩余: {new_sec//3600}h {(new_sec%3600)//60}m\n"
               f"⚠️ 时间未增加")
            return False
        else:
            log.warning("⚠️ 无法识别新时间，但 reCAPTCHA 已通过")
            tg(f"✅ <b>reCAPTCHA 已通过</b>\n"
               f"⏰ {now_cn():%H:%M:%S} (北京)\n"
               f"⚠️ 无法确认时间是否增加，请手动检查")
            return True

    except Exception as e:
        log.exception(f"❌ 未捕获异常: {e}")
        tg(f"❌ <b>续期异常</b>\n"
           f"⏰ {now_cn():%Y-%m-%d %H:%M:%S} (北京时间)\n"
           f"⚠️ 错误: {str(e)[:200]}")
        return False
    finally:
        try:
            page.quit()
        except:
            pass


if __name__ == "__main__":
    success = run()
    if success:
        log.info("🏁 续期完成")
        sys.exit(0)
    else:
        log.error("🏁 续期失败")
        sys.exit(1)
