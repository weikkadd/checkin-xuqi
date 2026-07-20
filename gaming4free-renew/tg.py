import urllib.request,urllib.parse
from datetime import datetime
from util import log
from cfg import *
def send_tg(msg,sn="",tt=""):
    if not TG_BOT or not TG_CHAT: return
    try:
        em="****"
        if ACCOUNTS:
            e=ACCOUNTS[0][2]
            if "@" in e:
                l,d=e.rsplit("@",1)
                em=l[:2]+"****"+l[-2:]+"@"+d if len(l)>3 else l+"****@"+d
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        t=f"🎮Gaming4Free Pro\n🖥️服务器: {sn}\n⏰时间: {now}\n📊状态: {msg}\n⏱剩余: {tt}\n⚙️模式: Renew-Pro v15"
        u=f"https://api.telegram.org/bot{TG_BOT}/sendMessage"
        data=f"chat_id={TG_CHAT}&text={urllib.parse.quote(t)}&parse_mode=HTML".encode()
        urllib.request.urlopen(urllib.request.Request(u,data=data,headers={"Content-Type":"application/x-www-form-urlencoded"}),timeout=10)
        log(f"📨 TG 通知成功")
    except Exception as e:
        log(f"⚠️ TG 失败: {e}")
