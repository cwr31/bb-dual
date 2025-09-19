#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit USDT自动赎回脚本
在进行双币投资前，先赎回理财产品中的USDT
"""

import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import requests
import sys
import os

# 加载.env配置文件
from load_env import load_env, get_config
from logger_config import get_logger

# 初始化logger
logger = get_logger('redeem_usdt')
load_env()


# 配置项
INVESTMENT_AMOUNT = get_config('BYBIT_INVESTMENT_AMOUNT', '20')
CURRENCY = get_config('BYBIT_CURRENCY', 'USDT')
TELEGRAM_BOT_TOKEN = get_config('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = get_config('TELEGRAM_CHAT_ID', '')
BROWSER_BACKGROUND = get_config('BROWSER_BACKGROUND', 'false').lower() == 'true'

logger.info(f"配置信息：投资金额 = {INVESTMENT_AMOUNT} {CURRENCY}")
logger.info(f"浏览器模式：{'后台窗口' if BROWSER_BACKGROUND else '前台显示'}")

# 全局变量记录赎回信息
redeem_info = {
    "timestamp": None,
    "target_amount": INVESTMENT_AMOUNT,  # 目标赎回金额
    "currency": CURRENCY,
    "available_products": [],
    "redeemed_products": [],
    "total_redeemed": 0,
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
    """USDT赎回主流程"""
    async with async_playwright() as p:
        print("🚀 启动Chrome浏览器进行USDT赎回...")
        
        # 使用相同的用户数据目录，保持浏览器数据
        user_data_dir = r"C:\Users\wenrui.cao\AppData\Local\BybitBot"
        
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
                channel="chrome",
                args=browser_args
            )
            
            print("✅ 浏览器已启动")
            
            # 获取或创建页面
            if context.pages:
                page = context.pages[0]
                print("📄 使用现有页面")
            else:
                page = await context.new_page()
                print("📄 创建新页面")
            
            # 记录当前时间
            redeem_info["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print("🌐 导航到Bybit理财页面...")
            await page.goto("https://www.bybit.com/user/assets/home/financial?protype=4")
            await page.wait_for_timeout(200)
            
            # 登录状态检测已移除
            
            print("🔍 等待理财页面加载...")
            await page.wait_for_timeout(5000)
            
            # 查找可赎回的USDT理财产品
            print("💰 查找可赎回的USDT理财产品...")
            
            try:
                # 等待产品列表加载
                await page.wait_for_selector('table, .product-list, [class*="table"]', timeout=10000)
                print("✅ 产品列表加载完成")
            except:
                print("⚠️ 产品列表加载较慢，继续尝试...")
            
            # 查找所有包含USDT和Redeem按钮的产品行
            product_selectors = [
                'tr:has-text("USDT")',
                '[class*="row"]:has-text("USDT")',
                '.product-item:has-text("USDT")',
                'tbody tr',
                '[class*="item"]'
            ]
            
            found_products = []
            target_amount = float(redeem_info["target_amount"])
            total_available = 0
            
            for selector in product_selectors:
                try:
                    print(f"🔍 尝试产品选择器: {selector}")
                    products = await page.locator(selector).all()
                    print(f"  找到 {len(products)} 个匹配的产品行")
                    
                    for i, product in enumerate(products):
                        try:
                            product_text = await product.text_content()
                            if not product_text or "USDT" not in product_text.upper():
                                continue
                            
                            print(f"  📋 产品{i+1}: {product_text[:100]}...")
                            
                            # 查找Redeem按钮
                            redeem_buttons = await product.locator('button:has-text("Redeem"), button:has-text("赎回"), [class*="redeem"]').all()
                            
                            if redeem_buttons:
                                # 尝试提取金额信息
                                amount_match = None
                                import re
                                amount_patterns = [
                                    r'(\d{1,3}(?:,\d{3})*\.?\d*)\s*USDT',  # 支持千位分隔符
                                    r'(\d{1,3}(?:,\d{3})*\.?\d*)\s*usdt',  # 支持千位分隔符
                                    r'(\d+\.?\d*)\s*USDT',                  # 原始模式作为备用
                                    r'(\d+\.?\d*)\s*usdt',                  # 原始模式作为备用
                                    r'Balance.*?(\d{1,3}(?:,\d{3})*\.?\d*)', # 支持千位分隔符
                                    r'Balance.*?(\d+\.?\d*)',               # 原始模式作为备用
                                    r'余额.*?(\d{1,3}(?:,\d{3})*\.?\d*)',   # 支持千位分隔符
                                    r'余额.*?(\d+\.?\d*)'                   # 原始模式作为备用
                                ]
                                
                                for pattern in amount_patterns:
                                    matches = re.findall(pattern, product_text)
                                    if matches:
                                        try:
                                            # 移除千位分隔符并转换为浮点数
                                            amount_str = matches[0].replace(',', '')
                                            amount_match = float(amount_str)
                                            print(f"  ✅ 匹配到金额: '{matches[0]}' -> {amount_match} USDT")
                                            break
                                        except Exception as parse_error:
                                            print(f"  ⚠️ 金额解析失败: '{matches[0]}' - {parse_error}")
                                            continue
                                
                                if amount_match and amount_match > 0:
                                    product_info = {
                                        "index": len(found_products) + 1,
                                        "amount": amount_match,
                                        "text": product_text[:200],
                                        "redeem_button": redeem_buttons[0],
                                        "row_element": product
                                    }
                                    found_products.append(product_info)
                                    total_available += amount_match
                                    print(f"  ✅ 找到可赎回产品: {amount_match} USDT")
                                else:
                                    print(f"  ⚠️ 无法提取金额信息")
                            else:
                                print(f"  ❌ 未找到Redeem按钮")
                        
                        except Exception as e:
                            print(f"  ❌ 解析产品{i+1}失败: {e}")
                            continue
                    
                    if found_products:
                        break  # 找到产品就停止尝试其他选择器
                        
                except Exception as e:
                    print(f"  ❌ 选择器失败: {e}")
                    continue
            
            redeem_info["available_products"] = [
                {"index": p["index"], "amount": p["amount"], "text": p["text"]} 
                for p in found_products
            ]
            
            print(f"\n📊 找到 {len(found_products)} 个可赎回的USDT产品")
            print(f"💰 总可赎回金额: {total_available} USDT")
            print(f"🎯 目标赎回金额: {target_amount} USDT")
            
            if not found_products:
                exit_with_error("未找到任何可赎回的USDT理财产品")
            
            # 检查赎回策略
            if total_available < target_amount:
                if total_available >= 20:
                    # 余额不足设置金额但>=20，赎回现有余额（取整）
                    actual_redeem_amount = int(total_available)  # 取整
                    print(f"⚠️ 可赎回金额({total_available} USDT)少于目标金额({target_amount} USDT)")
                    print(f"💡 余额大于等于20，将赎回现有余额: {actual_redeem_amount} USDT（已取整）")
                    redeem_info["target_amount"] = str(actual_redeem_amount)  # 更新目标金额
                    target_amount = actual_redeem_amount
                else:
                    print(f"⚠️ 可赎回金额({total_available} USDT)少于20 USDT，无法进行赎回")
                    exit_with_error(f"理财余额不足，需要至少20 USDT，当前仅有{total_available} USDT")
            else:
                # 余额充足，按配置金额赎回（取整）
                actual_redeem_amount = int(target_amount)
                print(f"✅ 余额充足，将按配置赎回: {actual_redeem_amount} USDT（已取整）")
                redeem_info["target_amount"] = str(actual_redeem_amount)
                target_amount = actual_redeem_amount
            
            # 按金额降序排序，优先赎回大额产品
            found_products.sort(key=lambda x: x["amount"], reverse=True)
            
            # 开始赎回流程
            redeemed_amount = 0
            for product in found_products:
                if redeemed_amount >= target_amount:
                    break
                
                print(f"\n🎯 赎回产品{product['index']}: {product['amount']} USDT")
                
                try:
                    # 点击Redeem按钮
                    redeem_button = product["redeem_button"]
                    if await redeem_button.is_visible() and await redeem_button.is_enabled():
                        await redeem_button.click()
                        await page.wait_for_timeout(200)
                        print("✅ 已点击Redeem按钮")
                        
                        # 等待赎回弹窗出现
                        await page.wait_for_timeout(200)
                        
                        # 查找赎回弹窗
                        print("🔍 查找赎回弹窗...")
                        redeem_modal = None
                        modal_selectors = [
                            '.ant-modal-content:has-text("Redeem")',
                            '.ant-modal:has-text("Redeem")',
                            '[data-testid="lux-modal"]:has-text("Amount")'
                        ]
                        
                        for modal_selector in modal_selectors:
                            try:
                                modal = page.locator(modal_selector).first
                                if await modal.is_visible(timeout=3000):
                                    redeem_modal = modal
                                    print(f"✅ 找到赎回弹窗: {modal_selector}")
                                    break
                            except:
                                continue
                        
                        if not redeem_modal:
                            print("⚠️ 未找到赎回弹窗，使用整个页面")
                            redeem_modal = page
                        
                        # 在弹窗中填写实际确定的赎回金额
                        print(f"💰 填写赎回金额: {target_amount} USDT...")
                        
                        # 查找金额输入框
                        amount_input_selectors = [
                            '.ant-input-affix-wrapper input[type="text"]',
                            '.ant-input[type="text"]',
                            'input[type="text"]',
                            '.ant-input'
                        ]
                        
                        amount_filled = False
                        for input_selector in amount_input_selectors:
                            try:
                                inputs = await redeem_modal.locator(input_selector).all()
                                print(f"  找到 {len(inputs)} 个输入框 ({input_selector})")
                                
                                for i, input_elem in enumerate(inputs):
                                    if await input_elem.is_visible():
                                        # 清空并填写实际金额
                                        await input_elem.clear()
                                        await input_elem.fill(str(target_amount))
                                        await page.wait_for_timeout(500)
                                        
                                        # 验证填写的值
                                        filled_value = await input_elem.input_value()
                                        print(f"  📝 输入框{i+1}: 填写值 = '{filled_value}'")
                                        
                                        if filled_value and filled_value == str(target_amount):
                                            print(f"✅ 成功填写赎回金额: {filled_value} USDT")
                                            amount_filled = True
                                            break
                                
                                if amount_filled:
                                    break
                            except Exception as e:
                                print(f"  ❌ 输入框选择器失败: {e}")
                                continue
                        
                        if not amount_filled:
                            print(f"❌ 无法填写赎回金额 {target_amount} USDT，跳过此产品")
                            continue
                        
                        # 等待一下让页面更新
                        await page.wait_for_timeout(200)
                        
                        # 查找并点击Confirm按钮
                        print("🚀 点击Confirm按钮...")
                        
                        confirm_selectors = [
                            'button:has-text("Confirm"):not([disabled])',
                            '.ant-btn-primary:has-text("Confirm"):not([disabled])',
                            'button.ant-btn-primary:not([disabled])'
                        ]
                        
                        confirmed = False
                        for selector in confirm_selectors:
                            try:
                                confirm_buttons = await redeem_modal.locator(selector).all()
                                print(f"  找到 {len(confirm_buttons)} 个Confirm按钮 ({selector})")
                                
                                for i, confirm_btn in enumerate(confirm_buttons):
                                    if await confirm_btn.is_visible():
                                        is_enabled = await confirm_btn.is_enabled()
                                        button_text = await confirm_btn.text_content()
                                        print(f"  📋 Confirm按钮{i+1}: '{button_text}', enabled={is_enabled}")
                                        
                                        if is_enabled:
                                            await confirm_btn.click()
                                            await page.wait_for_timeout(200)
                                            print("✅ 已点击Confirm按钮")
                                            confirmed = True
                                            break
                                
                                if confirmed:
                                    break
                            except Exception as e:
                                print(f"  ❌ Confirm按钮选择器失败: {e}")
                                continue
                        
                        if not confirmed:
                            print("❌ 无法点击Confirm按钮，可能按钮被禁用")
                            continue
                        
                        # 检测赎回成功弹窗
                        print("🔍 检测赎回成功弹窗...")
                        success_detected = False
                        
                        try:
                            # 等待成功弹窗出现
                            await page.wait_for_timeout(3000)
                            
                            # 查找成功弹窗的不同可能选择器
                            success_modal_selectors = [
                                'div[role="dialog"]:has-text("Redemption successful")',
                                '.moly-modal:has-text("Redemption successful")', 
                                'div:has-text("Redemption successful")',
                                '[class*="modal"]:has-text("successful")',
                                '[class*="result"]:has-text("successful")'
                            ]
                            
                            success_modal = None
                            for selector in success_modal_selectors:
                                try:
                                    modal = page.locator(selector).first
                                    if await modal.is_visible(timeout=2000):
                                        success_modal = modal
                                        print(f"✅ 检测到成功弹窗: {selector}")
                                        success_detected = True
                                        break
                                except:
                                    continue
                            
                            if success_detected and success_modal:
                                print("🎉 赎回成功弹窗已出现！")
                                
                                # 查找并点击关闭按钮
                                print("🔍 查找关闭按钮...")
                                close_button_selectors = [
                                    'svg[id="closeIcon"]',
                                    'button:has(svg[id="closeIcon"])',
                                    '.moly-iconbutton:has(svg)',
                                    'button[aria-label="Close"]',
                                    'div[role="dialog"] button:has(svg)',
                                    '.IconButton'
                                ]
                                
                                close_clicked = False
                                for close_selector in close_button_selectors:
                                    try:
                                        close_buttons = await success_modal.locator(close_selector).all()
                                        if not close_buttons:
                                            # 如果在modal内找不到，尝试在整个页面找
                                            close_buttons = await page.locator(close_selector).all()
                                        
                                        print(f"  找到 {len(close_buttons)} 个关闭按钮 ({close_selector})")
                                        
                                        for close_btn in close_buttons:
                                            if await close_btn.is_visible():
                                                await close_btn.click()
                                                await page.wait_for_timeout(1000)
                                                print("✅ 已点击关闭按钮")
                                                close_clicked = True
                                                break
                                        
                                        if close_clicked:
                                            break
                                    except Exception as e:
                                        print(f"  ❌ 关闭按钮选择器失败: {e}")
                                        continue
                                
                                if not close_clicked:
                                    print("⚠️ 无法自动关闭成功弹窗，尝试ESC键")
                                    await page.keyboard.press('Escape')
                                    await page.wait_for_timeout(1000)
                                
                                # 验证弹窗是否已关闭
                                try:
                                    if not await success_modal.is_visible(timeout=2000):
                                        print("✅ 成功弹窗已关闭")
                                    else:
                                        print("⚠️ 成功弹窗仍然显示")
                                except:
                                    print("✅ 成功弹窗已关闭")
                                
                            else:
                                print("⚠️ 未检测到明确的成功弹窗，但操作可能已成功")
                        
                        except Exception as e:
                            print(f"❌ 处理成功弹窗时出错: {e}")
                        
                        # 记录赎回的产品
                        redeem_info["redeemed_products"].append({
                            "index": product["index"],
                            "amount": float(target_amount),  # 使用实际赎回金额
                            "text": product["text"][:100],
                            "success_modal_detected": success_detected
                        })
                        
                        redeemed_amount += float(target_amount)  # 使用实际赎回金额
                        print(f"✅ 累计已赎回: {redeemed_amount} USDT")
                        
                        # 等待处理完成
                        await page.wait_for_timeout(200)
                        
                    else:
                        print("❌ Redeem按钮不可用")
                        
                except Exception as e:
                    print(f"❌ 赎回产品{product['index']}失败: {e}")
                    continue
            
            redeem_info["total_redeemed"] = redeemed_amount
            
            if redeemed_amount > 0:
                redeem_info["status"] = "success"
                print(f"\n🎉 赎回完成！总共赎回了 {redeemed_amount} USDT")
                
                # 保存实际赎回金额到文件，供双币投资使用
                try:
                    actual_amount_file = os.path.join(os.path.dirname(__file__), ".actual_investment_amount")
                    with open(actual_amount_file, 'w', encoding='utf-8') as f:
                        f.write(str(int(redeemed_amount)))  # 保存取整后的金额
                    print(f"💾 已保存实际投资金额: {int(redeemed_amount)} USDT")
                except Exception as e:
                    print(f"⚠️ 保存实际投资金额失败: {e}")
                
            else:
                redeem_info["status"] = "failed"
                exit_with_error("未能成功赎回任何USDT")
            
            print("\n✅ USDT赎回操作完成！")
            print("💡 现在可以进行双币投资了")
            print("🌐 浏览器将保持打开状态")
            
        except Exception as e:
            exit_with_error("执行过程中出现错误", e)

if __name__ == "__main__":
    print("💰 Bybit USDT自动赎回脚本")
    print("=" * 50)
    print("💡 操作流程：")
    print("   1️⃣ 导航到理财页面")
    print("   2️⃣ 查找可赎回的USDT产品")
    print("   3️⃣ 自动点击Redeem按钮")
    print("   4️⃣ 确认赎回操作")
    print("   5️⃣ 记录赎回详情")
    print("=" * 50)
    asyncio.run(main())
