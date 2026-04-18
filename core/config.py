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
    print(f"✅ .env loaded: {_ENV_FILE or 'None'}")
except Exception as e:
    print(f"⚠️ dotenv not used: {e}")
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
    print("✅ i18n module loaded successfully")
except ImportError:
    print("⚠️ i18n module not available, using Chinese only")
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
    print("⚠️ Python < 3.9 检测到，使用兼容的asyncio.to_thread实现")
else:
    print("✅ Python 3.9+ 检测到，使用原生asyncio.to_thread")

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
    print("⚠️ Python < 3.11 检测到，使用兼容的asyncio.timeout实现")
else:
    print("✅ Python 3.11+ 检测到，使用原生asyncio.timeout")

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
    print("✅ telegram库导入成功")
except ImportError as e:
    print(f"❌ telegram库导入失败: {e}")
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
    print("✅ telethon库导入成功")
    
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
        print("⚠️ 无法获取 Telethon 版本信息")
        
except ImportError:
    print("❌ telethon未安装")
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
    print("✅ 代理支持库导入成功")
except ImportError:
    print("⚠️ 代理支持库未安装，将使用基础代理功能")
    PROXY_SUPPORT = False

try:
    from opentele.api import API, UseCurrentSession
    from opentele.td import TDesktop
    from opentele.tl import TelegramClient as OpenTeleClient
    OPENTELE_AVAILABLE = True
    print("✅ opentele库导入成功")
except ImportError:
    print("⚠️ opentele未安装，格式转换功能不可用")
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
    print("✅ 账号分类模块导入成功")
except Exception as e:
    CLASSIFY_AVAILABLE = False
    print(f"⚠️ 账号分类模块不可用: {e}")

try:
    import phonenumbers
    print("✅ phonenumbers 导入成功")
except Exception:
    print("⚠️ 未安装 phonenumbers（账号国家识别将不可用）")
# Flask相关导入（新增或确认存在）
try:
    from flask import Flask, jsonify, request, render_template_string
    FLASK_AVAILABLE = True
    print("✅ Flask库导入成功")
except ImportError:
    FLASK_AVAILABLE = False
    print("❌ Flask未安装（验证码网页功能不可用）")

# ================================
# 数据结构定义
# ================================

@dataclass

