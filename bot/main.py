#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram账号检测机器人 - V8.0
群发通知完整版
"""

# 放在所有 import 附近（顶层，只执行一次）
import os
try:
    import argparse
    from dotenv import load_dotenv, find_dotenv
    
    # 支持 --config 参数指定配置文件
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=None, help='配置文件路径')
    args, unknown = parser.parse_known_args()
    
    # 优先用 --config，其次用环境变量，最后用默认 .env
    _ENV_FILE = args.config or os.getenv("ENV_FILE") or find_dotenv(".env", usecwd=True)
    load_dotenv(_ENV_FILE, override=True)
    print(f"[OK] .env loaded: {_ENV_FILE or 'None'}")
except Exception as e:
    print(f"[WARN] dotenv not used: {e}")
import sys
import sqlite3
import logging
import asyncio
import tempfile
import shutil
import zipfile
import json
import random
import string
import time
import re
import secrets
import csv
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, NamedTuple
from dataclasses import dataclass, field, asdict
from io import BytesIO
import threading
import struct
import base64
from pathlib import Path
from dataclasses import dataclass
from collections import deque, namedtuple

# 导入i18n模块用于多语言支持
try:
    from i18n import get_text as t, set_user_language, get_user_language
    I18N_AVAILABLE = True
    print("[OK] i18n module loaded successfully")
except ImportError:
    print("[WARN] i18n module not available, using Chinese only")
    I18N_AVAILABLE = False
    # Fallback functions if i18n is not available
    def t(user_id, key):
        return key
    def set_user_language(user_id, lang):
        pass
    def get_user_language(user_id):
        return 'zh'

# 定义北京时区常量
BEIJING_TZ = timezone(timedelta(hours=8))

# 冷却期判断阈值（6天23小时，单位：秒）
# Telegram密码重置冷却期为7天，如果剩余时间少于6天23小时，说明是已在冷却期
COOLDOWN_THRESHOLD_SECONDS = 6 * 24 * 3600 + 23 * 3600  # 604800秒 - 3600秒 = 604000秒

# 测试号码配置（用于检测通讯录限制）
# 注意：这些是实际注册的测试账号，用于检测目的
# 来源：需求文档中指定的测试号码
TEST_CONTACT_PHONES = [
    '+213540775893',
    '+254771625090'
]

# 通讯录限制检测配置
CONTACT_CHECK_MAX_CONCURRENT = 30  # 最大并发检测数
CONTACT_CHECK_DELAY_BETWEEN = 0.3  # 检测之间的延迟（秒）
SINGLE_ACCOUNT_TIMEOUT = 30  # 单个账号检测超时（秒）
BATCH_TIMEOUT = 30 * 60  # 批量检测总超时（秒）- 30分钟
UPDATE_INTERVAL = 5  # 进度消息更新间隔（秒）

# 一键清理功能配置
CLEANUP_UPDATE_INTERVAL = 10  # 一键清理进度刷新间隔（秒），改为10秒避免触发 Telegram 限流
TDATA_CONVERT_TIMEOUT = 30  # TData 转换超时（秒）
CLEANUP_SINGLE_ACCOUNT_TIMEOUT = 300  # 单个账号清理超时（秒），防止卡死
CLEANUP_OPERATION_TIMEOUT = 60  # 单个清理操作超时（秒），如删除联系人、退出群组等

# TData两阶段流水线配置
TDATA_PIPELINE_CONVERT_CONCURRENT = 50  # 阶段1：TData转Session并发数（纯本地操作）
TDATA_PIPELINE_CHECK_CONCURRENT = 50    # 阶段2：SpamBot检测并发数
TDATA_PIPELINE_CONVERT_TIMEOUT = 30     # 单个TData转换超时（秒）

# 进度更新配置（防止触发 Telegram 限流）
PROGRESS_UPDATE_INTERVAL = 10  # 进度更新最小间隔（秒）
PROGRESS_UPDATE_MIN_PERCENT = 2  # 最小百分比变化才更新（用于中等批量）
PROGRESS_UPDATE_MIN_PERCENT_LARGE = 5  # 大批量处理时的最小百分比变化
PROGRESS_LARGE_BATCH_THRESHOLD = 500  # 大批量阈值

# 通讯录限制检测状态常量
CONTACT_STATUS_NORMAL = 'normal'
CONTACT_STATUS_LIMITED = 'limited'
CONTACT_STATUS_BANNED = 'banned'
CONTACT_STATUS_ERROR = 'error'
CONTACT_STATUS_UNAUTHORIZED = 'unauthorized'

print("🔍 Telegram账号检测机器人 V8.0")
print(f"📅 当前时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}")

# ================================
# Python版本兼容性 - asyncio.to_thread
# ================================
# asyncio.to_thread在Python 3.9+才可用，为老版本提供兼容实现
import concurrent.futures

if not hasattr(asyncio, 'to_thread'):
    # Python < 3.9 兼容实现
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    
    async def _to_thread_compat(func, *args, **kwargs):
        """兼容Python < 3.9的asyncio.to_thread实现"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))
    
    asyncio.to_thread = _to_thread_compat
    print("[WARN] Python < 3.9 检测到，使用兼容的asyncio.to_thread实现")
