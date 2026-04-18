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

class ProxyManager:
    """代理管理器"""
    
    def __init__(self, proxy_file: str = "proxy.txt"):
        self.proxy_file = proxy_file
        self.proxies = []
        self.current_index = 0
        self.load_proxies()
    
    def is_proxy_mode_active(self, db: 'Database') -> bool:
        """判断代理模式是否真正启用（USE_PROXY=true 且存在有效代理 且数据库开关启用）"""
        try:
            proxy_enabled = db.get_proxy_enabled()
            has_valid_proxies = len(self.proxies) > 0
            return config.USE_PROXY and proxy_enabled and has_valid_proxies
        except:
            return config.USE_PROXY and len(self.proxies) > 0
    
    def get_proxy_activation_detail(self, db: 'Database') -> str:
        """获取代理模式激活状态的详细信息"""
        details = []
        details.append(f"ENV USE_PROXY: {config.USE_PROXY}")
        
        try:
            proxy_enabled = db.get_proxy_enabled()
            details.append(f"DB proxy_enabled: {proxy_enabled}")
        except Exception as e:
            details.append(f"DB proxy_enabled: error ({str(e)[:30]})")
        
        details.append(f"Valid proxies loaded: {len(self.proxies)}")
        details.append(f"Proxy mode active: {self.is_proxy_mode_active(db)}")
        
        return " | ".join(details)
    
    def load_proxies(self):
        """加载代理列表"""
        if not os.path.exists(self.proxy_file):
            print(f"⚠️ 代理文件不存在: {self.proxy_file}")
            print(f"💡 创建示例代理文件...")
            self.create_example_proxy_file()
            return
        
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            self.proxies = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    proxy_info = self.parse_proxy_line(line)
                    if proxy_info:
                        self.proxies.append(proxy_info)
            
            print(f"📡 加载了 {len(self.proxies)} 个代理")
            
        except Exception as e:
            print(f"❌ 加载代理文件失败: {e}")
    
    def create_example_proxy_file(self):
        """创建示例代理文件"""
        example_content = """# 代理文件示例 - proxy.txt
# 支持的格式：
# HTTP代理：ip:port 或 http://ip:port
# HTTP认证：ip:port:username:password 或 http://ip:port:username:password
# SOCKS5：socks5:ip:port:username:password 或 socks5://ip:port:username:password
# SOCKS4：socks4:ip:port 或 socks4://ip:port
# ABCProxy住宅代理：host:port:username:password 或 http://host:port:username:password

# 示例（请替换为真实代理）
# 127.0.0.1:8080
# http://127.0.0.1:8080
# 127.0.0.1:1080:user:pass
# socks5:127.0.0.1:1080:user:pass
# socks5://127.0.0.1:1080:user:pass
# socks4:127.0.0.1:1080

# ABCProxy住宅代理示例（两种格式都支持）：
# f01a4db3d3952561.abcproxy.vip:4950:FlBaKtPm7l-zone-abc:00937128
# http://f01a4db3d3952561.abcproxy.vip:4950:FlBaKtPm7l-zone-abc:00937128

# 注意：
# - 以#开头的行为注释行，会被忽略
# - 支持标准格式和URL格式（带 :// 的格式）
# - 住宅代理（如ABCProxy）会自动使用更长的超时时间（30秒）
# - 系统会自动检测住宅代理并优化连接参数
"""
        try:
            with open(self.proxy_file, 'w', encoding='utf-8') as f:
                f.write(example_content)
            print(f"✅ 已创建示例代理文件: {self.proxy_file}")
        except Exception as e:
            print(f"❌ 创建示例代理文件失败: {e}")
    
    def is_residential_proxy(self, host: str) -> bool:
        """检测是否为住宅代理"""
        host_lower = host.lower()
        for pattern in config.RESIDENTIAL_PROXY_PATTERNS:
            if pattern.strip().lower() in host_lower:
                return True
        return False
    
    def parse_proxy_line(self, line: str) -> Optional[Dict]:
        """解析代理行（支持ABCProxy等住宅代理格式）"""
        try:
            # 先处理URL格式的代理（如 http://host:port:user:pass 或 socks5://host:port）
            # 移除协议前缀（如果存在）
            original_line = line
            proxy_type = 'http'  # 默认类型
            
            # 检查并移除协议前缀
            if '://' in line:
                protocol, rest = line.split('://', 1)
                proxy_type = protocol.lower()
                line = rest  # 现在 line 是 host:port:user:pass 格式
            
            parts = line.split(':')
            
            if len(parts) == 2:
                # ip:port
                host = parts[0].strip()
                return {
                    'type': proxy_type,
                    'host': host,
                    'port': int(parts[1].strip()),
                    'username': None,
                    'password': None,
                    'is_residential': self.is_residential_proxy(host)
                }
            elif len(parts) == 4:
                # ip:port:username:password 或 ABCProxy格式
                # 例如: f01a4db3d3952561.abcproxy.vip:4950:FlBaKtPm7l-zone-abc:00937128
                host = parts[0].strip()
                return {
                    'type': proxy_type,
                    'host': host,
                    'port': int(parts[1].strip()),
                    'username': parts[2].strip(),
                    'password': parts[3].strip(),
                    'is_residential': self.is_residential_proxy(host)
                }
            elif len(parts) >= 3 and parts[0].lower() in ['socks5', 'socks4', 'http', 'https']:
                # 旧格式: socks5:ip:port or socks5:ip:port:username:password (无 ://)
                # 这种情况下 parts[0] 是协议类型
                proxy_type = parts[0].lower()
                host = parts[1].strip()
                port = int(parts[2].strip())
                username = parts[3].strip() if len(parts) > 3 else None
                password = parts[4].strip() if len(parts) > 4 else None
                
                return {
                    'type': proxy_type,
                    'host': host,
                    'port': port,
                    'username': username,
                    'password': password,
                    'is_residential': self.is_residential_proxy(host)
                }
        except Exception as e:
            print(f"❌ 解析代理行失败: {line} - {e}")
        
        return None
    
    def get_next_proxy(self) -> Optional[Dict]:
        """获取下一个代理"""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def get_random_proxy(self) -> Optional[Dict]:
        """获取随机代理"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def remove_proxy(self, proxy_to_remove: Dict):
        """从内存中移除代理"""
        self.proxies = [p for p in self.proxies if not (
            p['host'] == proxy_to_remove['host'] and p['port'] == proxy_to_remove['port']
        )]
    
    def backup_proxy_file(self) -> bool:
        """备份原始代理文件"""
        try:
            if os.path.exists(self.proxy_file):
                backup_file = self.proxy_file.replace('.txt', '_backup.txt')
                shutil.copy2(self.proxy_file, backup_file)
                print(f"✅ 代理文件已备份到: {backup_file}")
                return True
        except Exception as e:
            print(f"❌ 备份代理文件失败: {e}")
        return False
    
    def save_working_proxies(self, working_proxies: List[Dict]):
        """保存可用代理到新文件"""
        try:
            working_file = self.proxy_file.replace('.txt', '_working.txt')
            with open(working_file, 'w', encoding='utf-8') as f:
                f.write("# 可用代理文件 - 自动生成\n")
                f.write(f"# 生成时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
                f.write(f"# 总数: {len(working_proxies)}个\n\n")
                
                for proxy in working_proxies:
                    if proxy['username'] and proxy['password']:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                    else:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}\n"
                    f.write(line)
            
            print(f"✅ 可用代理已保存到: {working_file}")
            return working_file
        except Exception as e:
            print(f"❌ 保存可用代理失败: {e}")
            return None
    
    def save_failed_proxies(self, failed_proxies: List[Dict]):
        """保存失效代理到备份文件"""
        try:
            failed_file = self.proxy_file.replace('.txt', '_failed.txt')
            with open(failed_file, 'w', encoding='utf-8') as f:
                f.write("# 失效代理文件 - 自动生成\n")
                f.write(f"# 生成时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
                f.write(f"# 总数: {len(failed_proxies)}个\n\n")
                
                for proxy in failed_proxies:
                    if proxy['username'] and proxy['password']:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                    else:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}\n"
                    f.write(line)
            
            print(f"✅ 失效代理已保存到: {failed_file}")
            return failed_file
        except Exception as e:
            print(f"❌ 保存失效代理失败: {e}")
            return None

# ================================
# 账号资料管理器（Profile Manager）
# ================================

# 错误类型映射（用于资料修改）- 映射到翻译键
ERROR_TYPE_TO_TRANSLATION_KEY = {
    'UserDeactivatedBanError': 'profile_error_banned',
    'UserDeactivatedError': 'profile_error_deactivated',
    'AuthKeyUnregisteredError': 'profile_error_auth_expired',
    'UsernameOccupiedError': 'profile_error_username_taken',
    'UsernameInvalidError': 'profile_error_username_invalid',
    'FloodWaitError': 'profile_error_flood',
    'TimeoutError': 'profile_error_timeout',
    'ConnectionError': 'profile_error_network',
    'RPCError': 'profile_error_rpc_error',
    'SessionPasswordNeededError': 'profile_error_password_needed',
    'PhoneNumberBannedError': 'profile_error_phone_banned',
}

def get_profile_error_message(user_id, error_type, fallback=None):
    """根据用户语言获取错误消息"""
    if error_type in ERROR_TYPE_TO_TRANSLATION_KEY:
        return t(user_id, ERROR_TYPE_TO_TRANSLATION_KEY[error_type])
    return fallback if fallback else t(user_id, 'profile_error_unknown')


class ProxyTester:
    """代理测试器 - 快速验证和清理代理"""
    
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.test_url = "http://httpbin.org/ip"
        self.test_timeout = config.PROXY_CHECK_TIMEOUT
        self.max_concurrent = config.PROXY_CHECK_CONCURRENT
        
    async def test_proxy_connection(self, proxy_info: Dict) -> Tuple[bool, str, float]:
        """测试单个代理连接（支持住宅代理更长超时）"""
        start_time = time.time()
        
        # 住宅代理使用更长的超时时间
        is_residential = proxy_info.get('is_residential', False)
        test_timeout = config.RESIDENTIAL_PROXY_TIMEOUT if is_residential else self.test_timeout
        
        try:
            import aiohttp
            import aiosocks
            
            connector = None
            
            # 根据代理类型创建连接器
            if proxy_info['type'] == 'socks5':
                connector = aiosocks.SocksConnector.from_url(
                    f"socks5://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['host']}:{proxy_info['port']}"
                    if proxy_info.get('username') and proxy_info.get('password')
                    else f"socks5://{proxy_info['host']}:{proxy_info['port']}"
                )
            elif proxy_info['type'] == 'socks4':
                connector = aiosocks.SocksConnector.from_url(
                    f"socks4://{proxy_info['host']}:{proxy_info['port']}"
                )
            else:  # HTTP代理
                proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['host']}:{proxy_info['port']}" \
                    if proxy_info.get('username') and proxy_info.get('password') \
                    else f"http://{proxy_info['host']}:{proxy_info['port']}"
                
                connector = aiohttp.TCPConnector()
            
            timeout = aiohttp.ClientTimeout(total=test_timeout)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                if proxy_info['type'] in ['socks4', 'socks5']:
                    async with session.get(self.test_url) as response:
                        if response.status == 200:
                            elapsed = time.time() - start_time
                            proxy_type = "住宅代理" if is_residential else "代理"
                            return True, f"{proxy_type}连接成功 {elapsed:.2f}s", elapsed
                else:
                    # HTTP代理
                    proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['host']}:{proxy_info['port']}" \
                        if proxy_info.get('username') and proxy_info.get('password') \
                        else f"http://{proxy_info['host']}:{proxy_info['port']}"
                    
                    async with session.get(self.test_url, proxy=proxy_url) as response:
                        if response.status == 200:
                            elapsed = time.time() - start_time
                            proxy_type = "住宅代理" if is_residential else "代理"
                            return True, f"{proxy_type}连接成功 {elapsed:.2f}s", elapsed
                            
        except ImportError:
            # 如果没有aiohttp和aiosocks，使用基础方法
            return await self.basic_test_proxy(proxy_info, start_time, is_residential)
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return False, f"连接超时 {elapsed:.2f}s", elapsed
            elif "connection" in error_msg.lower():
                return False, f"连接失败 {elapsed:.2f}s", elapsed
            else:
                return False, f"错误: {error_msg[:20]} {elapsed:.2f}s", elapsed
        
        elapsed = time.time() - start_time
        return False, f"未知错误 {elapsed:.2f}s", elapsed
    
    async def basic_test_proxy(self, proxy_info: Dict, start_time: float, is_residential: bool = False) -> Tuple[bool, str, float]:
        """基础代理测试（不依赖aiohttp）"""
        try:
            import socket
            
            # 住宅代理使用更长的超时时间
            test_timeout = config.RESIDENTIAL_PROXY_TIMEOUT if is_residential else self.test_timeout
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(test_timeout)
            
            result = sock.connect_ex((proxy_info['host'], proxy_info['port']))
            elapsed = time.time() - start_time
            sock.close()
            
            if result == 0:
                return True, f"端口开放 {elapsed:.2f}s", elapsed
            else:
                return False, f"端口关闭 {elapsed:.2f}s", elapsed
                
        except Exception as e:
            elapsed = time.time() - start_time
            return False, f"测试失败: {str(e)[:20]} {elapsed:.2f}s", elapsed
    
    async def test_all_proxies(self, progress_callback=None) -> Tuple[List[Dict], List[Dict], Dict]:
        """测试所有代理"""
        if not self.proxy_manager.proxies:
            return [], [], {}
        
        print(f"🧪 开始测试 {len(self.proxy_manager.proxies)} 个代理...")
        print(f"⚡ 并发数: {self.max_concurrent}, 超时: {self.test_timeout}秒")
        
        working_proxies = []
        failed_proxies = []
        statistics = {
            'total': len(self.proxy_manager.proxies),
            'tested': 0,
            'working': 0,
            'failed': 0,
            'avg_response_time': 0,
            'start_time': time.time()
        }
        
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(self.max_concurrent)
        response_times = []
        
        async def test_single_proxy(proxy_info):
            async with semaphore:
                success, message, response_time = await self.test_proxy_connection(proxy_info)
                
                statistics['tested'] += 1
                
                if success:
                    working_proxies.append(proxy_info)
                    statistics['working'] += 1
                    response_times.append(response_time)
                    # 隐藏代理详细信息
                    print(f"✅ 代理测试通过 - {message}")
                else:
                    failed_proxies.append(proxy_info)
                    statistics['failed'] += 1
                    # 隐藏代理详细信息
                    print(f"❌ 代理测试失败 - {message}")
                
                # 更新统计
                if response_times:
                    statistics['avg_response_time'] = sum(response_times) / len(response_times)
                
                # 调用进度回调
                if progress_callback:
                    await progress_callback(statistics['tested'], statistics['total'], statistics)
        
        # 分批处理代理（使用较大批次以提高速度）
        batch_size = config.PROXY_BATCH_SIZE
        for i in range(0, len(self.proxy_manager.proxies), batch_size):
            batch = self.proxy_manager.proxies[i:i + batch_size]
            tasks = [test_single_proxy(proxy) for proxy in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # 批次间短暂休息（减少到0.05秒以提高速度）
            await asyncio.sleep(0.05)
        
        total_time = time.time() - statistics['start_time']
        test_speed = statistics['total'] / total_time if total_time > 0 else 0
        
        print(f"\n📊 代理测试完成:")
        print(f"   总计: {statistics['total']} 个")
        print(f"   可用: {statistics['working']} 个 ({statistics['working']/statistics['total']*100:.1f}%)")
        print(f"   失效: {statistics['failed']} 个 ({statistics['failed']/statistics['total']*100:.1f}%)")
        print(f"   平均响应: {statistics['avg_response_time']:.2f} 秒")
        print(f"   测试速度: {test_speed:.1f} 代理/秒")
        print(f"   总耗时: {total_time:.1f} 秒")
        
        return working_proxies, failed_proxies, statistics
    
    async def cleanup_and_update_proxies(self, auto_confirm: bool = False) -> Tuple[bool, str]:
        """清理并更新代理文件"""
        if not config.PROXY_AUTO_CLEANUP and not auto_confirm:
            return False, "自动清理已禁用"
        
        # 备份原始文件
        if not self.proxy_manager.backup_proxy_file():
            return False, "备份失败"
        
        # 测试所有代理
        working_proxies, failed_proxies, stats = await self.test_all_proxies()
        
        if not working_proxies:
            return False, "没有可用的代理"
        
        # 保存分类结果
        working_file = self.proxy_manager.save_working_proxies(working_proxies)
        failed_file = self.proxy_manager.save_failed_proxies(failed_proxies)
        
        # 更新原始代理文件为可用代理
        try:
            with open(self.proxy_manager.proxy_file, 'w', encoding='utf-8') as f:
                f.write("# 自动清理后的可用代理文件\n")
                f.write(f"# 清理时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
                f.write(f"# 原始数量: {stats['total']}, 可用数量: {stats['working']}\n\n")
                
                for proxy in working_proxies:
                    if proxy['username'] and proxy['password']:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}:{proxy['username']}:{proxy['password']}\n"
                    else:
                        if proxy['type'] == 'http':
                            line = f"{proxy['host']}:{proxy['port']}\n"
                        else:
                            line = f"{proxy['type']}:{proxy['host']}:{proxy['port']}\n"
                    f.write(line)
            
            # 重新加载代理
            self.proxy_manager.load_proxies()
            
            result_msg = f"""✅ 代理清理完成!
            
