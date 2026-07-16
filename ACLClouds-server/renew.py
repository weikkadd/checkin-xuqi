#!/usr/bin/env python3
"""
AclClouds 卡卡项目自动续期脚本
- Playwright + Google OAuth 登录
- 自动定位"卡卡"项目
- 到期前 2 天点击续期按钮
- TG 通知结果

网站: https://dash.aclclouds.com/projects
项目: 卡卡（node.js 通用 / 机器人 / 免费）
"""

import os
import time
import random
import asyncio
import sys

# ================== 环境变量 ==================
GOOGLE_EMAIL    = os.environ.get("KAKA_GOOGLE_EMAIL", "").strip()
GOOGLE_PASSWORD = os.environ.get("KAKA_GOOGLE_PASSWORD", "").strip()
TG_CHAT_ID      = os.environ.get("TG_CHAT_ID", "").strip()
TG_TOKEN        = os.environ.get("TG_BOT_TOKEN", "").strip()

# ================== 站点常量 ==================
BASE_URL      = "https://dash.aclclouds.com"
LOGIN_URL     = f"{BASE_URL}/login"
PROJECTS_URL  = f"{BASE_URL}/projects"


def random_delay(min_ms=500, max_ms=3000):
    """随机延迟，模拟人类行为"""
    t = random.uniform(min_ms / 1000, max_ms / 1000)
    time.sleep(t)


def tg_notify(title, message):
    """发送 Telegram 通知"""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    import urllib.request
    import urllib.parse
    text = f"<b>{title}</b>\n{message}"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode()
    try:
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        print(f"[TG] 通知发送失败: {e}")


async def run():
    """主流程"""
    from playwright.async_api import async_playwright

    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = await context.new_page()

        try:
            # === Step 1: Google 登录 ===
            print("[卡卡] Step 1/3: Google 登录")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            random_delay(1000, 2000)

            # 点击 Google 登录按钮
            google_selectors = [
                'button:has-text("Google")',
                'a:has-text("Google")',
                'button:has-text("谷歌")',
                '[data-provider="google"]',
            ]
            clicked = False
            for sel in google_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                raise Exception("未找到 Google 登录入口")

            random_delay(3000, 5000)

            # 填写邮箱
            await page.wait_for_selector('input[type="email"]', timeout=15000)
            await page.fill('input[type="email"]', GOOGLE_EMAIL)
            random_delay(500, 1500)

            next_btn = await page.query_selector(
                'button:has-text("Next"), button:has-text("下一步"), #identifierNext'
            )
            if next_btn:
                await next_btn.click()
            random_delay(3000, 5000)

            # 填写密码
            try:
                await page.wait_for_selector('input[type="password"]', timeout=15000)
                await page.fill('input[type="password"]', GOOGLE_PASSWORD)
                random_delay(500, 1500)
                pwd_next = await page.query_selector(
                    'button:has-text("Next"), button:has-text("下一步"), #passwordNext'
                )
                if pwd_next:
                    await pwd_next.click()
            except Exception:
                print("[卡卡] 未出现密码页（可能已信任设备）")

            random_delay(5000, 10000)

            # 处理 OAuth 授权页
            current_url = page.url
            if "accounts.google.com" in current_url:
                allow_btn = await page.query_selector(
                    'button:has-text("Allow"), button:has-text("允许"), '
                    'button:has-text("Continue")'
                )
                if allow_btn:
                    await allow_btn.click()
                    random_delay(3000, 5000)

            current_url = page.url
            if "login" in current_url and "dash.aclclouds.com" in current_url:
                raise Exception(f"Google 登录失败，当前 URL: {current_url}")

            print("[卡卡] ✅ Google 登录成功")

            # === Step 2: 找到卡卡项目 ===
            print("[卡卡] Step 2/3: 定位卡卡项目")
            await page.goto(PROJECTS_URL, wait_until="networkidle", timeout=30000)
            random_delay(2000, 4000)

            # 查找"卡卡"
            found = await page.evaluate("""
                () => {
                    const els = document.querySelectorAll(
                        'a, button, div[role="button"]'
                    );
                    for (const el of els) {
                        if (el.textContent.includes('卡卡')) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if not found:
                raise Exception("未在项目列表中找到'卡卡'")

            random_delay(2000, 4000)

            # === Step 3: 点击续期 ===
            print("[卡卡] Step 3/3: 点击续期按钮")

            renew_selectors = [
                'button:has-text("续期")',
                'a:has-text("续期")',
                'button:has-text("Renew")',
                'button:has-text("免费续期")',
                'button:has-text("延长")',
            ]
            renew_clicked = False
            for sel in renew_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    visible = await btn.is_visible()
                    disabled = await btn.is_disabled()
                    if visible and not disabled:
                        text = await btn.inner_text()
                        print(f"[卡卡] 找到续期按钮: {text.strip()}")
                        await btn.click()
                        renew_clicked = True
                        break
                    if visible and disabled:
                        raise Exception("续期按钮已禁用（未到续期窗口）")

            if not renew_clicked:
                raise Exception("续期按钮未出现（未到续期时间窗口）")

            random_delay(2000, 4000)

            # 检查续期结果
            success = await page.evaluate("""
                () => /续期成功|Renewal successful|已续期|操作成功/i.test(
                    document.body.innerText
                )
            """)

            duration = round(time.time() - start_time, 1)

            if success:
                print(f"[卡卡] ✅ 续期成功！耗时 {duration}s")
                tg_notify(
                    "🎮 AclClouds 续期通知",
                    f"🖥️项目: 卡卡\n📊续期结果: ✅续期成功！\n⏰耗时: {duration}s"
                )
            else:
                print(f"[卡卡] ✅ 续期执行完成（耗时 {duration}s）")
                tg_notify(
                    "🎮 AclClouds 续期通知",
                    f"🖥️项目: 卡卡\n📊续期结果: ✅续期已执行\n⏰耗时: {duration}s"
                )

        except Exception as e:
            duration = round(time.time() - start_time, 1)
            error_msg = str(e)
            print(f"[卡卡] ❌ 续期失败: {error_msg}")
            try:
                await page.screenshot(path="/tmp/aclclouds-kaka-error.png")
            except Exception:
                pass
            tg_notify(
                "🎮 AclClouds 续期失败",
                f"🖥️项目: 卡卡\n📊续期结果: ❌失败\n"
                f"⚠️错误: {error_msg}\n⏰耗时: {duration}s"
            )
            sys.exit(1)

        finally:
            await browser.close()


if __name__ == "__main__":
    if not GOOGLE_EMAIL or not GOOGLE_PASSWORD:
        print("❌ 请设置环境变量 KAKA_GOOGLE_EMAIL 和 KAKA_GOOGLE_PASSWORD")
        sys.exit(1)
    asyncio.run(run())
