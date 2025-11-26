import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

# 目标网页 URL
BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/71879/manage"

# Cookie 名称
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def handle_cloudflare(page):
    """
    通用 Cloudflare 人机验证处理函数。
    检测页面是否存在 Cloudflare 挑战，如果存在则尝试点击。
    """
    try:
        # 检查是否存在 Cloudflare Turnstile iframe
        # 使用 count() 快速检查，避免长时间等待
        if page.locator('iframe[src*="challenges.cloudflare.com"]').count() > 0:
            log("⚠️ 检测到 Cloudflare 安全验证页面，尝试自动处理...")
            
            turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            checkbox = turnstile_frame.locator('input[type="checkbox"]')
            
            # 确保复选框可见再点击
            if checkbox.is_visible(timeout=5000):
                log("正在点击人机验证复选框...")
                checkbox.click()
                
                # 等待验证通过的标志 (input value 出现 或 iframe 消失)
                try:
                    page.wait_for_function(
                        "() => !document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]') || (document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value)",
                        timeout=15000
                    )
                    log("✅ Cloudflare 验证点击完成，等待跳转...")
                    time.sleep(2) # 给予额外缓冲时间让页面刷新
                    return True
                except:
                    log("⚠️ 点击了验证框，但页面状态未在预期时间内改变，继续后续流程...")
            else:
                log("发现了验证框架但找不到复选框，可能正在加载...")
    except Exception as e:
        # 仅仅是检测，不要让报错中断主流程
        pass
    return False

def login(page):
    """
    处理登录逻辑。
    """
    log("开始登录流程...")

    # --- 方案一：Cookie 登录 ---
    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME, 'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com', 'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
            }])
            log("Cookie 已设置。正在访问服务管理页面...")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)

            # 检查是否遇到验证
            handle_cloudflare(page)

            if "auth/login" in page.url:
                log("Cookie 登录失败或会话已过期，将回退到账号密码登录。")
                page.context.clear_cookies()
            else:
                log("✅ Cookie 登录成功！")
                return True
        except Exception as e:
            log(f"使用 Cookie 访问时发生错误: {e}")
            log("将回退到账号密码登录。")
            page.context.clear_cookies()
    else:
        log("未提供 HIDENCLOUD_COOKIE，直接使用账号密码登录。")

    # --- 方案二：账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 错误: Cookie 无效/未提供，且未提供邮箱和密码。无法继续登录。")
        return False

    log("正在尝试使用邮箱和密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        
        # 填写前先处理可能出现的验证
        handle_cloudflare(page)
        
        log("登录页面已加载。")
        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("邮箱和密码已填写。")

        # 调用通用验证处理
        handle_cloudflare(page)

        page.click('button[type="submit"]:has-text("Sign in to your account")')
        log("已点击登录按钮，等待页面跳转...")

        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)

        if "auth/login" in page.url:
            log("❌ 账号密码登录失败，请检查凭据是否正确。")
            page.screenshot(path="login_failure.png")
            return False

        log("✅ 账号密码登录成功！")
        return True
    except PlaywrightTimeoutError as e:
        log(f"❌ 登录过程中超时: {e}")
        page.screenshot(path="login_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 登录过程中发生未知错误: {e}")
        page.screenshot(path="login_general_error.png")
        return False

def renew_service(page):
    """执行续费流程"""
    try:
        log("开始执行续费任务...")
        if page.url != SERVICE_URL:
            log(f"当前不在目标页面，正在导航至: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        
        # 页面加载后立即检查验证
        handle_cloudflare(page)
        
        log("服务管理页面已加载。")

        log("步骤 1: 正在查找并点击 'Renew' 按钮...")
        renew_button = page.locator('button:has-text("Renew")')
        renew_button.wait_for(state="visible", timeout=30000)
        renew_button.click()
        log("✅ 'Renew' 按钮已点击。")
        
        log("等待 0.9 秒...")
        time.sleep(0.9)

        log("步骤 2: 准备监听网络请求并点击 'Create Invoice' 按钮...")
        
        new_invoice_url = None

        def handle_response(response):
            nonlocal new_invoice_url
            if "/payment/invoice/" in response.url:
                new_invoice_url = response.url
                log(f"🎉 成功从网络请求中捕获到发票URL: {new_invoice_url}")

        page.on("response", handle_response)
        
        create_invoice_button = page.locator('button:has-text("Create Invoice")')
        create_invoice_button.wait_for(state="visible", timeout=30000)
        create_invoice_button.click()
        log("✅ 'Create Invoice' 按钮已点击，正在等待响应或跳转...")

        # --- 智能等待循环 (包含 Cloudflare 处理) ---
        # 增加超时时间以应对验证耗时
        timeout = 25 
        for i in range(timeout):
            # 1. 如果监听器捕获到了 URL
            if new_invoice_url:
                break
            
            # 2. 如果页面已经直接跳转到了发票页面 (Cloudflare 通过后可能发生)
            if "/payment/invoice/" in page.url:
                new_invoice_url = page.url
                log(f"🎉 页面已跳转至发票页面: {new_invoice_url}")
                break

            # 3. 检查并处理 Cloudflare 验证
            # 如果这里处理了验证，下一次循环可能会检测到 URL 变化
            handle_cloudflare(page)
            
            page.wait_for_timeout(1000)
        
        page.remove_listener("response", handle_response)
        
        if new_invoice_url:
            log(f"前往发票页面: {new_invoice_url}")
            if page.url != new_invoice_url:
                 page.goto(new_invoice_url, wait_until="networkidle", timeout=60000)
        else:
            log("❌ 错误：超时未获取到发票 URL。截图保存中...")
            page.screenshot(path="renew_failed_cloudflare.png")
            raise Exception("Failed to capture new invoice URL (possibly blocked by Cloudflare).")

        log("步骤 3: 正在查找可见的 'Pay' 按钮...")
        pay_button = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_button.wait_for(state="visible", timeout=15000)
        
        log("✅ 'Pay' 按钮已找到，正在点击...")
        pay_button.click()
        log("✅ 'Pay' 按钮已点击。")
        
        time.sleep(5)
        log("续费流程似乎已成功触发。")
        page.screenshot(path="renew_success.png")
        return True
    except PlaywrightTimeoutError as e:
        log(f"❌ 续费任务超时: {e}")
        page.screenshot(path="renew_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 续费任务执行错误: {e}")
        page.screenshot(path="renew_general_error.png")
        return False

def main():
    """主函数"""
    if not HIDENCLOUD_COOKIE and not (HIDENCLOUD_EMAIL and HIDENCLOUD_PASSWORD):
        log("❌ 致命错误: 必须提供环境变量。")
        sys.exit(1)

    with sync_playwright() as p:
        browser = None
        try:
            log("启动浏览器...")
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            if not login(page):
                log("登录失败，程序终止。")
                sys.exit(1)

            if not renew_service(page):
                log("续费失败，程序终止。")
                sys.exit(1)

            log("🎉🎉🎉 自动化续费任务成功完成！ 🎉🎉🎉")
        except Exception as e:
            log(f"💥 主程序发生严重错误: {e}")
            if 'page' in locals() and page:
                page.screenshot(path="main_critical_error.png")
            sys.exit(1)
        finally:
            log("关闭浏览器。")
            if browser:
                browser.close()

if __name__ == "__main__":
    main()
