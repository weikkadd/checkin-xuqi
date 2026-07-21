#!/usr/bin/env python3
"""Gaming4Free Renew Pro v15 - 循环续期至47小时"""
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
    log("========== 开始处理服务器账号 (Pro v15) ==========")
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
                with SB(uc=True,headless=False,browser='chrome',
                        agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as sb:
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
                        # Cookie 注入后等待页面加载，处理可能的 Turnstile
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
                    do_rounds(dr,sn,sc)
            except Exception as e:
                log(f"❌ 异常: {e}")
                try: scr(sb,"err")
                except: pass
                send_tg(f"❌ 异常: {e}",sn)
                break
            time.sleep(3)

def do_rounds(dr,sn,sc):
    ok=False
    cr=0
    while cr<MAX_ROUNDS:
        cr+=1
        log(f"\n🔄 --- 第 {cr}/{MAX_ROUNDS} 轮续期 ---")
        bl,bs=get_time(dr)
        log(f"⏱️ 当前剩余时长: {bl} ({bs}秒)")
        if bs>=THRESHOLD:
            log("✅ 已达目标时长 47 小时"); ok=True; break
        # 检查冷却
        ci=chk_cd(dr)
        if ci and ci.get('cooldown'):
            rem=ci.get('remaining',0)
            log(f"⏳ 检测到按钮冷却倒计时: {ci.get('text','')} (剩余 {rem}秒)")
            log(f"⏳ 按钮冷却中，等待...")
            for _ in range(rem):
                time.sleep(1)
                if (_ % 10)==0:
                    try: dr.refresh(); time.sleep(2)
                    except: pass
            dr.refresh(); time.sleep(5)
            bl,bs=get_time(dr)
            log(f"⏱️ 冷却后: {bl} ({bs}秒)")
        log("🖱️ 尝试触发续期...")
        # 记录续期前时间
        pre_ts=time.time()
        pre_time=bs
        try:
            # 诊断：打印页面中所有按钮的文本
            btns=dr.execute_script("""
                var res=[];
                var all=document.querySelectorAll('button,[role=button],[class*="btn"],[class*="Btn"],a[class*="btn"]');
                for(var i=0;i<all.length&&i<30;i++){
                    var t=(all[i].innerText||all[i].textContent||'').trim();
                    if(t.length>0 && t.length<50) res.push(t);
                }
                return JSON.stringify(res);""")
            log(f"🔍 页面按钮列表: {btns}")
            
            # 尝试 Livewire extend
            lr=dr.execute_script("""
                try{
                    var c=Livewire.all;
                    for(var i=0;i<c.length;i++){
                        try{
                            c[i].call('extend');
                            return'success:'+i;
                        }catch(e){}
                    }
                }catch(e){}
                return'fail_livewire';""")
            if lr.startswith('success:'):
                log(f"✅ Livewire extend 成功 (组件索引 {lr.split(':')[1]})")
            else:
                # Livewire 失败，回退到点击按钮
                btn=dr.execute_script("""
                    var buttons=document.querySelectorAll('button,[role=button],[class*="btn"],[class*="Btn"]');
                    for(var i=0;i<buttons.length;i++){
                        var t=(buttons[i].innerText||buttons[i].textContent||'').trim();
                        if(t.indexOf('90')!==-1 && t.indexOf('min')!==-1){
                            buttons[i].click();
                            return'clicked_90min';
                        }
                    }
                    return'not_found';""")
                log(f"⚠️ Livewire 失败，回退点击按钮: {btn}")
        except Exception as e: log(f"⚠️ 续期异常: {e}")
        time.sleep(5)
        # 等 Turnstile
        try:
            if dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                log("🛡️ 监测到 Cloudflare 验证...")
                for _ in range(30):
                    if not dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                        log("✅ Turnstile 通过"); break
                    time.sleep(1)
        except: pass
        log("🎬 等广告播放...")
        ad_end=time.time()+60
        while time.time()<ad_end:
            dr.execute_script("window.dispatchEvent(new Event('mousemove'));")
            try:
                dr.execute_script("""
                    var cb=document.querySelectorAll('[aria-label=Close],.modal-close');
                    for(var i=0;i<cb.length;i++)if(cb[i].offsetParent!==null)cb[i].click();""")
            except: pass
            try:
                btn=dr.execute_script("return document.querySelector('button.rt-btn-free');")
                if btn and btn.offsetParent is not None:
                    log("✅ 广告已关闭，按钮可见")
                    break
            except: pass
            time.sleep(3)
        # 强制刷新页面，等待 Livewire 完全更新
        log("🔄 强制刷新页面...")
        dr.refresh(); time.sleep(8)
        al,as_=get_time(dr)
        df=int(as_)-int(bs)
        elapsed=time.time()-pre_ts
        log(f"⏱️ 续期后: {al} ({as_}秒), 增加: {df}秒, 耗时: {elapsed:.0f}s")
        if df>0:
            log(f"✅ 续期成功! +{df}s ({bl}→{al})")
            send_tg(f"✅ Pro续期成功 (+{df}s)",sn,al)
            log(f"⏳ 等5分钟冷却后继续下一轮...")
            time.sleep(300)
            dr.refresh(); time.sleep(5)
            continue
        else:
            err=dr.execute_script("return document.body?document.body.innerText.substring(0,500):'';")
            if err: log(f"⚠️ 页面内容片段: {err[:200]}")
            log(f"❌ 续期失败，继续下一轮"); time.sleep(10)
    if ok:
        log("✅ 已达到目标时长，停止续期")
    else:
        log(f"⚠️ 已达到最大轮次 {MAX_ROUNDS}")

if __name__=="__main__":
    main()
