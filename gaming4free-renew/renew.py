#!/usr/bin/env python3
"""Gaming4Free Renew Pro v28 - 深度 Turnstile 诊断 + 自动处理"""
import os,sys,time,re,urllib.parse,urllib.request
from datetime import datetime
try:
    from seleniumbase import SB
except ImportError:
    print("seleniumbase not installed")
    sys.exit(1)
from cfg import *
from util import *
from cd import *
from tg import send_tg

def main():
    log("========== 开始处理服务器账号 (Pro v28) ==========")
    svrs=[]
    if RENEW_URL and COOKIE:
        nm="我的服务器"
        if "/server/" in RENEW_URL:
            sl=RENEW_URL.split("/server/")[1].split("/")[0]
            nm=f"服务器-{sl[:8]}"
        svrs.append((nm,RENEW_URL,COOKIE))
    for n,u,c in ACCOUNTS:
        svrs.append((n,u,c))
    if not svrs:
        log("❌ 未配置服务器信息"); sys.exit(1)
    for sn,su,sc in svrs:
        ok=False
        for bt in range(MAX_TRIES):
            if ok: break
            try:
                log(f"🚀 启动浏览器 (第 {bt+1}/{MAX_TRIES} 次尝试)...")
                # uc_cdp_events=True 让 SeleniumBase 自动处理 Turnstile
                with SB(uc=True,headless=False,browser='chrome',
                        agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        uc_cdp_events=True) as sb:
                    dr=sb.driver
                    dr.set_page_load_timeout(120)
                    log(f"🌐 访问页面: {su}")
                    dr.get(su)
                    log(f"📄 标题: {dr.title}")
                    if sc:
                        log("🍪 注入 Cookie...")
                        for it in sc.split(";"):
                            it=it.strip()
                            if "=" in it:
                                n,v=it.split("=",1)
                                try: dr.add_cookie({"name":n.strip(),"value":v.strip(),"domain":".gaming4free.net","path":"/","secure":True})
                                except: pass
                        dr.refresh(); time.sleep(5)
                        log("⏳ 等待页面加载...")
                        for _ in range(30):
                            try:
                                if dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                                    log("🛡️ 检测到 Turnstile，等待通过...")
                                    time.sleep(5)
                                    continue
                                title=dr.title
                                if title and "Login" not in title and "login" not in title:
                                    log(f"✅ 页面加载完成: {title}")
                                    break
                            except: pass
                            time.sleep(2)
                    do_rounds(dr,sb,sn,sc)
                    bl,bs=get_time(dr)
                    if bs>=THRESHOLD:
                        ok=True
            except Exception as e:
                log(f"❌ 异常: {e}")
                try: scr(sb,"err")
                except: pass
                try: send_tg(f"❌ 异常: {e}",sn)
                except: pass
                break
            time.sleep(3)
        if ok:
            try: send_tg(f"✅ 已达到目标时长 {THRESHOLD//3600}h，停止续期",sn)
            except: pass
        else:
            try: send_tg(f"⚠️ 已达最大轮数 {MAX_ROUNDS}，停止续期",sn)
            except: pass

