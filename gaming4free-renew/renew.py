#!/usr/bin/env python3
"""Gaming4Free Renew Pro v16 - 循环续期到47小时"""
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
    log("========== 开始处理服务器账号 (Pro v16) ==========")
    svrs=[]
    if RENEW_URL and COOKIE:
        nm="我的服务器"
        if "/server/" in RENEW_URL:
            sl=RENEW_URL.split("/server/")[1].split("/")[0]
            nm=f"我的服务器-{sl[:8]}"
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
                        # 等待页面加载，避开 Turnstile
                        log("⏳ 等待页面加载...")
                        for _ in range(30):
                            try:
                                if dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]'):
                                    log("⚠️ 检测到 Turnstile，等待通过...")
                                    time.sleep(5)
                                    continue
                                title=dr.title
                                if title and "Login" not in title and "login" not in title:
                                    log(f"✅ 页面加载完成: {title}")
                                    break
                            except: pass
                            time.sleep(2)
                    do_rounds(dr,sb,sn,sc)
                    # 检查是否达到阈值，决定是否继续
                    if not ok:
                        # 重新获取时间判断
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

        # 检查按钮冷却
        ci=chk_cd(dr)
        if ci and ci.get('cooldown'):
            rem=ci.get('remaining',0)
            log(f"⏳ 检测到按钮冷却，剩余: {ci.get('text','')} (剩 {rem}秒)")
            log(f"⏳ 等待冷却...")
            for _ in range(rem):
                time.sleep(1)
                if (_ % 10)==0:
                    try: dr.refresh(); time.sleep(2)
                    except: pass
            dr.refresh(); time.sleep(5)
            bl,bs=get_time(dr)
            log(f"⏱️ 冷却后: {bl} ({bs}秒)")

        # 记录点击前时间
        pre_ts=time.time()
        pre_time=bs
        renewed=False

        try:
            # 方法1: 尝试 Livewire extend
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
                log(f"✅ Livewire extend 成功 (组件 {lr.split(':')[1]})")
                renewed=True
            else:
                # 方法2: 直接点击页面上的 +90min 按钮
                log("⚠️ Livewire 失败，回退点击按钮...")
                btn_found=dr.execute_script("""
                    var buttons=document.querySelectorAll('button,[role=button]');
                    for(var i=0;i<buttons.length;i++){
                        var t=(buttons[i].innerText||buttons[i].textContent||'').trim();
                        if(t.indexOf('90')!==-1 && t.indexOf('min')!==-1){
                            buttons[i].scrollIntoView({block:'center'});
                            return i;
                        }
                    }
                    return -1;""")
                
                if btn_found >= 0:
                    btn_el=dr.execute_script(f"""
                        var buttons=document.querySelectorAll('button,[role=button]');
                        var b=buttons[{btn_found}];
                        b.scrollIntoView({{block:'center'}});
                        // 触发多种事件以确保完整点击
                        b.dispatchEvent(new MouseEvent('mousedown',{{bubbles:true,cancelable:true}}));
                        b.dispatchEvent(new MouseEvent('mouseup',{{bubbles:true,cancelable:true}}));
                        b.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));
                        return'b_click_fired';""")
                    log(f"🖱️ 按钮点击事件已触发: {btn_el}")
                    renewed=True
                else:
                    log("❌ 未找到 +90min 按钮!")
                    scr(sb,"no_btn")
                    return False

                # 等待广告/Turnstile 弹窗出现并关闭
                if renewed:
                    log("⏳ 等待广告弹窗处理...")
                    ad_end=time.time()+90
                    while time.time()<ad_end:
                        # 尝试关闭各种弹窗
                        try:
                            dr.execute_script("""
                                var closers=document.querySelectorAll('[aria-label="Close"],[aria-label=Close],.modal-close,.close-btn,.close,.dismiss,.overlay-close,.cf-turnstile-close');
                                for(var i=0;i<closers.length;i++){
                                    try{closers[i].click();}catch(e){}
                                }""")
                        except: pass
                        
                        # 检查 +90min 按钮是否重新可见
                        btn_visible=dr.execute_script("""
                            var buttons=document.querySelectorAll('button,[role=button]');
                            for(var i=0;i<buttons.length;i++){
                                var t=(buttons[i].innerText||buttons[i].textContent||'').trim();
                                if(t.indexOf('90')!==-1 && t.indexOf('min')!==-1){
                                    var r=buttons[i].getBoundingClientRect();
                                    return r.width>0 && r.height>0;
                                }
                            }
                            return false;""")
                        if btn_visible:
                            log("✅ 弹窗已关闭，按钮可见")
                            break
                        time.sleep(3)
                    else:
                        log("⚠️ 等待弹窗超时，继续...")
                        scr(sb,"popup_timeout")

        except Exception as e:
            log(f"❌ 点击异常: {e}")
            scr(sb,"click_err")

        # 等待 Cloudflare Turnstile 完全消失
        try:
            turnstile_end=time.time()+60
            while time.time()<turnstile_end:
                tf=dr.find_elements('css selector','iframe[src*="challenges.cloudflare.com"]')
                if not tf:
                    log("✅ Turnstile 验证通过")
                    break
                time.sleep(2)
            else:
                log("⚠️ Turnstile 等待超时")
        except: pass

        # 等待 Livewire/AJAX 响应
        log("⏳ 等待页面响应...")
        time.sleep(8)

        # 检查结果
        al,as_=get_time(dr)
        df=int(as_)-int(pre_time)
        elapsed=time.time()-pre_ts
        log(f"⏱️ 续期后: {al} ({as_}秒), 增加: {df}秒, 耗时: {elapsed:.0f}s")

        if df > 300:  # 至少增加了5分钟才算成功
            log(f"🎉 续期成功! +{df}s ({bl} → {al})")
            try: send_tg(f"🎉 Pro续期成功 (+{df//60}分钟)",sn,al)
            except: pass
            log(f"💤 等待5分钟再续下一轮...")
            time.sleep(300)
            dr.refresh(); time.sleep(5)
            continue
        else:
            # 失败：截图调试
            err_text=dr.execute_script("return document.body?document.body.innerText.substring(0,500):'';")
            if err_text: log(f"⚠️ 页面内容片段: {err_text[:200]}")
            scr(sb,f"fail_round{cr}")
            log(f"❌ 续期失败，继续下一轮")
            time.sleep(10)
    
    return False

if __name__=="__main__":
    main()
