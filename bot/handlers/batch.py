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

class BatchCreationConfig:
    """批量创建配置"""
    creation_type: str  # 'group' or 'channel'
    count_per_account: int  # 每个账号创建的数量
    admin_username: str = ""  # 管理员用户名（单个，向后兼容）
    admin_usernames: List[str] = field(default_factory=list)  # 管理员用户名列表（支持多个）
    group_names: List[str] = field(default_factory=list)  # 群组/频道名称列表
    group_descriptions: List[str] = field(default_factory=list)  # 群组/频道简介列表
    username_mode: str = "auto"  # 'auto' (自动生成), 'custom' (自定义)
    custom_usernames: List[str] = field(default_factory=list)  # 自定义用户名列表


@dataclass

class BatchCreationResult:
    """创建结果"""
    account_name: str
    phone: str
    creation_type: str  # 'group' or 'channel'
    name: str
    description: str = ""
    username: Optional[str] = None
    invite_link: Optional[str] = None
    status: str = 'pending'  # 'success', 'failed', 'skipped'
    error: Optional[str] = None
    creator_id: Optional[int] = None
    creator_username: Optional[str] = None
    admin_username: Optional[str] = None  # 向后兼容，保留单个
    admin_usernames: List[str] = field(default_factory=list)  # 成功添加的管理员列表
    admin_failures: List[str] = field(default_factory=list)  # 添加失败的管理员及原因
    created_at: str = field(default_factory=lambda: datetime.now(BEIJING_TZ).isoformat())


@dataclass

class BatchAccountInfo:
    """账号信息"""
    session_path: str
    file_name: str
    file_type: str  # 'session' or 'tdata'
    phone: Optional[str] = None
    is_valid: bool = False
    client: Optional[Any] = None
    daily_created: int = 0
    daily_remaining: int = 0
    validation_error: Optional[str] = None
    # 连接参数（用于在新事件循环中重新连接）
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    proxy_dict: Optional[Any] = None
    # TData转换后的Session路径（仅用于TData类型）
    converted_session_path: Optional[str] = None



