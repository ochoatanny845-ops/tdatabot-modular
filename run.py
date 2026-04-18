#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TData Bot - 模块化版本入口
所有功能从原版tdata.py完整提取，保持100%逻辑不变
"""

# 导入完整的EnhancedBot类
from bot.main import EnhancedBot

if __name__ == '__main__':
    print("=" * 50)
    print("TData Bot - 模块化版本")
    print("100%原版功能，独立模块组织")
    print("=" * 50)
    
    # 运行Bot
    bot = EnhancedBot()
    bot.run()
