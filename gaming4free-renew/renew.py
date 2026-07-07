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
COOLDOWN_SEC   = 285           # 冷却 4 分 45 秒（页面显示 expires 04:45）
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


def save_html(sb, name: str):
    """保存页面 HTML 源码，用于调试找不到按钮的问题"""
    p = SHOT_DIR / f"{datetime.now():%H%M%S}_{name}.html"
    try:
        html = sb.get_page_source()
        p.write_text(html, encoding="utf-8")
        log.info(f"HTML: {p}")
    except Exception as e:
        log.warning(f"保存 HTML 失败: {e}")
    return p


def save_body_text(sb, name: str):
    """保存页面 body 文本，用于调试"""
    p = SHOT_DIR / f"{datetime.now():%H%M%S}_{name}.txt"
    try:
        txt = sb.get_text("body")
        p.write_text(txt, encoding="utf-8")
        log.info(f"Body 文本: {p}")
        # 同时打印前 500 字到日志
        preview = txt[:500].replace("\n", " | ")
        log.info(f"Body 预览: {preview}")
    except Exception as e:
        log.warning(f"保存 body 文本失败: {e}")
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
    """从按钮文字提取冷却剩余秒数（-1 表示无冷却）

    gaming4free 按钮冷却时文字变成 'xx cd' 格式：
    - '4m cd' = 4 分钟冷却
    - '30s cd' = 30 秒冷却
    - '2m 30s cd' = 2 分 30 秒冷却

    注意：页面上的 'expires 02:48 PM' 是服务器到期时间（绝对时钟），
    NOT 按钮冷却时间，不能用来判断冷却剩余。
    """
    try:
        # 从按钮文字直接读取冷却时间
        try:
            txt = sb.execute_script("""
            (function(){
                const btn = document.querySelector('button.rt-btn-free, .rt-btn-free, button[wire\\\\:click="extendFree"]');
                if (btn) {
                    return (btn.textContent || '').trim();
                }
                return '';
            })()
            """)
            if txt:
                log.info(f"按钮文字: {txt}")
                # 匹配 '4m cd' / '30s cd' / '2m 30s cd' / '1h 5m cd' 等
                import re
                total = 0
                # 匹配 Xh
                m = re.search(r"(\d+)\s*h", txt.lower())
                if m:
                    total += int(m.group(1)) * 3600
                # 匹配 Xm
                m = re.search(r"(\d+)\s*m", txt.lower())
                if m:
                    total += int(m.group(1)) * 60
                # 匹配 Xs
                m = re.search(r"(\d+)\s*s", txt.lower())
                if m:
                    total += int(m.group(1))
                # 必须包含 'cd' 才算冷却中
                if total > 0 and "cd" in txt.lower():
                    log.info(f"冷却剩余 [按钮文字] = {txt} → {total}s")
                    return total
                # 如果按钮文字是 '+90 min'，说明没冷却
                if "min" in txt.lower() or "+90" in txt.lower():
                    log.info(f"按钮可用（无冷却）: {txt}")
                    return 0
        except Exception:
            pass

        # 兜底：扫描页面所有元素找 'xx cd' 文字
        try:
            txt = sb.execute_script("""
            (function(){
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.children.length > 0) continue;
                    const t = (el.textContent || '').trim();
                    if (/\\d+\\s*[hms]\\s*cd$/i.test(t)) {
                        return t;
                    }
                }
                return '';
            })()
            """)
            if txt:
                import re
                total = 0
                m = re.search(r"(\d+)\s*h", txt.lower())
                if m: total += int(m.group(1)) * 3600
                m = re.search(r"(\d+)\s*m", txt.lower())
                if m: total += int(m.group(1)) * 60
                m = re.search(r"(\d+)\s*s", txt.lower())
                if m: total += int(m.group(1))
                if total > 0:
                    log.info(f"冷却剩余 [扫描] = {txt} → {total}s")
                    return total
        except Exception:
            pass

        return -1
    except Exception as e:
        log.warning(f"提取冷却时间失败: {e}")
        return -1


