import os
import time
import sys
import random
import math
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

# --- 强力反指纹脚本 ---
# 这段 JS 会在页面加载前注入，伪装浏览器特征
STRONG_STEALTH_JS = """
    // 1. 移除自动化标记
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    
    // 2. 伪造 Chrome 对象
    window.chrome = { runtime: {} };
    
    // 3. 伪造插件列表
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ]
    });
    
    // 4. 伪造语言
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    
    // 5. 欺骗权限查询 (Cloudflare 常用检测手段)
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
"""

def human_mouse_move(page, start_x, start_y, end_x, end_y, steps=25):
    """
    模拟人类鼠标移动轨迹（贝塞尔曲线+随机抖动）
    """
    for i in range(steps + 1):
        t = i / steps
        # 简单的线性插值加上正弦波抖动
        x = start_x + (end_x - start_x) * t + random.uniform(-2, 2) * math.sin(t * math.pi)
        y = start_y + (end_y - start_y) * t + random.uniform(-2, 2) * math.sin(t * math.pi)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.005, 0.015))

def handle_cloudflare(page):
    """
    终极版 Cloudflare 处理逻辑
    """
    iframe_selector = 'iframe[src*="challenges.cloudflare.com"]'
    
    # 快速检查，如果没有验证框直接返回
    if page.locator(iframe_selector).count() == 0:
        return True

    log("⚠️ 遇到 Cloudflare 验证，启动对抗模式...")
    start_wait = time.time()
    
    # 循环检测直到验证通过或超时 (60秒)
    while time.time() - start_wait < 60:
        try:
            # 1. 检查是否已通过 (iframe 消失)
            if page.locator(iframe_selector).count() == 0:
                log("✅ Cloudflare 验证已通过！")
                return True

            frame = page.frame_locator(iframe_selector)
            checkbox = frame.locator('input[type="checkbox"]')
            
            # 2. 如果复选框可见，执行拟人点击
            if checkbox.is_visible():
                box = checkbox.bounding_box()
                if box:
                    log("定位到验证框，执行拟人轨迹移动...")
                    # 获取当前鼠标位置 (Playwright 没直接提供，假设从左上角开始)
                    # 移动到目标区域
                    target_x = box['x'] + box['width'] / 2 + random.uniform(-5, 5)
                    target_y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
                    
                    # 移动鼠标
                    page.mouse.move(target_x, target_y, steps=20)
                    time.sleep(random.uniform(0.2, 0.5))
                    
                    log("点击验证...")
                    page.mouse.down()
                    time.sleep(random.uniform(0.05, 0.15)) # 短暂按压
                    page.mouse.up()
                    
                    log("点击完成，等待跳转或刷新...")
                    # 点击后给足时间等待
                    time.sleep(8) 
                else:
                    # 获取不到坐标时的备选方案
                    checkbox.click()
            else:
                # 验证框存在但复选框不可见 (可能在加载或已经在转圈)
                # 检查是否是"Verify you are human"文本，有时候是点击文字
                pass

        except Exception as e:
            # 忽略过程中的报错，继续重试
            pass
            
        time.sleep(1)

    log("❌ Cloudflare 验证长时间未消除，可能已卡死。")
    return False

def login(page):
    log("开始登录流程...")
    
    # --- Cookie 登录 ---
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
            
            # 页面加载后立即检查盾
            handle_cloudflare(page)
            
            if "auth/login" not in page.url:
                log("✅ Cookie 登录成功！")
                return True
            log("Cookie 失效。")
            page.context.clear_cookies()
        except Exception:
            pass

    # --- 账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        return False

    log("尝试账号密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        
        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        time.sleep(1)
        
        handle_cloudflare(page)
        
        # 查找登录按钮
        login_btn = page.locator('button[type="submit"]')
        if login_btn.is_visible():
            login_btn.click()
        
        # 登录提交后通常会跳盾
        log("登录提交，等待验证...")
        time.sleep(3)
        handle_cloudflare(page)
        
        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)
        log("✅ 账号密码登录成功！")
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
        
        handle_cloudflare(page)

        # 点击 Renew
        log("查找并点击 'Renew'...")
        page.locator('button:has-text("Renew")').click()
        time.sleep(2)

        # 点击 Create Invoice (这里是最容易出盾的地方)
        log("准备点击 'Create Invoice'...")
        create_btn = page.locator('button:has-text("Create Invoice")')
        create_btn.wait_for(state="visible", timeout=10000)
        
        # 预先检查一次
        handle_cloudflare(page)
        
        # 点击
        create_btn.click()
        log("已点击 'Create Invoice'，开始监控...")

        # --- 监控阶段 ---
        new_invoice_url = None
        
        # 循环 60 次，每次约 1-2 秒，总共等待约 1-2 分钟
        for i in range(60):
            # 1. 成功跳转检测
            if "/payment/invoice/" in page.url:
                new_invoice_url = page.url
                log(f"🎉 页面跳转成功: {new_invoice_url}")
                break
            
            # 2. Cloudflare 检测与处理
            # 即使刚才没跳转，也有可能是盾出来了挡住了跳转
            handle_cloudflare(page)
            
            # 3. 检查是否还在原页面但有 Pay 按钮 (极少见)
            if page.locator('a:has-text("Pay")').count() > 0:
                log("检测到页面上已存在 Pay 按钮。")
                break

            time.sleep(1)
            
        # 如果循环结束还没 URL，截图
        if not new_invoice_url and "/payment/invoice/" not in page.url:
             # 再给最后一次机会检查当前 URL
            if "/payment/invoice/" in page.url:
                 new_invoice_url = page.url
            else:
                log("❌ 超时：未能进入发票页面。")
                page.screenshot(path="renew_stuck.png")
                return False

        # 确保我们在发票页
        if new_invoice_url and page.url != new_invoice_url:
            page.goto(new_invoice_url)

        # 再次检查盾 (发票页也可能有)
        handle_cloudflare(page)

        log("查找 'Pay' 按钮...")
        pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_btn.wait_for(state="visible", timeout=30000)
        
        # 拟人点击 Pay
        box = pay_btn.bounding_box()
        if box:
            page.mouse.move(box['x'] + 10, box['y'] + 10, steps=10)
            page.mouse.click(box['x'] + 10, box['y'] + 10)
        else:
            pay_btn.click()
            
        log("✅ 'Pay' 按钮已点击，续费流程结束。")
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
            log("启动浏览器 (加强版)...")
            # 启动参数优化
            browser = p.chromium.launch(
                headless=False, # 配合 XVFB
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized', # 最大化窗口
                    '--disable-infobars',
                    '--window-size=1920,1080' # 强制窗口大小
                ]
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = context.new_page()
            
            # 注入反指纹 JS
            page.add_init_script(STRONG_STEALTH_JS)

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