📊 清理统计:
• 原始代理: {stats['total']} 个
• 可用代理: {stats['working']} 个 
• 失效代理: {stats['failed']} 个
• 成功率: {stats['working']/stats['total']*100:.1f}%

📁 文件保存:
• 主文件: {self.proxy_manager.proxy_file} (已更新为可用代理)
• 可用代理: {working_file}
• 失效代理: {failed_file}
• 备份文件: {self.proxy_manager.proxy_file.replace('.txt', '_backup.txt')}"""
            
            return True, result_msg
            
        except Exception as e:
            return False, f"更新代理文件失败: {e}"

# ================================
# 配置类（增强）
# ================================


class ProxyUsageRecord:
    """代理使用记录"""
    account_name: str
    proxy_attempted: Optional[str]  # Format: "type host:port" or None for local
    attempt_result: str  # "success", "timeout", "connection_refused", "auth_failed", "dns_error", etc.
    fallback_used: bool  # True if fell back to local connection
    error: Optional[str]  # Error message if any
    is_residential: bool  # Whether it's a residential proxy
    elapsed: float  # Time elapsed in seconds

# ================================
# SpamBot检测器（增强代理支持）
# ================================


class ProxyRotator:
    """代理轮换器 - 用于2FA重置防封"""
    def __init__(self, proxies: list):
        self.proxies = proxies
        self.index = 0
        self.lock = None  # 将在异步环境中初始化
    
    def get_next_proxy(self):
        """获取下一个代理，用完后循环复用（线程安全）"""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.index]
        self.index = (self.index + 1) % len(self.proxies)
        return proxy


def utc_to_beijing(utc_time):
    """将 UTC 时间转换为北京时间 (UTC+8)"""
    if utc_time is None:
        return "N/A"
    
    # 如果是字符串，先转换为 datetime
    if isinstance(utc_time, str):
        utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
    
    # 如果没有时区信息，假设是 UTC
    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    
    # 转换为北京时间 (UTC+8)
    beijing_tz = timezone(timedelta(hours=8))
    beijing_time = utc_time.astimezone(beijing_tz)
    
    return beijing_time.strftime('%Y-%m-%d %H:%M:%S')