else:
    print("[OK] Python 3.9+ 检测到，使用原生asyncio.to_thread")

# ================================
# Python版本兼容性 - asyncio.timeout
# ================================
# asyncio.timeout在Python 3.11+才可用，为老版本提供兼容实现
if not hasattr(asyncio, 'timeout'):
    # Python < 3.11 兼容实现
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def _timeout_compat(delay):
        """兼容Python < 3.11的asyncio.timeout实现
        
        使用asyncio.wait_for的异常处理机制来模拟timeout上下文管理器
        """
        # 创建一个Task来跟踪超时
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        
        # 用于标记是否是超时取消
        is_timeout = False
        
        def _timeout_callback():
            nonlocal is_timeout
            is_timeout = True
            if task and not task.done():
                task.cancel()
        
        # 设置超时
        timeout_handle = loop.call_later(delay, _timeout_callback) if delay is not None else None
        
        try:
            yield
        except asyncio.CancelledError:
            # 如果是超时导致的取消，转换为TimeoutError
            if is_timeout:
                raise asyncio.TimeoutError()
            # 否则重新抛出CancelledError
            raise
        finally:
            # 清理超时句柄
            if timeout_handle:
                timeout_handle.cancel()
    
    asyncio.timeout = _timeout_compat
    print("[WARN] Python < 3.11 检测到，使用兼容的asyncio.timeout实现")
else:
    print("[OK] Python 3.11+ 检测到，使用原生asyncio.timeout")

# ================================
# 日志配置
# ================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================
# 环境变量加载
# ================================

def load_environment():
    """加载.env文件"""
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_environment()

# ================================
# 必要库导入
# ================================

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, InputFile
    from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
    from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest
    print("[OK] telegram库导入成功")
except ImportError as e:
    print(f"[ERROR] telegram库导入失败: {e}")
    print("💡 请安装: pip install python-telegram-bot==13.15")
    sys.exit(1)

try:
    from telethon import TelegramClient, functions, types
    from telethon.errors import (
        FloodWaitError, SessionPasswordNeededError, RPCError,
        UserDeactivatedBanError, UserDeactivatedError, AuthKeyUnregisteredError,
        PhoneNumberBannedError, UserBannedInChannelError,
        PasswordHashInvalidError, PhoneCodeInvalidError, AuthRestartError,
        UsernameOccupiedError, UsernameInvalidError, PeerFloodError
    )
    from telethon.tl.types import User, CodeSettings, InputPhoneContact
    from telethon.tl.functions.messages import SendMessageRequest, GetHistoryRequest, GetPeerSettingsRequest
    from telethon.tl.functions.account import GetPasswordRequest, GetAuthorizationsRequest
    from telethon.tl.functions.auth import ResetAuthorizationsRequest, SendCodeRequest
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
    TELETHON_AVAILABLE = True
    print("[OK] telethon库导入成功")
    
    # 输出Telethon版本信息（用于调试和支持registration_month字段）
    import telethon
    if hasattr(telethon, '__version__'):
        version = telethon.__version__
        print(f"📌 Telethon 版本: {version}")
        # 建议更新到最新版本以支持 registration_month 字段 (Layer 214+)
        try:
            major, minor = map(int, version.split('.')[:2])
            if major < 1 or (major == 1 and minor < 34):
                print(f"💡 提示: 建议更新到 Telethon 1.34+ 以获得最新API支持")
        except:
            pass
    else:
        print("[WARN] 无法获取 Telethon 版本信息")
        