def click_renew_button(sb) -> bool:
    """找到并点击续期按钮，返回是否点到了

    gaming4free 实际按钮 HTML:
    <button class="rt-btn-free"
            x-text="adCooldown > 0 ? cdLabel + ' cd' : '+90 min'"
            wire:click="extendFree">
      +90 min
    </button>

    按钮文字是 Alpine.js 动态生成，:contains 选择器可能找不到
    必须用 class 选择器：button.rt-btn-free
    或用 wire:click 属性：button[wire:click="extendFree"]
    """
    candidates = [
        # 优先按 class 找（最稳定，gaming4free 专用）
        'button.rt-btn-free',
        '.rt-btn-free',
        'button[wire\\:click="extendFree"]',
        # gaming4free 付费续期按钮（备用）
        'button.rt-btn-paid',
        '.rt-btn-paid',
        # 兼容文字匹配
        'button:contains("+90 min")',
        'button:contains("+ 90 min")',
        'button:contains("90 min")',
        'button:contains("+90")',
        'button:contains("Renew")',
        'button:contains("Extend")',
        'button:contains("续期")',
        'button:contains("增加")',
        'a:contains("+90 min")',
        'a:contains("Renew")',
        # 选择器兜底
        "#renew", ".renew", ".btn-renew",
        'button[class*="renew"]', 'a[class*="renew"]',
        'button[class*="extend"]', 'a[class*="extend"]',
    ]

    # 备用方案：通过 JS 找包含 "90 min" 或 "+90" 文字的所有可点击元素（已废弃，改用下面的终极兜底）
    # 保留变量供参考
    _js_find_button_doc = "已改用 execute_script 内联 IIFE，详见下方兜底逻辑"

    # gaming4free 用 Livewire 框架，wire:click="extendFree" 不响应合成 .click()
    # 必须用统一的 JS 兜底逻辑（包含 Livewire API 调用），所以这里直接跳到兜底
    # 不再用 seleniumbase 的 sb.click() 因为它无法触发 wire:click

    # 先用 JS 检查按钮是否存在 + 状态
    # 注意：用 sb.driver.execute_script 比 sb.execute_script 更稳定
    # 避免 UC mode + CDP 复杂转义导致返回 None
    try:
        # 简化 JS：不用 wire:click 选择器（避免转义问题），只用 class
        btn_info = sb.driver.execute_script(
            "var btn = document.querySelector('button.rt-btn-free, .rt-btn-free');"
            "if (!btn) {"
            "  var all = document.querySelectorAll('button, a, [role=button]');"
            "  var texts = [];"
            "  for (var i = 0; i < all.length && i < 15; i++) {"
            "    var t = (all[i].textContent || '').trim();"
            "    if (t.length > 0 && t.length < 30) texts.push(t);"
            "  }"
            "  return 'not-found|buttons=' + texts.join('||');"
            "}"
            "var t = (btn.textContent || '').trim().toLowerCase();"
            "var r = btn.getBoundingClientRect();"
            "var v = r.width > 0 && r.height > 0;"
            "return 'found|text=' + t + '|visible=' + v + '|disabled=' + btn.disabled;"
        )
        if btn_info is None:
            btn_info = "error|execute_script returned None"
        log.info(f"按钮状态: {btn_info}")

        if btn_info and btn_info.startswith("found|"):
            # 解析按钮文字
            parts = btn_info.split("|")
            text_part = ""
            for p in parts:
                if p.startswith("text="):
                    text_part = p[5:]
            # 检查冷却状态
            if text_part and "cd" in text_part and "min" not in text_part:
                log.info(f"⏳ 按钮处于冷却中（文字: {text_part}），跳过点击")
                return False
            if text_part and "wait" in text_part:
                log.info(f"⏳ 按钮显示等待中（文字: {text_part}），跳过点击")
                return False
        elif btn_info and btn_info.startswith("not-found|"):
            # 按钮不存在，可能是服务器在 STOPPING 状态或页面没渲染好
            log.warning(f"❌ rt-btn-free 按钮不存在。{btn_info}")
            return False
        else:
            log.warning(f"❌ 按钮状态异常: {btn_info}")
            return False
    except Exception as e:
        log.warning(f"检查按钮状态失败: {e}")
        return False

    # 终极兜底：用 JS 直接调用 Livewire API（绕过 wire:click 的 isTrusted 检查）
    # gaming4free 按钮使用 Livewire wire:click="extendFree"
    # 合成的 .click() 无法触发 wire:click，必须用 Livewire.find(id).call('extendFree')
    # 注意：用 sb.driver.execute_script（selenium 原生）比 sb.execute_script 稳定
    try:
        clicked = sb.driver.execute_script(
            "var btn = document.querySelector('button.rt-btn-free, .rt-btn-free');"
            "if (!btn) return '';"
            "var t = (btn.textContent || '').trim().toLowerCase();"
            "if ((/cd$/i.test(t) && !/min/i.test(t)) || /wait/i.test(t)) return 'cooldown: ' + t;"
            "if (btn.disabled) return 'disabled: ' + t;"
            # 方法1: Livewire API
            "if (window.Livewire) {"
            "  var comp = btn.closest('[wire\\\\:id]');"
            "  if (comp) {"
            "    var cid = comp.getAttribute('wire:id');"
            "    try {"
            "      Livewire.find(cid).call('extendFree');"
            "      return 'livewire-direct: extendFree (comp=' + cid + ', text=' + t + ')';"
            "    } catch(e) {}"
            "  }"
            "  try {"
            "    Livewire.dispatch('extendFree');"
            "    return 'livewire-dispatch: extendFree';"
            "  } catch(e) {}"
            "}"
            # 方法2: 模拟真实鼠标事件
            "btn.scrollIntoView({block:'center'});"
            "var r = btn.getBoundingClientRect();"
            "var x = r.left + r.width/2, y = r.top + r.height/2;"
            "var opts = {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0, buttons:1};"
            "btn.dispatchEvent(new MouseEvent('mousedown', opts));"
            "btn.dispatchEvent(new MouseEvent('mouseup', opts));"
            "btn.dispatchEvent(new MouseEvent('click', opts));"
            "return 'mouse-event: ' + t;"
        )
        if clicked:
            if clicked.startswith("cooldown:") or clicked.startswith("disabled:"):
                log.info(f"⏳ JS 检测按钮处于冷却/禁用状态 [{clicked}]，跳过点击")
                return False
            log.info(f"✅ JS 兜底点击续期按钮 [{clicked}]")
            return True
        else:
            log.warning("❌ JS 返回空，按钮可能不存在")
    except Exception as e:
        log.warning(f"JS 兜底点击失败: {e}")

    log.warning("❌ 未找到续期按钮")
    return False


