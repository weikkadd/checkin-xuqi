#!/usr/bin/env python3
"""Gaming4Free Renew Pro v15"""
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
                log(f"🚀 浏览器 (尝试 {bt+1})")
                with SB(uc=True,headless=False,browser='chrome',
                        agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as sb:
                    dr=sb.driver
                    dr.set_page_load_timeout(120)
                    log(f"🌐 访问: {su}")
                    dr.get(su)
                    log(f"📄 标题: {dr.title}")
                    if sc:
                        log("🍪 注入 Cookie")
                        for it in sc.split(";"):
                            it=it.strip()
                            if "=" in it:
                                n,v=it.split("=",1)
                                try: dr.add_cookie({"name":n.strip(),"value":v.strip(),"domain":".gaming4free.net","path":"/","secure":True})
                                except: pass
                        dr.refresh(); time.sleep(10)
                    do_rounds(dr,sn,sc)
            except Exception as e:
                log(f"❌ 异常: {e}")
                try: scr(sb,"err")
                except: pass
                send_tg(f"❌ 异常: {e}",sn)
                break

def do_rounds(dr,sn,sc):
    ok=False
    cr=0
    while cr<MAX_ROUNDS:
        cr+=1
        log(f"\n🔄 第 {cr}/{MAX_ROUNDS} 轮")
        bl,bs=get_time(dr)
        log(f"⏱️ 当前: {bl} ({bs}s)")
        if bs>=THRESHOLD:
            log("✅ 已达目标时长"); ok=True; break
        try:
            pt=dr.execute_script("return document.body.innerText")
            if "05:00" in pt and "cd" in pt:
                log("⏳ 5分钟冷却，等待310s")
                time.sleep(310); dr.refresh(); time.sleep(10); continue
        except: pass
        ci=chk_cd(dr)
        if ci and ci.get('cooldown'):
            rem=ci.get('remaining',0)
            log(f"⏳ 冷却 {rem}s")
            for _ in range(rem):
                time.sleep(1)
                if (_ % 10)==0:
                    try: dr.refresh(); time.sleep(2)
                    except: pass
            dr.refresh(); time.sleep(5); continue
        log("🖱️ 触发续期")
        try:
            lr=dr.execute_script("""
                try{var c=Livewire.all;for(var i=0;i<c.length;i++){try{c[i].call('extend');return'success';}catch(e){}}}catch(e){}
                try{var b=document.querySelector('button.rt-btn-free');if(b){b.click();return'clicked';}}catch(e){}
                return'fail';""")
            if lr=='success': log("✅ Livewire 成功")
            elif lr=='clicked': log("✅ 按钮点击成功")
            else: log("⚠️ 回退点击")
        except Exception as e: log(f"⚠️ 续期异常: {e}")
        time.sleep(5)
        try:
            if dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                log("🛡️ 等 Turnstile")
                for _ in range(30):
                    if not dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                        log("✅ Turnstile 通过"); break
                    time.sleep(1)
        except: pass
        log("🎬 等广告")
        sw=time.time()
        while time.time()-sw<90:
            dr.execute_script("window.dispatchEvent(new Event('mousemove'));")
            try:
                dr.execute_script("""
                    var cb=document.querySelectorAll('[aria-label=Close],.modal-close');
                    for(var i=0;i<cb.length;i++)if(cb[i].offsetParent!==null)cb[i].click();""")
            except: pass
            try:
                ac=get_time(dr)
                if ac[1]>bs+100: log(f"✅ 时间增加，提前跳出"); break
            except: pass
            time.sleep(5)
        try: dr.refresh(); time.sleep(5)
        except: time.sleep(10)
        al,as_=get_time(dr)
        df=as_-bs
        log(f"⏱️ 后: {al} ({as_}s), 增加: {df}s")
        if df>0:
            log(f"✅ 成功! +{df}s ({bl}→{al})")
            send_tg(f"✅ Pro续期成功 (+{df}s)",sn,al); break
        else:
            log(f"❌ 失败，继续下一轮"); time.sleep(10)

if __name__=="__main__":
    main()
