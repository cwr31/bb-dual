#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的.env文件加载器
"""

import os
from logger_config import get_logger

# 初始化logger
logger = get_logger('load_env')

def load_env(env_file='config.env'):
    """加载.env文件中的环境变量"""
    if not os.path.exists(env_file):
        logger.warning(f"配置文件 {env_file} 不存在，使用默认配置")
        return
    
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 移除引号
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # 设置环境变量
                    os.environ[key] = value
                    logger.info(f"加载配置: {key} = {value}")
                else:
                    logger.warning(f"第{line_num}行格式错误: {line}")
        
        logger.info(f"配置文件 {env_file} 加载完成")
        
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")

# 获取配置值的便捷函数
def get_config(key, default=None):
    """获取配置值"""
    return os.getenv(key, default)

if __name__ == "__main__":
    load_env()
    print("\n🔧 当前配置:")
    print(f"💰 投资金额: {get_config('BYBIT_INVESTMENT_AMOUNT', '20')} {get_config('BYBIT_CURRENCY', 'USDT')}")
    print(f"📂 用户数据目录: {get_config('USER_DATA_DIR', 'default')}")
