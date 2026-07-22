# -*- coding: utf-8 -*-
import os, sys, time, json, traceback
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from util import *
from cfg import *
from tg import send_tg

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_chromedriver():
    for p in ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver", "/opt/chrome/chromedriver"]:
        if os.path.exists(p):
            return p
    return "/usr/bin/chromedriver"

def init_browser(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1920,1080")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    opts.add_argument(f"--user-agent={ua}")
    svc = Service(executable_path=get_chromedriver())
    dr = webdriver.Chrome(service=svc, options=opts)
    dr.set_page_load_timeout(60)
    try:
        dr.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except:
        pass
    return dr

def inject_cookie(dr, cookie_str):
    pairs = [p.strip() for p in cookie_str.split(";")]
    for p in pairs:
        if "=" in p:
            k, v = p.split("=", 1)
            try:
                dr.add_cookie({"name": k.strip(), "value": v.strip(), "domain": ".gaming4free.net", "path": "/"})
            except:
                pass

def get_time(dr):
    for attempt in range(3):
        try:
            el = WebDriverWait(dr, 10).until(
                EC.presence_of_element_located((By.XPATH, "//span[contains(text(),'remaining')]"))
            )
            txt = el.text.strip()
            txt_clean = txt.replace("remaining", "").strip()
            parts = txt_clean.split(":")
            if len(parts) >= 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                total = h * 3600 + m * 60 + s
                log(f"✅ remaining 行: {txt_clean} (行: {txt})")
                return txt_clean, total
            elif len(parts) == 2:
                m, s = int(parts[0]), int(parts[1])
                total = m * 60 + s
                log(f"✅ remaining 行: {txt_clean} (行: {txt})")
                return txt_clean, total
        except Exception as e:
            if attempt == 2:
                log(f"⚠️ 获取剩余时间失败: {e}")
                try:
                    dr.refresh()
                    time.sleep(3)
                except:
                    pass
            time.sleep(2)
    return None, 0

def scr(dr, name):
    try:
        os.makedirs("debug_output", exist_ok=True)
        dr.save_screenshot(f"debug_output/{name}.png")
    except:
        pass

def do_rounds(dr, sn, su, max_rounds=10):
    cr = 0
    while cr < max_rounds:
        cr += 1
        log(f"\n🔄 --- 第 {cr}/{max_rounds} 轮续期 ---")

        bl, bs = get_time(dr)
        if not bl:
            log("⚠️ 无法获取剩余时间，刷新重试")
            dr.refresh()
            time.sleep(5)
            continue
        log(f"⏱️ 当前剩余时长: {bl} ({bs}秒)")

        pre_time = bs
        pre_ts = time.time()

        # ===== 第一轮：Livewire 诊断 =====
        if cr == 1:
            try:
                diag = dr.execute_script(_LW_DIAGNOSE_JS)
                log(f"🔧 Livewire 诊断:\n{diag}")
            except Exception as e:
                log(f"⚠️ 诊断失败: {e}")

        # ===== 三层点击策略 =====
        click_result = None

        # Layer 1: Livewire v3 - $wire.extend()
        try:
            r1 = dr.execute_script(_LW_EXTEND_V3_JS)
            log(f"🖱️ Layer1 (Livewire v3): {r1}")
            if r1 and 'fail' not in r1 and 'error' not in r1:
                click_result = r1
        except Exception as e:
            log(f"⚠️ Layer1 异常: {e}")

        # Layer 2: Livewire v2 - emit('extend')
        if not click_result:
            try:
                r2 = dr.execute_script(_LW_V2_JS)
                log(f"🖱️ Layer2 (Livewire v2): {r2}")
                if r2 and 'fail' not in r2 and 'error' not in r2:
                    click_result = r2
            except Exception as e:
                log(f"⚠️ Layer2 异常: {e}")

        # Layer 3: wire:click 鼠标事件派发
        if not click_result:
            try:
                r3 = dr.execute_script(_LW_CLICK_JS)
                log(f"🖱️ Layer3 (wire:click dispatch): {r3}")
                if r3 and 'not_found' not in r3 and 'error' not in r3:
                    click_result = r3
            except Exception as e:
                log(f"⚠️ Layer3 异常: {e}")

        # Layer 4: 回退 - 普通点击
        if not click_result:
            log("⚠️ Livewire 方式均未成功，回退到普通点击")
            btn_result = dr.execute_script("""
                var result=null;
                var allEls=Array.from(document.querySelectorAll('button,a,[role="button"],[wire\\:click]'));
                for(var i=0;i<allEls.length;i++){
                    var el=allEls[i];
                    var t=(el.innerText||el.textContent||'').trim();
                    if(t.indexOf('90')!==-1&&t.indexOf('min')!==-1){
                        var rect=el.getBoundingClientRect();
                        if(rect.width>0&&rect.height>0&&!el.disabled){
                            result={text:t.substring(0,30),disabled:el.disabled,visible:true,
                                    wireClick:el.getAttribute('wire\\:click')||el.getAttribute('wire\\:click\\.prevent')||''};
                            break;
                        }
                    }
                }
                return result?JSON.stringify(result):'not_found';
            """)
            if btn_result == 'not_found':
                log("❌ 未找到 +90min 按钮!")
                scr(dr, f"fail_round{cr}_no_btn")
                time.sleep(10)
                dr.refresh()
                time.sleep(5)
                continue

            bi = json.loads(btn_result)
            log(f"🔍 按钮: {bi.get('text')}, disabled={bi.get('disabled')}, visible={bi.get('visible')}, wire:click={bi.get('wireClick')}")

            if bi.get('disabled') or not bi.get('visible'):
                log("⚠️ 按钮不可用")
                scr(dr, f"fail_round{cr}_btn_disabled")
                time.sleep(10)
                dr.refresh()
                time.sleep(5)
                continue

            click_js = """
                var allEls=Array.from(document.querySelectorAll('button,a,[role="button"]'));
                for(var i=0;i<allEls.length;i++){
                    var el=allEls[i];
                    var t=(el.innerText||el.textContent||'').trim();
                    if(t.indexOf('90')!==-1&&t.indexOf('min')!==-1){
                        var rect=el.getBoundingClientRect();
                        if(rect.width>0&&rect.height>0&&!el.disabled){
                            el.scrollIntoView({block:'center'});
                            el.click();
                            return 'clicked:'+el.tagName+':'+t.substring(0,30);
                        }
                    }
                }
                return 'not_found';
            """
            click_result = dr.execute_script(click_js)
            log(f"🖱️ Layer4 (普通点击): {click_result}")

        # ===== 检测确认弹窗 =====
        time.sleep(1.5)
        confirm_selectors = [
            (By.XPATH, "//button[contains(text(), 'Confirm')]"),
            (By.XPATH, "//button[contains(text(), 'confirm')]"),
            (By.XPATH, "//button[contains(text(), 'Yes')]"),
            (By.XPATH, "//button[contains(text(), 'OK')]"),
            (By.XPATH, "//button[contains(text(), 'Renew')]"),
            (By.XPATH, "//button[contains(text(), 'Extend')]"),
            (By.XPATH, "//button[contains(text(), 'Add')]"),
            (By.CSS_SELECTOR, ".swal2-confirm"),
            (By.CSS_SELECTOR, ".modal-footer button"),
            (By.CSS_SELECTOR, "button[class*='confirm']"),
            (By.CSS_SELECTOR, "button[class*='primary']"),
        ]
        for by, sel in confirm_selectors:
            try:
                confirm_btn = WebDriverWait(dr, 2).until(
                    EC.element_to_be_clickable((by, sel))
                )
                confirm_btn.click()
                log(f"✅ 处理确认弹窗: {sel}")
                break
            except:
                continue

        # ===== 检测 alert =====
        try:
            alert = dr.switch_to.alert
            log(f"⚠️ 检测到 Alert: {alert.text}")
            alert.accept()
        except:
            pass

        # ===== 等待续期生效 (30s) =====
        log("⏳ 等待续期生效 (最长 30s)...")
        wait_end = time.time() + 30
        renewed = False
        while time.time() < wait_end:
            try:
                ct, cs = get_time(dr)
                diff = int(cs) - int(pre_time)
                if diff > 300:
                    log(f"✅ 检测到时间增加 → {ct}, +{diff}秒")
                    renewed = True
                    break
            except:
                pass
            time.sleep(3)

        # ===== 最终判断 =====
        al, as_ = get_time(dr)
        df = int(as_) - int(pre_time) if as_ else 0
        elapsed = time.time() - pre_ts
        log(f"⏱️ 续期后: {al} ({as_}秒), 增加: {df}秒, 耗时: {elapsed:.0f}s")

        if df > 300:
            log(f"🎉 续期成功! +{df}s ({bl} → {al})")
            try: send_tg(f"🎉 [{sn}] Pro续期成功 (+{df//60}分钟)", sn, al)
            except: pass
            log("💤 等待5分钟再续下一轮...")
            time.sleep(300)
            dr.refresh()
            time.sleep(5)
            continue
        else:
            scr(dr, f"fail_round{cr}")
            try:
                err_text = dr.execute_script("return document.body?document.body.innerText.substring(0,500):'';")
                if err_text:
                    log(f"⚠️ 页面内容片段: {err_text[:300]}")
            except:
                pass
            log(f"❌ 续期失败，继续下一轮")
            time.sleep(10)
            dr.refresh()
            time.sleep(5)
            continue

    return False

def main():
    log("========== 开始处理服务器账号 (Pro v30-fix) ==========")

    cookie = os.environ.get("G4F_COOKIE", "")
    server_url = os.environ.get("G4F_SERVER_URL", "")
    server_name = os.environ.get("G4F_SERVER_NAME", "gaming4free")

    if not cookie or not server_url:
        log("❌ 缺少环境变量 G4F_COOKIE 或 G4F_SERVER_URL")
        sys.exit(1)

    for attempt in range(3):
        log(f"🚀 启动浏览器 (第 {attempt + 1}/3 次尝试)...")
        dr = None
        try:
            dr = init_browser(headless=True)
            log(f"🌐 访问页面: {server_url}")
            dr.get("https://gaming4free.net/login")
            time.sleep(3)

            log("🍪 注入 Cookie...")
            inject_cookie(dr, cookie)

            log("⏳ 等待页面加载...")
            dr.get(server_url)
            time.sleep(5)

            try:
                WebDriverWait(dr, 30).until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(text(),'remaining')]"))
                )
            except:
                log("⚠️ 等待按钮超时，尝试继续...")

            title = dr.title
            log(f"📄 标题: {title}")

            if "Login" in title:
                log("❌ Cookie 失效，仍在登录页")
                dr.quit()
                sys.exit(1)

            result = do_rounds(dr, server_name, server_url, max_rounds=10)
            dr.quit()
            return

        except Exception as e:
            log(f"❌ 异常: {e}")
            log(traceback.format_exc())
            if dr:
                try: scr(dr, f"error_attempt{attempt}")
                except: pass
                try: dr.quit()
                except: pass
            time.sleep(10)

    log("❌ 3次尝试均失败")

if __name__ == "__main__":
    main()
