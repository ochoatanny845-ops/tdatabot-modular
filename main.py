#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TData Bot - 模块化入口
保持原版tdata.py所有功能，只重新组织结构
"""

# 1. 首先导入原版tdata.py的所有内容
import sys
from pathlib import Path

# 添加原版代码目录到路径
original_dir = Path(__file__).parent / 'original'
sys.path.insert(0, str(original_dir))

# 导入原版tdata.py的主类
from tdata import EnhancedBot

# 2. 直接运行原版Bot
if __name__ == '__main__':
    # 使用原版EnhancedBot
    bot = EnhancedBot()
    bot.run()
