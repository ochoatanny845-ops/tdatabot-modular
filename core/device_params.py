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

class DeviceParamsManager:
    """设备参数管理器 - 从device_params文件夹读取并随机选择设备参数"""
    
    def __init__(self, params_dir: str = "device_params"):
        self.params_dir = params_dir
        self.params = {}
        self.load_all_params()
    
    def load_all_params(self):
        """加载所有设备参数文件"""
        if not os.path.exists(self.params_dir):
            print(f"⚠️ 设备参数目录不存在: {self.params_dir}")
            return
        
        param_files = {
            'api_credentials': 'api_id+api_hash.txt',
            'app_name': 'app_name.txt',
            'app_version': 'app_version.txt',
            'cpu_cores': 'cpu_cores.txt',
            'device_sdk': 'device+sdk.txt',
            'device_model': 'device_model.txt',
            'lang_code': 'lang_code.txt',
            'ram_size': 'ram_size.txt',
            'screen_resolution': 'screen_resolution.txt',
            'system_lang_code': 'system_lang_code.txt',
            'system_version': 'system_version.txt',
            'timezone': 'timezone.txt',
            'user_agent': 'user_agent.txt'
        }
        
        for param_name, filename in param_files.items():
            filepath = os.path.join(self.params_dir, filename)
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                        self.params[param_name] = lines
                        print(f"✅ 加载设备参数: {param_name} ({len(lines)} 项)")
                else:
                    print(f"⚠️ 设备参数文件不存在: {filename}")
            except Exception as e:
                print(f"❌ 加载设备参数失败 {filename}: {e}")
        
        total_params = sum(len(v) for v in self.params.values())
        print(f"📱 设备参数管理器初始化完成，共加载 {total_params} 个参数项")
    
    def get_random_device_params(self) -> Dict[str, Any]:
        """获取一组随机设备参数"""
        params = {}
        
        # API凭据（api_id和api_hash）
        if 'api_credentials' in self.params and self.params['api_credentials']:
            cred = random.choice(self.params['api_credentials'])
            if ':' in cred:
                try:
                    api_id, api_hash = cred.split(':', 1)
                    params['api_id'] = int(api_id.strip())
                    params['api_hash'] = api_hash.strip()
                except (ValueError, AttributeError) as e:
                    print(f"⚠️ 解析API凭据失败: {cred} - {e}")
        
        # 其他参数
        for key in ['app_name', 'app_version', 'device_model', 'lang_code', 
                    'system_lang_code', 'system_version', 'timezone', 'user_agent']:
            if key in self.params and self.params[key]:
                params[key] = random.choice(self.params[key])
        
        # 数值类型参数
        if 'cpu_cores' in self.params and self.params['cpu_cores']:
            try:
                params['cpu_cores'] = int(random.choice(self.params['cpu_cores']))
            except (ValueError, AttributeError) as e:
                print(f"⚠️ 解析CPU核心数失败: {e}")
        
        if 'ram_size' in self.params and self.params['ram_size']:
            try:
                params['ram_size'] = int(random.choice(self.params['ram_size']))
            except (ValueError, AttributeError) as e:
                print(f"⚠️ 解析RAM大小失败: {e}")
        
        # 设备和SDK
        if 'device_sdk' in self.params and self.params['device_sdk']:
            device_sdk = random.choice(self.params['device_sdk'])
            if ':' in device_sdk:
                device, sdk = device_sdk.split(':', 1)
                params['device'] = device.strip()
                params['sdk'] = sdk.strip()
        
        # 屏幕分辨率
        if 'screen_resolution' in self.params and self.params['screen_resolution']:
            resolution = random.choice(self.params['screen_resolution'])
            if 'x' in resolution:
                try:
                    width, height = resolution.split('x', 1)
                    params['screen_width'] = int(width.strip())
                    params['screen_height'] = int(height.strip())
                except (ValueError, AttributeError) as e:
                    print(f"⚠️ 解析屏幕分辨率失败: {resolution} - {e}")
        
        return params
    
    def get_random_api_credentials(self) -> Tuple[Optional[int], Optional[str]]:
        """获取随机API凭据（api_id和api_hash）"""
        if 'api_credentials' in self.params and self.params['api_credentials']:
            cred = random.choice(self.params['api_credentials'])
            if ':' in cred:
                api_id, api_hash = cred.split(':', 1)
                return int(api_id.strip()), api_hash.strip()
        return None, None

# ================================
# 代理测试器（新增）
# ================================


