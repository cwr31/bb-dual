#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit自动化定时任务调度器
每30分钟执行一次complete_flow.py
"""

import asyncio
import schedule
import time
import sys
import traceback
from datetime import datetime
import os

# 加载.env配置文件
from load_env import load_env, get_config
from logger_config import get_logger

# 直接导入业务模块
import redeem_usdt
import dual_buy

# 初始化logger
logger = get_logger('scheduler')

load_env()

# 配置项
TELEGRAM_BOT_TOKEN = get_config('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = get_config('TELEGRAM_CHAT_ID', '')
SCHEDULE_INTERVAL = int(get_config('SCHEDULE_INTERVAL_MINUTES', '30'))

def send_telegram_message(message):
    """发送Telegram通知"""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            logger.info("Telegram通知发送成功")
            return True
        else:
            logger.warning(f"Telegram通知发送失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"发送Telegram通知时出错: {e}")
        return False

async def run_complete_flow():
    """执行完整流程"""
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info("="*60)
        logger.info(f"开始执行定时任务 - {current_time}")
        logger.info("="*60)
        
        # 第一阶段：赎回USDT
        logger.info("第一阶段：执行USDT赎回...")
        redeem_result = {}
        try:
            await redeem_usdt.main()
            redeem_result = redeem_usdt.redeem_info.copy()
            logger.info("USDT赎回完成")
        except Exception as e:
            logger.error(f"USDT赎回失败: {e}")
            logger.error(f"赎回异常详情:\n{traceback.format_exc()}")
            redeem_result = {"status": "failed", "error": str(e)}
        
        # 无论第一阶段是否成功，都继续执行第二阶段
        # 第二阶段：双币投资
        logger.info("第二阶段：执行双币投资...")
        purchase_result = {}
        try:
            await dual_buy.main()
            purchase_result = dual_buy.purchase_info.copy()
            logger.info("双币投资完成")
        except Exception as e:
            logger.error(f"双币投资失败: {e}")
            logger.error(f"投资异常详情:\n{traceback.format_exc()}")
            purchase_result = {"status": "failed", "error": str(e)}
        
        # 发送综合通知
        end_time = datetime.now()
        start_time_obj = datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')
        duration = end_time - start_time_obj
        
        logger.info("发送综合流程通知...")
        
        # 构建综合通知消息
        telegram_message = f"""🎉 *Bybit完整自动化流程执行完成！*

⏱️ *总耗时:* {duration.total_seconds():.1f} 秒

📊 *第一阶段 - USDT赎回:*"""
        
        if redeem_result and redeem_result.get('status') == 'success':
            telegram_message += f"""
⏰ 赎回时间: {redeem_result.get('timestamp', 'N/A')}
💵 总赎回金额: {redeem_result.get('total_redeemed', 0)} USDT
🎯 目标金额: {redeem_result.get('target_amount', 'N/A')} USDT
📊 赎回产品数量: {redeem_result.get('redeemed_count', len(redeem_result.get('redeemed_products', [])))}"""
        else:
            error_info = redeem_result.get('error', '未知错误')
            telegram_message += f"\n❌ 赎回失败: {error_info}"

        telegram_message += f"""

🎯 *第二阶段 - 双币投资:*"""
        
        if purchase_result and purchase_result.get('status') == 'success':
            selected = purchase_result.get('selected_product', {})
            telegram_message += f"""
⏰ 申购时间: {purchase_result.get('timestamp', 'N/A')}
💰 投资金额: {purchase_result.get('investment_amount', 'N/A')} {purchase_result.get('currency', 'USDT')}
📈 产品类型: {purchase_result.get('product_type', 'N/A')}

🎯 选中产品信息:
📍 目标价格: {selected.get('target_price', 'N/A')}
⏳ 投资期限: {selected.get('duration', 'N/A')}
📈 年化收益率: {selected.get('apr', 'N/A')}
📅 结算日期: {selected.get('settlement_date', 'N/A')}"""
        else:
            error_info = purchase_result.get('error', '未知错误')
            telegram_message += f"\n❌ 申购失败: {error_info}"

        # 判断整体状态
        overall_success = (redeem_result.get('status') == 'success' and 
                          purchase_result.get('status') == 'success')
        
        if overall_success:
            telegram_message += "\n\n✅ *完整流程已成功完成！*"
        else:
            telegram_message += "\n\n⚠️ *流程部分失败，请检查详细信息*"
        
        # 发送通知
        try:
            send_telegram_message(telegram_message)
        except Exception as notify_error:
            logger.error(f"发送综合通知失败: {notify_error}")
        
        logger.info(f"定时任务完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        logger.error(f"定时任务执行出错: {str(e)}")
        logger.error(f"错误详情:\n{traceback.format_exc()}")
        
        # 发送错误通知
        try:
            telegram_message = f"""🚫 *定时任务执行异常*

