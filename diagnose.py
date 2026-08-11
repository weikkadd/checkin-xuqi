#!/usr/bin/env python3
"""
诊断脚本 - 检查所有服务的配置和依赖
"""

import os
import sys

def check_seleniumbase():
    """检查 seleniumbase 是否正确安装"""
    try:
        from seleniumbase import Driver
        print("✓ seleniumbase 已安装")
        return True
    except ImportError as e:
        print(f"✗ seleniumbase 导入失败: {e}")
        return False

def check_requests():
    """检查 requests 库"""
    try:
        import requests
        print("✓ requests 已安装")
        return True
    except ImportError as e:
        print(f"✗ requests 导入失败: {e}")
        return False

def check_env_vars():
    """检查环境变量"""
    print("\n=== 环境变量检查 ===")
    
    # ACLClouds
    acl_cookies = os.getenv("ACL_COOKIES", "")
    if acl_cookies:
        print(f"✓ ACL_COOKIES: 已设置 ({len(acl_cookies)} 字符)")
    else:
        print("✗ ACL_COOKIES: 未设置")
    
    # Gaming4Free
    g4f_url = os.getenv("GAME4FREE_RENEW_URL", "")
    g4f_cookie = os.getenv("GAME4FREE_COOKIE", "")
    if g4f_url:
        print(f"✓ GAME4FREE_RENEW_URL: 已设置")
    else:
        print("✗ GAME4FREE_RENEW_URL: 未设置")
    if g4f_cookie:
        print(f"✓ GAME4FREE_COOKIE: 已设置 ({len(g4f_cookie)} 字符)")
    else:
        print("✗ GAME4FREE_COOKIE: 未设置")
    
    # Host2Play
    h2p_url = os.getenv("H2P_RENEW_URL", "")
    h2p_cookie = os.getenv("H2P_COOKIE", "")
    if h2p_url:
        print(f"✓ H2P_RENEW_URL: 已设置")
    else:
        print("✗ H2P_RENEW_URL: 未设置")
    if h2p_cookie:
        print(f"✓ H2P_COOKIE: 已设置 ({len(h2p_cookie)} 字符)")
    else:
        print("✗ H2P_COOKIE: 未设置")
    
    # Telegram
    tg_token = os.getenv("TG_BOT_TOKEN", "")
    tg_chat = os.getenv("TG_CHAT_ID", "")
    if tg_token:
        print(f"✓ TG_BOT_TOKEN: 已设置")
    else:
        print("✗ TG_BOT_TOKEN: 未设置")
    if tg_chat:
        print(f"✓ TG_CHAT_ID: 已设置")
    else:
        print("✗ TG_CHAT_ID: 未设置")

def check_files():
    """检查关键文件是否存在"""
    print("\n=== 文件检查 ===")
    
    files = [
        "ACLClouds-server/renew.py",
        "ACLClouds-server/renew_browser.py",
        "gaming4free-renew/renew.py",
        "host2play-renew/main.py",
        ".github/workflows/aclclouds-kaka.yml",
        ".github/workflows/aclclouds-browser.yml",
        ".github/workflows/gaming4free.yml",
        ".github/workflows/host2play.yml",
    ]
    
    for f in files:
        if os.path.exists(f):
            print(f"✓ {f}")
        else:
            print(f"✗ {f} 不存在")

def main():
    print("=" * 60)
    print("Checkin-Xuqi 诊断工具")
    print("=" * 60)
    
    print("\n=== 依赖检查 ===")
    sb_ok = check_seleniumbase()
    req_ok = check_requests()
    
    check_env_vars()
    check_files()
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    
    if not sb_ok:
        print("\n建议: 运行 'pip install seleniumbase>=4.34.0'")
    if not req_ok:
        print("\n建议: 运行 'pip install requests'")

if __name__ == "__main__":
    main()