class DeviceParamsLoader:
    """设备参数加载器 - 从device_params目录加载并随机组合参数
    
    Loads device parameters from text files in the device_params directory
    and provides methods to get random or compatible parameter combinations.
    """
    
    def __init__(self, params_dir: str = None):
        """初始化设备参数加载器
        
        Args:
            params_dir: 参数文件目录路径，默认使用脚本目录下的device_params
        """
        if params_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            params_dir = os.path.join(script_dir, "device_params")
        
        self.params_dir = params_dir
        self.params: Dict[str, List[str]] = {}
        self.load_all_params()
    
    def load_all_params(self) -> None:
        """加载所有参数文件"""
        if not os.path.exists(self.params_dir):
            print(f"⚠️ 设备参数目录不存在: {self.params_dir}")
            return
        
        # 定义参数文件名到参数键的映射
        param_files = {
            'api_id+api_hash.txt': 'api_credentials',
            'app_version.txt': 'app_version',
            'device+sdk.txt': 'device_sdk',
            'lang_code.txt': 'lang_code',
            'system_lang_code.txt': 'system_lang_code',
            'system_version.txt': 'system_version',
            'app_name.txt': 'app_name',
            'device_model.txt': 'device_model',
            'timezone.txt': 'timezone',
            'screen_resolution.txt': 'screen_resolution',
            'user_agent.txt': 'user_agent',
            'cpu_cores.txt': 'cpu_cores',
            'ram_size.txt': 'ram_size'
        }
        
        for filename, param_key in param_files.items():
            file_path = os.path.join(self.params_dir, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f if line.strip()]
                        self.params[param_key] = lines
                        print(f"✅ 加载设备参数 {filename}: {len(lines)} 项")
                except Exception as e:
                    print(f"❌ 加载设备参数失败 {filename}: {e}")
            else:
                print(f"⚠️ 设备参数文件不存在: {filename}")
    
    def _get_random_param(self, param_key: str, default: str = "") -> str:
        """获取指定参数的随机值
        
        Args:
            param_key: 参数键名
            default: 默认值（当参数不存在时）
            
        Returns:
            随机选择的参数值或默认值
        """
        if param_key in self.params and self.params[param_key]:
            return random.choice(self.params[param_key])
        return default
    
    def get_random_device_config(self) -> Dict[str, Any]:
        """获取随机设备配置
        
        Returns:
            包含所有随机设备参数的字典
        """
        config_dict = {}
        
        # API credentials (format: api_id:api_hash)
        api_cred = self._get_random_param('api_credentials', '')
        if api_cred and ':' in api_cred:
            api_id, api_hash = api_cred.split(':', 1)
            try:
                config_dict['api_id'] = int(api_id)
                config_dict['api_hash'] = api_hash
            except ValueError:
                # Skip invalid API credentials
                pass
        
        # App version
        config_dict['app_version'] = self._get_random_param('app_version', '4.12.2 x64')
        
        # Device and SDK (format: device:sdk)
        device_sdk = self._get_random_param('device_sdk', 'PC 64bit:Windows 10')
        if ':' in device_sdk:
            device, sdk = device_sdk.split(':', 1)
            config_dict['device'] = device
            config_dict['sdk'] = sdk
        else:
            config_dict['device'] = device_sdk
            config_dict['sdk'] = 'Windows 10'
        
        # Language codes
        config_dict['lang_code'] = self._get_random_param('lang_code', 'en')
        config_dict['system_lang_code'] = self._get_random_param('system_lang_code', 'en-US')
        
        # System version
        config_dict['system_version'] = self._get_random_param('system_version', 'Windows 10 Pro 19045')
        
        # App name
        config_dict['app_name'] = self._get_random_param('app_name', 'Telegram Desktop')
        
        # Device model
        config_dict['device_model'] = self._get_random_param('device_model', 'PC 64bit')
        
        # Timezone
        config_dict['timezone'] = self._get_random_param('timezone', 'UTC+0')
        
        # Screen resolution
        config_dict['screen_resolution'] = self._get_random_param('screen_resolution', '1920x1080')
        
        # User agent
        config_dict['user_agent'] = self._get_random_param('user_agent', 
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # CPU cores
        cpu_cores = self._get_random_param('cpu_cores', '8')
        try:
            config_dict['cpu_cores'] = int(cpu_cores)
        except ValueError:
            config_dict['cpu_cores'] = 8
        
        # RAM size (in MB)
        ram_size = self._get_random_param('ram_size', '16384')
        try:
            config_dict['ram_size'] = int(ram_size)
        except ValueError:
            config_dict['ram_size'] = 16384
        
        return config_dict
    
    def get_compatible_params(self) -> Dict[str, Any]:
        """获取兼容的参数组合（智能匹配）
        
        智能匹配规则:
        - Windows 11 系统配合较新的 Telegram 版本
        - Windows 10 系统可以配合任意版本
        - 语言代码与系统语言代码匹配
        
        Returns:
            包含兼容设备参数的字典
        """
        config = self.get_random_device_config()
        
        # 智能匹配: Windows 11 使用较新版本
        if 'Windows 11' in config.get('system_version', ''):
            # 确保使用 4.x 版本的 Telegram
            newer_versions = [v for v in self.params.get('app_version', []) if v.startswith('4.')]
            if newer_versions:
                config['app_version'] = random.choice(newer_versions)
        
        # 智能匹配: 语言代码与系统语言代码应该一致
        lang_code = config.get('lang_code', 'en')
        system_lang_codes = self.params.get('system_lang_code', [])
        
        # 找到匹配的系统语言代码
        matching_system_langs = [slc for slc in system_lang_codes if slc.startswith(lang_code)]
        if matching_system_langs:
            config['system_lang_code'] = random.choice(matching_system_langs)
        
        # 智能匹配: 高端配置（多核CPU）配合更多内存
        cpu_cores = config.get('cpu_cores', 8)
        if cpu_cores >= 16:
            # 高核心数配合更大内存
            high_ram = []
            for r in self.params.get('ram_size', []):
                try:
                    if int(r) >= 32768:
                        high_ram.append(r)
                except ValueError:
                    continue
            if high_ram:
                try:
                    config['ram_size'] = int(random.choice(high_ram))
                except ValueError:
                    pass
        
        return config


# ================================
# 批量创建群组/频道相关类
# ================================

@dataclass

