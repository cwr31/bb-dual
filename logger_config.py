#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的日志配置模块
为整个项目提供一致的日志设置
"""

import logging
import os
import sys
from datetime import datetime


def setup_logger(name=None, log_level='INFO'):
    """
    设置并返回logger实例
    
    Args:
        name: logger名称，如果为None则使用调用模块的名称
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        logger: 配置好的logger实例
    """
    
    # 如果没有指定名称，使用调用者的模块名
    if name is None:
        frame = sys._getframe(1)
        name = frame.f_globals.get('__name__', 'unknown')
    
    # 创建logger
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 设置日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 创建日志目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 创建格式器
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # 创建文件处理器
    log_filename = f"{log_dir}/bybit_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # 添加处理器到logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name=None):
    """
    获取logger实例的便捷函数
    
    Args:
        name: logger名称
    
    Returns:
        logger: logger实例
    """
    return setup_logger(name)


# 为常用模块预创建logger
def create_module_loggers():
    """为项目中的主要模块创建logger"""
    modules = [
        'scheduler',
        'redeem_usdt', 
        'dual_buy',
        'complete_flow',
        'load_env'
    ]
    
    loggers = {}
    for module in modules:
        loggers[module] = setup_logger(module)
    
    return loggers


# 日志级别映射，用于兼容原有的print格式
LOG_LEVEL_MAP = {
    '[OK]': 'INFO',
    '[SUCCESS]': 'INFO', 
    '[COMPLETE]': 'INFO',
    '[START]': 'INFO',
    '[PHASE1]': 'INFO',
    '[PHASE2]': 'INFO',
    '[PATH]': 'DEBUG',
    '[NOTIFICATION]': 'INFO',
    '[IMMEDIATE]': 'INFO',
    '[INTERVAL]': 'INFO',
    '[TASK]': 'INFO',
    '[BROWSER]': 'INFO',
    '[SCHEDULER]': 'INFO',
    '[WARN]': 'WARNING',
    '[WARNING]': 'WARNING',
    '[ERROR]': 'ERROR',
    '[TRACE]': 'ERROR',
    '[STOP]': 'INFO',
    '✅': 'INFO',
    '🎉': 'INFO', 
    '🚀': 'INFO',
    '📊': 'INFO',
    '💰': 'INFO',
    '🌐': 'INFO',
    '⚠️': 'WARNING',
    '❌': 'ERROR',
    '🔍': 'DEBUG',
    '📱': 'INFO',
    '💾': 'INFO'
}


def log_with_emoji(logger, message, level='INFO'):
    """
    根据消息中的emoji或标签确定日志级别
    
    Args:
        logger: logger实例
        message: 日志消息
        level: 默认日志级别
    """
    # 检查消息开头是否有已知的标签或emoji
    for prefix, log_level in LOG_LEVEL_MAP.items():
        if message.startswith(prefix):
            level = log_level
            # 移除标签前缀，保留消息内容
            if prefix.startswith('[') and prefix.endswith(']'):
                message = message[len(prefix):].strip()
            break
    
    # 根据级别记录日志
    level_method = getattr(logger, level.lower(), logger.info)
    level_method(message)


if __name__ == "__main__":
    # 测试日志配置
    test_logger = get_logger('test')
    test_logger.info("日志系统初始化完成")
    test_logger.debug("这是调试信息")
    test_logger.warning("这是警告信息")
    test_logger.error("这是错误信息")