⏰ *异常时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
❌ *异常信息:* {str(e)}

⏭️ 调度器仍在运行，将在下次计划时间继续执行任务。
请检查程序日志获取详细信息。"""
            
            send_telegram_message(telegram_message)
        except Exception as notify_error:
            logger.error(f"发送错误通知失败: {notify_error}")

def main():
    """主函数"""
    logger.info("Bybit自动化定时任务调度器启动")
    logger.info(f"执行频率：每{SCHEDULE_INTERVAL}分钟")
    logger.info("执行任务：complete_flow.py")
    logger.info("浏览器模式：后台窗口")
    logger.info(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    
    # 发送启动通知
    start_message = f"""🕒 *Bybit定时任务调度器已启动*

⏰ *启动时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📋 *执行频率:* 每{SCHEDULE_INTERVAL}分钟
🎯 *执行任务:* 完整流程（赎回+申购）
🌐 *浏览器模式:* 后台窗口
🚀 *执行模式:* 启动时立即执行一次，然后定时运行

定时任务已开始运行，将自动执行Bybit操作。"""
    
    send_telegram_message(start_message)
    
    # 包装async函数为同步函数
    def run_async_task():
        """同步包装器，用于schedule调用"""
        try:
            logger.info("开始执行定时任务...")
            asyncio.run(run_complete_flow())
            logger.info("定时任务执行完成")
        except Exception as e:
            logger.error(f"定时任务执行失败: {e}")
            logger.error(f"错误详情:\n{traceback.format_exc()}")
            
            # 发送任务失败通知
            error_message = f"""⚠️ *定时任务执行失败*

⏰ *失败时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
❌ *错误信息:* {str(e)}

⏭️ 调度器仍在运行，将在下次计划时间继续执行任务。
📋 下次执行时间: {SCHEDULE_INTERVAL}分钟后"""
            
            try:
                send_telegram_message(error_message)
            except Exception as notify_error:
                logger.error(f"发送错误通知失败: {notify_error}")
        
        # 确保函数总是正常返回，不抛出异常
    
    # 设置定时任务：根据配置文件设置间隔
    schedule.every(SCHEDULE_INTERVAL).minutes.do(run_async_task)
    
    # 启动时立即执行一次
    logger.info("启动时立即执行一次任务...")
    run_async_task()
    
    try:
        logger.info("调度器主循环开始运行...")
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                # 捕获调度器运行中的任何异常，但不停止调度器
                logger.error(f"调度器循环中出现异常: {e}")
                logger.error(f"异常详情:\n{traceback.format_exc()}")
                
                # 发送异常通知但继续运行
                try:
                    exception_message = f"""⚠️ *调度器运行中遇到异常*

⏰ *异常时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
❌ *异常信息:* {str(e)}

🔄 调度器将继续运行，请监控后续执行情况。"""
                    
                    send_telegram_message(exception_message)
                except Exception as notify_error:
                    logger.error(f"发送调度器异常通知失败: {notify_error}")
                
                # 等待一段时间后继续
                logger.info("等待60秒后继续调度器运行...")
                time.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止定时任务...")
        
        # 发送停止通知
        try:
            stop_message = f"""🛑 *Bybit定时任务调度器已停止*

⏰ *停止时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📋 *停止原因:* 用户手动停止

定时任务已停止运行。"""
            
            send_telegram_message(stop_message)
        except Exception as notify_error:
            logger.error(f"发送停止通知失败: {notify_error}")
        
        sys.exit(0)
        
    except Exception as e:
        # 只有在极严重的系统级错误时才停止调度器
        logger.critical(f"调度器遇到严重系统异常，必须停止: {str(e)}")
        logger.critical(f"异常详情:\n{traceback.format_exc()}")
        
        # 发送严重异常通知
        try:
            critical_message = f"""🚨 *定时任务调度器严重异常*

⏰ *异常时间:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
❌ *严重异常:* {str(e)}

🚫 调度器已停止运行，请立即检查并重新启动。"""
            
            send_telegram_message(critical_message)
        except Exception as notify_error:
            logger.error(f"发送严重异常通知失败: {notify_error}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()