def do_rounds(dr,sb,sn,sc):
    cr=0
    while cr<MAX_ROUNDS:
        cr+=1
        log(f"\n🔄 --- 第 {cr}/{MAX_ROUNDS} 轮续期 ---")
        bl,bs=get_time(dr)
        log(f"⏱️ 当前剩余时长: {bl} ({bs}秒)")
        if bs>=THRESHOLD:
            log(f"✅ 已超过目标时长 {THRESHOLD//3600} 小时")
            try: send_tg(f"🎉 已达到目标时长 {bl}",sn,bl)
            except: pass
            return True

        ci=chk_cd(dr)
        if ci and ci.get('cooldown'):
            rem=ci.get('remaining',0)
            log(f"⏳ 检测到按钮冷却，剩余: {ci.get('text','')} (剩 {rem}秒)")
            for _ in range(rem):
                time.sleep(1)
                if (_ % 10)==0:
                    try: dr.refresh(); time.sleep(2)
                    except: pass
            dr.refresh(); time.sleep(5)
            bl,bs=get_time(dr)
            log(f"⏱️ 冷却后: {bl} ({bs}秒)")

        pre_ts=time.time()
        pre_time=bs

        try:
            # ===== 注入 Turnstile callback 监听 =====
            log("🔍 注入 Turnstile 回调监听...")
            dr.execute_script("""
                window._turnstile_passed = false;
                window._turnstile_token = '';
                window._turnstile_error = '';
                // 监听所有可能的 callback 名称
                var turnstileCallbacks = ['turnstileCallback', 'turnstileSuccess', 'onSuccess'];
                for(var i=0;i<turnstileCallbacks.length;i++){
                    if(window[turnstileCallbacks[i]]){
                        var orig = window[turnstileCallbacks[i]];
                        window[turnstileCallbacks[i]] = function(token) {
                            window._turnstile_passed = true;
                            window._turnstile_token = token;
                            if(orig) orig(token);
                        };
                    }
                }
                // 监听 Turnstile 全局对象
                if(window.turnstile){
                    var origReset = window.turnstile.reset;
                    var origRemove = window.turnstile.remove;
                    var origReload = window.turnstile.reload;
                    var origCallback = window.turnstile.callback;
                    window.turnstile.reset = function(el) {
                        window._turnstile_error = 'reset';
                        if(origReset) origReset(el);
                    };
                    window.turnstile.remove = function(el) {
                        if(origRemove) origRemove(el);
                    };
                    window.turnstile.reload = function(el) {
                        window._turnstile_error = 'reload';
                        if(origReload) origReload(el);
                    };
                }
                return 'turnstile_monitor_injected';
            """)

            # 1. 找到 +90min 按钮
            btn_result=dr.execute_script("""
                var result=null;
                var allEls = Array.from(document.querySelectorAll('*'));
                for(var i=0;i<allEls.length;i++){
                    var el=allEls[i];
                    if(el.tagName!=='BUTTON' && el.tagName!=='A' && el.tagName!=='SPAN' && el.tagName!=='DIV') continue;
                    if(el.getAttribute('role')!=='button' && el.tagName!=='BUTTON' && el.tagName!=='A') continue;
                    var t=(el.innerText||el.textContent||'').trim();
                    if(t.indexOf('90')!==-1 && t.indexOf('min')!==-1){
                        var rect=el.getBoundingClientRect();
                        result={
                            tagName:el.tagName,
                            text:t,
                            disabled:!!el.disabled,
                            visible:rect.width>0&&rect.height>0,
                        };
                        break;
                    }
                }
                return result?JSON.stringify(result):'not_found';
            """)
            
            if btn_result == 'not_found':
                log("❌ 未找到 +90min 按钮!")
                scr(sb, f"fail_round{cr}_no_btn")
                time.sleep(10)
                continue
            
            import json
            bi=json.loads(btn_result)
            log(f"🔍 按钮: {bi.get('text')}, disabled={bi.get('disabled')}, visible={bi.get('visible')}")

            if bi.get('disabled') or not bi.get('visible'):
                log(f"⚠️ 按钮不可用")
                scr(sb, f"fail_round{cr}_btn_disabled")
                time.sleep(10)
                continue

            # 2. 点击按钮
            click_js = """
                var allEls = Array.from(document.querySelectorAll('*'));
                for(var i=0;i<allEls.length;i++){
                    var el=allEls[i];
                    if(el.tagName!=='BUTTON' && el.tagName!=='A' && el.tagName!=='SPAN' && el.tagName!=='DIV') continue;
                    if(el.getAttribute('role')!=='button' && el.tagName!=='BUTTON' && el.tagName!=='A') continue;
                    var t=(el.innerText||el.textContent||'').trim();
                    if(t.indexOf('90')!==-1 && t.indexOf('min')!==-1){
                        var rect=el.getBoundingClientRect();
                        if(rect.width>0 && rect.height>0 && !el.disabled){
                            el.scrollIntoView({block:'center'});
                            el.click();
                            return 'clicked:'+el.tagName+':'+t.substring(0,30);
                        }
                    }
                }
                return 'not_found';
            """
            click_result=dr.execute_script(click_js)
            log(f"🖱️ 点击: {click_result}")

            # 3. 深度诊断：检查页面上所有 iframe
            time.sleep(2)
            iframe_info=dr.execute_script("""
                var frames = document.querySelectorAll('iframe');
                var info = [];
                for (var i = 0; i < frames.length; i++) {
                    info.push({
                        src: frames[i].src || 'no-src',
                        id: frames[i].id || '',
                        class: frames[i].className || '',
                        name: frames[i].name || '',
                        visible: frames[i].offsetParent !== null
                    });
                }
                return JSON.stringify(info);
            """)
            log(f"🔍 页面上所有 iframe: {iframe_info[:500]}")

            # 4. 检查 Turnstile 状态
            ts_status=dr.execute_script("""
                return JSON.stringify({
                    passed: window._turnstile_passed || false,
                    token: window._turnstile_token || '',
                    error: window._turnstile_error || '',
                    has_turnstile: !!window.turnstile,
                    turnstile_version: window.turnstile ? window.turnstile.version || 'unknown' : 'none'
                });
            """)
            log(f"🔍 Turnstile 状态: {ts_status}")

            # 5. 等待 Turnstile 验证 — 延长到 180 秒
            log("⏳ 等待 Turnstile 验证和续期生效 (最长 180s)...")
            ad_end=time.time()+180
            renewed=False
            while time.time()<ad_end:
                # 检查 Turnstile 是否通过
                ts_passed=dr.execute_script("return window._turnstile_passed;")
                if ts_passed:
                    log("✅ Turnstile 验证已通过！")
                    scr(sb, f"round{cr}_turnstile_passed")
                    # 等待 Livewire 响应
                    time.sleep(5)
                    break

                # 检查时间是否增加
                try:
                    ct,cs=get_time(dr)
                    diff=cs-pre_time
                    if diff > 300:
                        log(f"✅ 检测到时间增加 ({ct} > {bl}), 增加 {diff}秒")
                        renewed=True
                        break
                except: pass

                # 每 15 秒检查一次 iframe 和 Turnstile 状态
                if int(time.time()) % 15 < 3:
                    iframe_count=dr.execute_script("return document.querySelectorAll('iframe').length;")
                    ts_iframe=dr.execute_script("""
                        var frames = document.querySelectorAll('iframe');
                        for(var i=0;i<frames.length;i++){
                            if(frames[i].src && frames[i].src.indexOf('turnstile')!==-1) return true;
                        }
                        return false;
                    """)
                    if iframe_count > 0:
                        log(f"🔍 当前 iframe 数量: {iframe_count}, Turnstile iframe: {ts_iframe}")
                    if ts_iframe:
                        log("🛡️ 检测到 Turnstile iframe！")
                        scr(sb, f"round{cr}_turnstile_iframe")

                time.sleep(3)
            
            if not renewed and not ts_passed:
                log("⚠️ 等待超时，Turnstile 未通过")
                scr(sb, f"fail_round{cr}_timeout")

        except Exception as e:
            log(f"❌ 续期异常: {e}")
            scr(sb, f"fail_round{cr}_exception")

        # 最终检查
        al,as_=get_time(dr)
        df=int(as_)-int(pre_time)
        elapsed=time.time()-pre_ts
        log(f"⏱️ 续期后: {al} ({as_}秒), 增加: {df}秒, 耗时: {elapsed:.0f}s")

        if df > 300:
            log(f"🎉 续期成功! +{df}s ({bl} → {al})")
            try: send_tg(f"🎉 Pro续期成功 (+{df//60}分钟)",sn,al)
            except: pass
            log(f"💤 等待5分钟再续下一轮...")
            time.sleep(300)
            dr.refresh(); time.sleep(5)
            continue
        else:
            err_text=dr.execute_script("return document.body?document.body.innerText.substring(0,500):'';")
            if err_text: log(f"⚠️ 页面内容片段: {err_text[:200]}")
            scr(sb, f"fail_round{cr}")
            log(f"❌ 续期失败，继续下一轮")
            time.sleep(10)

    return False

if __name__=="__main__":
    main()