class BatchCreatorService:
    """批量创建服务"""
    
    # 常量定义
    MAX_CONTACTS_TO_CHECK = 10  # 检查联系人列表时的最大数量
    
    def __init__(self, db, proxy_manager, device_loader, config_obj):
        """初始化批量创建服务"""
        self.db = db
        self.proxy_manager = proxy_manager
        self.device_loader = device_loader
        self.config = config_obj
        self.daily_limit = config_obj.BATCH_CREATE_DAILY_LIMIT
        
        logger.info(f"📦 批量创建服务初始化，每日限制: {self.daily_limit}")
    
    def generate_random_username(self) -> str:
        """生成随机用户名 - 完全随机，无前缀，避免相似"""
        # 随机选择用户名类型：纯字母或字母+数字
        use_digits = random.choice([True, False])
        
        # 随机长度在5-15之间，增加多样性
        length = random.randint(5, 15)
        
        # 确保第一个字符始终是字母（Telegram要求）
        first_char = random.choice(string.ascii_lowercase)
        
        if use_digits:
            # 字母+数字混合
            remaining_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length-1))
        else:
            # 纯字母
            remaining_chars = ''.join(random.choices(string.ascii_lowercase, k=length-1))
        
        username = first_char + remaining_chars
        
        # Telegram用户名规则：5-32字符，只能包含字母、数字和下划线
        return username[:32]
    
    def parse_name_template(self, template: str, number: int, prefix: str = "", suffix: str = "") -> str:
        """解析命名模板"""
        # 检查原始模板中是否有占位符
        has_placeholder = '{n}' in template or '{num}' in template
        
        # 替换占位符
        name = template.replace('{n}', str(number)).replace('{num}', str(number))
        
        # 如果原始模板中没有占位符，在末尾添加序号
        if not has_placeholder:
            name = f"{template}{number}"
        
        # 添加前缀和后缀
        if prefix:
            name = f"{prefix}{name}"
        if suffix:
            name = f"{name}{suffix}"
        return name
    
    async def validate_account(
        self, 
        account: BatchAccountInfo,
        api_id: int,
        api_hash: str,
        proxy_dict: Optional[Dict] = None,
        user_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """验证账号有效性 - 支持TData自动转换"""
        client = None
        temp_session_path = None
        
        try:
            # 问题1: TData格式需要先转换为Session
            session_path = account.session_path
            
            if account.file_type == "tdata":
                # TData需要转换为临时Session
                print(f"🔄 [批量创建] [{account.file_name}] 开始TData转Session转换...")
                
                if not OPENTELE_AVAILABLE:
                    return False, "opentele库未安装，无法转换TData"
                
                try:
                    # 加载TData
                    tdesk = TDesktop(account.session_path)
                    if not tdesk.isLoaded():
                        return False, "TData未授权或无效"
                    
                    # 创建临时Session（使用用户ID前缀，确保隔离）
                    os.makedirs(config.SESSIONS_BAK_DIR, exist_ok=True)
                    if user_id:
                        temp_session_name = f"user_{user_id}_batch_{time.time_ns()}"
                    else:
                        temp_session_name = f"batch_validate_{time.time_ns()}"
                    temp_session_path = os.path.join(config.SESSIONS_BAK_DIR, temp_session_name)
                    
                    # 转换TData到Session
                    temp_client = await tdesk.ToTelethon(
                        session=temp_session_path,
                        flag=UseCurrentSession,
                        api=API.TelegramDesktop
                    )
                    await temp_client.disconnect()
                    
                    session_path = f"{temp_session_path}.session"
                    if not os.path.exists(session_path):
                        return False, "Session转换失败：文件未生成"
                    
                    print(f"✅ [批量创建] [{account.file_name}] TData转换完成")
                    
                except Exception as e:
                    error_msg = f"TData转换失败: {str(e)[:50]}"
                    logger.error(f"❌ {error_msg} - {account.file_name}")
                    return False, error_msg
            
            # 使用Session进行验证（无论是原始Session还是从TData转换的）
            # 移除.session后缀（如果有）因为TelegramClient会自动添加
            session_base = session_path.replace('.session', '') if session_path.endswith('.session') else session_path
            
            client = TelegramClient(
                session_base,
                api_id,
                api_hash,
                proxy=proxy_dict,
                timeout=15
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False, "账号未授权"
            
            me = await client.get_me()
            account.phone = me.phone if me.phone else "未知"
            account.is_valid = True
            # 保存连接参数以便在新事件循环中重新连接
            account.api_id = api_id
            account.api_hash = api_hash
            account.proxy_dict = proxy_dict
            account.daily_created = self.db.get_daily_creation_count(account.phone)
            account.daily_remaining = max(0, self.daily_limit - account.daily_created)
            
            # 对于TData，保存转换后的Session路径
            if account.file_type == "tdata" and temp_session_path:
                account.converted_session_path = temp_session_path
                print(f"💾 [批量创建] [{account.file_name}] 已保存转换后的Session路径")
            
            # 断开连接，稍后在执行阶段重新连接
            await client.disconnect()
            account.client = None
            
            return True, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 验证账号失败 {account.file_name}: {error_msg}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return False, error_msg
        finally:
            # 注意: 不要删除临时Session文件，因为批量创建时还需要使用
            # 会在批量创建完成后统一清理
            pass
    
    async def create_group(
        self,
        client: TelegramClient,
        name: str,
        username: Optional[str] = None,
        description: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """创建超级群组（使用 megagroup 模式）
        
        注意：此方法创建的是超级群组，而非基础群组。
        超级群组支持用户名、更多成员、更多功能。
        """
        try:
            # 直接创建超级群组（megagroup），避免基础群组的限制
            # 使用 CreateChannelRequest 与 megagroup=True 创建超级群组
            # 这样可以直接设置用户名和描述，无需迁移
            result = await client(functions.channels.CreateChannelRequest(
                title=name,
                about=description or "",
                megagroup=True  # True = 超级群组, False = 频道
            ))
            group = result.chats[0]
            
            actual_username = None
            if username:
                try:
                    await client(functions.channels.UpdateUsernameRequest(channel=group, username=username))
                    actual_username = username
                except (UsernameOccupiedError, UsernameInvalidError) as e:
                    logger.warning(f"⚠️ 用户名 '{username}' 设置失败: {e}")
                except RPCError as e:
                    logger.warning(f"⚠️ 设置用户名失败: {e}")
            
            if actual_username:
                invite_link = f"https://t.me/{actual_username}"
            else:
                try:
                    # 使用正确的API：ExportChatInviteRequest
                    invite_result = await client(functions.messages.ExportChatInviteRequest(peer=group.id))
                    invite_link = invite_result.link
                except RPCError as e:
                    logger.warning(f"⚠️ 获取邀请链接失败: {e}")
                    invite_link = None
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return True, invite_link, actual_username, None
        except FloodWaitError as e:
            return False, None, None, f"频率限制，需等待 {e.seconds} 秒"
        except RPCError as e:
            logger.error(f"❌ 创建群组失败 (RPC错误): {e}")
            return False, None, None, str(e)
        except Exception as e:
            logger.error(f"❌ 创建群组失败: {e}")
            return False, None, None, str(e)
    
    async def create_channel(
        self,
        client: TelegramClient,
        name: str,
        username: Optional[str] = None,
        description: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """创建频道"""
        try:
            result = await client(functions.channels.CreateChannelRequest(
                title=name,
                about=description or "",
                megagroup=False
            ))
            channel = result.chats[0]
            
            actual_username = None
            if username:
                try:
                    await client(functions.channels.UpdateUsernameRequest(channel=channel, username=username))
                    actual_username = username
                except (UsernameOccupiedError, UsernameInvalidError) as e:
                    logger.warning(f"⚠️ 用户名 '{username}' 设置失败: {e}")
                except RPCError as e:
                    logger.warning(f"⚠️ 设置用户名失败: {e}")
            
            if actual_username:
                invite_link = f"https://t.me/{actual_username}"
            else:
                try:
                    # 使用正确的API：ExportChatInviteRequest
                    invite_result = await client(functions.messages.ExportChatInviteRequest(peer=channel.id))
                    invite_link = invite_result.link
                except RPCError as e:
                    logger.warning(f"⚠️ 获取邀请链接失败: {e}")
                    invite_link = None
            
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return True, invite_link, actual_username, None
        except FloodWaitError as e:
            return False, None, None, f"频率限制，需等待 {e.seconds} 秒"
        except RPCError as e:
            logger.error(f"❌ 创建频道失败 (RPC错误): {e}")
            return False, None, None, str(e)
        except Exception as e:
            logger.error(f"❌ 创建频道失败: {e}")
            return False, None, None, str(e)
    
    async def create_single(
        self,
        account: BatchAccountInfo,
        config: BatchCreationConfig,
        number: int
    ) -> BatchCreationResult:
        """为单个账号创建一个群组/频道"""
        result = BatchCreationResult(
            account_name=account.file_name,
            phone=account.phone or "未知",
            creation_type=config.creation_type,
            name=""
        )
        
        try:
            if account.daily_remaining <= 0:
                result.status = 'skipped'
                result.error = '已达每日创建上限'
                return result
            
            # 如果客户端未连接，重新连接
            if not account.client:
                # 【关键修复】移除.session后缀（如果有），因为TelegramClient会自动添加
                session_base = account.session_path.replace('.session', '') if account.session_path.endswith('.session') else account.session_path
                account.client = TelegramClient(
                    session_base,
                    account.api_id,
                    account.api_hash,
                    proxy=account.proxy_dict,
                    timeout=15
                )
                await account.client.connect()
            
            name = self.parse_name_template(
                config.name_template, number, config.name_prefix, config.name_suffix
            )
            result.name = name
            
            username = None
            if config.username_mode == 'random':
                username = self.generate_random_username()  # 完全随机，无前缀
            elif config.username_mode == 'custom' and config.custom_username_template:
                username_template = config.custom_username_template.replace('{n}', str(number))
                username = username_template.replace('{num}', str(number))
            
            if config.creation_type == 'group':
                success, invite_link, actual_username, error = await self.create_group(
                    account.client, name, username, config.description
                )
            else:
                success, invite_link, actual_username, error = await self.create_channel(
                    account.client, name, username, config.description
                )
            
            if success:
                result.status = 'success'
                result.invite_link = invite_link
                result.username = actual_username
                me = await account.client.get_me()
                result.creator_id = me.id
                self.db.record_creation(account.phone, config.creation_type, name, invite_link, actual_username, me.id)
                account.daily_created += 1
                account.daily_remaining -= 1
            else:
                result.status = 'failed'
                result.error = error
        except Exception as e:
            result.status = 'failed'
            result.error = str(e)
        
        return result
    
    async def add_admin_to_group(
        self,
        client: TelegramClient,
        chat_id: int,
        admin_username: str
    ) -> Tuple[bool, Optional[str]]:
        """添加管理员到群组/频道（直接设置管理员权限，自动邀请用户）
        
        优化方案：不单独邀请，直接使用 EditAdminRequest 设置管理员权限
        EditAdminRequest 会自动邀请用户到群组/频道，减少API调用和频率限制
        """
        try:
            if not admin_username:
                return True, None
            
            # 查找用户
            try:
                user = await client.get_entity(admin_username)
            except ValueError:
                return False, f"用户名 @{admin_username} 不存在或无效"
            except Exception as e:
                error_msg = str(e).lower()
                if "username not" in error_msg or "no user" in error_msg:
                    return False, f"用户 @{admin_username} 不存在"
                elif "username invalid" in error_msg:
                    return False, f"用户名 @{admin_username} 格式无效"
                return False, f"无法找到用户 @{admin_username}: {str(e)}"
            
            # 直接设置为管理员（EditAdminRequest 会自动邀请用户到群组）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await client(functions.channels.EditAdminRequest(
                        channel=chat_id,
                        user_id=user,
                        admin_rights=types.ChatAdminRights(
                            change_info=True,
                            post_messages=True,
                            edit_messages=True,
                            delete_messages=True,
                            ban_users=True,
                            invite_users=True,
                            pin_messages=True,
                            add_admins=False
                        ),
                        rank=""
                    ))
                    return True, None
                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    logger.warning(f"⚠️ 设置管理员触发频率限制，需等待 {wait_seconds} 秒")
                    print(f"⚠️ 设置管理员触发频率限制，需等待 {wait_seconds} 秒", flush=True)
                    if attempt < max_retries - 1 and wait_seconds < self.config.BATCH_CREATE_MAX_FLOOD_WAIT:
                        await asyncio.sleep(wait_seconds + 1)
                    else:
                        return False, f"设置失败: 操作触发频率限制 ({wait_seconds}秒)"
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # 检查是否是 "Too many requests" 错误
                    if "too many requests" in error_msg or "flood" in error_msg:
                        logger.warning(f"⚠️ 设置管理员触发频率限制，等待5秒后重试")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(5.0)
                            continue
                        else:
                            return False, f"设置失败: 频率限制，请稍后手动添加管理员"
                    
                    # 提供更详细的错误信息
                    if "chat_admin_required" in error_msg or "admin" in error_msg:
                        return False, f"设置失败: 权限不足（Basic Group无法添加管理员，需先升级为SuperGroup）"
                    elif "user_not_participant" in error_msg:
                        # EditAdminRequest 应该会自动邀请，如果出现此错误可能是权限问题
                        return False, f"设置失败: 无法邀请 @{admin_username} 加入（可能是隐私设置或群组限制）"
                    elif "user_privacy_restricted" in error_msg or "privacy" in error_msg:
                        return False, f"设置失败: @{admin_username} 隐私设置不允许被添加"
                    elif "user_channels_too_much" in error_msg:
                        return False, f"设置失败: @{admin_username} 加入的群组数量已达上限"
                    elif "user_bot_required" in error_msg or "peer_id_invalid" in error_msg:
                        return False, f"设置失败: @{admin_username} 账号无效"
                    elif "chat_not_modified" in error_msg:
                        # 用户已经是管理员
                        return True, None
                    elif "bot" in error_msg and "cannot" in error_msg:
                        return False, f"设置失败: @{admin_username} 是机器人，无法添加为管理员"
                    
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2.0)
                    else:
                        return False, f"设置失败: {str(e)[:200]}"
            
            return False, "设置失败: 达到最大重试次数"
        except Exception as e:
            return False, str(e)
    
    async def create_single_new(
        self,
        account: BatchAccountInfo,
        config: BatchCreationConfig,
        index: int
    ) -> BatchCreationResult:
        """使用新配置结构为单个账号创建一个群组/频道"""
        logger.info(f"🎯 开始创建 #{index+1} - 账号: {account.phone}")
        print(f"🎯 开始创建 #{index+1} - 账号: {account.phone}", flush=True)
        
        result = BatchCreationResult(
            account_name=account.file_name,
            phone=account.phone or "未知",
            creation_type=config.creation_type,
            name=""
        )
        
        try:
            if account.daily_remaining <= 0:
                logger.warning(f"⏭️ 跳过创建 #{index+1}: 账号 {account.phone} 已达每日上限")
                print(f"⏭️ 跳过创建 #{index+1}: 账号 {account.phone} 已达每日上限", flush=True)
                result.status = 'skipped'
                result.error = '已达每日创建上限'
                return result
            
            # 确保客户端已连接并且准备就绪
            # 使用锁避免并发创建/连接同一个客户端
            if not hasattr(account, '_client_lock'):
                account._client_lock = asyncio.Lock()
            
            async with account._client_lock:
                if not account.client:
                    logger.info(f"🔌 创建新客户端连接: {account.phone}")
                    print(f"🔌 创建新客户端连接: {account.phone}", flush=True)
                    
                    # 问题1: 对于TData账号，使用转换后的Session路径
                    if account.file_type == "tdata" and account.converted_session_path:
                        session_path = account.converted_session_path
                        logger.info(f"📂 使用TData转换的Session: {account.phone}")
                        print(f"📂 使用TData转换的Session: {account.phone}", flush=True)
                    else:
                        session_path = account.session_path
                    
                    # 【关键修复】移除.session后缀（如果有），因为TelegramClient会自动添加
                    # 这样可以确保验证和创建阶段使用相同的session文件
                    session_base = session_path.replace('.session', '') if session_path.endswith('.session') else session_path
                    
                    account.client = TelegramClient(
                        session_base,
                        account.api_id,
                        account.api_hash,
                        proxy=account.proxy_dict,
                        timeout=15
                    )
                    await account.client.connect()
                    
                    # 验证连接是否成功
                    if not account.client.is_connected():
                        raise Exception("客户端连接失败")
                    
                    # 验证账号是否已授权
                    if not await account.client.is_user_authorized():
                        raise Exception("账号未授权")
                    
                    logger.info(f"✅ 客户端连接成功: {account.phone}")
                    print(f"✅ 客户端连接成功: {account.phone}", flush=True)
                elif not account.client.is_connected():
                    # 如果客户端存在但未连接，重新连接
                    logger.info(f"🔄 重新连接客户端: {account.phone}")
                    print(f"🔄 重新连接客户端: {account.phone}", flush=True)
                    await account.client.connect()
                    
                    if not account.client.is_connected():
                        raise Exception("客户端重新连接失败")
            
            # 获取名称和描述（循环使用列表）
            if config.group_names:
                name_idx = index % len(config.group_names)
                name = config.group_names[name_idx]
                description = config.group_descriptions[name_idx] if name_idx < len(config.group_descriptions) else ""
                logger.info(f"📝 使用名称: {name}")
                print(f"📝 使用名称: {name}", flush=True)
            else:
                name = f"Group {index + 1}"
                description = ""
                logger.info(f"📝 使用默认名称: {name}")
                print(f"📝 使用默认名称: {name}", flush=True)
            
            result.name = name
            result.description = description
            
            # 获取用户名
            username = None
            if config.username_mode == 'custom' and config.custom_usernames:
                username_idx = index % len(config.custom_usernames)
                username = config.custom_usernames[username_idx]
                logger.info(f"🔗 使用自定义用户名: {username}")
                print(f"🔗 使用自定义用户名: {username}", flush=True)
            elif config.username_mode == 'auto':
                username = self.generate_random_username()
                logger.info(f"🎲 生成随机用户名: {username}")
                print(f"🎲 生成随机用户名: {username}", flush=True)
            
            # 创建群组或频道
            type_text = "群组" if config.creation_type == 'group' else "频道"
            logger.info(f"🚀 开始创建{type_text}: {name} (用户名: {username or '无'})")
            print(f"🚀 开始创建{type_text}: {name} (用户名: {username or '无'})", flush=True)
            
            if config.creation_type == 'group':
                success, invite_link, actual_username, error = await self.create_group(
                    account.client, name, username, description
                )
            else:
                success, invite_link, actual_username, error = await self.create_channel(
                    account.client, name, username, description
                )
            
            if success:
                logger.info(f"✅ 创建成功 #{index+1}: {name} - {invite_link}")
                print(f"✅ 创建成功 #{index+1}: {name} - {invite_link}", flush=True)
                
                result.status = 'success'
                result.invite_link = invite_link
                result.username = actual_username
                me = await account.client.get_me()
                result.creator_id = me.id
                result.creator_username = me.username if me.username else str(me.id)
                
                # 添加管理员（支持多个管理员）
                admin_list = []
                if config.admin_usernames:
                    admin_list = config.admin_usernames
                elif config.admin_username:  # 向后兼容
                    admin_list = [config.admin_username]
                
                if admin_list and actual_username:
                    # 添加延迟避免频率限制（增加到3-5秒）
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    
                    try:
                        entity = await account.client.get_entity(actual_username)
                        chat_id = entity.id
                        
                        # 逐个添加管理员
                        for idx, admin_username in enumerate(admin_list):
                            if not admin_username:
                                continue
                            
                            logger.info(f"👤 尝试添加管理员 [{idx+1}/{len(admin_list)}]: {admin_username}")
                            print(f"👤 尝试添加管理员 [{idx+1}/{len(admin_list)}]: {admin_username}", flush=True)
                            
                            admin_success, admin_error = await self.add_admin_to_group(
                                account.client, chat_id, admin_username
                            )
                            
                            if admin_success:
                                result.admin_usernames.append(admin_username)
                                if not result.admin_username:  # 向后兼容，记录第一个
                                    result.admin_username = admin_username
                                logger.info(f"✅ 管理员添加成功 [{idx+1}/{len(admin_list)}]: {admin_username}")
                                print(f"✅ 管理员添加成功 [{idx+1}/{len(admin_list)}]: {admin_username}", flush=True)
                            else:
                                result.admin_failures.append(f"{admin_username}: {admin_error}")
                                logger.warning(f"⚠️ 添加管理员失败 [{idx+1}/{len(admin_list)}] {admin_username}: {admin_error}")
                                print(f"⚠️ 添加管理员失败 [{idx+1}/{len(admin_list)}] {admin_username}: {admin_error}", flush=True)
                            
                            # 多个管理员之间添加更长延迟，避免频率限制（增加到5-8秒）
                            if idx < len(admin_list) - 1:  # 不是最后一个
                                delay = random.uniform(5.0, 8.0)
                                logger.info(f"⏳ 管理员添加间隔：等待 {delay:.1f} 秒...")
                                print(f"⏳ 管理员添加间隔：等待 {delay:.1f} 秒...", flush=True)
                                await asyncio.sleep(delay)
                                
                    except Exception as e:
                        logger.warning(f"⚠️ 获取群组实体失败: {e}")
                        print(f"⚠️ 获取群组实体失败: {e}", flush=True)
                        for admin_username in admin_list:
                            result.admin_failures.append(f"{admin_username}: 无法获取群组信息")
                
                self.db.record_creation(account.phone, config.creation_type, name, invite_link, actual_username, me.id)
                account.daily_created += 1
                account.daily_remaining -= 1
            else:
                logger.error(f"❌ 创建失败 #{index+1}: {name} - {error}")
                print(f"❌ 创建失败 #{index+1}: {name} - {error}", flush=True)
                result.status = 'failed'
                result.error = error
        except Exception as e:
            result.status = 'failed'
            result.error = str(e)
            logger.error(f"❌ 创建异常 #{index+1}: {type(e).__name__}: {e}")
            print(f"❌ 创建异常 #{index+1}: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        return result
    
    def generate_report(self, results: List[BatchCreationResult], user_id: int) -> str:
        """生成创建报告"""
        lines = ["=" * 60, t(user_id, 'report_batch_create_title'), "=" * 60]
        lines.append(t(user_id, 'report_batch_create_generated').format(
            time=datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')
        ) + "\n")
        
        total = len(results)
        success = len([r for r in results if r.status == 'success'])
        failed = len([r for r in results if r.status == 'failed'])
        skipped = len([r for r in results if r.status == 'skipped'])
        
        lines.append(t(user_id, 'report_batch_create_stats'))
        lines.append(t(user_id, 'report_batch_create_total').format(count=total))
        lines.append(t(user_id, 'report_batch_create_success').format(count=success))
        lines.append(t(user_id, 'report_batch_create_failed').format(count=failed))
        lines.append(t(user_id, 'report_batch_create_skipped').format(count=skipped) + "\n")
        
        if success > 0:
            lines.append(t(user_id, 'report_batch_create_success_list'))
            lines.append("-" * 60)
            for r in results:
                if r.status == 'success':
                    type_text = t(user_id, 'report_batch_create_type_group') if r.creation_type == 'group' else t(user_id, 'report_batch_create_type_channel')
                    lines.append(t(user_id, 'report_batch_create_type').format(type=type_text))
                    lines.append(t(user_id, 'report_batch_create_name').format(name=r.name))
                    lines.append(t(user_id, 'report_batch_create_desc').format(
                        desc=r.description or t(user_id, 'report_batch_create_desc_none')
                    ))
                    lines.append(t(user_id, 'report_batch_create_username').format(
                        username=r.username or t(user_id, 'report_batch_create_desc_none')
                    ))
                    lines.append(t(user_id, 'report_batch_create_link').format(
                        link=r.invite_link or t(user_id, 'report_batch_create_desc_none')
                    ))
                    lines.append(t(user_id, 'report_batch_create_creator_account').format(account=r.phone))
                    # Display username with @ prefix, or @none if no username
                    if r.creator_username and not r.creator_username.isdigit():
                        creator_display = f"@{r.creator_username}"
                    else:
                        # No username, display @none using translation
                        creator_display = t(user_id, 'report_batch_create_admins_none')
                    lines.append(t(user_id, 'report_batch_create_creator_username').format(username=creator_display))
                    lines.append(t(user_id, 'report_batch_create_creator_id').format(
                        id=r.creator_id or t(user_id, 'report_batch_create_desc_none')
                    ))
                    
                    # 管理员信息（支持多个）
                    if r.admin_usernames:
                        lines.append(t(user_id, 'report_batch_create_admins').format(
                            admins=', '.join([f'@{u}' for u in r.admin_usernames])
                        ))
                    else:
                        lines.append(t(user_id, 'report_batch_create_admins').format(
                            admins=f"@{r.admin_username}" if r.admin_username else t(user_id, 'report_batch_create_admins_none')
                        ))
                    
                    # 管理员添加失败信息
                    if r.admin_failures:
                        lines.append(t(user_id, 'report_batch_create_admin_failed'))
                        for failure in r.admin_failures:
                            lines.append(f"  - {failure}")
                    
                    lines.append("")
        
        if failed > 0:
            lines.append(t(user_id, 'report_batch_create_failed') + ":")
            lines.append("-" * 60)
            for r in results:
                if r.status == 'failed':
                    lines.append(t(user_id, 'report_batch_create_name').format(name=r.name))
                    lines.append(t(user_id, 'report_batch_create_desc').format(
                        desc=r.description or t(user_id, 'report_batch_create_desc_none')
                    ))
                    lines.append(t(user_id, 'report_batch_create_creator_account').format(account=r.phone))
                    lines.append(t(user_id, 'report_failure_list_reason').format(reason=r.error))
                    lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# ================================
# 一键清理辅助函数
# ================================

# 全局变量用于追踪上次更新时间
_last_cleanup_update_time = {}

async def maybe_update_cleanup_progress(message, text, user_id, parse_mode='HTML'):
    """限制一键清理进度刷新频率，避免触发 Telegram FloodWait"""
    global _last_cleanup_update_time
    current_time = time.time()
    
    # 检查是否需要更新（距离上次更新至少 CLEANUP_UPDATE_INTERVAL 秒）
    if user_id not in _last_cleanup_update_time or \
       current_time - _last_cleanup_update_time[user_id] >= CLEANUP_UPDATE_INTERVAL:
        try:
            await message.edit_text(text, parse_mode=parse_mode)
            _last_cleanup_update_time[user_id] = current_time
            logger.debug(f"进度消息已更新: user_id={user_id}")
            return True
        except FloodWaitError as e:
            logger.warning(f"FloodWaitError: 等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            # 重试一次
            try:
                await message.edit_text(text, parse_mode=parse_mode)
                _last_cleanup_update_time[user_id] = current_time
                return True
            except Exception as retry_e:
                logger.warning(f"更新进度消息重试失败: {retry_e}")
                return False
        except Exception as e:
            logger.warning(f"更新进度消息失败: {e}")
            return False
    return False

async def safe_convert_tdata(tdata_path, phone_for_log=None):
    """安全转换 TData，带超时和错误处理
    
    Args:
        tdata_path: TData 路径
        phone_for_log: 用于日志的手机号（可选）
        
    Returns:
        成功返回 (session_path, None)，失败返回 (None, error_message)
    """
    # 初始化 phone_str，确保在所有路径中都可用
    phone_str = phone_for_log or tdata_path
    
    try:
        from opentele.api import API, UseCurrentSession
        from opentele.td import TDesktop
        
        logger.info(f"🔄 开始转换 TData [{phone_str}]")
        
        # 使用 asyncio.wait_for 添加超时机制
        async def _convert():
            tdesk = TDesktop(tdata_path)
            session_path = tdata_path.replace('tdata', 'session').replace('.zip', '.session')
            
            # 转换 TData 到 Session
            temp_client = await tdesk.ToTelethon(
                session=session_path,
                flag=UseCurrentSession,
                api=API.TelegramDesktop
            )
            
            # 测试连接
            await temp_client.connect()
            await temp_client.disconnect()
            
            return session_path
        
        # 添加超时保护
        session_path = await asyncio.wait_for(
            _convert(),
            timeout=TDATA_CONVERT_TIMEOUT
        )
        
        logger.info(f"✅ TData转换成功 [{phone_str}]")
        return (session_path, None)
        
    except asyncio.TimeoutError:
        error_msg = f"⏱️ TData转换超时（{TDATA_CONVERT_TIMEOUT}秒）"
        logger.error(f"{error_msg} [{phone_str}]")
        return (None, error_msg)
    except Exception as e:
        error_msg = f"❌ TData转换失败: {str(e)[:100]}"
        logger.error(f"{error_msg} [{phone_str}]")
        return (None, error_msg)


# ================================
# 增强版机器人
# ================================


