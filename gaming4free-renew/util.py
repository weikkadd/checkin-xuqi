import os,re
from datetime import datetime
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
def scr(sb,name="s"):
    try:
        d=os.path.join(os.path.dirname(__file__),"debug_output")
        os.makedirs(d,exist_ok=True)
        sb.save_screenshot(os.path.join(d,f"{name}.png"))
    except: pass
def pars_s(ms):
    if not ms: return 0
    m=re.match(r'(\d+):(\d+):(\d+)',ms)
    if m: return int(m.group(1))*3600+int(m.group(2))*60+int(m.group(3))
    m=re.match(r'(\d+)\s*m',ms,re.I)
    if m: return int(m.group(1))*60
    m=re.match(r'(\d+)\s*h',ms,re.I)
    if m: return int(m.group(1))*3600
    return 0
def get_time(dr):
    """从页面提取服务器到期时间（秒）和显示字符串"""
    try:
        # 方法1: 尝试从 Livewire 组件数据中获取
        pt=dr.execute_script("""
            var result='';
            try{
                var c=Livewire.all;
                for(var i=0;i<c.length;i++){
                    try{
                        var data=c[i].data;
                        if(data && data.expires){result=data.expires;break;}
                        if(data && data.remaining){result=data.remaining;break;}
                        if(data && data.server_time){result=data.server_time;break;}
                        // 打印所有 data 键名用于诊断
                        if(!result && i===0){
                            var keys=Object.keys(data);
                            window._livewire_keys=keys.join(',');
                        }
                    }catch(e){}
                }
            }catch(e){}
            return result||'';""")
        if pt:
            secs=pars_s(pt)
            if secs>0:
                h,m,s=secs//3600,(secs%3600)//60,secs%60
                log(f"✅ 从 Livewire 数据获取: {pt} ({secs}s)")
                return(f"{h:02d}:{m:02d}:{s:02d}",secs)
        
        # 诊断：打印 Livewire 键名
        lk=dr.execute_script("return window._livewire_keys||'';")
        if lk: log(f"🔑 Livewire data keys: {lk}")
        
        # 方法2: 从页面文本中提取
        pt=dr.execute_script("return document.body?document.body.innerText.substring(0,3000):'';")
        if not pt: return("(未知",0)
        
        # 找包含 "remaining" 的行（这是服务器到期时间）
        for line in pt.split('\n'):
            ll=line.lower()
            if 'remaining' in ll:
                lt=re.findall(r'(\d{1,2}:\d{2}:\d{2})',line)
                if lt:
                    log(f"✅ remaining 行: {lt[0]} (行: {line.strip()[:100]})")
                    return(lt[0],pars_s(lt[0]))
        
        # 回退: 找第一个 >= 1小时的时间（过滤短倒计时如 00:03:00）
        tm=re.findall(r'(\d{1,2}:\d{2}:\d{2})',pt)
        valid=[t for t in tm if pars_s(t)>=3600]
        if valid:
            best=max(valid,key=pars_s)
            log(f"🔍 所有匹配时间: {tm}, 选中最大有效: {best} ({pars_s(best)}s)")
            # 诊断：打印包含该时间的上下文
            for line in pt.split('\n'):
                if best in line:
                    log(f"📍 时间上下文: [{line.strip()}]")
                    break
            return(best,pars_s(best))
        
        log(f"⚠️ 未找到有效时间, 所有匹配: {tm}")
        return("(未找到)",0)
    except Exception as e:
        log(f"❌ get_time 错误: {e}")
        return("(错误)",0)
