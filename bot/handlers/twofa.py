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

class TwoFactorManager:
    """二级密码管理器 - 批量修改2FA密码"""
    
    # 配置常量 - 并发处理数量
    DEFAULT_CONCURRENT_LIMIT = 50  # 默认并发数限制，提升批量处理速度
    
    def __init__(self, proxy_manager: ProxyManager, db: Database):
        self.proxy_manager = proxy_manager
        self.db = db
        self.password_detector = PasswordDetector()
        self.semaphore = asyncio.Semaphore(self.DEFAULT_CONCURRENT_LIMIT)  # 使用配置的并发数
        # 用于存储待处理的2FA任务
        self.pending_2fa_tasks = {}  # {user_id: {'files': [...], 'file_type': '...', 'extract_dir': '...', 'task_id': '...'}}
    
    async def change_2fa_password(self, session_path: str, old_password: str, new_password: str, 
                                  account_name: str, user_id: int = None) -> Tuple[bool, str]:
        """
        修改单个账号的2FA密码
        
        Args:
            session_path: Session文件路径
            old_password: 旧密码
            new_password: 新密码
            account_name: 账号名称（用于日志）
            user_id: 用户ID（用于翻译）
            
        Returns:
            (是否成功, 详细信息)
        """
        if not TELETHON_AVAILABLE:
            return False, "Telethon未安装"
        
        async with self.semaphore:
            client = None
            proxy_dict = None
            proxy_used = "本地连接"
            
            try:
                # 尝试使用代理
                proxy_enabled = self.db.get_proxy_enabled() if self.db else True
                if config.USE_PROXY and proxy_enabled and self.proxy_manager.proxies:
                    proxy_info = self.proxy_manager.get_next_proxy()
                    if proxy_info:
                        proxy_dict = self.create_proxy_dict(proxy_info)
                        if proxy_dict:
                            # 隐藏代理详细信息，保护用户隐私
                            proxy_used = t(user_id, 'report_2fa_using_proxy')
                
                # 创建客户端
                # Telethon expects session path without .session extension
                session_base = session_path.replace('.session', '') if session_path.endswith('.session') else session_path
                client = TelegramClient(
                    session_base,
                    int(config.API_ID),
                    str(config.API_HASH),
                    timeout=config.CONNECTION_TIMEOUT,
                    connection_retries=3,
                    retry_delay=1,
                    proxy=proxy_dict
                )
                
                # 连接
                await asyncio.wait_for(client.connect(), timeout=15)
                
                # 检查授权
                is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
                if not is_authorized:
                    return False, f"{proxy_used} | 账号未授权"
                
                # 获取用户信息
                try:
                    me = await asyncio.wait_for(client.get_me(), timeout=5)
                    user_info = f"ID:{me.id}"
                    if me.username:
                        user_info += f" @{me.username}"
                except Exception as e:
                    user_info = "账号"
                
                # 修改2FA密码 - 使用 Telethon 内置方法
                try:
                    # 使用 Telethon 的内置密码修改方法
                    result = await client.edit_2fa(
                        current_password=old_password if old_password else None,
                        new_password=new_password,
                        hint=f"Modified {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')}"
                    )
                    
                    # 修改成功后，更新文件中的密码
                    json_path = session_path.replace('.session', '.json')
                    has_json = os.path.exists(json_path)
                    
                    update_success = await self._update_password_files(
                        session_path, 
                        new_password, 
                        'session'
                    )
                    
                    if update_success:
                        if has_json:
                            return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')}"
                        else:
                            return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')} {t(user_id, 'status_no_json_found')}"
                    else:
                        return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')} {t(user_id, 'status_file_update_failed')}"
                    
                except AttributeError:
                    # 如果 edit_2fa 不存在，使用手动方法
                    return await self._change_2fa_manual(
                        client, session_path, old_password, new_password, 
                        user_info, proxy_used
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    if "password" in error_msg and "invalid" in error_msg:
                        return False, f"{user_info} | {proxy_used} | 旧密码错误"
                    elif "password" in error_msg and "incorrect" in error_msg:
                        return False, f"{user_info} | {proxy_used} | 旧密码不正确"
                    elif "flood" in error_msg:
                        return False, f"{user_info} | {proxy_used} | 操作过于频繁，请稍后重试"
                    else:
                        return False, f"{user_info} | {proxy_used} | 修改失败: {str(e)[:50]}"
                
            except Exception as e:
                error_msg = str(e).lower()
                if any(word in error_msg for word in ["timeout", "network", "connection"]):
                    return False, f"{proxy_used} | 网络连接失败"
                else:
                    return False, f"{proxy_used} | 错误: {str(e)[:50]}"
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
    
    async def _change_2fa_manual(self, client, session_path: str, old_password: str, 
                                 new_password: str, user_info: str, proxy_used: str) -> Tuple[bool, str]:
        """
        手动修改2FA密码（备用方法）
        """
        try:
            from telethon.tl.functions.account import GetPasswordRequest, UpdatePasswordSettingsRequest
            from telethon.tl.types import PasswordInputSettings
            
            # 获取密码配置
            pwd_info = await client(GetPasswordRequest())
            
            # 使用 Telethon 客户端的内置密码处理
            if old_password:
                password_bytes = old_password.encode('utf-8')
            else:
                password_bytes = b''
            
            # 生成新密码
            new_password_bytes = new_password.encode('utf-8')
            
            # 创建密码设置
            new_settings = PasswordInputSettings(
                new_password_hash=new_password_bytes,
                hint=f"Modified {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')}"
            )
            
            # 尝试更新
            await client(UpdatePasswordSettingsRequest(
                password=password_bytes,
                new_settings=new_settings
            ))
            
            # 更新文件
            json_path = session_path.replace('.session', '.json')
            has_json = os.path.exists(json_path)
            
            update_success = await self._update_password_files(session_path, new_password, 'session')
            
            if update_success:
                if has_json:
                    return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')}"
                else:
                    return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')} {t(user_id, 'status_no_json_found')}"
            else:
                return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_2fa_success_updated')} {t(user_id, 'status_file_update_failed')}"
            
        except Exception as e:
            return False, f"{user_info} | {proxy_used} | 手动修改失败: {str(e)[:50]}"
    
    async def remove_2fa_password(self, session_path: str, old_password: str, 
                                  account_name: str = "", file_type: str = 'session',
                                  proxy_dict: Optional[Dict] = None, user_id: int = None) -> Tuple[bool, str]:
        """
        删除2FA密码
        
        Args:
            session_path: Session文件路径
            old_password: 当前的2FA密码
            account_name: 账号名称（用于日志）
            file_type: 文件类型（'session' 或 'tdata'）
            proxy_dict: 代理配置（可选）
            user_id: 用户ID（用于翻译）
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息说明)
        """
        if not TELETHON_AVAILABLE:
            return False, "Telethon未安装"
        
        async with self.semaphore:
            client = None
            # Use translation for proxy_used, with fallback for None user_id
            if user_id:
                proxy_used = t(user_id, 'report_delete_2fa_local_connection')
            else:
                proxy_used = "本地连接"
            
            try:
                # 尝试使用代理
                if not proxy_dict:
                    proxy_enabled = self.db.get_proxy_enabled() if self.db else True
                    if config.USE_PROXY and proxy_enabled and self.proxy_manager.proxies:
                        proxy_info = self.proxy_manager.get_next_proxy()
                        if proxy_info:
                            proxy_dict = self.create_proxy_dict(proxy_info)
                            if proxy_dict:
                                if user_id:
                                    proxy_used = t(user_id, 'report_delete_2fa_using_proxy')
                                else:
                                    proxy_used = "使用代理"
                
                # 创建客户端
                session_base = session_path.replace('.session', '') if session_path.endswith('.session') else session_path
                client = TelegramClient(
                    session_base,
                    int(config.API_ID),
                    str(config.API_HASH),
                    timeout=config.CONNECTION_TIMEOUT,
                    connection_retries=3,
                    retry_delay=1,
                    proxy=proxy_dict
                )
                
                # 连接
                await asyncio.wait_for(client.connect(), timeout=15)
                
                # 检查授权
                is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
                if not is_authorized:
                    if user_id:
                        return False, f"{proxy_used} | {t(user_id, 'report_delete_2fa_error_unauthorized')}"
                    else:
                        return False, f"{proxy_used} | 账号未授权"
                
                # 获取用户信息
                try:
                    me = await asyncio.wait_for(client.get_me(), timeout=5)
                    user_info = f"ID:{me.id}"
                    if me.username:
                        user_info += f" @{me.username}"
                except Exception as e:
                    user_info = "账号"
                
                # 删除2FA密码 - 使用 Telethon 的 edit_2fa 方法
                try:
                    # 使用 edit_2fa 删除密码（new_password=None表示删除）
                    result = await client.edit_2fa(
                        current_password=old_password if old_password else None,
                        new_password=None,  # None表示删除密码
                        hint=''
                    )
                    
                    # 删除成功后，更新文件中的密码为空
                    json_path = session_path.replace('.session', '.json')
                    has_json = os.path.exists(json_path)
                    
                    update_success = await self._update_password_files(
                        session_path, 
                        '', 
                        'session'
                    )
                    
                    if update_success:
                        if has_json:
                            if user_id:
                                return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_with_json')}"
                            else:
                                return True, f"{user_info} | {proxy_used} | 2FA密码已删除，文件已更新"
                        else:
                            if user_id:
                                return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_no_json')}"
                            else:
                                return True, f"{user_info} | {proxy_used} | 2FA密码已删除"
                    else:
                        if user_id:
                            return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_update_failed')}"
                        else:
                            return True, f"{user_info} | {proxy_used} | 2FA密码已删除，但文件更新失败"
                    
                except AttributeError:
                    # 如果 edit_2fa 不存在，使用手动方法
                    return await self._remove_2fa_manual(
                        client, session_path, old_password, 
                        user_info, proxy_used, user_id
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    if "password" in error_msg and ("invalid" in error_msg or "incorrect" in error_msg):
                        if user_id:
                            return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_error_wrong_password')}"
                        else:
                            return False, f"{user_info} | {proxy_used} | 密码错误"
                    elif "no password" in error_msg or "not set" in error_msg:
                        if user_id:
                            return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_error_no_2fa')}"
                        else:
                            return False, f"{user_info} | {proxy_used} | 未设置2FA"
                    elif "flood" in error_msg:
                        if user_id:
                            return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_error_flood')}"
                        else:
                            return False, f"{user_info} | {proxy_used} | 操作过于频繁，请稍后重试"
                    elif any(word in error_msg for word in ["frozen", "deactivated", "banned"]):
                        if user_id:
                            return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_error_frozen')}"
                        else:
                            return False, f"{user_info} | {proxy_used} | 账号已冻结/封禁"
                    else:
                        if user_id:
                            return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_error_deletion_failed')}: {str(e)[:50]}"
                        else:
                            return False, f"{user_info} | {proxy_used} | 删除失败: {str(e)[:50]}"
                
            except Exception as e:
                error_msg = str(e).lower()
                if any(word in error_msg for word in ["timeout", "network", "connection"]):
                    if user_id:
                        return False, f"{proxy_used} | {t(user_id, 'report_delete_2fa_error_network')}"
                    else:
                        return False, f"{proxy_used} | 网络连接失败"
                else:
                    if user_id:
                        return False, f"{proxy_used} | {t(user_id, 'report_delete_2fa_error_general')}: {str(e)[:50]}"
                    else:
                        return False, f"{proxy_used} | 错误: {str(e)[:50]}"
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
    
    async def _remove_2fa_manual(self, client, session_path: str, old_password: str, 
                                 user_info: str, proxy_used: str, user_id: int = None) -> Tuple[bool, str]:
        """
        手动删除2FA密码（备用方法）
        """
        try:
            from telethon.tl.functions.account import GetPasswordRequest, UpdatePasswordSettingsRequest
            from telethon.tl.types import PasswordInputSettings
            
            # 获取密码配置
            pwd_info = await client(GetPasswordRequest())
            
            # 使用旧密码验证
            if old_password:
                password_bytes = old_password.encode('utf-8')
            else:
                password_bytes = b''
            
            # 创建密码设置（删除密码）
            new_settings = PasswordInputSettings(
                new_algo=None,  # 删除密码
                new_password_hash=b'',
                hint=''
            )
            
            # 尝试更新
            await client(UpdatePasswordSettingsRequest(
                password=password_bytes,
                new_settings=new_settings
            ))
            
            # 更新文件
            json_path = session_path.replace('.session', '.json')
            has_json = os.path.exists(json_path)
            
            update_success = await self._update_password_files(session_path, '', 'session')
            
            if update_success:
                if has_json:
                    if user_id:
                        return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_with_json')}"
                    else:
                        return True, f"{user_info} | {proxy_used} | 2FA密码已删除，文件已更新"
                else:
                    if user_id:
                        return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_no_json')}"
                    else:
                        return True, f"{user_info} | {proxy_used} | 2FA密码已删除"
            else:
                if user_id:
                    return True, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_success_update_failed')}"
                else:
                    return True, f"{user_info} | {proxy_used} | 2FA密码已删除，但文件更新失败"
            
        except Exception as e:
            if user_id:
                return False, f"{user_info} | {proxy_used} | {t(user_id, 'report_delete_2fa_manual_failed')}: {str(e)[:50]}"
            else:
                return False, f"{user_info} | {proxy_used} | 手动删除失败: {str(e)[:50]}"

    def create_proxy_dict(self, proxy_info: Dict) -> Optional[Dict]:
        """创建代理字典（复用SpamBotChecker的实现）"""
        if not proxy_info:
            return None
        
        try:
            if PROXY_SUPPORT:
                if proxy_info['type'] == 'socks5':
                    proxy_type = socks.SOCKS5
                elif proxy_info['type'] == 'socks4':
                    proxy_type = socks.SOCKS4
                else:
                    proxy_type = socks.HTTP
                
                proxy_dict = {
                    'proxy_type': proxy_type,
                    'addr': proxy_info['host'],
                    'port': proxy_info['port']
                }
                
                if proxy_info.get('username') and proxy_info.get('password'):
                    proxy_dict['username'] = proxy_info['username']
                    proxy_dict['password'] = proxy_info['password']
            else:
                proxy_dict = (proxy_info['host'], proxy_info['port'])
            
            return proxy_dict
            
        except Exception as e:
            print(f"❌ 创建代理配置失败: {e}")
            return None
    
    async def _update_password_files(self, file_path: str, new_password: str, file_type: str) -> bool:
        """
        更新文件中的密码
        
        Args:
            file_path: 文件路径（session或tdata路径）
            new_password: 新密码
            file_type: 文件类型（'session' 或 'tdata'）
            
        Returns:
            是否更新成功。对于纯Session文件（无JSON），返回True表示成功（非阻塞）
        """
        try:
            if file_type == 'session':
                # 更新Session对应的JSON文件（可选，如果存在）
                json_path = file_path.replace('.session', '.json')
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 更新密码字段 - 统一使用 twofa 字段，删除其他密码字段
                        # 1. 删除所有旧的密码字段（除了 twofa）
                        old_fields_to_remove = ['twoFA', '2fa', 'password', 'two_fa']
                        removed_fields = []
                        for field in old_fields_to_remove:
                            if field in data:
                                del data[field]
                                removed_fields.append(field)
                        
                        # 2. 设置标准的 twofa 字段
                        data['twofa'] = new_password
                        
                        # 3. 保存更新后的文件
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
                        if removed_fields:
                            print(f"✅ 文件已更新: {os.path.basename(json_path)} - 已删除字段 {removed_fields}，统一使用 twofa 字段")
                        else:
                            print(f"✅ 文件已更新: {os.path.basename(json_path)} - twofa 字段已设置")
                        
                        return True
                            
                    except Exception as e:
                        print(f"❌ 更新JSON文件失败 {os.path.basename(json_path)}: {e}")
                        return False
                else:
                    print(f"ℹ️ JSON文件不存在，跳过JSON更新: {os.path.basename(file_path)}")
                    # 对于纯Session文件，不存在JSON是正常情况，返回True表示不影响密码修改成功
                    return True
                    
            elif file_type == 'tdata':
                # 更新TData目录中的密码文件
                d877_path = os.path.join(file_path, "D877F783D5D3EF8C")
                if not os.path.exists(d877_path):
                    print(f"⚠️ TData目录结构无效: {file_path}")
                    return False
                
                updated = False
                found_files = []
                
                # 方法1: 在整个 tdata 目录搜索现有密码文件
                for password_file_name in ['2fa.txt', 'twofa.txt', 'password.txt']:
                    for root, dirs, files in os.walk(file_path):
                        for file in files:
                            if file.lower() == password_file_name.lower():
                                password_file = os.path.join(root, file)
                                try:
                                    with open(password_file, 'w', encoding='utf-8') as f:
                                        f.write(new_password)
                                    print(f"✅ TData密码文件已更新: {file}")
                                    found_files.append(file)
                                    updated = True
                                except Exception as e:
                                    print(f"❌ 更新密码文件失败 {file}: {e}")
                
                # 方法2: 如果没有找到任何密码文件，创建新的 2fa.txt（与 tdata 同级）
                if not found_files:
                    try:
                        # 获取 tdata 的父目录（与 tdata 同级）
                        parent_dir = os.path.dirname(file_path)
                        new_password_file = os.path.join(parent_dir, "2fa.txt")
                        
                        with open(new_password_file, 'w', encoding='utf-8') as f:
                            f.write(new_password)
                        print(f"✅ TData密码文件已创建: 2fa.txt (位置: 与 tdata 目录同级)")
                        updated = True
                    except Exception as e:
                        print(f"❌ 创建密码文件失败: {e}")
                
                return updated
            
            return False
            
        except Exception as e:
            print(f"❌ 更新文件密码失败: {e}")
            return False
    
    async def batch_change_passwords(self, files: List[Tuple[str, str]], file_type: str, 
                                    old_password: Optional[str], new_password: str,
                                    progress_callback=None, user_id: int = None) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        批量修改密码
        
        Args:
            files: 文件列表 [(路径, 名称), ...]
            file_type: 文件类型（'tdata' 或 'session'）
            old_password: 手动输入的旧密码（备选）
            new_password: 新密码
            progress_callback: 进度回调函数
            user_id: 用户ID（用于翻译）
            
        Returns:
            结果字典 {'成功': [...], '失败': [...]}
        """
        results = {
            "成功": [],
            "失败": []
        }
        
        total = len(files)
        processed = 0
        start_time = time.time()
        
        async def process_single_file(file_path, file_name):
            nonlocal processed
            try:
                # 1. 如果是 TData 格式，需要先转换为 Session
                if file_type == 'tdata':
                    print(f"🔄 TData格式需要先转换为Session: {file_name}")
                    
                    # 使用 FormatConverter 转换
                    converter = FormatConverter(self.db)
                    status, info, name = await converter.convert_tdata_to_session(
                        file_path, 
                        file_name,
                        int(config.API_ID),
                        str(config.API_HASH)
                    )
                    
                    if status != "转换成功":
                        results["失败"].append((file_path, file_name, t(user_id, 'report_2fa_conversion_failed').format(error=info)))
                        processed += 1
                        return
                    
                    # 转换成功，使用生成的 session 文件
                    sessions_dir = config.SESSIONS_DIR
                    phone = file_name  # TData 的名称通常是手机号
                    session_path = os.path.join(sessions_dir, f"{phone}.session")
                    
                    if not os.path.exists(session_path):
                        if user_id:
                            results["失败"].append((file_path, file_name, t(user_id, 'report_delete_2fa_error_session_not_found')))
                        else:
                            results["失败"].append((file_path, file_name, "转换后的Session文件未找到"))
                        processed += 1
                        return
                    
                    print(f"✅ TData已转换为Session: {phone}.session")
                    actual_file_path = session_path
                    actual_file_type = 'session'
                else:
                    actual_file_path = file_path
                    actual_file_type = file_type
                
                # 2. 尝试自动检测密码
                detected_password = self.password_detector.detect_password(file_path, file_type)
                
                # 3. 如果检测失败，使用手动输入的备选密码
                current_old_password = detected_password if detected_password else old_password
                
                if not current_old_password:
                    results["失败"].append((file_path, file_name, t(user_id, 'report_2fa_old_password_not_found')))
                    processed += 1
                    return
                
                # 4. 修改密码（使用 Session 格式）
                success, info = await self.change_2fa_password(
                    actual_file_path, current_old_password, new_password, file_name, user_id
                )
                
                if success:
                    # 如果原始是 TData，需要更新原始 TData 文件
                    if file_type == 'tdata':
                        tdata_update = await self._update_password_files(
                            file_path, new_password, 'tdata'
                        )
                        if tdata_update:
                            info += f" | {t(user_id, 'status_tdata_updated')}"
                    
                    results["成功"].append((file_path, file_name, info))
                    print(f"✅ 修改成功 {processed + 1}/{total}: {file_name}")
                else:
                    results["失败"].append((file_path, file_name, info))
                    print(f"❌ 修改失败 {processed + 1}/{total}: {file_name} - {info}")
                
                processed += 1
                
                # 调用进度回调
                if progress_callback:
                    elapsed = time.time() - start_time
                    speed = processed / elapsed if elapsed > 0 else 0
                    await progress_callback(processed, total, results, speed, elapsed)
                
            except Exception as e:
                if user_id:
                    results["失败"].append((file_path, file_name, f"{t(user_id, 'report_delete_2fa_error_exception')}: {str(e)[:50]}"))
                else:
                    results["失败"].append((file_path, file_name, f"异常: {str(e)[:50]}"))
                processed += 1
                print(f"❌ 处理失败 {processed}/{total}: {file_name} - {str(e)}")
        
        # 批量并发处理（使用配置的并发数）
        semaphore = asyncio.Semaphore(self.DEFAULT_CONCURRENT_LIMIT)
        
        async def process_with_semaphore(file_path, file_name):
            async with semaphore:
                await process_single_file(file_path, file_name)
        
        tasks = [process_with_semaphore(file_path, file_name) for file_path, file_name in files]
        
        # 等待所有任务完成 - 添加超时保护
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=3600  # 1小时超时
            )
        except asyncio.TimeoutError:
            logger.error("批量修改2FA密码超时")
            print("❌ 批量修改2FA密码超时（1小时）")
        
        # 确保最后一次进度回调被调用
        if progress_callback:
            try:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                await progress_callback(processed, total, results, speed, elapsed)
                logger.info(f"修改2FA密码完成: {processed}/{total}")
            except Exception as e:
                logger.error(f"最终进度回调错误: {e}")
        
        return results
    
    async def batch_remove_passwords(self, files: List[Tuple[str, str]], file_type: str, 
                                    old_password: Optional[str],
                                    progress_callback=None, user_id: int = None) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        批量删除2FA密码
        
        Args:
            files: 文件列表 [(路径, 名称), ...]
            file_type: 文件类型（'tdata' 或 'session'）
            old_password: 手动输入的旧密码（备选）
            progress_callback: 进度回调函数
            user_id: 用户ID（用于翻译）
            
        Returns:
            结果字典 {'成功': [...], '失败': [...]}
        """
        results = {
            "成功": [],
            "失败": []
        }
        
        total = len(files)
        processed = 0
        start_time = time.time()
        
        # 智能进度更新控制变量
        last_update_time = 0
        last_update_percent = 0
        
        async def process_single_file(file_path, file_name):
            nonlocal processed
            try:
                # 1. 如果是 TData 格式，需要先转换为 Session
                if file_type == 'tdata':
                    print(f"🔄 TData格式需要先转换为Session: {file_name}")
                    
                    # 使用 FormatConverter 转换
                    converter = FormatConverter(self.db)
                    status, info, name = await converter.convert_tdata_to_session(
                        file_path, 
                        file_name,
                        int(config.API_ID),
                        str(config.API_HASH)
                    )
                    
                    if status != "转换成功":
                        results["失败"].append((file_path, file_name, t(user_id, 'report_2fa_conversion_failed').format(error=info)))
                        processed += 1
                        return
                    
                    # 转换成功，使用生成的 session 文件
                    sessions_dir = config.SESSIONS_DIR
                    phone = file_name  # TData 的名称通常是手机号
                    session_path = os.path.join(sessions_dir, f"{phone}.session")
                    
                    if not os.path.exists(session_path):
                        results["失败"].append((file_path, file_name, "转换后的Session文件未找到"))
                        processed += 1
                        return
                    
                    print(f"✅ TData已转换为Session: {phone}.session")
                    actual_file_path = session_path
                    actual_file_type = 'session'
                else:
                    actual_file_path = file_path
                    actual_file_type = file_type
                
                # 2. 尝试自动检测密码
                detected_password = self.password_detector.detect_password(file_path, file_type)
                
                # 3. 如果检测失败，使用手动输入的备选密码
                current_old_password = detected_password if detected_password else old_password
                
                if not current_old_password:
                    if user_id:
                        results["失败"].append((file_path, file_name, t(user_id, 'report_2fa_old_password_not_found')))
                    else:
                        results["失败"].append((file_path, file_name, "未找到旧密码"))
                    processed += 1
                    return
                
                # 4. 删除密码（使用 Session 格式）
                success, info = await self.remove_2fa_password(
                    actual_file_path, current_old_password, file_name, 
                    file_type=actual_file_type, user_id=user_id
                )
                
                if success:
                    # 如果原始是 TData，需要更新原始 TData 文件
                    if file_type == 'tdata':
                        tdata_update = await self._update_password_files(
                            file_path, '', 'tdata'
                        )
                        if tdata_update:
                            info += " | TData文件已更新"
                    
                    results["成功"].append((file_path, file_name, info))
                    print(f"✅ 删除成功 {processed + 1}/{total}: {file_name}")
                else:
                    results["失败"].append((file_path, file_name, info))
                    print(f"❌ 删除失败 {processed + 1}/{total}: {file_name} - {info}")
                
                processed += 1
                
                # 智能进度回调 - 避免触发 Telegram 限流
                if progress_callback:
                    nonlocal last_update_time, last_update_percent
                    
                    current_time = time.time()
                    current_percent = int(processed / total * 100) if total > 0 else 0
                    
                    # 确定更新策略（大批量降低更新频率）
                    update_interval = PROGRESS_UPDATE_INTERVAL
                    if total >= PROGRESS_LARGE_BATCH_THRESHOLD:
                        percent_step = PROGRESS_UPDATE_MIN_PERCENT_LARGE
                    elif total >= 100:
                        percent_step = PROGRESS_UPDATE_MIN_PERCENT
                    else:
                        percent_step = 1  # 小批量每1%更新
                    
                    # 判断是否应该更新进度
                    time_ok = (current_time - last_update_time) >= update_interval
                    percent_ok = (current_percent - last_update_percent) >= percent_step
                    is_final = (processed == total)
                    
                    should_update = is_final or (time_ok and percent_ok)
                    
                    if should_update:
                        try:
                            elapsed = time.time() - start_time
                            speed = processed / elapsed if elapsed > 0 else 0
                            await progress_callback(processed, total, results, speed, elapsed)
                            last_update_time = current_time
                            last_update_percent = current_percent
                        except FloodWaitError as e:
                            # 被限流时不阻塞，直接跳过本次更新
                            logger.warning(f"进度更新被限流（跳过）: {e.seconds}秒")
                        except Exception as e:
                            # 其他错误也不阻塞处理流程
                            logger.warning(f"进度更新失败（跳过）: {e}")
                
            except Exception as e:
                if user_id:
                    results["失败"].append((file_path, file_name, f"{t(user_id, 'report_delete_2fa_error_exception')}: {str(e)[:50]}"))
                else:
                    results["失败"].append((file_path, file_name, f"异常: {str(e)[:50]}"))
                processed += 1
                print(f"❌ 处理失败 {processed}/{total}: {file_name} - {str(e)}")
        
        # 批量并发处理（使用配置的并发数）
        semaphore = asyncio.Semaphore(self.DEFAULT_CONCURRENT_LIMIT)
        
        async def process_with_semaphore(file_path, file_name):
            async with semaphore:
                await process_single_file(file_path, file_name)
        
        tasks = [process_with_semaphore(file_path, file_name) for file_path, file_name in files]
        
        # 等待所有任务完成 - 添加超时保护
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=3600  # 1小时超时
            )
        except asyncio.TimeoutError:
            logger.error("批量删除2FA超时")
            print("❌ 批量删除2FA超时（1小时）")
        
        # 确保最后一次进度回调被调用
        if progress_callback:
            try:
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                await progress_callback(processed, total, results, speed, elapsed)
                logger.info(f"删除2FA完成: {processed}/{total}")
            except FloodWaitError as e:
                logger.warning(f"最终进度回调被限流（跳过）: {e.seconds}秒")
            except Exception as e:
                logger.error(f"最终进度回调错误: {e}")
        
        return results
    
    def create_result_files(self, results: Dict, task_id: str, file_type: str = 'session', user_id: int = None, operation: str = 'change') -> List[Tuple[str, str, str, int]]:
        """
        创建结果文件（修复版 - 分离 ZIP 和 TXT）
        
        Args:
            operation: 操作类型，'change' 表示修改2FA，'remove' 表示删除2FA
        
        Returns:
            [(zip文件路径, txt文件路径, 状态名称, 数量), ...]
        """
        logger.info(f"开始创建结果文件: task_id={task_id}, file_type={file_type}, operation={operation}")
        result_files = []
        
        for status, items in results.items():
            if not items:
                continue
            
            logger.info(f"📦 正在创建 {status} 结果文件，包含 {len(items)} 个账号")
            print(f"📦 正在创建 {status} 结果文件，包含 {len(items)} 个账号")
            
            # 为每个状态创建唯一的临时目录
            timestamp_short = str(int(time.time()))[-6:]
            status_temp_dir = os.path.join(config.RESULTS_DIR, f"{status}_{timestamp_short}")
            os.makedirs(status_temp_dir, exist_ok=True)
            
            # 确保每个账号有唯一目录名
            used_names = set()
            
            try:
                logger.info(f"开始复制文件到临时目录: {status_temp_dir}")
                for index, (file_path, file_name, info) in enumerate(items):
                    if file_type == "session":
                        # 复制 session 文件
                        dest_path = os.path.join(status_temp_dir, file_name)
                        if os.path.exists(file_path):
                            shutil.copy2(file_path, dest_path)
                            print(f"📄 复制Session文件: {file_name}")
                        
                        # 查找对应的 json 文件（如果存在）
                        json_name = file_name.replace('.session', '.json')
                        json_path = os.path.join(os.path.dirname(file_path), json_name)
                        if os.path.exists(json_path):
                            json_dest = os.path.join(status_temp_dir, json_name)
                            shutil.copy2(json_path, json_dest)
                            print(f"📄 复制JSON文件: {json_name}")
                        else:
                            print(f"ℹ️ 无JSON文件: {file_name} (纯Session文件)")
                    
                    elif file_type == "tdata":
                        # 使用原始文件夹名称（通常是手机号）
                        original_name = file_name
                        
                        # 确保名称唯一性
                        unique_name = original_name
                        counter = 1
                        while unique_name in used_names:
                            unique_name = f"{original_name}_{counter}"
                            counter += 1
                        
                        used_names.add(unique_name)
                        
                        # 创建 手机号/ 目录（与转换模块一致）
                        phone_dir = os.path.join(status_temp_dir, unique_name)
                        os.makedirs(phone_dir, exist_ok=True)
                        
                        # 1. 复制 tdata 目录
                        target_dir = os.path.join(phone_dir, "tdata")
                        
                        # 复制 TData 文件（使用正确的递归复制）
                        if os.path.exists(file_path) and os.path.isdir(file_path):
                            # 遍历 TData 目录
                            for item in os.listdir(file_path):
                                item_path = os.path.join(file_path, item)
                                dest_item_path = os.path.join(target_dir, item)
                                
                                if os.path.isdir(item_path):
                                    # 递归复制目录
                                    shutil.copytree(item_path, dest_item_path, dirs_exist_ok=True)
                                else:
                                    # 复制文件
                                    os.makedirs(target_dir, exist_ok=True)
                                    shutil.copy2(item_path, dest_item_path)
                            
                            print(f"📂 复制TData: {unique_name}/tdata/")
                        
                        # 2. 复制密码文件（从 tdata 的父目录，即与 tdata 同级）
                        parent_dir = os.path.dirname(file_path)
                        for password_file_name in ['2fa.txt', 'twofa.txt', 'password.txt']:
                            password_file_path = os.path.join(parent_dir, password_file_name)
                            if os.path.exists(password_file_path):
                                # 复制到 手机号/ 目录下（与 tdata 同级）
                                dest_password_path = os.path.join(phone_dir, password_file_name)
                                shutil.copy2(password_file_path, dest_password_path)
                                print(f"📄 复制密码文件: {unique_name}/{password_file_name}")
                
                # 创建 ZIP 文件 - 新格式
                logger.info(f"开始打包ZIP文件: {status}, {len(items)} 个文件")
                # Use translation for ZIP filename based on operation
                if operation == 'remove':
                    # Delete 2FA operation
                    if status == "成功":
                        zip_filename = t(user_id, 'zip_delete_2fa_success').format(count=len(items)) + '.zip'
                    else:  # 失败
                        zip_filename = t(user_id, 'zip_delete_2fa_failed').format(count=len(items)) + '.zip'
                else:
                    # Change 2FA operation (default)
                    if status == "成功":
                        zip_filename = t(user_id, 'zip_change_2fa_success').format(count=len(items)) + '.zip'
                    else:  # 失败
                        zip_filename = t(user_id, 'zip_change_2fa_failed').format(count=len(items)) + '.zip'
                zip_path = os.path.join(config.RESULTS_DIR, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files_list in os.walk(status_temp_dir):
                        for file in files_list:
                            file_path_full = os.path.join(root, file)
                            # 使用相对路径，避免重复
                            arcname = os.path.relpath(file_path_full, status_temp_dir)
                            zipf.write(file_path_full, arcname)
                
                logger.info(f"✅ ZIP文件创建成功: {zip_filename}")
                print(f"✅ 创建ZIP文件: {zip_filename}")
                
                # 创建 TXT 报告 - 新格式
                logger.info(f"开始创建TXT报告: {status}")
                # Use translation for TXT filename based on operation
                if operation == 'remove':
                    # Delete 2FA operation
                    if status == "成功":
                        txt_filename = t(user_id, 'report_delete_2fa_success').format(count=len(items))
                    else:  # 失败
                        txt_filename = t(user_id, 'report_delete_2fa_failed').format(count=len(items))
                else:
                    # Change 2FA operation (default)
                    if status == "成功":
                        txt_filename = t(user_id, 'report_change_2fa_success').format(count=len(items))
                    else:  # 失败
                        txt_filename = t(user_id, 'report_change_2fa_failed').format(count=len(items))
                txt_path = os.path.join(config.RESULTS_DIR, txt_filename)
                
                with open(txt_path, 'w', encoding='utf-8') as f:
                    # Use translation for report title based on operation
                    if operation == 'remove':
                        # Delete 2FA operation
                        if status == "成功":
                            f.write(t(user_id, 'report_delete_2fa_title_success') + "\n")
                        else:  # 失败
                            f.write(t(user_id, 'report_delete_2fa_title_failed') + "\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(t(user_id, 'report_delete_2fa_total').format(count=len(items)) + "\n\n")
                        f.write(t(user_id, 'report_delete_2fa_generated').format(time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')) + "\n")
                        
                        f.write(t(user_id, 'report_delete_2fa_detail_list') + "\n")
                        f.write("-" * 50 + "\n\n")
                        
                        for idx, (file_path, file_name, info) in enumerate(items, 1):
                            # 隐藏代理详细信息，保护用户隐私
                            masked_info = Forget2FAManager.mask_proxy_in_string(info)
                            f.write(f"{idx}. {t(user_id, 'report_delete_2fa_account').format(account=file_name)}\n")
                            f.write(f"   {t(user_id, 'report_delete_2fa_details').format(info=masked_info)}\n")
                            f.write(f"   {t(user_id, 'report_delete_2fa_process_time').format(time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST'))}\n\n")
                        
                        # 如果是失败列表，添加解决方案
                        if status == "失败":
                            f.write("\n" + "=" * 50 + "\n")
                            f.write(t(user_id, 'report_delete_2fa_failure_analysis') + "\n")
                            f.write("-" * 50 + "\n\n")
                            f.write(f"1. {t(user_id, 'report_delete_2fa_reason_unauthorized')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_unauthorized_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_unauthorized_desc2')}\n\n")
                            f.write(f"2. {t(user_id, 'report_delete_2fa_reason_wrong_password')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_wrong_password_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_wrong_password_desc2')}\n\n")
                            f.write(f"3. {t(user_id, 'report_delete_2fa_reason_network')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_network_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_delete_2fa_reason_network_desc2')}\n\n")
                    else:
                        # Change 2FA operation (default)
                        if status == "成功":
                            f.write(t(user_id, 'report_2fa_title_success') + "\n")
                        else:  # 失败
                            f.write(t(user_id, 'report_2fa_title_failed') + "\n")
                        f.write("=" * 50 + "\n\n")
                        f.write(t(user_id, 'report_2fa_total').format(count=len(items)) + "\n\n")
                        f.write(t(user_id, 'report_2fa_generated').format(time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')) + "\n")
                        
                        f.write(t(user_id, 'report_2fa_detail_list') + "\n")
                        f.write("-" * 50 + "\n\n")
                        
                        for idx, (file_path, file_name, info) in enumerate(items, 1):
                            # 隐藏代理详细信息，保护用户隐私
                            masked_info = Forget2FAManager.mask_proxy_in_string(info)
                            f.write(f"{idx}. {t(user_id, 'report_2fa_account').format(account=file_name)}\n")
                            f.write(f"   {t(user_id, 'report_2fa_details').format(info=masked_info)}\n")
                            f.write(f"   {t(user_id, 'report_2fa_process_time').format(time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST'))}\n\n")
                        
                        # 如果是失败列表，添加解决方案
                        if status == "失败":
                            f.write("\n" + "=" * 50 + "\n")
                            f.write(t(user_id, 'report_2fa_failure_analysis') + "\n")
                            f.write("-" * 50 + "\n\n")
                            f.write(f"1. {t(user_id, 'report_2fa_reason_unauthorized')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_unauthorized_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_unauthorized_desc2')}\n\n")
                            f.write(f"2. {t(user_id, 'report_2fa_reason_wrong_password')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_wrong_password_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_wrong_password_desc2')}\n\n")
                            f.write(f"3. {t(user_id, 'report_2fa_reason_network')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_network_desc1')}\n")
                            f.write(f"   - {t(user_id, 'report_2fa_reason_network_desc2')}\n\n")
                
                logger.info(f"✅ TXT报告创建成功: {txt_filename}")
                print(f"✅ 创建TXT报告: {txt_filename}")
                
                result_files.append((zip_path, txt_path, status, len(items)))
                
            except Exception as e:
                logger.error(f"❌ 创建{status}结果文件失败: {e}")
                print(f"❌ 创建{status}结果文件失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 清理临时目录
                if os.path.exists(status_temp_dir):
                    shutil.rmtree(status_temp_dir, ignore_errors=True)
                    logger.info(f"临时目录已清理: {status_temp_dir}")
        
        logger.info(f"结果文件创建完成: 共 {len(result_files)} 组文件")
        return result_files
    
    def cleanup_expired_tasks(self, timeout_seconds: int = 300):
        """
        清理过期的待处理任务（默认5分钟超时）
        
        Args:
            timeout_seconds: 超时时间（秒）
        """
        current_time = time.time()
        expired_users = []
        
        for user_id, task_info in self.pending_2fa_tasks.items():
            task_start_time = task_info.get('start_time', 0)
            if current_time - task_start_time > timeout_seconds:
                expired_users.append(user_id)
        
        # 清理过期任务
        for user_id in expired_users:
            task_info = self.pending_2fa_tasks[user_id]
            
            # 清理临时文件
            extract_dir = task_info.get('extract_dir')
            temp_zip = task_info.get('temp_zip')
            
            if extract_dir and os.path.exists(extract_dir):
                try:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    print(f"🗑️ 清理过期任务的解压目录: {extract_dir}")
                except:
                    pass
            
            if temp_zip and os.path.exists(temp_zip):
                try:
                    shutil.rmtree(os.path.dirname(temp_zip), ignore_errors=True)
                    print(f"🗑️ 清理过期任务的临时文件: {temp_zip}")
                except:
                    pass
            
            # 删除任务信息
            del self.pending_2fa_tasks[user_id]
            print(f"⏰ 清理过期任务: user_id={user_id}")

# ================================
# 统一版 APIFormatConverter（Python 3.8/3.9 缩进已对齐）
# ================================
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
import os, shutil, time, threading


class Forget2FAManager:
    """忘记2FA管理器 - 官方密码重置流程（高速+防封混合模式）"""
    
    # 配置常量 - 平衡速度与防封
    DEFAULT_CONCURRENT_LIMIT = 50      # 并发限制50（批量高速处理）
    DEFAULT_MAX_PROXY_RETRIES = 3      # 代理重试次数为3
    DEFAULT_PROXY_TIMEOUT = 10         # 代理超时时间10秒
    DEFAULT_MIN_DELAY = 3.0            # 批次间最小延迟3秒
    DEFAULT_MAX_DELAY = 6.0            # 批次间最大延迟6秒
    DEFAULT_NOTIFY_WAIT = 0.5          # 等待通知到达的时间
    
    def __init__(self, proxy_manager: ProxyManager, db: Database,
                 concurrent_limit: int = None,
                 max_proxy_retries: int = None,
                 proxy_timeout: int = None,
                 min_delay: float = None,
                 max_delay: float = None,
                 notify_wait: float = None):
        self.proxy_manager = proxy_manager
        self.db = db
        
        # 使用环境变量配置或传入参数或默认值
        self.concurrent_limit = concurrent_limit if concurrent_limit is not None else (getattr(config, 'FORGET2FA_CONCURRENT', None) or self.DEFAULT_CONCURRENT_LIMIT)
        self.max_proxy_retries = max_proxy_retries if max_proxy_retries is not None else (getattr(config, 'FORGET2FA_MAX_PROXY_RETRIES', None) or self.DEFAULT_MAX_PROXY_RETRIES)
        self.proxy_timeout = proxy_timeout if proxy_timeout is not None else (getattr(config, 'FORGET2FA_PROXY_TIMEOUT', None) or self.DEFAULT_PROXY_TIMEOUT)
        self.min_delay = min_delay if min_delay is not None else (getattr(config, 'FORGET2FA_MIN_DELAY', None) or self.DEFAULT_MIN_DELAY)
        self.max_delay = max_delay if max_delay is not None else (getattr(config, 'FORGET2FA_MAX_DELAY', None) or self.DEFAULT_MAX_DELAY)
        self.notify_wait = notify_wait if notify_wait is not None else (getattr(config, 'FORGET2FA_NOTIFY_WAIT', None) or self.DEFAULT_NOTIFY_WAIT)
        
        # 创建代理轮换器（每个账号使用不同代理）
        self.proxy_rotator = ProxyRotator(self.proxy_manager.proxies if self.proxy_manager.proxies else [])
        
        # 创建信号量控制并发
        self.semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        # 打印配置
        print(f"⚡ 忘记2FA管理器初始化（高速+防封模式）:")
        print(f"   - 并发处理: {self.concurrent_limit}个账号/批次")
        print(f"   - 批次间隔: {self.min_delay}-{self.max_delay}秒")
        print(f"   - 代理策略: 每账号轮换，IP不够循环复用")
        print(f"   - 超时重试: 最多{self.max_proxy_retries}次")
        print(f"   - 可用代理: {len(self.proxy_rotator.proxies)}个")
    
    def create_proxy_dict(self, proxy_info: Dict) -> Optional[Dict]:
        """创建代理字典"""
        if not proxy_info:
            return None
        
        try:
            if PROXY_SUPPORT:
                if proxy_info['type'] == 'socks5':
                    proxy_type = socks.SOCKS5
                elif proxy_info['type'] == 'socks4':
                    proxy_type = socks.SOCKS4
                else:
                    proxy_type = socks.HTTP
                
                proxy_dict = {
                    'proxy_type': proxy_type,
                    'addr': proxy_info['host'],
                    'port': proxy_info['port']
                }
                
                if proxy_info.get('username') and proxy_info.get('password'):
                    proxy_dict['username'] = proxy_info['username']
                    proxy_dict['password'] = proxy_info['password']
            else:
                proxy_dict = (proxy_info['host'], proxy_info['port'])
            
            return proxy_dict
            
        except Exception as e:
            print(f"❌ 创建代理配置失败: {e}")
            return None
    
    def format_proxy_string(self, proxy_info: Optional[Dict]) -> str:
        """格式化代理字符串用于显示 - 隐藏详细信息，保护用户隐私"""
        if not proxy_info:
            return "本地连接"
        # 不再暴露具体的代理地址和端口，只显示使用了代理
        return "使用代理"
    
    def format_proxy_string_internal(self, proxy_info: Optional[Dict]) -> str:
        """格式化代理字符串用于内部日志（仅服务器日志，不暴露给用户）"""
        if not proxy_info:
            return "本地连接"
        proxy_type = proxy_info.get('type', 'http')
        host = proxy_info.get('host', '')
        port = proxy_info.get('port', '')
        return f"{proxy_type} {host}:{port}"
    
    @staticmethod
    def mask_proxy_for_display(proxy_used: str, user_id: int = None) -> str:
        """
        隐藏代理详细信息，仅显示是否使用代理
        用于报告文件和进度显示，保护用户代理隐私
        """
        # 如果没有提供user_id，返回默认中文（向后兼容）
        if user_id is None:
            if not proxy_used:
                return "本地连接"
            if "本地连接" in proxy_used or proxy_used == "本地连接":
                return "本地连接"
            return "✅ 使用代理"
        
        # 使用翻译
        if not proxy_used:
            return t(user_id, 'forget_2fa_proxy_local')
        if "本地连接" in proxy_used or proxy_used == "本地连接":
            return t(user_id, 'forget_2fa_proxy_local')
        # 只显示使用了代理，不暴露具体IP/端口
        return t(user_id, 'forget_2fa_proxy_using')
    
    @staticmethod
    def mask_proxy_in_string(text: str) -> str:
        """
        从任意字符串中移除代理详细信息，保护用户代理隐私
        用于报告和日志输出
        """
        import re
        if not text:
            return text
        
        # 匹配各种代理格式的正则表达式
        patterns = [
            # 代理 host:port 格式
            r'代理\s+[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # //host:port 格式
            r'//[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # http://host:port 格式
            r'https?://[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # socks5://host:port 格式
            r'socks[45]?://[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # 住宅代理 host:port 格式
            r'住宅代理\s+[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # HTTP host:port 格式
            r'HTTP\s+[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # SOCKS host:port 格式
            r'SOCKS[45]?\s+[a-zA-Z0-9\-_.]+\.[a-zA-Z0-9\-_.]+:\d+',
            # 一般的 host:port 格式（IP或域名后面跟端口）
            r'\b[a-zA-Z0-9\-_.]+\.(vip|com|net|org|io|xyz|cn):\d+\b',
        ]
        
        result = text
        for pattern in patterns:
            result = re.sub(pattern, '使用代理', result, flags=re.IGNORECASE)
        
        return result
    
    async def check_2fa_status(self, client) -> Tuple[bool, str, Optional[Dict]]:
        """
        检测账号是否设置2FA
        
        Returns:
            (是否有2FA, 状态描述, 密码信息字典)
        """
        try:
            from telethon.tl.functions.account import GetPasswordRequest
            
            pwd_info = await asyncio.wait_for(
                client(GetPasswordRequest()),
                timeout=10
            )
            
            if pwd_info.has_password:
                return True, "账号已设置2FA密码", {
                    'has_password': True,
                    'has_recovery': pwd_info.has_recovery,
                    'hint': pwd_info.hint or ""
                }
            else:
                return False, "账号未设置2FA密码", {'has_password': False}
                
        except Exception as e:
            return False, f"检测2FA状态失败: {str(e)[:50]}", None
    
    async def request_password_reset(self, client) -> Tuple[bool, str, Optional[datetime]]:
        """
        请求重置密码
        
        Returns:
            (是否成功, 状态描述, 冷却期结束时间)
        """
        try:
            from telethon.tl.functions.account import ResetPasswordRequest
            from datetime import timezone
            
            result = await asyncio.wait_for(
                client(ResetPasswordRequest()),
                timeout=15
            )
            
            # 检查结果类型 - 使用类名字符串比较避免导入问题
            result_type = type(result).__name__
            
            if hasattr(result, 'until_date'):
                # ResetPasswordRequestedWait - 正在等待冷却期
                until_date = result.until_date
                
                # 判断是新请求还是已在冷却期
                # 如果until_date距离现在小于6天23小时，说明是已存在的冷却期（不是刚刚请求的）
                # Note: Telegram API returns UTC times, so we use UTC for comparison if timezone-aware
                # Otherwise use naive Beijing time for comparison with naive datetime
                now = datetime.now(timezone.utc) if until_date.tzinfo else datetime.now(BEIJING_TZ).replace(tzinfo=None)
                time_remaining = until_date - now
                
                # 7天 = 604800秒，如果剩余时间少于6天23小时，说明是已在冷却期
                # 但是如果时间已经过期（负数），则冷却期已结束
                remaining_seconds = time_remaining.total_seconds()
                
                if remaining_seconds <= 0:
                    # 冷却期已过，需要再次请求完成重置
                    # 根据 Telegram 官方规则，7天后需要手动再点一次忘记密码才会真正重置
                    logger.info("冷却期已过，自动发起第二次重置请求...")
                    try:
                        second_result = await asyncio.wait_for(
                            client(ResetPasswordRequest()),
                            timeout=15
                        )
                        second_result_type = type(second_result).__name__
                        
                        if second_result_type == 'ResetPasswordOk':
                            return True, "密码已成功重置（冷却期结束后完成）", None
                        elif hasattr(second_result, 'until_date'):
                            # 仍然有冷却期（不太可能，但需要处理）
                            return False, "第二次请求仍在冷却期中", second_result.until_date
                        else:
                            return True, "密码重置请求已提交（冷却期结束后）", None
                    except Exception as e2:
                        logger.warning(f"第二次重置请求失败: {e2}")
                        # 即使第二次请求失败，也返回成功，因为冷却期确实已过
                        return True, f"冷却期已结束，第二次请求遇到问题: {str(e2)[:30]}", None
                elif remaining_seconds < COOLDOWN_THRESHOLD_SECONDS:
                    days_remaining = time_remaining.days
                    hours_remaining = time_remaining.seconds // 3600
                    return False, f"已在冷却期中 (剩余约{days_remaining}天{hours_remaining}小时)", until_date
                else:
                    # 新请求，剩余时间接近7天
                    return True, "已请求密码重置，正在等待冷却期", until_date
            elif result_type == 'ResetPasswordOk':
                # ResetPasswordOk - 密码已被重置（极少见，通常需要等待）
                return True, "密码已成功重置", None
            elif result_type == 'ResetPasswordFailedWait':
                # ResetPasswordFailedWait - 重置请求失败，需要等待
                retry_date = getattr(result, 'retry_date', None)
                return False, f"重置请求失败，需等待后重试", retry_date
            else:
                # 其他情况 - 通常是成功
                return True, "密码重置请求已提交", None
                
        except Exception as e:
            error_msg = str(e).lower()
            if "flood" in error_msg:
                return False, "操作过于频繁，请稍后重试", None
            elif "fresh_reset" in error_msg or "recently" in error_msg:
                return False, "已在冷却期中", None
            else:
                return False, f"请求重置失败: {str(e)[:50]}", None
    
    async def delete_reset_notification(self, client, account_name: str = "") -> bool:
        """
        删除来自777000（Telegram官方）的密码重置通知消息
        
        Args:
            client: TelegramClient实例
            account_name: 账号名称（用于日志）
            
        Returns:
            是否成功删除
        """
        try:
            # 获取777000实体（Telegram官方通知账号）
            entity = await asyncio.wait_for(
                client.get_entity(777000),
                timeout=10
            )
            
            # 获取最近的消息（通常重置通知是最新的几条之一）
            messages = await asyncio.wait_for(
                client.get_messages(entity, limit=10),  # 增加到10条确保覆盖
                timeout=10
            )
            
            deleted_count = 0
            for msg in messages:
                if msg.text:
                    # 检查是否是密码重置通知（多语言匹配，包含更多关键词）
                    text_lower = msg.text.lower()
                    if any(keyword in text_lower for keyword in [
                        # 英文关键词
                        'reset password',
                        'reset your telegram password',
                        'request to reset password',
                        'request to reset',
                        '2-step verification',
                        'two-step verification',
                        'cancel the password reset',
                        'cancel reset request',
                        'password reset request',
                        # 中文关键词
                        '重置密码',
                        '密码重置',
                        '二次验证',
                        '两步验证',
                        '二步验证',
                        '取消密码重置',
                        '取消重置',
                        # 俄语关键词
                        'сброс пароля',
                        'двухфакторн',
                        # 印尼语关键词
                        'reset kata sandi',
                        'verifikasi dua langkah',
                        # 其他语言
                        'réinitialiser',  # 法语
                        'zurücksetzen',    # 德语
                        'restablecer',     # 西班牙语
                    ]):
                        try:
                            await client.delete_messages(entity, msg.id)
                            deleted_count += 1
                            print(f"🗑️ [{account_name}] 已删除重置通知消息 (ID: {msg.id})")
                        except Exception as del_err:
                            print(f"⚠️ [{account_name}] 删除消息失败: {str(del_err)[:30]}")
            
            if deleted_count > 0:
                print(f"✅ [{account_name}] 成功删除 {deleted_count} 条重置通知")
                return True
            else:
                print(f"ℹ️ [{account_name}] 未找到需要删除的重置通知")
                return True  # 没有找到也算成功
                
        except Exception as e:
            print(f"⚠️ [{account_name}] 获取/删除通知失败: {str(e)[:50]}")
            return False
    
    async def connect_with_proxy_fallback(self, file_path: str, account_name: str, file_type: str = 'session') -> Tuple[Optional[TelegramClient], str, bool]:
        """
        使用代理轮换器连接，IP超时自动切换下一个重试（最多3次）
        支持 session 和 tdata 两种格式
        
        Returns:
            (client或None, 代理描述字符串, 是否成功连接)
        """
        # 检查代理是否可用
        proxy_enabled = self.db.get_proxy_enabled() if self.db else True
        use_proxy = config.USE_PROXY and proxy_enabled and len(self.proxy_rotator.proxies) > 0
        
        tried_proxies = []
        
        # 处理 tdata 格式
        if file_type == 'tdata':
            return await self._connect_tdata_with_proxy_fallback(file_path, account_name, use_proxy, tried_proxies)
        
        # 处理 session 格式
        session_base = file_path.replace('.session', '') if file_path.endswith('.session') else file_path
        
        # 优先尝试代理连接 - 使用代理轮换器
        if use_proxy:
            for attempt in range(self.max_proxy_retries):
                # 使用代理轮换器获取下一个代理
                proxy_info = self.proxy_rotator.get_next_proxy()
                if not proxy_info:
                    break
                
                # 使用内部格式用于去重，但不暴露给用户
                proxy_str_internal = self.format_proxy_string_internal(proxy_info)
                if proxy_str_internal in tried_proxies:
                    # 如果已尝试过这个代理，获取下一个
                    continue
                tried_proxies.append(proxy_str_internal)
                
                # 用于显示的代理字符串（隐藏详细信息）
                proxy_str = "使用代理"
                
                proxy_dict = self.create_proxy_dict(proxy_info)
                if not proxy_dict:
                    continue
                
                print(f"🌐 [{account_name}] 尝试代理连接 #{attempt + 1} (轮换)")
                
                client = None
                try:
                    # 住宅代理使用更长超时
                    timeout = config.RESIDENTIAL_PROXY_TIMEOUT if proxy_info.get('is_residential', False) else self.proxy_timeout
                    
                    client = TelegramClient(
                        session_base,
                        int(config.API_ID),
                        str(config.API_HASH),
                        timeout=timeout,
                        connection_retries=1,
                        retry_delay=1,
                        proxy=proxy_dict
                    )
                    
                    await asyncio.wait_for(client.connect(), timeout=timeout)
                    
                    # 检查授权
                    is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
                    if not is_authorized:
                        await client.disconnect()
                        return None, proxy_str, False
                    
                    print(f"✅ [{account_name}] 代理连接成功")
                    return client, proxy_str, True
                    
                except asyncio.TimeoutError:
                    print(f"⏱️ [{account_name}] 代理超时，切换下一个...")
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
                except Exception as e:
                    print(f"❌ [{account_name}] 代理连接失败 - {str(e)[:50]}")
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
        
        # 所有代理都失败，回退到本地连接
        print(f"🔄 [{account_name}] 所有代理失败，回退到本地连接...")
        try:
            client = TelegramClient(
                session_base,
                int(config.API_ID),
                str(config.API_HASH),
                timeout=15,
                connection_retries=2,
                retry_delay=1,
                proxy=None
            )
            
            await asyncio.wait_for(client.connect(), timeout=15)
            
            is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
            if not is_authorized:
                await client.disconnect()
                return None, "本地连接", False
            
            print(f"✅ [{account_name}] 本地连接成功")
            return client, "本地连接 (代理失败后回退)", True
            
        except Exception as e:
            print(f"❌ [{account_name}] 本地连接也失败: {str(e)[:50]}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return None, "本地连接", False
    
    async def _connect_tdata_with_proxy_fallback(self, tdata_path: str, account_name: str, 
                                                  use_proxy: bool, tried_proxies: list) -> Tuple[Optional[TelegramClient], str, bool]:
        """
        处理TData格式的连接（使用opentele转换）- 使用代理轮换器
        
        Returns:
            (client或None, 代理描述字符串, 是否成功连接)
        """
        if not OPENTELE_AVAILABLE:
            print(f"❌ [{account_name}] opentele库未安装，无法处理TData格式")
            return None, "本地连接", False
        
        # 优先尝试代理连接 - 使用代理轮换器
        if use_proxy:
            for attempt in range(self.max_proxy_retries):
                # 使用代理轮换器获取下一个代理
                proxy_info = self.proxy_rotator.get_next_proxy()
                if not proxy_info:
                    break
                
                # 使用内部格式用于去重，但不暴露给用户
                proxy_str_internal = self.format_proxy_string_internal(proxy_info)
                if proxy_str_internal in tried_proxies:
                    continue
                tried_proxies.append(proxy_str_internal)
                
                # 用于显示的代理字符串（隐藏详细信息）
                proxy_str = "使用代理"
                
                proxy_dict = self.create_proxy_dict(proxy_info)
                if not proxy_dict:
                    continue
                
                print(f"🌐 [{account_name}] TData代理连接 #{attempt + 1} (轮换)")
                
                client = None
                try:
                    # 使用opentele加载TData
                    tdesk = TDesktop(tdata_path)
                    
                    if not tdesk.isLoaded():
                        print(f"❌ [{account_name}] TData未授权或无效")
                        return None, proxy_str, False
                    
                    # 创建临时session名称（保存在sessions/temp目录）
                    os.makedirs(config.SESSIONS_BAK_DIR, exist_ok=True)
                    session_name = os.path.join(config.SESSIONS_BAK_DIR, f"temp_forget2fa_{int(time.time()*1000)}")
                    
                    # 住宅代理使用更长超时
                    timeout = config.RESIDENTIAL_PROXY_TIMEOUT if proxy_info.get('is_residential', False) else self.proxy_timeout
                    
                    # 转换为Telethon客户端（带代理）
                    client = await tdesk.ToTelethon(
                        session=session_name, 
                        flag=UseCurrentSession, 
                        api=API.TelegramDesktop,
                        proxy=proxy_dict
                    )
                    
                    await asyncio.wait_for(client.connect(), timeout=timeout)
                    
                    # 检查授权
                    is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
                    if not is_authorized:
                        await client.disconnect()
                        # 清理临时session文件
                        self._cleanup_temp_session(session_name)
                        return None, proxy_str, False
                    
                    print(f"✅ [{account_name}] TData代理连接成功")
                    return client, proxy_str, True
                    
                except asyncio.TimeoutError:
                    print(f"⏱️ [{account_name}] TData代理超时，切换下一个...")
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
                except Exception as e:
                    print(f"❌ [{account_name}] TData代理连接失败 - {str(e)[:50]}")
                    if client:
                        try:
                            await client.disconnect()
                        except:
                            pass
        
        # 所有代理都失败，回退到本地连接
        print(f"🔄 [{account_name}] TData所有代理失败，回退到本地连接...")
        try:
            tdesk = TDesktop(tdata_path)
            
            if not tdesk.isLoaded():
                print(f"❌ [{account_name}] TData未授权或无效")
                return None, "本地连接", False
            
            session_name = f"temp_forget2fa_{int(time.time()*1000)}"
            
            # 转换为Telethon客户端（无代理）
            client = await tdesk.ToTelethon(
                session=session_name, 
                flag=UseCurrentSession, 
                api=API.TelegramDesktop
            )
            
            await asyncio.wait_for(client.connect(), timeout=15)
            
            is_authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=5)
            if not is_authorized:
                await client.disconnect()
                self._cleanup_temp_session(session_name)
                return None, "本地连接", False
            
            print(f"✅ [{account_name}] TData本地连接成功")
            return client, "本地连接 (代理失败后回退)", True
            
        except Exception as e:
            print(f"❌ [{account_name}] TData本地连接也失败: {str(e)[:50]}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return None, "本地连接", False
    
    def _cleanup_temp_session(self, session_name: str):
        """清理临时session文件"""
        try:
            session_file = f"{session_name}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
        except:
            pass
    
    async def process_single_account(self, file_path: str, file_name: str, 
                                     file_type: str, batch_id: str) -> Dict:
        """
        处理单个账号（强制使用代理，失败后回退本地）
        
        Returns:
            结果字典
        """
        start_time = time.time()
        result = {
            'account_name': file_name,
            'phone': '',
            'file_type': file_type,
            'proxy_used': '',
            'status': 'failed',
            'error': '',
            'cooling_until': '',
            'elapsed': 0.0
        }
        
        async with self.semaphore:
            client = None
            try:
                # 1. 连接（优先代理，回退本地）- 支持 session 和 tdata 格式
                client, proxy_used, connected = await self.connect_with_proxy_fallback(
                    file_path, file_name, file_type
                )
                result['proxy_used'] = proxy_used
                
                if not connected or not client:
                    result['status'] = 'failed'
                    result['error'] = '连接失败 (所有代理和本地都失败)'
                    result['elapsed'] = time.time() - start_time
                    self.db.insert_forget_2fa_log(
                        batch_id, file_name, '', file_type, proxy_used,
                        'failed', result['error'], '', result['elapsed']
                    )
                    return result
                
                # 2. 获取用户信息
                try:
                    me = await asyncio.wait_for(client.get_me(), timeout=5)
                    result['phone'] = me.phone or ''
                    user_info = f"ID:{me.id}"
                    if me.username:
                        user_info += f" @{me.username}"
                except Exception as e:
                    user_info = "账号"
                
                # 3. 检测2FA状态
                has_2fa, status_msg, pwd_info = await self.check_2fa_status(client)
                
                if not has_2fa:
                    # 账号没有设置2FA
                    result['status'] = 'no_2fa'
                    result['error'] = status_msg
                    result['elapsed'] = time.time() - start_time
                    self.db.insert_forget_2fa_log(
                        batch_id, file_name, result['phone'], file_type, proxy_used,
                        'no_2fa', status_msg, '', result['elapsed']
                    )
                    print(f"⚠️ [{file_name}] {status_msg}")
                    return result
                
                # 4. 请求密码重置
                success, reset_msg, cooling_until = await self.request_password_reset(client)
                
                if success:
                    result['status'] = 'requested'
                    if cooling_until:
                        # 转换为北京时间显示
                        result['cooling_until'] = utc_to_beijing(cooling_until)
                        result['error'] = f"{reset_msg}，冷却期至: {result['cooling_until']} (北京时间)"
                    else:
                        result['error'] = reset_msg
                    print(f"✅ [{file_name}] {reset_msg}")
                    
                    # 5. 删除来自777000的重置通知消息
                    # 使用可配置的等待时间（默认0.5秒，从原来的2秒减少以提升速度）
                    await asyncio.sleep(self.notify_wait)
                    await self.delete_reset_notification(client, file_name)
                else:
                    # 检查是否已在冷却期
                    if "冷却期" in reset_msg or "recently" in reset_msg.lower():
                        result['status'] = 'cooling'
                        if cooling_until:
                            # 转换为北京时间显示
                            result['cooling_until'] = utc_to_beijing(cooling_until)
                            result['error'] = f"{reset_msg}，冷却期至: {result['cooling_until']} (北京时间)"
                        else:
                            result['error'] = reset_msg
                        print(f"⏳ [{file_name}] {reset_msg}")  # 冷却期使用⏳图标
                    else:
                        result['status'] = 'failed'
                        result['error'] = reset_msg
                        print(f"❌ [{file_name}] {reset_msg}")
                
                result['elapsed'] = time.time() - start_time
                self.db.insert_forget_2fa_log(
                    batch_id, file_name, result['phone'], file_type, proxy_used,
                    result['status'], result['error'], result['cooling_until'], result['elapsed']
                )
                
            except Exception as e:
                result['status'] = 'failed'
                result['error'] = f"处理异常: {str(e)[:50]}"
                result['elapsed'] = time.time() - start_time
                self.db.insert_forget_2fa_log(
                    batch_id, file_name, result['phone'], file_type, result['proxy_used'],
                    'failed', result['error'], '', result['elapsed']
                )
                print(f"❌ [{file_name}] {result['error']}")
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
            
            return result
    
    async def batch_process_with_progress(self, files: List[Tuple[str, str]], 
                                         file_type: str, 
                                         batch_id: str,
                                         progress_callback=None) -> Dict:
        """
        批量处理（高速+防封混合模式 - 批量并发，每批次间隔3-6秒）
        
        Args:
            files: [(文件路径, 文件名), ...]
            file_type: 'session' 或 'tdata'
            batch_id: 批次ID
            progress_callback: 进度回调函数
            
        Returns:
            结果字典
        """
        results = {
            'requested': [],    # 已请求重置
            'no_2fa': [],       # 无需重置
            'cooling': [],      # 冷却期中
            'failed': []        # 失败
        }
        
        total = len(files)
        processed = [0]  # 使用列表以便在闭包中修改
        start_time = time.time()
        results_lock = asyncio.Lock()  # 用于线程安全地更新results
        
        async def process_single_with_callback(file_path: str, file_name: str):
            """处理单个账号并更新结果"""
            # 处理单个账号
            result = await self.process_single_account(
                file_path, file_name, file_type, batch_id
            )
            
            # 线程安全地更新结果
            async with results_lock:
                processed[0] += 1
                
                # 分类结果
                status = result.get('status', 'failed')
                if status == 'requested':
                    results['requested'].append(result)
                elif status == 'no_2fa':
                    results['no_2fa'].append(result)
                elif status == 'cooling':
                    results['cooling'].append(result)
                else:
                    results['failed'].append(result)
                
                # 调用进度回调
                if progress_callback:
                    elapsed = time.time() - start_time
                    speed = processed[0] / elapsed if elapsed > 0 else 0
                    await progress_callback(processed[0], total, results, speed, elapsed, result)
            
            return result
        
        # 批量并发处理（每批50个，批次间延迟3-6秒）
        batch_size = self.concurrent_limit
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            
            print(f"📦 处理批次 {i//batch_size + 1}/{(len(files)-1)//batch_size + 1}，包含 {len(batch)} 个账号")
            
            # 创建任务列表
            tasks = [
                process_single_with_callback(file_path, file_name)
                for file_path, file_name in batch
            ]
            
            # 并发执行当前批次
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # 批次间延迟（防风控）- 最后一批不延迟
            if i + batch_size < len(files):
                delay = random.uniform(self.min_delay, self.max_delay)
                print(f"⏳ 批次间延迟 {delay:.1f} 秒...")
                await asyncio.sleep(delay)
        
        return results
    
    def create_result_files(self, results: Dict, task_id: str, files: List[Tuple[str, str]], file_type: str, user_id: int = None) -> List[Tuple[str, str, str, int]]:
        """
        生成结果压缩包（按状态分类）
        
        Returns:
            [(zip路径, txt路径, 状态名称, 数量), ...]
        """
        result_files = []
        
        # 如果没有提供user_id，使用默认语言
        if user_id is None:
            user_id = 0  # 使用默认语言
        
        # 状态映射
        status_map = {
            'requested': (t(user_id, 'forget_2fa_status_requested'), '✅'),
            'no_2fa': (t(user_id, 'forget_2fa_status_no_2fa'), '⚠️'),
            'cooling': (t(user_id, 'forget_2fa_status_cooling'), '⏳'),
            'failed': (t(user_id, 'forget_2fa_status_failed'), '❌')
        }
        
        # 创建文件路径映射
        file_path_map = {name: path for path, name in files}
        
        for status_key, items in results.items():
            if not items:
                continue
            
            status_name, emoji = status_map.get(status_key, (status_key, '📄'))
            
            print(f"📦 正在创建 {status_name} 结果文件，包含 {len(items)} 个账号")
            
            # 创建临时目录
            timestamp_short = str(int(time.time()))[-6:]
            status_temp_dir = os.path.join(config.RESULTS_DIR, f"forget2fa_{status_key}_{timestamp_short}")
            os.makedirs(status_temp_dir, exist_ok=True)
            
            try:
                for item in items:
                    account_name = item.get('account_name', '')
                    file_path = file_path_map.get(account_name, '')
                    
                    if not file_path or not os.path.exists(file_path):
                        continue
                    
                    if file_type == 'session':
                        # 复制session文件
                        dest_path = os.path.join(status_temp_dir, account_name)
                        shutil.copy2(file_path, dest_path)
                        
                        # 复制对应的json文件（如果存在）
                        json_name = account_name.replace('.session', '.json')
                        json_path = os.path.join(os.path.dirname(file_path), json_name)
                        if os.path.exists(json_path):
                            shutil.copy2(json_path, os.path.join(status_temp_dir, json_name))
                    
                    elif file_type == 'tdata':
                        # TData格式正确结构: 号码/tdata/D877F783D5D3EF8C
                        # file_path 指向的是 tdata 目录本身
                        # account_name 是号码（如 123456789）
                        
                        # 创建 号码/tdata 目录结构
                        account_dir = os.path.join(status_temp_dir, account_name)
                        tdata_dest_dir = os.path.join(account_dir, "tdata")
                        os.makedirs(tdata_dest_dir, exist_ok=True)
                        
                        # 复制tdata目录内容到 号码/tdata/
                        if os.path.isdir(file_path):
                            for item_name in os.listdir(file_path):
                                src_item = os.path.join(file_path, item_name)
                                dst_item = os.path.join(tdata_dest_dir, item_name)
                                if os.path.isdir(src_item):
                                    shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(src_item, dst_item)
                        
                        # 同时复制tdata同级目录下的密码文件（如2fa.txt等）
                        parent_dir = os.path.dirname(file_path)
                        for password_file in ['2fa.txt', 'twofa.txt', 'password.txt']:
                            password_path = os.path.join(parent_dir, password_file)
                            if os.path.exists(password_path):
                                shutil.copy2(password_path, os.path.join(account_dir, password_file))
                
                # 创建ZIP文件 - 使用翻译
                zip_key_map = {
                    'requested': 'zip_forget_2fa_reset',
                    'no_2fa': 'zip_forget_2fa_no_reset',
                    'cooling': 'zip_forget_2fa_cooling',
                    'failed': 'zip_forget_2fa_failed'
                }
                zip_key = zip_key_map.get(status_key, 'zip_forget_2fa_reset')
                zip_filename = t(user_id, zip_key).format(count=len(items)) + ".zip"
                zip_path = os.path.join(config.RESULTS_DIR, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files_list in os.walk(status_temp_dir):
                        for file in files_list:
                            file_path_full = os.path.join(root, file)
                            arcname = os.path.relpath(file_path_full, status_temp_dir)
                            zipf.write(file_path_full, arcname)
                
                # 创建TXT报告 - 使用翻译
                report_key_map = {
                    'requested': 'report_forget_2fa_reset',
                    'no_2fa': 'report_forget_2fa_no_reset',
                    'cooling': 'report_forget_2fa_cooling',
                    'failed': 'report_forget_2fa_failed'
                }
                report_key = report_key_map.get(status_key, 'report_forget_2fa_reset')
                txt_filename = t(user_id, report_key).format(count=len(items))
                txt_path = os.path.join(config.RESULTS_DIR, txt_filename)
                
                # 获取报告标题翻译键
                title_key_map = {
                    'requested': 'report_forget_2fa_title_reset',
                    'no_2fa': 'report_forget_2fa_title_no_reset',
                    'cooling': 'report_forget_2fa_title_cooling',
                    'failed': 'report_forget_2fa_title_failed'
                }
                title_key = title_key_map.get(status_key, 'report_forget_2fa_title_reset')
                
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(f"{t(user_id, title_key)}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(f"{t(user_id, 'report_forget_2fa_total').format(count=len(items))}\n")
                    f.write(f"{t(user_id, 'report_forget_2fa_generated').format(time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST'))}\n\n")
                    
                    f.write(f"{t(user_id, 'report_forget_2fa_detail_list')}\n")
                    f.write("-" * 50 + "\n\n")
                    
                    for idx, item in enumerate(items, 1):
                        f.write(f"{idx}. {emoji} {item.get('account_name', '')}\n")
                        phone = item.get('phone', t(user_id, 'forget_2fa_status_unknown'))
                        f.write(f"   {t(user_id, 'report_forget_2fa_phone').format(phone=phone)}\n")
                        
                        # 状态描述 - 使用正确的翻译键
                        error_msg = item.get('error', status_name)
                        
                        # 根据状态键选择正确的状态翻译
                        if status_key == 'requested':
                            cooling_date = item.get('cooling_until', '')
                            if cooling_date:
                                status_text = t(user_id, 'report_forget_2fa_status_reset_waiting').format(date=cooling_date)
                            else:
                                status_text = t(user_id, 'report_forget_2fa_status_reset_waiting').format(date='N/A')
                        elif status_key == 'no_2fa':
                            if 'detect' in error_msg.lower() or '检测' in error_msg:
                                status_text = t(user_id, 'report_forget_2fa_status_detect_failed').format(error=error_msg)
                            else:
                                status_text = t(user_id, 'report_forget_2fa_status_no_2fa')
                        elif status_key == 'cooling':
                            cooling_date = item.get('cooling_until', '')
                            status_text = t(user_id, 'report_forget_2fa_status_in_cooling').format(date=cooling_date)
                        else:  # failed
                            status_text = t(user_id, 'report_forget_2fa_status_connection_failed')
                        
                        f.write(f"   {status_text}\n")
                        
                        # 隐藏代理详细信息，保护用户隐私
                        masked_proxy = self.mask_proxy_for_display(item.get('proxy_used', t(user_id, 'forget_2fa_status_local')), user_id)
                        f.write(f"   {masked_proxy}\n")
                        
                        if item.get('cooling_until') and status_key != 'requested':
                            f.write(f"   {t(user_id, 'report_forget_2fa_cooling_until').format(date=item.get('cooling_until'))}\n")
                        elapsed_time = f"{item.get('elapsed', 0):.1f}"
                        f.write(f"   {t(user_id, 'report_forget_2fa_duration').format(time=elapsed_time)}\n\n")
                
                print(f"✅ 创建文件: {zip_filename}")
                result_files.append((zip_path, txt_path, status_name, len(items)))
                
            except Exception as e:
                print(f"❌ 创建{status_name}结果文件失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 清理临时目录
                if os.path.exists(status_temp_dir):
                    shutil.rmtree(status_temp_dir, ignore_errors=True)
        
        return result_files

# ================================
# 设备参数加载器
# ================================




# ===== Handler Methods from EnhancedBot =====

    def handle_change_2fa(self, query):
    """处理修改2FA"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用2FA修改功能")
        return
    
    if not TELETHON_AVAILABLE:
        self.safe_edit_message(query, "❌ 2FA修改功能不可用\n\n原因: Telethon库未安装")
        return
    
    text = f"""

    def handle_forget_2fa(self, query):
    """处理忘记2FA"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用忘记2FA功能")
        return
    
    if not TELETHON_AVAILABLE:
        self.safe_edit_message(query, "❌ 忘记2FA功能不可用\n\n原因: Telethon库未安装")
        return
    
    # 检查代理是否可用
    proxy_count = len(self.proxy_manager.proxies)
    proxy_warning = ""
    if proxy_count < 3:
        proxy_warning = f"\n⚠️ <b>{t(user_id, 'forget_2fa_proxy_warning').format(count=proxy_count)}</b>\n"
    
    # 构建代理模式状态文本
    proxy_mode_text = t(user_id, 'forget_2fa_proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'forget_2fa_proxy_mode_disabled')
    
    text = f"""

    def handle_add_2fa(self, query):
    """处理添加2FA功能"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, t(user_id, 'add_2fa_need_member'))
        return
    
    text = f"""

    def handle_remove_2fa(self, query):
    """处理删除2FA入口"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用删除2FA功能")
        return
    
    if not TELETHON_AVAILABLE:
        self.safe_edit_message(query, "❌ 删除2FA功能不可用\n\n原因: Telethon库未安装")
        return
    
    text = f"""

    def handle_add_2fa_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理添加2FA密码输入"""
    if user_id not in self.pending_add_2fa_tasks:
        self.safe_send_message(update, t(user_id, 'add_2fa_no_pending_task'))
        return
    
    task = self.pending_add_2fa_tasks[user_id]
    
    # 检查超时（5分钟）
    if time.time() - task['start_time'] > 300:
        del self.pending_add_2fa_tasks[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, t(user_id, 'add_2fa_operation_timeout'))
        return
    
    # 验证密码
    two_fa_password = text.strip()
    
    if not two_fa_password:
        self.safe_send_message(update, t(user_id, 'add_2fa_password_empty'))
        return
    
    # 确认接收密码
    self.safe_send_message(
        update,
        f"<b>{t(user_id, 'add_2fa_password_received')}</b>\n\n"
        f"{t(user_id, 'add_2fa_password_display').format(password=two_fa_password)}\n\n"
        f"{t(user_id, 'add_2fa_processing_now')}",
        'HTML'
    )
    
    # 异步处理添加2FA
    def process_add_2fa():
        asyncio.run(self.complete_add_2fa(update, context, user_id, two_fa_password))
    
    thread = threading.Thread(target=process_add_2fa, daemon=True)
    thread.start()


async def process_forget_2fa(self, update, context, document):
    """忘记2FA处理 - 批量请求密码重置"""
    user_id = update.effective_user.id
    start_time = time.time()
    task_id = f"{user_id}_{int(start_time)}"
    batch_id = f"forget2fa_{task_id}"
    
    progress_msg = self.safe_send_message(update, f"<b>{t(user_id, 'forget_2fa_processing_file')}</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="temp_forget2fa_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 使用FileProcessor扫描
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, task_id)
        
        if not files:
            try:
                progress_msg.edit_text(
                    f"<b>{t(user_id, 'forget_2fa_no_valid_files')}</b>\n\n{t(user_id, 'forget_2fa_ensure_format')}",
                    parse_mode='HTML'
                )
            except:
                pass
            return
        
        total_files = len(files)
        proxy_count = len(self.proxy_manager.proxies)
        
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'forget_2fa_processing')}</b>\n\n"
                f"{t(user_id, 'forget_2fa_found_accounts').format(count=total_files)}\n"
                f"{t(user_id, 'forget_2fa_format').format(format=file_type.upper())}\n"
                f"{t(user_id, 'forget_2fa_proxy_count').format(count=proxy_count)}\n\n"
                f"{t(user_id, 'forget_2fa_initializing')}",
                parse_mode='HTML'
            )
        except:
            pass
        
        # 创建Forget2FAManager实例
        forget_manager = Forget2FAManager(self.proxy_manager, self.db)
        
        # 进度回调函数
        last_update_time = [time.time()]
        
        async def progress_callback(processed, total, results, speed, elapsed, current_result):
            # 限制更新频率（每3秒最多更新一次）
            current_time = time.time()
            if current_time - last_update_time[0] < 3 and processed < total:
                return
            last_update_time[0] = current_time
            
            # 格式化时间 - 使用翻译
            minutes = int(elapsed) // 60
            seconds = int(elapsed) % 60
            if minutes > 0:
                time_str = f"{minutes}{t(user_id, 'minutes_unit')}{seconds}{t(user_id, 'seconds_unit')}"
            else:
                time_str = f"{seconds}{t(user_id, 'seconds_unit')}"
            
            # 统计各状态数量
            requested = len(results.get('requested', []))
            no_2fa = len(results.get('no_2fa', []))
            cooling = len(results.get('cooling', []))
            failed = len(results.get('failed', []))
            pending = total - processed
            
            # 当前处理状态
            current_name = current_result.get('account_name', '')
            current_status = current_result.get('status', '')
            # 隐藏代理详细信息，保护用户隐私
            current_proxy_raw = current_result.get('proxy_used', t(user_id, 'forget_2fa_status_local'))
            current_proxy = Forget2FAManager.mask_proxy_for_display(current_proxy_raw, user_id)
            
            # 状态映射 - 使用翻译
            status_map = {
                'requested': t(user_id, 'forget_2fa_status_reset'),
                'no_2fa': t(user_id, 'forget_2fa_status_no_reset'),
                'cooling': t(user_id, 'forget_2fa_status_cooling'),
                'failed': t(user_id, 'forget_2fa_status_failed')
            }
            status_emoji = status_map.get(current_status, t(user_id, 'status_processing'))
            
            # 计算百分比
            percent = processed * 100 // total if total > 0 else 0
            
            progress_text = f"""



# ===== Handler Methods =====

    def handle_change_2fa(self, query):
    """处理修改2FA"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用2FA修改功能")
        return
    
    if not TELETHON_AVAILABLE:
        self.safe_edit_message(query, "❌ 2FA修改功能不可用\n\n原因: Telethon库未安装")
        return
    
    text = f"""

    def handle_forget_2fa(self, query):
    """处理忘记2FA"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用忘记2FA功能")
        return
    
    if not TELETHON_AVAILABLE:
        self.safe_edit_message(query, "❌ 忘记2FA功能不可用\n\n原因: Telethon库未安装")
        return
    
    # 检查代理是否可用
    proxy_count = len(self.proxy_manager.proxies)
    proxy_warning = ""
    if proxy_count < 3:
        proxy_warning = f"\n⚠️ <b>{t(user_id, 'forget_2fa_proxy_warning').format(count=proxy_count)}</b>\n"
    
    # 构建代理模式状态文本
    proxy_mode_text = t(user_id, 'forget_2fa_proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'forget_2fa_proxy_mode_disabled')
    
    text = f"""

    def handle_add_2fa(self, query):
    """处理添加2FA功能"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查权限
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, t(user_id, 'add_2fa_need_member'))
        return
    
    text = f"""

    def handle_add_2fa_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理添加2FA密码输入"""
    if user_id not in self.pending_add_2fa_tasks:
        self.safe_send_message(update, t(user_id, 'add_2fa_no_pending_task'))
        return
    
    task = self.pending_add_2fa_tasks[user_id]
    
    # 检查超时（5分钟）
    if time.time() - task['start_time'] > 300:
        del self.pending_add_2fa_tasks[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, t(user_id, 'add_2fa_operation_timeout'))
        return
    
    # 验证密码
    two_fa_password = text.strip()
    
    if not two_fa_password:
        self.safe_send_message(update, t(user_id, 'add_2fa_password_empty'))
        return
    
    # 确认接收密码
    self.safe_send_message(
        update,
        f"<b>{t(user_id, 'add_2fa_password_received')}</b>\n\n"
        f"{t(user_id, 'add_2fa_password_display').format(password=two_fa_password)}\n\n"
        f"{t(user_id, 'add_2fa_processing_now')}",
        'HTML'
    )
    
    # 异步处理添加2FA
    def process_add_2fa():
        asyncio.run(self.complete_add_2fa(update, context, user_id, two_fa_password))
    
    thread = threading.Thread(target=process_add_2fa, daemon=True)
    thread.start()


async def process_forget_2fa(self, update, context, document):
    """忘记2FA处理 - 批量请求密码重置"""
    user_id = update.effective_user.id
    start_time = time.time()
    task_id = f"{user_id}_{int(start_time)}"
    batch_id = f"forget2fa_{task_id}"
    
    progress_msg = self.safe_send_message(update, f"<b>{t(user_id, 'forget_2fa_processing_file')}</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="temp_forget2fa_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 使用FileProcessor扫描
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, task_id)
        
        if not files:
            try:
                progress_msg.edit_text(
                    f"<b>{t(user_id, 'forget_2fa_no_valid_files')}</b>\n\n{t(user_id, 'forget_2fa_ensure_format')}",
                    parse_mode='HTML'
                )
            except:
                pass
            return
        
        total_files = len(files)
        proxy_count = len(self.proxy_manager.proxies)
        
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'forget_2fa_processing')}</b>\n\n"
                f"{t(user_id, 'forget_2fa_found_accounts').format(count=total_files)}\n"
                f"{t(user_id, 'forget_2fa_format').format(format=file_type.upper())}\n"
                f"{t(user_id, 'forget_2fa_proxy_count').format(count=proxy_count)}\n\n"
                f"{t(user_id, 'forget_2fa_initializing')}",
                parse_mode='HTML'
            )
        except:
            pass
        
        # 创建Forget2FAManager实例
        forget_manager = Forget2FAManager(self.proxy_manager, self.db)
        
        # 进度回调函数
        last_update_time = [time.time()]
        
        async def progress_callback(processed, total, results, speed, elapsed, current_result):
            # 限制更新频率（每3秒最多更新一次）
            current_time = time.time()
            if current_time - last_update_time[0] < 3 and processed < total:
                return
            last_update_time[0] = current_time
            
            # 格式化时间 - 使用翻译
            minutes = int(elapsed) // 60
            seconds = int(elapsed) % 60
            if minutes > 0:
                time_str = f"{minutes}{t(user_id, 'minutes_unit')}{seconds}{t(user_id, 'seconds_unit')}"
            else:
                time_str = f"{seconds}{t(user_id, 'seconds_unit')}"
            
            # 统计各状态数量
            requested = len(results.get('requested', []))
            no_2fa = len(results.get('no_2fa', []))
            cooling = len(results.get('cooling', []))
            failed = len(results.get('failed', []))
            pending = total - processed
            
            # 当前处理状态
            current_name = current_result.get('account_name', '')
            current_status = current_result.get('status', '')
            # 隐藏代理详细信息，保护用户隐私
            current_proxy_raw = current_result.get('proxy_used', t(user_id, 'forget_2fa_status_local'))
            current_proxy = Forget2FAManager.mask_proxy_for_display(current_proxy_raw, user_id)
            
            # 状态映射 - 使用翻译
            status_map = {
                'requested': t(user_id, 'forget_2fa_status_reset'),
                'no_2fa': t(user_id, 'forget_2fa_status_no_reset'),
                'cooling': t(user_id, 'forget_2fa_status_cooling'),
                'failed': t(user_id, 'forget_2fa_status_failed')
            }
            status_emoji = status_map.get(current_status, t(user_id, 'status_processing'))
            
            # 计算百分比
            percent = processed * 100 // total if total > 0 else 0
            
            progress_text = f"""

