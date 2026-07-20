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
    try:
        pt=dr.execute_script("return document.body?document.body.innerText.substring(0,2000):'';")
        if not pt: return("(未知)",0)
        tm=re.findall(r'(\d{1,2}:\d{2}:\d{2})',pt)
        if tm:
            log(f"🔍 所有匹配时间: {tm}")
            for line in pt.split('\n'):
                ll=line.lower()
                if any(kw in ll for kw in ['expire','remain','end','next','due']):
                    lt=re.findall(r'(\d{1,2}:\d{2}:\d{2})',line)
                    if lt:
                        log(f"✅ 选中关键字附近: {lt[0]} (行: {line.strip()[:100]})")
                        return(lt[0],pars_s(lt[0]))
            log(f"⚠️ 未找到关键字，使用第一个: {tm[0]}")
            return(tm[0],pars_s(tm[0]))
        return("(未找到)",0)
    except: return("(错误)",0)
