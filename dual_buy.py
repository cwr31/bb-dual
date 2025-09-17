import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import requests
import sys
import os
import re

# 加载.env配置文件
from load_env import load_env, get_config
from logger_config import get_logger

# 初始化logger
logger = get_logger('dual_buy')
load_env()

def is_price_multiple_of_5(price_str):
    """检查价格是否是整数且是5的倍数（不能有小数部分）"""
    try:
        # 提取价格中的数字部分
        clean_price = price_str.replace(',', '').replace(' ', '').strip()
        
        # 检查是否包含小数点
        if '.' in clean_price:
            # 如果有小数点，检查小数部分是否为0
            parts = clean_price.split('.')
            if len(parts) == 2:
                integer_part = parts[0]
                decimal_part = parts[1]
                
                # 小数部分必须全为0
                if not all(d == '0' for d in decimal_part):
                    return False
                    
                # 检查整数部分
                if integer_part.isdigit():
                    price_num = int(integer_part)
                    return price_num % 5 == 0
            return False
        else:
            # 没有小数点，直接检查是否是5的倍数
            if clean_price.isdigit():
                price_num = int(clean_price)
                return price_num % 5 == 0
                
    except (ValueError, AttributeError, TypeError):
        pass
    return False


# 配置项
CONFIGURED_AMOUNT = get_config('BYBIT_INVESTMENT_AMOUNT', '20')
CURRENCY = get_config('BYBIT_CURRENCY', 'USDT')
TELEGRAM_BOT_TOKEN = get_config('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = get_config('TELEGRAM_CHAT_ID', '')
BROWSER_BACKGROUND = get_config('BROWSER_BACKGROUND', 'false').lower() == 'true'

# 读取实际投资金额（如果存在的话）
def get_actual_investment_amount():
    """获取实际投资金额，优先使用赎回时保存的金额"""
    try:
        actual_amount_file = os.path.join(os.path.dirname(__file__), ".actual_investment_amount")
        if os.path.exists(actual_amount_file):
            with open(actual_amount_file, 'r', encoding='utf-8') as f:
                amount = f.read().strip()
                if amount and amount.isdigit():
                    logger.info(f"读取到实际投资金额: {amount} USDT（来自赎回记录）")
                    return amount
    except Exception as e:
        logger.warning(f"读取实际投资金额失败: {e}")
    
    logger.info(f"使用配置的投资金额: {CONFIGURED_AMOUNT} USDT")
    return CONFIGURED_AMOUNT

INVESTMENT_AMOUNT = get_actual_investment_amount()

logger.info(f"配置信息：投资金额 = {INVESTMENT_AMOUNT} {CURRENCY}")
logger.info(f"浏览器模式：{'后台窗口' if BROWSER_BACKGROUND else '前台显示'}")

# 全局变量记录申购信息
purchase_info = {
    "timestamp": None,
    "product_list": [],
    "selected_product": {},
    "investment_amount": INVESTMENT_AMOUNT,
    "currency": CURRENCY,
    "product_type": "Buy Low",
    "status": "pending"
}

def send_telegram_message(message):
    """发送Telegram通知"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram通知发送成功")
            return True
        else:
            print(f"⚠️ Telegram通知发送失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 发送Telegram通知时出错: {e}")
        return False

def exit_with_error(error_message, exception=None):
    """错误退出函数"""
    print(f"\n❌ 脚本执行失败: {error_message}")
    if exception:
        print(f"错误详情: {exception}")
    
    
    error_msg = f"{error_message}"
    if exception:
        error_msg += f" - {str(exception)}"
    raise RuntimeError(error_msg)


async def main():
    """双币投资自动申购主流程"""
    async with async_playwright() as p:
        print("🚀 启动新的Chrome浏览器...")
        
        # 使用用户数据目录，保持浏览器数据
        user_data_dir = r"C:\Users\wenrui.cao\AppData\Local\BybitBot"  # 专用目录
        
        try:
            # 启动持久化浏览器上下文
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--disable-default-apps'
            ]
            
            # 如果是后台窗口模式，添加窗口控制参数
            if BROWSER_BACKGROUND:
                browser_args.extend([
                    '--window-position=-2000,-2000',  # 将窗口移到屏幕外
                    '--window-size=1280,720',         # 设置合理的窗口大小
                    '--disable-extensions',           # 禁用扩展以减少干扰
                    '--disable-plugins',              # 禁用插件
                    '--disable-default-apps'          # 禁用默认应用
                ])
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,  # 保持有界面模式，但窗口在后台
                channel="chrome",  # 使用系统Chrome
                args=browser_args
            )
            
            print("✅ 浏览器已启动")
            print("💡 如果这是第一次运行，请先登录Bybit账户")
            
            # 获取或创建页面
            if context.pages:
                page = context.pages[0]
                print("📄 使用现有页面")
            else:
                page = await context.new_page()
                print("📄 创建新页面")
            
            print("🌐 导航到Bybit双币投资页面...")
            await page.goto("https://www.bybit.com/en/earn/dual-asset-mining/")
            await page.wait_for_timeout(200)
            
            # 登录状态检测已移除
            
            print("🔍 寻找ETH低买产品...")
            
            # 等待页面加载
            try:
                await page.wait_for_selector('text=ETH', timeout=10000)
                print("✅ 页面加载完成")
            except:
                print("⚠️ 页面加载较慢，继续尝试...")
            
            # 步骤1：点击ETH-USDT产品选择器
            print("🎯 步骤1：选择ETH-USDT产品...")
            
            try:
                # 更精确的ETH-USDT选择器，基于实际HTML结构
                eth_usdt_selectors = [
                    # 使用币种卡片的具体CSS类名和内容
                    '.CoinCards_coinCard__6OCq2:has(.CoinCards_coinCardTitle__IXqO2:text("ETH-USDT"))',
                    # 直接查找包含ETH-USDT的标题元素
                    '.CoinCards_coinCardTitle__IXqO2:text("ETH-USDT")',
                    # 备用选择器
                    'text="ETH-USDT"',
                    ':has-text("ETH-USDT")',
                ]
                
                eth_selected = False
                for selector in eth_usdt_selectors:
                    try:
                        print(f"🔍 尝试ETH-USDT选择器: {selector}")
                        eth_elements = await page.locator(selector).all()
                        print(f"  找到 {len(eth_elements)} 个匹配的元素")
                        
                        for i, element in enumerate(eth_elements):
                            if await element.is_visible():
                                element_text = await element.text_content()
                                print(f"  📋 元素{i+1}: '{element_text}'")
                                # 严格匹配ETH-USDT，避免误选ETH-BTC
                                if element_text and element_text.strip() == "ETH-USDT":
                                    print(f"  ✅ 找到精确匹配的ETH-USDT，准备点击")
                                    # 如果是标题元素，需要点击父级卡片
                                    if 'coinCardTitle' in selector:
                                        card_element = element.locator('..').first  # 父级元素
                                        await card_element.click()
                                    else:
                                        await element.click()
                                    await page.wait_for_timeout(200)
                                    eth_selected = True
                                    print("✅ 成功选择ETH-USDT")
                                    break
                        if eth_selected:
                            break
                    except Exception as e:
                        print(f"  ❌ 选择器失败: {e}")
                        continue
                
                if not eth_selected:
                    print("⚠️ 未找到ETH-USDT选择器，尝试其他方法...")
                    # 尝试更通用的方法：先查找所有币种卡片，然后筛选
                    try:
                        print("🔍 查找所有币种卡片...")
                        all_coin_cards = await page.locator('.CoinCards_coinCard__6OCq2').all()
                        print(f"  找到 {len(all_coin_cards)} 个币种卡片")
                        
                        for i, card in enumerate(all_coin_cards):
                            try:
                                card_text = await card.text_content()
                                print(f"  📋 卡片{i+1}: '{card_text}'")
                                # 检查是否包含ETH-USDT且不包含其他组合
                                if "ETH-USDT" in card_text and "ETH-BTC" not in card_text and "BTC" not in card_text:
                                    print(f"  ✅ 找到ETH-USDT卡片，准备点击")
                                    await card.click()
                                    await page.wait_for_timeout(200)
                                    eth_selected = True
                                    print("✅ 成功选择ETH-USDT卡片")
                                    break
                            except Exception as e:
                                print(f"  ❌ 处理卡片{i+1}失败: {e}")
                                continue
                        
                        # 如果还是没找到，尝试查找包含ETH-USDT的任何可见元素
                        if not eth_selected:
                            print("🔍 尝试查找任何包含ETH-USDT的元素...")
                            all_elements = await page.locator('*:has-text("ETH-USDT")').all()
                            for element in all_elements:
                                if await element.is_visible():
                                    element_text = await element.text_content()
                                    if "ETH-USDT" in element_text and "ETH-BTC" not in element_text:
                                        print(f"  🎯 尝试点击元素: {element_text[:50]}...")
                                        await element.click()
                                        await page.wait_for_timeout(200)
                                        eth_selected = True
                                        break
                    except Exception as e:
                        print(f"  ❌ 备用方法失败: {e}")
                        pass
                
                if not eth_selected:
                    print("⚠️ 仍无法选择ETH-USDT，可能页面结构已改变或已选中")
                
            except Exception as e:
                print(f"❌ 选择ETH-USDT失败: {e}")
            
            # 步骤2：选择Buy Low选项卡
            print("🎯 步骤2：选择Buy Low选项卡...")
            
            try:
                buy_low_selectors = [
                    'text="Buy Low"',
                    ':has-text("Buy Low")',
                    '[class*="buy"]:has-text("Low")',
                    'text=/Buy.*Low/'
                ]
                
                buy_low_selected = False
                for selector in buy_low_selectors:
                    try:
                        print(f"🔍 尝试Buy Low选择器: {selector}")
                        buy_low_buttons = await page.locator(selector).all()
                        print(f"  找到 {len(buy_low_buttons)} 个匹配的元素")
                        
                        for i, button in enumerate(buy_low_buttons):
                            if await button.is_visible():
                                button_text = await button.text_content()
                                print(f"  📋 元素{i+1}: '{button_text}'")
                                if button_text and "BUY LOW" in button_text.upper():
                                    print(f"  ✅ 点击Buy Low选项卡")
                                    await button.click()
                                    await page.wait_for_timeout(500)
                                    buy_low_selected = True
                                    break
                        if buy_low_selected:
                            break
                    except Exception as e:
                        print(f"  ❌ 选择器失败: {e}")
                        continue
                
                if not buy_low_selected:
                    print("⚠️ 未找到Buy Low选项卡，可能已经选中")
                
            except Exception as e:
                print(f"❌ 选择Buy Low失败: {e}")
            
            # 步骤3：等待产品列表加载并记录产品信息
            print("🎯 步骤3：等待产品列表加载...")
            await page.wait_for_timeout(100)  # 等待产品列表加载
            
            try:
                # 记录当前时间
                purchase_info["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 检查确保已选择ETH-USDT产品
                print("📊 确认当前产品选择...")
                try:
                    current_product_elem = page.locator('.ProductList_filter__BVtTe, [class*="active"], .selected').first
                    if await current_product_elem.is_visible():
                        current_text = await current_product_elem.text_content()
                        print(f"📋 当前选中产品: {current_text}")
                    else:
                        print("⚠️ 无法确认当前产品选择")
                except Exception as e:
                    print(f"⚠️ 无法确认当前产品选择: {e}")
                
                # 查找非VIP的Buy Now按钮
                print("🔍 查找产品列表中的非VIP Buy Now按钮...")
                
                # 首先尝试滚动到表格底部，确保所有产品都加载
                try:
                    print("📜 尝试滚动加载所有产品...")
                    table_container = page.locator('.table_tableBody__yzcMg')
                    if await table_container.count() > 0:
                        # 滚动到表格底部
                        await table_container.scroll_into_view_if_needed()
                        await page.wait_for_timeout(1000)
                        
                        # 多次滚动确保加载完整
                        for scroll_attempt in range(3):
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await page.wait_for_timeout(100)
                            print(f"   📜 滚动尝试 {scroll_attempt + 1}/3")
                            
                        # 滚动回顶部
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(500)
                except Exception as e:
                    print(f"⚠️ 滚动加载失败，继续扫描: {e}")
                
                # 查找所有产品行，尝试多种选择器
                print("🔍 使用多种选择器查找产品行...")
                
                # 尝试不同的选择器
                selectors_to_try = [
                    'tr.table_tr__p0hoR',
                    'tbody tr',
                    '.table_tableBody__yzcMg tr',
                    'table tr:has(.ProductList_title__dQRgA)',
                    'tr:has(.ProductList_button__JPmz2)'
                ]
                
                product_rows = []
                for selector in selectors_to_try:
                    try:
                        rows = await page.locator(selector).all()
                        print(f"   🔍 选择器 '{selector}': 找到 {len(rows)} 行")
                        if len(rows) > len(product_rows):
                            product_rows = rows
                            print(f"   ✅ 使用此选择器，找到更多产品行")
                    except Exception as e:
                        print(f"   ❌ 选择器 '{selector}' 失败: {e}")
                
                print(f"📋 最终找到 {len(product_rows)} 个产品行")
                
                non_vip_buttons = []
                vip_count = 0
                
                for i, row in enumerate(product_rows):
                    try:
                        # 检查是否包含VIP标签
                        vip_tags = await row.locator('.ProductList_vipTag__yZPlr').count()
                        row_text = await row.text_content()
                        
                        if vip_tags > 0:
                            vip_count += 1
                            print(f"  🔒 产品{i+1}: VIP专属 - 跳过")
                            continue
                        
                        # 非VIP产品，查找Buy Now按钮
                        buy_button = row.locator('button:has-text("Buy Now")').first
                        if await buy_button.is_visible():
                            # 解析产品信息
                            target_price_elem = row.locator('td').first.locator('.ProductList_title__dQRgA')
                            target_price_count = await target_price_elem.count()
                            
                            if target_price_count > 0:
                                # 获取价格和百分比信息
                                try:
                                    # 获取完整文本内容
                                    full_text = await target_price_elem.text_content()
                                    
                                    # 获取纯价格部分（移除span中的百分比）
                                    price_text = await target_price_elem.evaluate("""
                                        element => {
                                            // 克隆元素以避免修改原始DOM
                                            const clone = element.cloneNode(true);
                                            // 移除所有span元素（包含百分比）
                                            const spans = clone.querySelectorAll('span');
                                            spans.forEach(span => span.remove());
                                            // 返回纯文本内容
                                            return clone.textContent.trim();
                                        }
                                    """)
                                    target_price = price_text if price_text else "N/A"
                                    
                                    # 提取百分比信息
                                    try:
                                        offset_elem = target_price_elem.locator('.ProductList_offset__cNbj9')
                                        if await offset_elem.count() > 0:
                                            price_offset = await offset_elem.text_content()
                                            price_offset = price_offset.strip() if price_offset else "N/A"
                                        else:
                                            # 如果没找到span，尝试从完整文本中提取百分比
                                            offset_match = re.search(r'([+-]?\d+\.?\d*%)', full_text)
                                            price_offset = offset_match.group(1) if offset_match else "N/A"
                                    except:
                                        price_offset = "N/A"
                                        
                                except:
                                    # 如果JavaScript执行失败，使用备用方法
                                    full_text = await target_price_elem.text_content()
                                    # 使用正则表达式提取价格部分
                                    price_match = re.match(r'^([0-9,]+)', full_text.replace(' ', ''))
                                    target_price = price_match.group(1) if price_match else "N/A"
                                    
                                    # 提取百分比
                                    offset_match = re.search(r'([+-]?\d+\.?\d*%)', full_text)
                                    price_offset = offset_match.group(1) if offset_match else "N/A"
                            else:
                                target_price = "N/A"
                                price_offset = "N/A"
                            
                            cells = await row.locator('td').all()
                            settlement_date = await cells[1].text_content() if len(cells) > 1 else "N/A"
                            duration = await cells[2].text_content() if len(cells) > 2 else "N/A"
                            
                            # 处理APR元素
                            if len(cells) > 3:
                                apr_elem = cells[3].locator('.ProductList_greenApy__awkwK').first
                                apr_count = await apr_elem.count()
                                apr = await apr_elem.text_content() if apr_count > 0 else "N/A"
                            else:
                                apr = "N/A"
                            
                            # 价格已经在上面清理过了，这里不需要额外处理
                            
                            product_info = {
                                "index": len(non_vip_buttons) + 1,
                                "target_price": target_price.strip(),
                                "price_offset": price_offset.strip(),
                                "settlement_date": settlement_date.strip(),
                                "duration": duration.strip(),
                                "apr": apr.strip(),
                                "is_vip": False,
                                "row_index": i  # 存储行索引而不是Locator对象
                            }
                            
                            non_vip_buttons.append(product_info)
                            # 格式化显示价格和百分比
                            price_display = target_price.strip()
                            if price_offset.strip() and price_offset.strip() != "N/A":
                                price_display += f" ({price_offset.strip()})"
                            
                            # 检查是否是整数且是5的倍数的价格
                            is_multiple_of_5 = is_price_multiple_of_5(target_price)
                            price_tag = "🎯 [整5]" if is_multiple_of_5 else ""
                            print(f"  ✅ 产品{len(non_vip_buttons)}: 目标价={price_display}, 期限={duration.strip()}, APR={apr.strip()} {price_tag}")
                            
                    except Exception as e:
                        print(f"  ❌ 解析产品{i+1}失败: {e}")
                        continue
                
                print(f"📊 跳过了 {vip_count} 个VIP产品，找到 {len(non_vip_buttons)} 个可用产品")
                
                # 更新产品列表信息
                purchase_info["product_list"] = [p for p in non_vip_buttons]
                
                if non_vip_buttons:
                    # 优先选择价格是整5的产品
                    selected_product = None
                    
                    # 首先尝试找到价格是整5的产品
                    for product in non_vip_buttons:
                        target_price = product.get('target_price', '')
                        if is_price_multiple_of_5(target_price):
                            selected_product = product
                            print(f"🎯 找到整数且5倍数价格产品: {target_price}")
                            break
                    
                    # 如果没有找到整5的产品，选择第一个非VIP产品
                    if selected_product is None:
                        selected_product = non_vip_buttons[0]
                        print(f"🔍 未找到整数且5倍数价格产品，选择第一个可用产品")
                    
                    purchase_info["selected_product"] = selected_product
                    
                    # 格式化选中产品的价格显示
                    price_display = selected_product['target_price']
                    if selected_product.get('price_offset', '').strip() and selected_product.get('price_offset', '').strip() != "N/A":
                        price_display += f" ({selected_product.get('price_offset', '').strip()})"
                    
                    print(f"🎯 选择第一个非VIP产品进行申购:")
                    print(f"   📍 目标价格: {price_display}")
                    print(f"   ⏳ 投资期限: {selected_product['duration']}")
                    print(f"   📈 年化收益率: {selected_product['apr']}")
                    
                    # 重新获取对应行的Buy Now按钮并点击
                    selected_row_index = selected_product['row_index']
                    selected_row = product_rows[selected_row_index]
                    buy_button = selected_row.locator('button:has-text("Buy Now")').first
                    
                    if await buy_button.is_visible() and await buy_button.is_enabled():
                        await buy_button.click()
                        await page.wait_for_timeout(100)
                        print("✅ 已点击非VIP产品的Buy Now按钮")
                    else:
                        exit_with_error("无法点击选中产品的Buy Now按钮")
                    
                else:
                    exit_with_error("未找到任何非VIP产品")
                    
            except Exception as e:
                exit_with_error("选择产品失败", e)
            
            # 开始处理订单弹窗的循环，最多重试3次
            max_retries = 3
            retry_count = 0
            order_success = False
            
            while retry_count < max_retries and not order_success:
                print(f"\n🔄 尝试处理订单弹窗 (第{retry_count + 1}次/共{max_retries}次)")
                
                # 等待订单弹窗出现
                print("⏳ 等待订单弹窗加载...")
                await page.wait_for_timeout(200)
                
                # 等待弹窗完全加载 - 寻找弹窗容器
                print("🔍 寻找订单弹窗容器...")
                dialog_selectors = [
                    '.ant-modal',  # Ant Design 模态框
                    '.modal',  # 通用模态框
                    '[role="dialog"]',  # 有dialog角色的元素
                    '.ant-modal-content',  # Ant Design 模态框内容
                    '.order-dialog',  # 可能的订单对话框类名
                    '[class*="dialog"]',  # 包含dialog的类名
                    '[class*="modal"]'  # 包含modal的类名
                ]
                
                dialog_container = None
                for selector in dialog_selectors:
                    try:
                        dialog = page.locator(selector).first
                        if await dialog.is_visible(timeout=5000):
                            print(f"✅ 找到弹窗容器: {selector}")
                            dialog_container = dialog
                            break
                    except:
                        continue
                
                if not dialog_container:
                    print("⚠️ 未找到弹窗容器，将在整个页面中寻找")
                    dialog_container = page  # 如果找不到弹窗，则在整个页面中寻找
                
                # 检查是否有价格更新错误信息
                print("🔍 检查是否有价格更新错误...")
                # wait for 200
                await page.wait_for_timeout(100)
                price_update_error = False
                error_selectors = [
                    'text="Price has been updated. Please choose again."',
                    '.index_errorTxt__pYQD_:has-text("Price has been updated")',
                    '[class*="error"]:has-text("Price has been updated")',
                    ':has-text("价格已更新")',
                    ':has-text("please choose again")'
                ]
                
                for error_selector in error_selectors:
                    try:
                        error_elements = await dialog_container.locator(error_selector).all()
                        if error_elements:
                            for error_elem in error_elements:
                                if await error_elem.is_visible():
                                    error_text = await error_elem.text_content()
                                    print(f"⚠️ 检测到价格更新错误: {error_text}")
                                    price_update_error = True
                                    break
                        if price_update_error:
                            break
                    except:
                        continue
                
                if price_update_error:
                    print("🔄 价格已更新，需要关闭弹窗并重新选择产品...")
                    retry_count += 1
                    
                    # 关闭当前弹窗
                    close_selectors = [
                        '.index_close__9N423',  # 估算收益弹窗的关闭按钮
                        '.anticon-close',       # 带有关闭图标的元素
                        '.ant-modal-close',
                        '.modal-close',
                        '[class*="close"]',
                        '[aria-label="close"]', # 通过aria-label属性查找
                        'button:has-text("×")',
                        'button:has-text("Close")',
                        'button:has-text("Cancel")',
                        'button:has-text("取消")'
                    ]
                    
                    closed = False
                    for close_selector in close_selectors:
                        try:
                            close_buttons = await page.locator(close_selector).all()
                            print(f"🔍 尝试选择器: {close_selector}, 找到 {len(close_buttons)} 个元素")
                            for close_btn in close_buttons:
                                if await close_btn.is_visible():
                                    print(f"✅ 找到可见的关闭按钮，使用选择器: {close_selector}")
                                    await close_btn.click()
                                    await page.wait_for_timeout(500)  # 增加等待时间
                                    print("✅ 已关闭价格更新错误弹窗")
                                    closed = True
                                    break
                            if closed:
                                break
                        except Exception as e:
                            print(f"⚠️ 选择器 {close_selector} 失败: {str(e)}")
                            continue
                    
                    if not closed:
                        # 尝试按ESC键关闭弹窗
                        try:
                            await page.keyboard.press('Escape')
                            await page.wait_for_timeout(200)
                            print("✅ 已通过ESC键关闭弹窗")
                        except:
                            print("⚠️ 无法关闭弹窗，尝试继续...")
                    
                    # 重新选择第一个非VIP产品
                    if retry_count < max_retries:
                        print("🔄 重新选择非VIP产品...")
                        try:
                            # 重新获取产品行列表
                            product_rows = await page.locator('tr.table_tr__p0hoR').all()
                            print(f"📋 重新找到 {len(product_rows)} 个产品行")
                            
                            found_new_product = False
                            for i, row in enumerate(product_rows):
                                try:
                                    # 检查是否为VIP产品
                                    vip_tags = await row.locator('.ProductList_vipTag__yZPlr').count()
                                    if vip_tags > 0:
                                        continue
                                    
                                    # 查找Buy Now按钮
                                    buy_button = row.locator('button:has-text("Buy Now")').first
                                    if await buy_button.is_visible() and await buy_button.is_enabled():
                                        # 获取产品信息
                                        target_price_elem = row.locator('td').first.locator('.ProductList_title__dQRgA')
                                        
                                        if await target_price_elem.count() > 0:
                                            try:
                                                # 获取完整文本和价格部分
                                                full_text = await target_price_elem.text_content()
                                                
                                                # 只获取价格部分，排除百分比部分
                                                price_text = await target_price_elem.evaluate("""
                                                    element => {
                                                        const clone = element.cloneNode(true);
                                                        const spans = clone.querySelectorAll('span');
                                                        spans.forEach(span => span.remove());
                                                        return clone.textContent.trim();
                                                    }
                                                """)
                                                target_price = price_text if price_text else "N/A"
                                                
                                                # 提取百分比
                                                try:
                                                    offset_elem = target_price_elem.locator('.ProductList_offset__cNbj9')
                                                    if await offset_elem.count() > 0:
                                                        price_offset = await offset_elem.text_content()
                                                        price_offset = price_offset.strip() if price_offset else ""
                                                    else:
                                                        offset_match = re.search(r'([+-]?\d+\.?\d*%)', full_text)
                                                        price_offset = offset_match.group(1) if offset_match else ""
                                                except:
                                                    price_offset = ""
                                                    
                                            except:
                                                # 备用方法
                                                full_text = await target_price_elem.text_content()
                                                price_match = re.match(r'^([0-9,]+)', full_text.replace(' ', ''))
                                                target_price = price_match.group(1) if price_match else "N/A"
                                                
                                                # 提取百分比
                                                offset_match = re.search(r'([+-]?\d+\.?\d*%)', full_text)
                                                price_offset = offset_match.group(1) if offset_match else ""
                                        else:
                                            target_price = "N/A"
                                            price_offset = ""
                                        
                                        # 格式化重新选择产品的价格显示
                                        price_display = target_price
                                        if price_offset.strip() and price_offset.strip() != "N/A":
                                            price_display += f" ({price_offset.strip()})"
                                        
                                        logger.info(f"重新选择产品: {price_display}")
                                        await buy_button.click()
                                        await page.wait_for_timeout(200)
                                        found_new_product = True
                                        break
                                
                                except Exception as e:
                                    continue
                            
                            if not found_new_product:
                                print("❌ 重新选择产品失败")
                                break
                        except Exception as e:
                            print(f"❌ 重新选择产品时出错: {e}")
                            break
                    
                    # 继续下一次循环尝试
                    continue
                else:
                    # 没有价格更新错误，继续正常处理流程
                    print("✅ 未检测到价格更新错误，继续正常流程")
                    order_success = True  # 标记可以继续处理订单
                    break
            
            if not order_success:
                exit_with_error(f"经过{max_retries}次重试仍无法处理价格更新问题")
            
            # 在弹窗容器中填写投资金额
            print("💰 步骤4：在弹窗中填写投资金额 20 USDT...")
            
            # 先在弹窗容器中查找所有输入框以便调试
            try:
                dialog_inputs = await dialog_container.locator('input').all()
                print(f"🔍 弹窗容器中找到 {len(dialog_inputs)} 个输入框")
                
                for i, input_elem in enumerate(dialog_inputs):  # 检查所有输入框
                    try:
                        placeholder = await input_elem.get_attribute('placeholder')
                        input_type = await input_elem.get_attribute('type')
                        class_name = await input_elem.get_attribute('class')
                        is_visible = await input_elem.is_visible()
                        parent_text = ""
                        try:
                            # 获取父元素的文本以了解上下文
                            parent = input_elem.locator('xpath=..')
                            parent_text = await parent.text_content()
                            parent_text = parent_text[:50] + "..." if len(parent_text) > 50 else parent_text
                        except:
                            pass
                        print(f"📋 弹窗输入框{i+1}: type={input_type}, placeholder={placeholder}, class={class_name}, visible={is_visible}")
                        if parent_text:
                            print(f"     上下文: {parent_text}")
                    except:
                        pass
            except Exception as e:
                print(f"⚠️ 无法检查弹窗输入框: {e}")
            
            # 改进的金额输入框选择器，在弹窗上下文中查找
            amount_selectors = [
                # 基于placeholder的选择器
                'input[placeholder*="20"]',  # 包含20的placeholder
                'input[placeholder*="~"]',   # 包含~的placeholder
                'input[placeholder*="USDT"]', # 包含USDT的placeholder
                # 基于标签文本的选择器
                'text="Invested Amount" >> .. >> input',  # Invested Amount标签的输入框
                'text="投资金额" >> .. >> input',  # 中文标签
                'text="Amount" >> .. >> input',  # Amount标签
                # 基于类名的选择器
                '.index_amountInput__JeXip input',
                '.index_input__SuqTr',
                'input[class*="amount"]',
                'input[class*="Amount"]',
                # 通用输入框选择器（作为后备）
                'input[type="text"]',
                'input[type="number"]'
            ]
            
            amount_filled = False
            for i, selector in enumerate(amount_selectors):
                try:
                    print(f"🔍 在弹窗中尝试金额选择器{i+1}: {selector}")
                    # 在弹窗容器中查找输入框
                    amount_inputs = await dialog_container.locator(selector).all()
                    print(f"  找到 {len(amount_inputs)} 个匹配的输入框")
                    
                    for j, amount_input in enumerate(amount_inputs):
                        try:
                            if await amount_input.is_visible():
                                placeholder = await amount_input.get_attribute('placeholder')
                                print(f"  📋 输入框{j+1}: placeholder='{placeholder}', visible=True")
                                
                                # 尝试填写金额
                                await amount_input.clear()
                                await amount_input.fill(INVESTMENT_AMOUNT)
                                print(f"✅ 已在弹窗中填写金额：{INVESTMENT_AMOUNT} USDT")
                                amount_filled = True
                                break
                            else:
                                print(f"  📋 输入框{j+1}: 不可见")
                        except Exception as e:
                            print(f"  ❌ 输入框{j+1}处理失败: {e}")
                            continue
                    
                    if amount_filled:
                        break
                        
                except Exception as e:
                    print(f"  ❌ 选择器失败: {e}")
                    continue
            
            if not amount_filled:
                exit_with_error("未在弹窗中找到投资金额输入框")
            
            # 在弹窗中勾选协议复选框
            print("☑️ 步骤5：在弹窗中勾选协议...")
            
            checkbox_selectors = [
                'input[type="checkbox"]',
                '.ant-checkbox-input',
                'label:has-text("I understand") input',
                'label:has-text("principal guaranteed") input',
                '.index_checkbox__ICF9u input'
            ]
            
            checkbox_checked = False
            for i, selector in enumerate(checkbox_selectors):
                try:
                    print(f"🔍 在弹窗中尝试复选框选择器{i+1}: {selector}")
                    # 在弹窗容器中查找复选框
                    checkboxes = await dialog_container.locator(selector).all()
                    print(f"  找到 {len(checkboxes)} 个匹配的复选框")
                    
                    for j, checkbox in enumerate(checkboxes):
                        try:
                            if await checkbox.is_visible():
                                is_checked = await checkbox.is_checked()
                                print(f"  📋 复选框{j+1}，当前状态：{'已勾选' if is_checked else '未勾选'}")
                                
                                if not is_checked:
                                    await checkbox.check()
                                    print("✅ 已在弹窗中勾选协议复选框")
                                    checkbox_checked = True
                                    break
                                else:
                                    print("✅ 弹窗中的协议复选框已经勾选")
                                    checkbox_checked = True
                                    break
                        except Exception as e:
                            print(f"  ❌ 复选框{j+1}处理失败: {e}")
                            continue
                    
                    if checkbox_checked:
                        break
                        
                except Exception as e:
                    print(f"  ❌ 复选框选择器失败: {e}")
                    continue
            
            if not checkbox_checked:
                exit_with_error("未在弹窗中找到协议复选框")
            
            # 点击最终的 Order Now 按钮
            print("🚀 步骤6：点击 Order Now 按钮...")
            
            # 等待一下确保页面更新
            await page.wait_for_timeout(200)
            
            # 先查找所有按钮并显示状态
            all_buttons = await page.locator('button').all()
            print(f"🔍 弹窗中找到 {len(all_buttons)} 个按钮")
            
            for i, button in enumerate(all_buttons):  # 检查所有按钮
                try:
                    button_text = await button.text_content()
                    is_visible = await button.is_visible()
                    is_enabled = await button.is_enabled()
                    disabled = await button.get_attribute('disabled')
                    if button_text:
                        clean_text = button_text.strip()
                        print(f"📋 按钮{i+1}: '{clean_text}', visible={is_visible}, enabled={is_enabled}, disabled={disabled}")
                except:
                    pass
            
            # 查找 Order Now 按钮
            order_selectors = [
                'button:has-text("Order Now"):not([disabled])',
                '.index_orderBut__aa_Vc:not([disabled])',
                '.byfi-button:has-text("Order Now"):not([disabled])',
                'button[class*="orderBut"]:not([disabled])',
                'button:has-text("Order Now")'  # 最后尝试，即使是disabled状态
            ]
            
            order_clicked = False
            for i, selector in enumerate(order_selectors):
                try:
                    print(f"🔍 尝试Order Now选择器{i+1}: {selector}")
                    order_buttons = await page.locator(selector).all()
                    print(f"  找到 {len(order_buttons)} 个匹配的按钮")
                    
                    for j, button in enumerate(order_buttons):
                        if await button.is_visible():
                            button_text = await button.text_content()
                            is_enabled = await button.is_enabled()
                            disabled = await button.get_attribute('disabled')
                            
                            print(f"  📋 Order Now按钮{j+1}: '{button_text}', enabled={is_enabled}, disabled={disabled}")
                            
                            if is_enabled and disabled is None:
                                print(f"  ✅ 点击可用的Order Now按钮")
                                await button.click()
                                order_clicked = True
                                break
                            elif disabled is not None:
                                print(f"  ⚠️ Order Now按钮被禁用，可能需要先完成所有字段")
                    
                    if order_clicked:
                        break
                except Exception as e:
                    print(f"  ❌ 选择器失败: {e}")
                    continue
            
            if not order_clicked:
                exit_with_error("Order Now按钮不可用或未找到")
            
            await page.wait_for_timeout(500)
            
            # 检查确认对话框 - 增强版本
            print("🔍 检查Order Now后的确认对话框...")
            
            # 等待可能的确认对话框出现
            await page.wait_for_timeout(200)
            
            # 查找所有按钮以便调试
            try:
                all_buttons_after_order = await page.locator('button').all()
                print(f"🔍 Order Now后找到 {len(all_buttons_after_order)} 个按钮")
                
                for i, button in enumerate(all_buttons_after_order):  # 检查所有按钮
                    try:
                        button_text = await button.text_content()
                        is_visible = await button.is_visible()
                        if button_text and is_visible:
                            clean_text = button_text.strip()
                            print(f"📋 可见按钮{i+1}: '{clean_text}'")
                    except:
                        pass
            except Exception as e:
                print(f"⚠️ 无法检查按钮列表: {e}")
            
            # 增强的确认按钮选择器
            confirm_selectors = [
                'button:has-text("Order Now")',  # 可能是第二个 Order Now
                'button:has-text("Confirm")',
                'button:has-text("确认")',
                'button:has-text("OK")',
                'button:has-text("Continue")',
                'button:has-text("Proceed")',
                'button:has-text("Yes")',
                'button:has-text("是")',
                'button:has-text("Submit")',
                'button:has-text("提交")',
                'button:has-text("Place Order")',
                'button:has-text("下单")',
                '.ant-btn-primary:not([disabled])',  # Ant Design主要按钮
                '.byfi-button-primary:not([disabled])',  # Bybit主要按钮
                'button[class*="primary"]:not([disabled])',  # 任何主要按钮
                'button[type="submit"]:not([disabled])'  # 提交按钮
            ]
            
            confirmation_found = False
            for i, selector in enumerate(confirm_selectors):
                try:
                    print(f"🔍 尝试确认按钮选择器{i+1}: {selector}")
                    confirm_buttons = await page.locator(selector).all()
                    print(f"  找到 {len(confirm_buttons)} 个匹配的按钮")
                    
                    for j, button in enumerate(confirm_buttons):
                        try:
                            if await button.is_visible(timeout=1000):
                                button_text = await button.text_content()
                                is_enabled = await button.is_enabled()
                                print(f"  📋 确认按钮{j+1}: '{button_text}', enabled={is_enabled}")
                                
                                if is_enabled:
                                    print(f"  ✅ 点击确认按钮: '{button_text}'")
                                    await button.click()
                                    confirmation_found = True
                                    await page.wait_for_timeout(500)  # 等待确认处理
                                    break
                        except Exception as e:
                            print(f"  ❌ 按钮{j+1}处理失败: {e}")
                            continue
                    
                    if confirmation_found:
                        break
                        
                except Exception as e:
                    print(f"  ❌ 选择器{i+1}失败: {e}")
                    continue
            
            if not confirmation_found:
                print("⚠️ 未找到确认对话框或确认按钮，可能没有额外确认步骤")
                print("✅ 继续检查申购结果...")
            else:
                print("✅ 已处理确认对话框")
            
            await page.wait_for_timeout(200)
            
            # 检查申购结果并记录详细信息
            print("🔍 检查申购结果...")
            # 等待一段时间让成功弹窗出现
            await page.wait_for_timeout(1000)
            
            success_texts = [
                'Your order is successful', 'success', 'successful', '成功', '订单创建', 
                'order created', 'order placed', 'purchase completed', 'transaction completed', 
                '申购成功', '投资成功', 'order submitted', 'submitted successfully', 
                '提交成功', 'confirmed'
            ]
            
            purchase_success = False
            
            # 增强的成功检测逻辑
            try:
                print("🔍 开始全面检查申购成功状态...")
                
                # 等待更长时间让弹窗出现
                print("⏳ 等待2秒让成功弹窗完全加载...")
                await page.wait_for_timeout(2000)
                
                # 方法1: 检查具体的成功弹窗元素
                success_modal_selectors = [
                    '.ant-modal-body',
                    '.index_title__05HWD',
                    '.ant-modal',
                    '[class*="modal"]',
                    '.index_pic__es8SJ'  # 成功图标
                ]
                
                for selector in success_modal_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        print(f"🔍 检查选择器 '{selector}': 找到 {len(elements)} 个元素")
                        for element in elements:
                            if await element.is_visible():
                                text_content = await element.text_content()
                                print(f"📝 元素文本内容: {text_content[:100] if text_content else 'None'}")
                                if text_content and "Your order is successful" in text_content:
                                    print(f"✅ 通过选择器 '{selector}' 找到成功弹窗！")
                                    purchase_success = True
                                    break
                        if purchase_success:
                            break
                    except Exception as e:
                        print(f"⚠️ 检查选择器 '{selector}' 失败: {e}")
                        continue
                
                # 方法2: 如果没找到弹窗，检查整个页面文本
                if not purchase_success:
                    print("🔍 未找到弹窗，检查整个页面内容...")
                    try:
                        page_content = await page.content()
                        if "Your order is successful" in page_content:
                            print("✅ 在页面内容中找到成功标识！")
                            purchase_success = True
                        else:
                            print("⚠️ 页面内容中未找到成功标识")
                            # 保存调试截图
                            try:
                                screenshot_path = f"debug_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                await page.screenshot(path=screenshot_path)
                                print(f"📸 已保存调试截图: {screenshot_path}")
                            except:
                                pass
                            # 打印页面部分内容用于调试
                            print(f"📄 页面内容片段: {page_content[-500:] if len(page_content) > 500 else page_content}")
                    except Exception as e:
                        print(f"⚠️ 检查页面内容失败: {e}")
                
                # 方法3: 作为最后手段，检查页面URL或其他状态指示器
                if not purchase_success:
                    print("🔍 检查页面URL和其他状态指示器...")
                    try:
                        current_url = page.url
                        print(f"📍 当前页面URL: {current_url}")
                        
                        # 检查URL中是否有成功相关的参数
                        if "success" in current_url.lower() or "complete" in current_url.lower():
                            print("✅ URL中包含成功指示器！")
                            purchase_success = True
                    except Exception as e:
                        print(f"⚠️ 检查URL失败: {e}")
                        
            except Exception as e:
                print(f"⚠️ 检查成功状态时出错: {e}")
            
            if purchase_success:
                # 更新申购状态
                purchase_info["status"] = "success"
                
                # 检测到申购成功，无需关闭弹窗
                print("🎉 检测到申购成功！流程完成，无需处理弹窗")
                
                # 等待一下确保页面状态稳定
                await page.wait_for_timeout(1000)
                
                # 生成详细的成功日志
                print("\n" + "="*80)
                print("🎉 申购成功！")
                print("="*80)
                
                # JSON记录功能已移除
                
                # 文本日志记录功能已移除
                
                # 打印详细的申购信息
                print(f"\n📊 申购详细信息:")
                print(f"   ⏰ 申购时间: {purchase_info['timestamp']}")
                print(f"   💰 投资金额: {purchase_info['investment_amount']} {purchase_info['currency']}")
                print(f"   📈 产品类型: {purchase_info['product_type']}")
                
                if purchase_info["selected_product"]:
                    print(f"\n🎯 选中产品信息:")
                    selected = purchase_info["selected_product"]
                    # 格式化最终结果的价格显示
                    price_display = selected.get('target_price', 'N/A')
                    if selected.get('price_offset', '').strip() and selected.get('price_offset', '').strip() != "N/A":
                        price_display += f" ({selected.get('price_offset', '').strip()})"
                    
                    print(f"   📍 目标价格: {price_display}")
                    print(f"   ⏳ 投资期限: {selected.get('duration', 'N/A')}")
                    print(f"   📈 年化收益率: {selected.get('apr', 'N/A')}")
                    print(f"   📅 结算日期: {selected.get('settlement_date', 'N/A')}")
                
                if purchase_info["product_list"]:
                    print(f"\n📋 当时可选产品列表 (共{len(purchase_info['product_list'])}个非VIP产品):")
                    for i, product in enumerate(purchase_info["product_list"]):
                        status = "✅ [已选择]" if product == purchase_info["selected_product"] else "   "
                        vip_status = " [VIP]" if product.get('is_vip', False) else ""
                        # 格式化产品列表的价格显示
                        price_display = product.get('target_price', 'N/A')
                        if product.get('price_offset', '').strip() and product.get('price_offset', '').strip() != "N/A":
                            price_display += f" ({product.get('price_offset', '').strip()})"
                        
                        print(f"{status} 产品{i+1}: 目标价={price_display}, "
                              f"期限={product.get('duration', 'N/A')}, APR={product.get('apr', 'N/A')}{vip_status}")
                
                print("\n" + "="*80)
                print("🎊 恭喜！ETH双币投资申购完成")
                print("="*80)
                
                # 发送成功通知到Telegram
                selected = purchase_info["selected_product"]
                telegram_message = f"""🎉 *Bybit双币投资申购成功！*

⏰ *申购时间:* {purchase_info['timestamp']}
💰 *投资金额:* {purchase_info['investment_amount']} {purchase_info['currency']}
📈 *产品类型:* {purchase_info['product_type']}

🎯 *选中产品信息:*
📍 目标价格: {selected.get('target_price', 'N/A')}{' (' + selected.get('price_offset', '').strip() + ')' if selected.get('price_offset', '').strip() and selected.get('price_offset', '').strip() != 'N/A' else ''}
⏳ 投资期限: {selected.get('duration', 'N/A')}
📈 年化收益率: {selected.get('apr', 'N/A')}
📅 结算日期: {selected.get('settlement_date', 'N/A')}

✅ 申购已成功完成！"""
                
            else:
                purchase_info["status"] = "unknown"
                print("⚠️ 无法确认申购状态，请检查页面")
                print("📸 保存最终页面截图...")
                # 操作完成
            
            print("\n✅ 操作完成！")
            print("💡 浏览器数据已保存")
            print("🌐 浏览器将保持打开状态")
            
        except Exception as e:
            exit_with_error("执行过程中出现错误", e)

if __name__ == "__main__":
    print("🚀 Bybit双币投资自动申购（智能版）")
    print("=" * 60)
    print("💡 操作流程：")
    print("   1️⃣ 选择ETH-USDT产品")
    print("   2️⃣ 选择Buy Low选项卡") 
    print("   3️⃣ 跳过VIP-Only产品")
    print("   4️⃣ 选择第一个非VIP产品的Buy Now")
    print("   5️⃣ 填写投资金额20 USDT")
    print("   6️⃣ 勾选协议复选框")
    print("   7️⃣ 点击Order Now确认订单")
    print("   8️⃣ 记录申购详情和产品信息")
    print("=" * 60)
    asyncio.run(main())