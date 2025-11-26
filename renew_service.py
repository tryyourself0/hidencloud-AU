import os
import time
import sys
import random
from playwright.sync_api import sync_playwright

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/71879/manage"
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

# Firefox 专用的反指纹 JS
STEALTH_JS = """
    // 移除 webdriver 标记
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    
    // 伪造语言
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    
    // 伪造插件 (Firefox 默认插件列表不同，这里简单置空或伪造)
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
"""

def handle_cloudflare(page):
    """
    通用验证处理逻辑
    """
    iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
    
    # 稍微等待一下让 iframe 加载
    time.sleep(2)
    
    if page.locator(iframe_selector).count() == 0:
        return True

    log("⚠️ (Firefox) 检测到 Cloudflare 验证...")
    start_time = time.time()
    
    while time.time() - start_time < 60:
        if page.locator(iframe_selector).count() == 0:
            log("✅ 验证通过！")
            return True

        try:
            frame = page.frame_locator(iframe_selector)
            checkbox = frame.locator('input[type="checkbox"]')
            
            if checkbox.is_visible():
                log("尝试点击验证复选框...")
                time.sleep(random.uniform(0.5, 1.0))
                checkbox.click()
                
                # 点击后等待 5 秒看结果
                time.sleep(5)
            else:
                # 验证框还在，但没复选框，可能在转圈或加载
                time.sleep(1)

        except Exception:
            pass
            
    log("❌ 验证超时。")
    return False

def login(page):
    log("开始登录流程...")
    
    # Cookie 登录
    if HIDENCLOUD_COOKIE:
        log("尝试 Cookie 登录...")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME, 'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com', 'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
            }])
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 等待页面稳定
            page.wait_for_load_state("networkidle")
            handle_cloudflare(page)
            
            if "auth/login" not in page.url:
                log("✅ Cookie 登录成功！")
                return True
            log("Cookie 失效。")
        except:
            pass

    # 密码登录
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        return False

    log("尝试账号密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        
        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        
        # Firefox 下有时候输入太快会被检测，稍微等一下
        time.sleep(0.5)
        handle_cloudflare(page)
        
        page.click('button[type="submit"]')
        
        # 等待跳转
        time.sleep(5)
        handle_cloudflare(page)
        
        if "dashboard" in page.url or "service" in page.url:
             log("✅ 账号密码登录成功！")
             return True
             
        # 再给一点时间
        page.wait_for_url(f"{BASE_URL}/*", timeout=30000)
        return True
    except Exception as e:
        log(f"❌ 登录失败: {e}")
        page.screenshot(path="login_fail.png")
        return False

def renew_service(page):
    try:
        log("进入续费流程...")
        if page.url != SERVICE_URL:
            page.goto(SERVICE_URL, wait_until="domcontentloaded", timeout=60000)
        
        # 确保加载完成
        page.wait_for_load_state("networkidle")
        handle_cloudflare(page)

        log("点击 'Renew'...")
        page.locator('button:has-text("Renew")').click()
        time.sleep(3) # Firefox 渲染可能稍慢，多给点时间

        log("查找 'Create Invoice'...")
        create_btn = page.locator('button:has-text("Create Invoice")')
        create_btn.wait_for(state="visible", timeout=15000)
        
        # 滚动到元素可见 (Firefox 有时需要)
        create_btn.scroll_into_view_if_needed()
        time.sleep(1)
        
        # 再次检查盾
        handle_cloudflare(page)
        
        log("点击 'Create Invoice'...")
        create_btn.click()
        
        # --- 监控 ---
        log("等待跳转发票页...")
        start_wait = time.time()
        new_invoice_url = None
        
        while time.time() - start_wait < 60:
            if "/payment/invoice/" in page.url:
                new_invoice_url = page.url
                log(f"🎉 页面已跳转: {new_invoice_url}")
                break
            
            # 如果出现盾，尝试解决
            if page.locator('iframe[src*="challenges.cloudflare.com"]').count() > 0:
                log("⚠️ 遇到拦截，尝试处理...")
                handle_cloudflare(page)
                
            time.sleep(1)
        
        if not new_invoice_url:
            log("❌ 未能进入发票页面，可能被拦截。")
            page.screenshot(path="renew_stuck_firefox.png")
            return False

        if page.url != new_invoice_url:
            page.goto(new_invoice_url)
            
        handle_cloudflare(page)

        log("查找 'Pay' 按钮...")
        pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_btn.wait_for(state="visible", timeout=30000)
        pay_btn.click()
        
        log("✅ 'Pay' 按钮已点击。")
        time.sleep(5)
        return True

    except Exception as e:
        log(f"❌ 续费异常: {e}")
        page.screenshot(path="renew_error.png")
        return False

def main():
    if not HIDENCLOUD_COOKIE and not (HIDENCLOUD_EMAIL and HIDENCLOUD_PASSWORD):
        sys.exit(1)

    with sync_playwright() as p:
        try:
            log("启动 Firefox 浏览器...")
            # --- 关键修改：使用 Firefox ---
            browser = p.firefox.launch(
                headless=False, # 配合 XVFB
            )
            
            # Firefox 的 context 设置
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0' # 指定一个常见的 Firefox UA
            )
            page = context.new_page()
            
            page.add_init_script(STEALTH_JS)

            if not login(page):
                sys.exit(1)

            if not renew_service(page):
                sys.exit(1)

            log("🎉 任务全部完成！")
        except Exception as e:
            log(f"💥 严重错误: {e}")
            sys.exit(1)
        finally:
            if 'browser' in locals() and browser:
                browser.close()

if __name__ == "__main__":
    main()