def handle_ad_popup(sb) -> bool:
    """处理 gaming4free 的广告弹窗

    点击 '+90 min' 按钮后，右下角会自动弹出广告（显示 'AD 0:26' 倒计时）
    广告会自动播放 15-30 秒，播完后时间自动加上
    不需要点任何按钮！点了 × 反而会取消广告不给奖励

    正确逻辑：
    1. 等 3 秒让广告加载
    2. 检测广告元素（AD XX:XX 倒计时文字 + video + iframe）
    3. 等广告自然消失（最长 90s）
    4. 不要点 × 或 Skip 按钮

    返回 True 如果检测到广告并等完了，False 如果没检测到广告
    """
    log.info("📺 检测广告弹窗（最长等 90s，等广告自然播完）...")

    # 先等 3 秒让广告弹窗加载
    time.sleep(3)

    ad_detected = False
    last_video_time = -1
    last_video_time_stuck_count = 0
    no_ad_count = 0

    for i in range(90):
        try:
            # 检测广告状态
            ad_status = sb.driver.execute_script(
                # 检测广告文字（如 "AD 0:26"）
                "var adText = '';"
                "var allEls = document.querySelectorAll('*');"
                "for (var e = 0; e < allEls.length; e++) {"
                "  var t = (allEls[e].textContent || '').trim();"
                "  if (/^AD\\s+\\d{1,2}:\\d{2}/i.test(t) && allEls[e].children.length === 0) {"
                "    adText = t; break;"
                "  }"
                "}"
                # 检测广告 iframe
                "var iframes = document.querySelectorAll('iframe');"
                "var adIframes = [];"
                "for (var i2 = 0; i2 < iframes.length; i2++) {"
                "  var src = iframes[i2].src || '';"
                "  var w = iframes[i2].getBoundingClientRect().width;"
                "  var h = iframes[i2].getBoundingClientRect().height;"
                "  if (w > 200 && h > 100 && (src.indexOf('imasdk') >= 0 || src.indexOf('ad') >= 0 || src.indexOf('vungle') >= 0 || src.indexOf('unity') >= 0 || src.indexOf('reward') >= 0 || src.indexOf('video') >= 0 || src === '')) {"
                "    adIframes.push(src.substring(0, 60) + ' (' + w + 'x' + h + ')');"
                "  }"
                "}"
                # 检测 video 元素
                "var videos = document.querySelectorAll('video');"
                "var videoInfo = [];"
                "for (var v = 0; v < videos.length; v++) {"
                "  var vw = videos[v].getBoundingClientRect().width;"
                "  var vh = videos[v].getBoundingClientRect().height;"
                "  if (vw > 100 && vh > 100) videoInfo.push('paused=' + videos[v].paused + ' time=' + Math.round(videos[v].currentTime) + ' ended=' + videos[v].ended);"
                "}"
                "return JSON.stringify({adText: adText, ad: adIframes, video: videoInfo});"
            )

            has_ad = False
            ad_text = ""
            try:
                import json
                data = json.loads(ad_status) if ad_status else {}
                ad_text = data.get("adText", "")
                ad_iframes = data.get("ad", [])
                videos = data.get("video", [])
                if ad_text or ad_iframes or videos:
                    has_ad = True
            except Exception:
                pass

            if has_ad:
                ad_detected = True
                no_ad_count = 0
                # 提取广告倒计时
                if ad_text:
                    if i % 5 == 0 or i < 3:
                        log.info(f"📺 广告播放中 ({i}s): {ad_text}")
                else:
                    if i % 5 == 0 or i < 3:
                        log.info(f"📺 广告播放中 ({i}s): {ad_status[:150]}")

                # 检测视频是否结束
                video_ended = False
                for v_info in videos:
                    if "ended=true" in v_info:
                        video_ended = True
                if video_ended:
                    log.info(f"✅ 广告视频已结束 ({i}s)")
                    time.sleep(2)
                    return True

                # 检测视频卡住
                if videos:
                    import re
                    for v_info in videos:
                        m = re.search(r"time=(\d+)", v_info)
                        if m:
                            cur_time = int(m.group(1))
                            if cur_time == last_video_time:
                                last_video_time_stuck_count += 1
                                if last_video_time_stuck_count >= 15:
                                    log.info(f"⚠️ 视频卡住 15s，认为广告结束")
                                    time.sleep(2)
                                    return True
                            else:
                                last_video_time = cur_time
                                last_video_time_stuck_count = 0
                            break

                time.sleep(1)

            elif ad_detected:
                # 之前有广告，现在没了
                no_ad_count += 1
                if no_ad_count >= 3:
                    log.info(f"✅ 广告已消失 ({i}s)，认为播完了")
                    return True
                time.sleep(1)
            else:
                # 还没检测到广告
                if i > 0 and i % 10 == 0:
                    log.info(f"⏳ 等广告出现 ({i}s)...")
                time.sleep(1)

        except Exception as e:
            if i == 0:
                log.warning(f"广告检测异常: {e}")
            time.sleep(1)

    if ad_detected:
        log.info("📺 广告处理超时（90s），继续后续流程")
        return True
    else:
        log.info("📺 未检测到广告弹窗，可能按钮没生效或已直接给时间")
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
    """如果提供了 cookie 字符串，注入到当前域名，然后刷新页面

    seleniumbase UC mode 下 sb.set_cookie() 不可用（'BaseCase' object has no attribute 'set_cookie'），
    需要改用 sb.driver.add_cookie() 形式，且必须先在目标域下。
    """
    if not COOKIE_STR:
        log.info("未配置 GF_COOKIE，跳过 cookie 注入（可能无法登录）")
        return False

    log.info(f"准备注入 cookie（{COOKIE_STR.count(';')+1} 项）...")

    # 先确保当前在 gaming4free 域下（add_cookie 必须在目标域调用）
    from urllib.parse import urlparse
    try:
        current_url = sb.get_current_url()
        target_host = urlparse(SITE_URL).hostname
        current_host = urlparse(current_url).hostname
        if current_host != target_host:
            log.info(f"当前域 {current_host} 与目标域 {target_host} 不一致，先访问目标域...")
            sb.open(SITE_URL)
            sb.sleep(2)
    except Exception as e:
        log.warning(f"检查当前 URL 失败: {e}")

    injected = 0
    failed = 0
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
            # 用 driver.add_cookie 注入（dict 格式）- UC mode 兼容
            sb.driver.add_cookie({"name": k, "value": v})
            injected += 1
        except Exception as e:
            failed += 1
            # 只打印前 3 个失败的，避免日志爆炸
            if failed <= 3:
                log.warning(f"  cookie [{k}] 注入失败: {e}")

    log.info(f"✅ 成功注入 {injected} 个 cookie，失败 {failed} 个")

    # 注入后刷新页面让 cookie 生效
    log.info("🔄 刷新页面让 cookie 生效...")
    sb.refresh()
    sb.sleep(3)
    return True


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
        # gaming4free 控制台特征关键词（看到任一就认为页面已加载）
        ready_keywords_strong = ["rt-btn-free", "rt-btn-paid", "active session", "cap 48h",
                                   "remaining", "expires",
                                   # 控制台页面特征（服务器详情页）
                                   "uptime", "restart", "kill", "delete",
                                   "minecraft java", "node ·", "console"]
        page_ready = False
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
            # 强信号：看到 gaming4free 控制台特征，说明页面真的渲染好了
            if any(kw in body_lower for kw in ready_keywords_strong):
                log.info(f"✅ 页面已加载完成 ({i}s) - 强信号匹配")
                page_ready = True
                break
            time.sleep(1)

        # 即使匹配到弱信号也要至少等 8 秒
        if not page_ready:
            log.info("⏳ 未检测到强信号，强制等待 8s 让 JS 渲染...")
            time.sleep(8)

        # 再额外等 3 秒让 JS 完全渲染
        sb.sleep(3)

        # Step 3: 注入 cookie / 登录
        cookie_injected = inject_cookies(sb)
        if LOGIN_URL:
            sb.open(LOGIN_URL)
            sb.sleep(2)
            do_login(sb)
            sb.open(SITE_URL)
            sb.sleep(2)

        # 如果注入了 cookie，需要再次等页面渲染（cookie 让我们从登录页跳到控制台）
        if cookie_injected:
            log.info("cookie 注入后等待页面重新渲染...")
            for i in range(30):
                try:
                    body_lower = sb.get_text("body").lower()
                    if any(kw in body_lower for kw in ["rt-btn-free", "active session",
                                                          "remaining", "console", "+90 min"]):
                        log.info(f"✅ cookie 生效，页面已进入控制台 ({i}s)")
                        break
                    # 还是登录页？
                    if any(kw in body_lower for kw in ["login", "sign in", "google",
                                                          "log in", "press start"]):
                        log.warning(f"⚠️ cookie 注入后仍是登录页 ({i}s)，cookie 可能已失效")
                        break
                except Exception:
                    pass
                time.sleep(1)
            sb.sleep(2)

        screenshot(sb, "dashboard")
        # 同时保存 HTML 和 body 文本，方便排查"找不到按钮"的问题
        save_html(sb, "dashboard")
        save_body_text(sb, "dashboard")

        # Step 3.5: 如果当前在服务器列表页，需要点进具体服务器才能看到 +90 min 按钮
        # gaming4free 主页 /servers 显示服务器列表，点进某个服务器才能看到续期按钮
        try:
            body_text = sb.get_text("body").lower()
            # 检测是否在服务器列表页
            if ("my servers" in body_text or "servers" in body_text) and "rt-btn-free" not in body_text:
                log.info("📋 当前在服务器列表页，尝试点进具体服务器...")

                # 方案 1: 用 JS 找到第一个服务器卡片/链接并点击
                # 用 sb.driver.execute_script 比 sb.execute_script 稳定
                try:
                    clicked = sb.driver.execute_script(
                        "var links = document.querySelectorAll('a[href*=\"/server/\"]');"
                        "for (var i = 0; i < links.length; i++) {"
                        "  var href = links[i].getAttribute('href') || '';"
                        "  var m = href.match(/\\/server\\/([a-z0-9_-]+)/i);"
                        "  if (m && m[1].length >= 3) {"
                        "    links[i].click();"
                        "    return 'link: ' + href;"
                        "  }"
                        "}"
                        # 兜底：找 OPEN / MANAGE / CONSOLE 按钮
                        "var btns = document.querySelectorAll('a, button, [role=button], .btn');"
                        "for (var j = 0; j < btns.length; j++) {"
                        "  var t = (btns[j].textContent || '').trim().toLowerCase();"
                        "  if (/^open/i.test(t) || /manage/i.test(t) || /console/i.test(t)) {"
                        "    if (btns[j].disabled) continue;"
                        "    btns[j].click();"
                        "    return 'button: ' + t;"
                        "  }"
                        "}"
                        # 兜底2: 找所有链接里看起来像服务器的
                        "var allLinks = document.querySelectorAll('a[href]');"
                        "var found = [];"
                        "for (var k = 0; k < allLinks.length; k++) {"
                        "  var h = allLinks[k].getAttribute('href') || '';"
                        "  var txt = (allLinks[k].textContent || '').trim();"
                        "  if (h && txt && txt.length < 30) found.push(h + ' | ' + txt.substring(0,30));"
                        "}"
                        "return 'links-debug:\\n' + found.join('\\n');"
                    )
                    if clicked and not clicked.startswith("links-debug:"):
                        log.info(f"✅ 点击进入服务器: {clicked}")
                        sb.sleep(3)
                        # 等服务器页面加载
                        for i in range(30):
                            try:
                                body_lower = sb.get_text("body").lower()
                                if any(kw in body_lower for kw in ["rt-btn-free", "+90 min",
                                                                      "active session", "remaining",
                                                                      "uptime", "restart", "console"]):
                                    log.info(f"✅ 服务器页面已加载 ({i}s)")
                                    break
                            except Exception:
                                pass
                            time.sleep(1)
                        sb.sleep(2)
                        screenshot(sb, "server_page")
                        save_body_text(sb, "server_page")
                    else:
                        log.warning("⚠️ 未找到服务器入口")
                        if clicked:
                            log.info(f"页面所有链接:\n{clicked}")
                except Exception as e:
                    log.warning(f"点进服务器失败: {e}")
        except Exception as e:
            log.warning(f"检测服务器列表页失败: {e}")

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
                # 按钮没点到 - 可能是冷却中（按钮文字变成 'xx cd'）或不在页面
                # 检查按钮冷却时间，自动等到冷却结束
                cooldown_left = get_cooldown_seconds(sb)
                if cooldown_left > 0:
                    wait_sec = cooldown_left + 10  # 多等 10s 保险
                    log.info(f"⏳ 续期按钮冷却中，剩余 {cooldown_left}s，等待 {wait_sec}s 后重试")
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
                            if any(kw in body_lower for kw in ["remaining", "90 min", "console",
                                                                  "uptime", "restart"]):
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

            # Step 4.3: 处理广告弹窗（gaming4free 按钮是 "watch ad · +90 min"）
            # 点击后会弹出广告，必须看完广告或点击 Skip 才会加时间
            click_time = time.time()  # 记录点击时间戳
            log.info("📺 检查广告弹窗...")
            ad_handled = handle_ad_popup(sb)

            # Step 4.4: 等待 Livewire AJAX 响应 / 时间更新
            log.info("⏳ 等待续期生效（最长 30s）...")
            for wait_i in range(30):
                time.sleep(1)
                try:
                    # 检测按钮文字是否变成冷却中（说明续期成功了）
                    loading = sb.driver.execute_script(
                        "var btn = document.querySelector('button.rt-btn-free, .rt-btn-free');"
                        "if (btn) {"
                        "  var t = (btn.textContent || '').trim().toLowerCase();"
                        "  if (/cd$/i.test(t) || /wait/i.test(t)) return 'cooldown:' + t;"
                        "}"
                        "return '';"
                    )
                    if loading and loading.startswith("cooldown:"):
                        log.info(f"✅ 按钮进入冷却状态 [{loading}]，续期成功！")
                        break
                except Exception:
                    pass

            # 再等 3 秒让时间更新
            sb.sleep(3)

            # Step 4.4: 对比时间
            # 重要：剩余时间是自然递减的，所以新读的时间会比旧时间少（除非续期生效）
            # 正确算法：新时间 > (旧时间 - 经过秒数 + 60s 缓冲) 才算续期成功
            new_sec = get_remaining_seconds(sb)
            elapsed = int(time.time() - click_time)
            if last_sec > 0 and new_sec > 0:
                # 期望最低值 = 旧时间 - 经过秒数 - 30s（容忍页面刷新延迟）
                expected_min = last_sec - elapsed - 30
                # 续期成功判定：新时间比期望最低值高 60s 以上（说明确实加了时间）
                success = new_sec > expected_min + 60
                delta = new_sec - last_sec
                log.info(f"点击 #{click_count+1}: {last_sec}s → {new_sec}s (Δ={delta}s, 经过 {elapsed}s, 期望最低 {expected_min}s)")
            elif new_sec > 0 and last_sec <= 0:
                # 之前没识别到时间，现在识别到了，算成功
                success = True
                log.info(f"点击 #{click_count+1}: 之前未识别 → {new_sec}s")
            else:
                success = False
                log.warning(f"点击 #{click_count+1}: 时间仍未识别")

            if success:
                click_count += 1
                log.info(f"✅ 续期成功 (累计 {click_count} 次)")
                screenshot(sb, f"success_{click_count}")
                last_sec = new_sec
            else:
                log.warning(f"⚠️ 续期可能失败")
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