except ImportError:
    print("[ERROR] telethon未安装")
    print("💡 请安装: pip install telethon")
    TELETHON_AVAILABLE = False

# Define fallback exception classes for when imports fail
try:
    PasswordHashInvalidError
except NameError:
    class PasswordHashInvalidError(Exception):
        """Fallback class when telethon error not available"""
        pass

try:
    PhoneCodeInvalidError
except NameError:
    class PhoneCodeInvalidError(Exception):
        """Fallback class when telethon error not available"""
        pass

try:
    AuthRestartError
except NameError:
    class AuthRestartError(Exception):
        """Fallback class when telethon error not available"""
        pass

try:
    import socks
    PROXY_SUPPORT = True
    print("[OK] 代理支持库导入成功")
except ImportError:
    print("[WARN] 代理支持库未安装，将使用基础代理功能")
    PROXY_SUPPORT = False

try:
    from opentele.api import API, UseCurrentSession
    from opentele.td import TDesktop
    from opentele.tl import TelegramClient as OpenTeleClient
    OPENTELE_AVAILABLE = True
    print("[OK] opentele库导入成功")
except ImportError:
    print("[WARN] opentele未安装，格式转换功能不可用")
    print("💡 请安装: pip install opentele")
    OPENTELE_AVAILABLE = False

# Define fallback classes for when opentele is not available
if not OPENTELE_AVAILABLE:
    class TDesktop:
        """Fallback class when opentele not available"""
        pass
    
    class UseCurrentSession:
        """Fallback class when opentele not available"""
        pass

try:
    from account_classifier import AccountClassifier
    CLASSIFY_AVAILABLE = True
    print("[OK] 账号分类模块导入成功")
except Exception as e:
    CLASSIFY_AVAILABLE = False
    print(f"[WARN] 账号分类模块不可用: {e}")

try:
    import phonenumbers
    print("[OK] phonenumbers 导入成功")
except Exception:
    print("[WARN] 未安装 phonenumbers（账号国家识别将不可用）")
# Flask相关导入（新增或确认存在）
try:
    from flask import Flask, jsonify, request, render_template_string
    FLASK_AVAILABLE = True
    print("[OK] Flask库导入成功")
except ImportError:
    FLASK_AVAILABLE = False
    print("[ERROR] Flask未安装（验证码网页功能不可用）")

# ================================
# 数据结构定义
# ================================

@dataclass