class Config:
    def __init__(self):
        self.TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
        self.API_ID = int(os.getenv("API_ID", "0"))
        # Ensure API_HASH is always a string to prevent TypeError in Telethon
        self.API_HASH = str(os.getenv("API_HASH", ""))
        
        admin_ids = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = []
        if admin_ids:
            try:
                self.ADMIN_IDS = [int(x.strip()) for x in admin_ids.split(",") if x.strip()]
            except:
                pass
        
        self.TRIAL_DURATION = int(os.getenv("TRIAL_DURATION", "30"))
        self.TRIAL_DURATION_UNIT = os.getenv("TRIAL_DURATION_UNIT", "minutes")
        
        if self.TRIAL_DURATION_UNIT == "minutes":
            self.TRIAL_DURATION_SECONDS = self.TRIAL_DURATION * 60
        else:
            self.TRIAL_DURATION_SECONDS = self.TRIAL_DURATION
        
        self.DB_NAME = "bot_data.db"
        self.MAX_CONCURRENT_CHECKS = int(os.getenv("MAX_CONCURRENT_CHECKS", "20"))
        self.CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", "15"))
        self.SPAMBOT_WAIT_TIME = float(os.getenv("SPAMBOT_WAIT_TIME", "2.0"))
        
        # 账号处理速度优化配置（带验证）
        self.MAX_CONCURRENT = max(1, min(50, int(os.getenv("MAX_CONCURRENT", "15"))))  # 限制在1-50之间
        self.DELAY_BETWEEN_ACCOUNTS = max(0.1, min(10.0, float(os.getenv("DELAY_BETWEEN_ACCOUNTS", "0.3"))))  # 限制在0.1-10秒之间
        self.CONNECTION_TIMEOUT = max(5, min(60, int(os.getenv("CONNECTION_TIMEOUT", "10"))))  # 限制在5-60秒之间
        
        # 代理配置
        self.USE_PROXY = os.getenv("USE_PROXY", "true").lower() == "true"
        self.PROXY_TIMEOUT = int(os.getenv("PROXY_TIMEOUT", "10"))
        self.PROXY_FILE = os.getenv("PROXY_FILE", "proxy.txt")
        
        # 住宅代理配置
        self.RESIDENTIAL_PROXY_TIMEOUT = int(os.getenv("RESIDENTIAL_PROXY_TIMEOUT", "30"))
        self.RESIDENTIAL_PROXY_PATTERNS = os.getenv(
            "RESIDENTIAL_PROXY_PATTERNS", 
            "abcproxy,residential,resi,mobile"
        ).split(",")
                # 新增：对外访问的基础地址，用于生成验证码网页链接
        # 例如: http://45.147.196.113:5000 或 https://your.domain
        self.BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
        ...
        print(f"🌐 验证码网页 BASE_URL: {self.BASE_URL}")
        # 新增速度优化配置
        self.PROXY_CHECK_CONCURRENT = int(os.getenv("PROXY_CHECK_CONCURRENT", "100"))
        self.PROXY_CHECK_TIMEOUT = int(os.getenv("PROXY_CHECK_TIMEOUT", "3"))
        self.PROXY_AUTO_CLEANUP = os.getenv("PROXY_AUTO_CLEANUP", "true").lower() == "true"
        self.PROXY_FAST_MODE = os.getenv("PROXY_FAST_MODE", "true").lower() == "true"
        self.PROXY_RETRY_COUNT = int(os.getenv("PROXY_RETRY_COUNT", "2"))
        self.PROXY_BATCH_SIZE = int(os.getenv("PROXY_BATCH_SIZE", "100"))
        self.PROXY_USAGE_LOG_LIMIT = int(os.getenv("PROXY_USAGE_LOG_LIMIT", "500"))
        self.PROXY_ROTATE_RETRIES = int(os.getenv("PROXY_ROTATE_RETRIES", "2"))
        self.PROXY_SHOW_FAILURE_REASON = os.getenv("PROXY_SHOW_FAILURE_REASON", "true").lower() == "true"
        self.PROXY_DEBUG_VERBOSE = os.getenv("PROXY_DEBUG_VERBOSE", "false").lower() == "true"
        
        
        # 忘记2FA批量处理速度优化配置
        self.FORGET2FA_CONCURRENT = int(os.getenv("FORGET2FA_CONCURRENT", "50"))  # 并发数50（高速处理）
        self.FORGET2FA_MIN_DELAY = float(os.getenv("FORGET2FA_MIN_DELAY", "3.0"))  # 批次间最小延迟3秒
        self.FORGET2FA_MAX_DELAY = float(os.getenv("FORGET2FA_MAX_DELAY", "6.0"))  # 批次间最大延迟6秒
        self.FORGET2FA_NOTIFY_WAIT = float(os.getenv("FORGET2FA_NOTIFY_WAIT", "0.5"))  # 等待通知到达的时间（秒）
        self.FORGET2FA_MAX_PROXY_RETRIES = int(os.getenv("FORGET2FA_MAX_PROXY_RETRIES", "3"))  # 代理重试次数3次
        self.FORGET2FA_PROXY_TIMEOUT = int(os.getenv("FORGET2FA_PROXY_TIMEOUT", "10"))  # 代理超时时间10秒
        self.FORGET2FA_DEFAULT_COUNTRY_PREFIX = os.getenv("FORGET2FA_DEFAULT_COUNTRY_PREFIX", "+62")  # 默认国家前缀
        
        # API格式转换器和验证码服务器配置
        self.WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8080"))
        self.ALLOW_PORT_SHIFT = os.getenv("ALLOW_PORT_SHIFT", "true").lower() == "true"
        
        # 一键清理功能配置
        self.ENABLE_ONE_CLICK_CLEANUP = os.getenv("ENABLE_ONE_CLICK_CLEANUP", "true").lower() == "true"
        self.CLEANUP_ACCOUNT_CONCURRENCY = int(os.getenv("CLEANUP_ACCOUNT_CONCURRENCY", "30"))  # 同时处理的账户数（改为30）
        self.CLEANUP_LEAVE_CONCURRENCY = int(os.getenv("CLEANUP_LEAVE_CONCURRENCY", "3"))
        self.CLEANUP_DELETE_HISTORY_CONCURRENCY = int(os.getenv("CLEANUP_DELETE_HISTORY_CONCURRENCY", "2"))
        self.CLEANUP_DELETE_CONTACTS_CONCURRENCY = int(os.getenv("CLEANUP_DELETE_CONTACTS_CONCURRENCY", "3"))
        self.CLEANUP_ACTION_SLEEP = float(os.getenv("CLEANUP_ACTION_SLEEP", "0.3"))
        self.CLEANUP_MIN_PEER_INTERVAL = float(os.getenv("CLEANUP_MIN_PEER_INTERVAL", "1.5"))
        self.CLEANUP_REVOKE_DEFAULT = os.getenv("CLEANUP_REVOKE_DEFAULT", "true").lower() == "true"
        
        # 批量创建功能配置
        self.ENABLE_BATCH_CREATE = os.getenv("ENABLE_BATCH_CREATE", "true").lower() == "true"
        self.BATCH_CREATE_DAILY_LIMIT = int(os.getenv("BATCH_CREATE_DAILY_LIMIT", "10"))  # 每个账号每日创建上限
        self.BATCH_CREATE_CONCURRENT = int(os.getenv("BATCH_CREATE_CONCURRENT", "10"))  # 同时处理的账户数
        
        # 重新授权功能配置
        self.ENABLE_REAUTHORIZE = os.getenv("ENABLE_REAUTHORIZE", "true").lower() == "true"
        self.REAUTH_CONCURRENT = int(os.getenv("REAUTH_CONCURRENT", "30"))  # 同时处理的账户数（默认30）
        self.REAUTH_USE_RANDOM_DEVICE = os.getenv("REAUTH_USE_RANDOM_DEVICE", "true").lower() == "true"  # 使用随机设备参数
        self.REAUTH_FORCE_PROXY = os.getenv("REAUTH_FORCE_PROXY", "true").lower() == "true"  # 强制使用代理
        self.BATCH_CREATE_MIN_INTERVAL = int(os.getenv("BATCH_CREATE_MIN_INTERVAL", "60"))  # 创建间隔最小秒数
        self.BATCH_CREATE_MAX_INTERVAL = int(os.getenv("BATCH_CREATE_MAX_INTERVAL", "120"))  # 创建间隔最大秒数
        self.BATCH_CREATE_MAX_FLOOD_WAIT = int(os.getenv("BATCH_CREATE_MAX_FLOOD_WAIT", "60"))  # 最大可接受的flood等待时间（秒）
        
        # 获取当前脚本目录
        self.SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        
        # 文件管理配置
        self.RESULTS_DIR = os.getenv("RESULTS_DIR") or os.path.join(self. SCRIPT_DIR, "results")
        self.UPLOADS_DIR = os.getenv("UPLOAD_DIR") or os.path.join(self.SCRIPT_DIR, "uploads")
        self.CLEANUP_REPORTS_DIR = os. path.join(self.RESULTS_DIR, "cleanup_reports")

        # Session文件目录结构
        # sessions:  存放用户上传的session文件
        # sessions/sessions_bak: 存放临时处理文件
        self.SESSIONS_DIR = os. getenv("SESSION_DIR") or os.path.join(self. SCRIPT_DIR, "sessions")
        self.SESSIONS_BAK_DIR = os.path. join(self.SESSIONS_DIR, "sessions_bak")
        # 创建目录
        os.makedirs(self.RESULTS_DIR, exist_ok=True)
        os.makedirs(self.UPLOADS_DIR, exist_ok=True)
        os.makedirs(self.CLEANUP_REPORTS_DIR, exist_ok=True)
        os.makedirs(self.SESSIONS_DIR, exist_ok=True)
        os.makedirs(self.SESSIONS_BAK_DIR, exist_ok=True)
        
        print(f"📁 上传目录: {self.UPLOADS_DIR}")
        print(f"📁 结果目录: {self.RESULTS_DIR}")
        print(f"📁 清理报告目录: {self.CLEANUP_REPORTS_DIR}")
        print(f"📁 Session目录: {self.SESSIONS_DIR}")
        print(f"📁 临时文件目录: {self.SESSIONS_BAK_DIR}")
        print(f"📡 系统配置: USE_PROXY={'true' if self.USE_PROXY else 'false'}")
        print(f"🧹 一键清理: {'启用' if self.ENABLE_ONE_CLICK_CLEANUP else '禁用'}")
        print(f"📦 批量创建: {'启用' if self.ENABLE_BATCH_CREATE else '禁用'}，每日限制: {self.BATCH_CREATE_DAILY_LIMIT}")
        print(f"⏱️ 创建间隔: {self.BATCH_CREATE_MIN_INTERVAL}-{self.BATCH_CREATE_MAX_INTERVAL}秒（避免频率限制）")
        print(f"🔄 重新授权: {'启用' if self.ENABLE_REAUTHORIZE else '禁用'}，并发数: {self.REAUTH_CONCURRENT}，随机设备: {'开启' if self.REAUTH_USE_RANDOM_DEVICE else '关闭'}，强制代理: {'开启' if self.REAUTH_FORCE_PROXY else '关闭'}")
        print(f"💡 注意: 实际代理模式需要配置文件+数据库开关+有效代理文件同时满足")
    
    def validate(self):
        if not self.TOKEN or not self.API_ID or not self.API_HASH:
            self.create_env_file()
            return False
        return True
    
    def create_env_file(self):
        if not os.path.exists(".env"):
            env_content = """TOKEN=YOUR_BOT_TOKEN_HERE
API_ID=YOUR_API_ID_HERE
API_HASH=YOUR_API_HASH_HERE
ADMIN_IDS=123456789
TRIAL_DURATION=30
TRIAL_DURATION_UNIT=minutes
MAX_CONCURRENT_CHECKS=20
CHECK_TIMEOUT=15
SPAMBOT_WAIT_TIME=2.0
# 账号处理速度优化配置
MAX_CONCURRENT=15  # 并发账号处理数：从3提高到15
DELAY_BETWEEN_ACCOUNTS=0.3  # 账号间隔：从2秒减少到0.3秒
CONNECTION_TIMEOUT=10  # 连接超时：从30秒减少到10秒
USE_PROXY=true
PROXY_TIMEOUT=10
PROXY_FILE=proxy.txt
RESIDENTIAL_PROXY_TIMEOUT=30
RESIDENTIAL_PROXY_PATTERNS=abcproxy,residential,resi,mobile
PROXY_CHECK_CONCURRENT=100
PROXY_CHECK_TIMEOUT=3
PROXY_AUTO_CLEANUP=true
PROXY_FAST_MODE=true
PROXY_RETRY_COUNT=2
PROXY_BATCH_SIZE=100
PROXY_ROTATE_RETRIES=2
PROXY_SHOW_FAILURE_REASON=true
PROXY_USAGE_LOG_LIMIT=500
PROXY_DEBUG_VERBOSE=false
BASE_URL=http://127.0.0.1:5000
# 忘记2FA批量处理速度优化配置
FORGET2FA_CONCURRENT=50
FORGET2FA_MIN_DELAY=3.0
FORGET2FA_MAX_DELAY=6.0
FORGET2FA_NOTIFY_WAIT=0.5
FORGET2FA_MAX_PROXY_RETRIES=3
FORGET2FA_PROXY_TIMEOUT=10
FORGET2FA_DEFAULT_COUNTRY_PREFIX=+62
# API格式转换器和验证码服务器配置
WEB_SERVER_PORT=8080
ALLOW_PORT_SHIFT=true
# 一键清理功能配置
ENABLE_ONE_CLICK_CLEANUP=true
CLEANUP_ACCOUNT_CONCURRENCY=3  # 同时处理的账户数量（提升清理速度）
CLEANUP_LEAVE_CONCURRENCY=3
CLEANUP_DELETE_HISTORY_CONCURRENCY=2
CLEANUP_DELETE_CONTACTS_CONCURRENCY=3
CLEANUP_ACTION_SLEEP=0.3
CLEANUP_MIN_PEER_INTERVAL=1.5
CLEANUP_REVOKE_DEFAULT=true
# 批量创建功能配置
ENABLE_BATCH_CREATE=true
BATCH_CREATE_DAILY_LIMIT=10  # 每个账号每日创建上限
BATCH_CREATE_CONCURRENT=10  # 同时处理的账户数
BATCH_CREATE_MIN_INTERVAL=60  # 创建间隔最小秒数（每个账号内）
BATCH_CREATE_MAX_INTERVAL=120  # 创建间隔最大秒数（每个账号内）
BATCH_CREATE_MAX_FLOOD_WAIT=60  # 最大可接受的flood等待时间（秒）
# 重新授权功能配置
ENABLE_REAUTHORIZE=true
REAUTH_CONCURRENT=30  # 同时处理的账户数（默认30）
REAUTH_USE_RANDOM_DEVICE=true  # 使用随机设备参数
REAUTH_FORCE_PROXY=true  # 强制使用代理
"""
            with open(".env", "w", encoding="utf-8") as f:
                f.write(env_content)
            print("✅ 已创建.env配置文件，请填入正确的配置信息")

# ================================
# Proxy Usage Tracking
# ================================

@dataclass