class EnhancedBot:
    """Telegram Bot主类（核心方法）"""

    def __init__(self):
        print("🤖 初始化增强版机器人...")
        
        global config
        config = Config()
        if not config.validate():
            print("[ERROR] 配置验证失败")
            sys.exit(1)
        
        self.db = Database(config.DB_NAME)
        self.proxy_manager = ProxyManager(config.PROXY_FILE)
        self.proxy_tester = ProxyTester(self.proxy_manager)
        self.device_params_manager = DeviceParamsManager()  # 初始化设备参数管理器
        self.checker = SpamBotChecker(self.proxy_manager)
        self.processor = FileProcessor(self.checker, self.db)
        self.converter = FormatConverter(self.db)
        self.two_factor_manager = TwoFactorManager(self.proxy_manager, self.db)
        self.profile_manager = ProfileManager(self.proxy_manager, self.db)  # 初始化资料管理器
        import inspect
        print("DEBUG APIFormatConverter source:", inspect.getsourcefile(APIFormatConverter))
        print("DEBUG APIFormatConverter signature:", str(inspect.signature(APIFormatConverter)))
        # 初始化 API 格式转换器（带兜底，兼容无参老版本）
        try:
            # 首选：带参构造（新版本）
            self.api_converter = APIFormatConverter(self.db, base_url=config.BASE_URL)
        except TypeError as e:
            print(f"[WARN] APIFormatConverter 带参构造失败：{e}，切换到兼容模式（无参+手动注入）")
            self.api_converter = APIFormatConverter()   # 老版本：无参
            self.api_converter.db = self.db
            self.api_converter.base_url = config.BASE_URL


        # API转换待处理任务池：上传ZIP后先问网页展示的2FA，等待用户回复
        self.pending_api_tasks: Dict[int, Dict[str, Any]] = {}

        # 启动验证码接收服务器（Flask）
        try:
            self.api_converter.start_web_server()
        except Exception as e:
            print(f"[WARN] 验证码服务器启动失败: {e}")

        # 初始化账号分类器
        self.classifier = AccountClassifier() if CLASSIFY_AVAILABLE else None
        self.pending_classify_tasks: Dict[int, Dict[str, Any]] = {}
        
        # 广播消息待处理任务
        self.pending_broadcasts: Dict[int, Dict[str, Any]] = {}
        
        # 人工开通会员待处理任务
        self.pending_manual_open: Dict[int, int] = {}
        
        # 文件重命名待处理任务
        self.pending_rename: Dict[int, Dict[str, Any]] = {}
        
        # 账户合并待处理任务
        self.pending_merge: Dict[int, Dict[str, Any]] = {}
        
        # 添加2FA待处理任务
        self.pending_add_2fa_tasks: Dict[int, Dict[str, Any]] = {}
        
        # 一键清理待处理任务
        self.pending_cleanup: Dict[int, Dict[str, Any]] = {}
        
        # 批量创建待处理任务
        self.pending_batch_create: Dict[int, Dict[str, Any]] = {}
        
        # 重新授权待处理任务
        self.pending_reauthorize: Dict[int, Dict[str, Any]] = {}
        
        # 查询注册时间任务跟踪
        self.pending_registration_check: Dict[int, Dict[str, Any]] = {}
        
        # 资料修改待处理任务
        self.pending_profile_update: Dict[int, Dict[str, Any]] = {}
        
        # 通讯录限制检测待处理任务
        self.pending_contact_limit_check: Dict[int, Dict[str, Any]] = {}
        
        # 常量定义
        self.MAX_DISPLAY_ITEMS = 20  # 配置预览最大显示条目数
        self.ALERT_TEXT_MAX_LENGTH = 200  # 弹出提示最大文本长度
        
        # 初始化设备参数加载器
        self.device_loader = DeviceParamsLoader()
        
        # 初始化批量创建服务
        if config.ENABLE_BATCH_CREATE:
            try:
                self.batch_creator = BatchCreatorService(self.db, self.proxy_manager, self.device_loader, config)
                print("[OK] 批量创建服务初始化成功")
            except Exception as e:
                print(f"[WARN] 批量创建服务初始化失败: {e}")
                self.batch_creator = None
        else:
            self.batch_creator = None

        self.updater = Updater(config.TOKEN, use_context=True)
        self.dp = self.updater.dispatcher
        
        self.setup_handlers()
        
        print("[OK] 增强版机器人初始化完成")
    

    def run(self):
        print("🚀 启动增强版机器人（速度优化版）...")
        print(f"📡 代理模式: {'启用' if config.USE_PROXY else '禁用'}")
        print(f"🔢 可用代理: {len(self.proxy_manager.proxies)}个")
        print(f"[*] 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}")
        print(f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT if config.PROXY_FAST_MODE else config.MAX_CONCURRENT_CHECKS}个")
        print(f"⏱️ 检测超时: {config.PROXY_CHECK_TIMEOUT if config.PROXY_FAST_MODE else config.CHECK_TIMEOUT}秒")
        print(f"🔄 智能重试: {config.PROXY_RETRY_COUNT}次")
        print(f"🧹 自动清理: {'启用' if config.PROXY_AUTO_CLEANUP else '禁用'}")
        print("[OK] 管理员系统: 启用")
        print("[OK] 速度优化: 预计提升3-5倍")
        print("🛑 按 Ctrl+C 停止机器人")
        print("-" * 50)
        
        try:
            self.updater.start_polling()
            self.updater.idle()
        except KeyboardInterrupt:
            print("\n👋 机器人已停止")
        except Exception as e:
            print(f"\n[ERROR] 运行错误: {e}")


