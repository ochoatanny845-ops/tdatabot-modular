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

class ProfileUpdateConfig:
    """资料更新配置"""
    mode: str  # 'random' 或 'custom'
    
    # 姓名配置
    update_name: bool = True
    custom_names: List[str] = field(default_factory=list)  # 自定义姓名列表
    
    # 头像配置
    update_photo: bool = False
    photo_action: str = 'keep'  # 'keep', 'delete_all', 'custom'
    custom_photos: List[str] = field(default_factory=list)  # 自定义头像路径列表
    
    # 简介配置
    update_bio: bool = False
    bio_action: str = 'keep'  # 'keep', 'clear', 'random', 'custom'
    custom_bios: List[str] = field(default_factory=list)  # 自定义简介列表
    
    # 用户名配置
    update_username: bool = False
    username_action: str = 'keep'  # 'keep', 'delete', 'random', 'custom'
    custom_usernames: List[str] = field(default_factory=list)  # 自定义用户名列表

# ================================
# 代理管理器
# ================================


class ProfileManager:
    """账号资料管理器 - 使用Faker动态生成随机不重样的本地化内容"""
    
    def __init__(self, proxy_manager: ProxyManager, db: 'Database'):
        self.proxy_manager = proxy_manager
        self.db = db
        self.faker_instances = {}  # 存储不同语言的Faker实例
        self.used_names = set()  # 记录已使用的姓名，确保不重复
        self.used_usernames = set()  # 记录已使用的用户名
        self.init_faker_instances()
    
    def init_faker_instances(self):
        """初始化各国语言的Faker实例"""
        try:
            from faker import Faker
            
            # 创建不同语言的Faker实例
            # Faker支持的locale: https://faker.readthedocs.io/en/master/locales.html
            self.faker_instances = {
                'CN': Faker('zh_CN'),   # 中文（中国）
                'HK': Faker('zh_TW'),   # 中文（台湾/香港）
                'MO': Faker('zh_TW'),   # 中文（澳门）
                'TW': Faker('zh_TW'),   # 中文（台湾）
                'US': Faker('en_US'),   # 英语（美国）
                'GB': Faker('en_GB'),   # 英语（英国）
                'CA': Faker('en_CA'),   # 英语（加拿大）
                'AU': Faker('en_AU'),   # 英语（澳大利亚）
                'NZ': Faker('en_NZ'),   # 英语（新西兰）
                'ID': Faker('id_ID'),   # 印尼语
                'RU': Faker('ru_RU'),   # 俄语
                'UA': Faker('uk_UA'),   # 乌克兰语
                'BY': Faker('ru_RU'),   # 白俄罗斯（使用俄语）
                'KZ': Faker('ru_RU'),   # 哈萨克斯坦（使用俄语）
                'JP': Faker('ja_JP'),   # 日语
                'KR': Faker('ko_KR'),   # 韩语
                'DE': Faker('de_DE'),   # 德语
                'FR': Faker('fr_FR'),   # 法语
                'ES': Faker('es_ES'),   # 西班牙语
                'IT': Faker('it_IT'),   # 意大利语
                'PT': Faker('pt_PT'),   # 葡萄牙语
                'BR': Faker('pt_BR'),   # 葡萄牙语（巴西）
                'TR': Faker('tr_TR'),   # 土耳其语
                'PL': Faker('pl_PL'),   # 波兰语
                'NL': Faker('nl_NL'),   # 荷兰语
                'SE': Faker('sv_SE'),   # 瑞典语
                'NO': Faker('no_NO'),   # 挪威语
                'DK': Faker('da_DK'),   # 丹麦语
                'FI': Faker('fi_FI'),   # 芬兰语
                'TH': Faker('th_TH'),   # 泰语
                'VN': Faker('vi_VN'),   # 越南语
                'PH': Faker('fil_PH'),  # 菲律宾语
                'IN': Faker('en_IN'),   # 印度（使用英语）
                'PK': Faker('en_IN'),   # 巴基斯坦（使用英语）
                'BD': Faker('en_IN'),   # 孟加拉国（使用英语）
                'IR': Faker('fa_IR'),   # 波斯语（伊朗）
                'SA': Faker('ar_SA'),   # 阿拉伯语（沙特）
                'AE': Faker('ar_SA'),   # 阿拉伯语（阿联酋）
                'EG': Faker('ar_EG'),   # 阿拉伯语（埃及）
                'IL': Faker('he_IL'),   # 希伯来语（以色列）
                'GR': Faker('el_GR'),   # 希腊语
                'CZ': Faker('cs_CZ'),   # 捷克语
                'HU': Faker('hu_HU'),   # 匈牙利语
                'RO': Faker('ro_RO'),   # 罗马尼亚语
                'SK': Faker('sk_SK'),   # 斯洛伐克语
                'HR': Faker('hr_HR'),   # 克罗地亚语
                'BG': Faker('bg_BG'),   # 保加利亚语
                'MX': Faker('es_MX'),   # 西班牙语（墨西哥）
                'AR': Faker('es_AR'),   # 西班牙语（阿根廷）
                'CO': Faker('es_CO'),   # 西班牙语（哥伦比亚）
                'CL': Faker('es_CL'),   # 西班牙语（智利）
            }
            
            print(f"✅ Faker实例初始化完成，支持 {len(self.faker_instances)} 个国家/地区")
        except Exception as e:
            logger.error(f"初始化Faker实例失败: {e}")
            # 至少提供一个默认的英语实例
            from faker import Faker
            self.faker_instances = {'DEFAULT': Faker('en_US')}
    
    def get_country_from_phone(self, phone: str) -> str:
        """根据手机号获取国家代码（ISO 3166-1 alpha-2）"""
        try:
            import phonenumbers
            # 确保手机号以+开头
            if not phone.startswith('+'):
                phone = '+' + phone
            
            parsed = phonenumbers.parse(phone, None)
            country_code = phonenumbers.region_code_for_number(parsed)
            
            logger.info(f"手机号 {phone} 解析为国家: {country_code}")
            return country_code if country_code else 'US'  # 默认返回美国
        except Exception as e:
            logger.warning(f"解析手机号国家失败 {phone}: {e}")
            return 'US'  # 默认返回美国
    
    def generate_random_name(self, country_code: str) -> Tuple[str, str]:
        """根据国家代码生成随机不重样的本地化姓名
        
        Args:
            country_code: ISO 3166-1 alpha-2 国家代码（如 CN, US, RU, ID 等）
            
        Returns:
            (first_name, last_name) 元组
        """
        try:
            # 获取对应国家的Faker实例，如果没有则使用默认
            faker = self.faker_instances.get(country_code.upper(), 
                                            self.faker_instances.get('DEFAULT', 
                                            self.faker_instances.get('US')))
            
            # 尝试生成不重复的姓名，最多尝试10次
            for _ in range(10):
                # 根据国家选择姓名格式
                if country_code.upper() in ['CN', 'HK', 'TW', 'MO']:
                    # 中文姓名：姓+名，通常2-3个字
                    full_name = faker.name()
                    # 中文姓名不分first/last，全部作为first_name
                    first_name = full_name
                    last_name = ''
                elif country_code.upper() in ['JP', 'KR']:
                    # 日韩姓名：也是姓在前，名在后
                    full_name = faker.name()
                    # 尝试分割
                    parts = full_name.split()
                    if len(parts) >= 2:
                        last_name = parts[0]  # 姓
                        first_name = ' '.join(parts[1:])  # 名
                    else:
                        first_name = full_name
                        last_name = ''
                else:
                    # 西方姓名：名在前，姓在后
                    first_name = faker.first_name()
                    last_name = faker.last_name()
                    full_name = f"{first_name} {last_name}"
                
                # 检查是否重复
                if full_name not in self.used_names:
                    self.used_names.add(full_name)
                    logger.info(f"生成姓名 [{country_code}]: {first_name} {last_name}")
                    return (first_name, last_name)
            
            # 如果10次都重复，则返回最后一次生成的（虽然重复但总比失败好）
            logger.warning(f"姓名生成重复，使用最后一次结果: {first_name} {last_name}")
            return (first_name, last_name)
            
        except Exception as e:
            logger.error(f"生成随机姓名失败 [{country_code}]: {e}")
            # 失败时返回简单的随机名字
            return (f"User{random.randint(1000, 9999)}", '')
    
    def generate_random_bio(self, country_code: str) -> str:
        """根据国家代码生成随机不重样的本地化简介
        
        Args:
            country_code: ISO 3166-1 alpha-2 国家代码（如 CN, US, RU, ID 等）
            
        Returns:
            本地化的个人简介文本
        """
        try:
            # 获取对应国家的Faker实例
            faker = self.faker_instances.get(country_code.upper(), 
                                            self.faker_instances.get('DEFAULT', 
                                            self.faker_instances.get('US')))
            
            # 根据国家生成不同风格的简介
            bio_templates = []
            
            if country_code.upper() in ['CN', 'HK', 'TW', 'MO']:
                # 中文简介模板
                templates = [
                    lambda: f"{faker.job()}，{faker.catch_phrase()}",
                    lambda: f"来自{faker.city()}，{faker.job()}",
                    lambda: f"{faker.catch_phrase()}",
                    lambda: f"{faker.job()} | {faker.city()}",
                    lambda: f"热爱生活 | {faker.job()}",
                ]
            elif country_code.upper() in ['RU', 'UA', 'BY', 'KZ']:
                # 俄语简介模板
                templates = [
                    lambda: f"{faker.job()} | {faker.city()}",
                    lambda: f"{faker.catch_phrase()}",
                    lambda: f"{faker.job()} из {faker.city()}",
                ]
            elif country_code.upper() == 'ID':
                # 印尼简介模板
                templates = [
                    lambda: f"{faker.job()} | {faker.city()}",
                    lambda: f"{faker.catch_phrase()}",
                    lambda: f"Suka {faker.job()}",
                ]
            else:
                # 英文及其他语言简介模板
                templates = [
                    lambda: f"{faker.job()} | {faker.city()}",
                    lambda: f"{faker.catch_phrase()}",
                    lambda: f"{faker.job()} from {faker.city()}",
                    lambda: faker.sentence(nb_words=6)[:-1],  # 6个词的句子
                ]
            
            # 随机选择一个模板并生成
            bio = random.choice(templates)()
            
            # 限制长度（Telegram bio最多70个字符）
            if len(bio) > 70:
                bio = bio[:67] + '...'
            
            logger.info(f"生成简介 [{country_code}]: {bio}")
            return bio
            
        except Exception as e:
            logger.error(f"生成随机简介失败 [{country_code}]: {e}")
            return ''
    
    def generate_random_username(self) -> str:
        """生成随机用户名"""
        # 生成8-15位的随机用户名（字母+数字）
        length = random.randint(8, 15)
        chars = string.ascii_lowercase + string.digits
        username = ''.join(random.choice(chars) for _ in range(length))
        # 确保以字母开头
        if username[0].isdigit():
            username = random.choice(string.ascii_lowercase) + username[1:]
        return username
    
    async def update_profile_name(self, client, first_name: str, last_name: str = "") -> bool:
        """修改账号姓名"""
        try:
            from telethon.tl.functions.account import UpdateProfileRequest
            await client(UpdateProfileRequest(
                first_name=first_name,
                last_name=last_name
            ))
            logger.info(f"成功修改姓名: {first_name} {last_name}")
            return True
        except Exception as e:
            logger.error(f"修改姓名失败: {e}")
            return False
    
    async def update_profile_bio(self, client, bio: str) -> bool:
        """修改账号简介"""
        try:
            from telethon.tl.functions.account import UpdateProfileRequest
            await client(UpdateProfileRequest(about=bio))
            logger.info(f"成功修改简介: {bio}")
            return True
        except Exception as e:
            logger.error(f"修改简介失败: {e}")
            return False
    
    async def update_profile_username(self, client, username: str) -> bool:
        """修改账号用户名"""
        try:
            from telethon.tl.functions.account import UpdateUsernameRequest
            await client(UpdateUsernameRequest(username=username))
            logger.info(f"成功修改用户名: {username}")
            return True
        except UsernameOccupiedError:
            logger.warning(f"用户名已被占用: {username}")
            return False
        except UsernameInvalidError:
            logger.warning(f"用户名无效: {username}")
            return False
        except Exception as e:
            logger.error(f"修改用户名失败: {e}")
            return False
    
    async def update_profile_photo(self, client, photo_path: str) -> bool:
        """修改账号头像"""
        try:
            from telethon.tl.functions.photos import UploadProfilePhotoRequest
            await client(UploadProfilePhotoRequest(
                file=await client.upload_file(photo_path)
            ))
            logger.info(f"成功上传头像: {photo_path}")
            return True
        except Exception as e:
            logger.error(f"上传头像失败: {e}")
            return False
    
    async def delete_profile_photos(self, client, delete_all: bool = True) -> bool:
        """删除账号头像"""
        try:
            from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
            
            me = await client.get_me()
            photos = await client(GetUserPhotosRequest(
                user_id=me,
                offset=0,
                max_id=0,
                limit=100
            ))
            
            if hasattr(photos, 'photos') and photos.photos:
                photo_ids = list(photos.photos)
                await client(DeletePhotosRequest(id=photo_ids))
                logger.info(f"成功删除 {len(photo_ids)} 个头像")
                return True
            else:
                logger.info("没有头像需要删除")
                return True
        except Exception as e:
            logger.error(f"删除头像失败: {e}")
            return False
    
    async def batch_update_profiles(self, files: List[Tuple[str, str]], 
                                     file_type: str,
                                     config: ProfileUpdateConfig,
                                     progress_callback) -> Dict:
        """批量更新账号资料
        
        Args:
            files: 文件列表 [(账号名, 文件路径), ...]
            file_type: 文件类型 ('tdata', 'session', 'session-json')
            config: 资料更新配置
            progress_callback: 进度回调函数
            
        Returns:
            更新结果统计
        """
        results = {
            'total': len(files),
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        for idx, (account_name, file_path) in enumerate(files):
            try:
                await progress_callback(f"处理账号 {idx + 1}/{len(files)}: {account_name}")
                
                # 创建客户端连接
                client = None
                session_path = None
                
                try:
                    # 根据文件类型创建客户端
                    if file_type == 'tdata':
                        # TData 转换为 session
                        tdesk = TDesktop(file_path)
                        session_path = f"/tmp/profile_update_{secrets.token_hex(8)}.session"
                        client = await tdesk.ToTelethon(session_path, flag=UseCurrentSession)
                        # 重要：TData转Session后必须显式连接
                        if not client.is_connected():
                            await client.connect()
                    elif file_type in ['session', 'session-json']:
                        session_path = file_path
                        # 从session文件创建客户端
                        # 需要api_id和api_hash（从db或config获取）
                        api_id = config.get('api_id', 2040)
                        api_hash = config.get('api_hash', 'b18441a1ff607e10a989891a5462e627')
                        client = TelegramClient(session_path, api_id, api_hash)
                        await client.connect()
                    
                    if not client or not await client.is_user_authorized():
                        raise Exception("客户端未授权")
                    
                    # 获取账号信息
                    me = await client.get_me()
                    phone = me.phone if hasattr(me, 'phone') else None
                    country = self.get_country_from_phone(phone) if phone else 'US'
                    
                    detail = {
                        'account': account_name,
                        'phone': phone,
                        'actions': []
                    }
                    
                    # 根据配置更新资料
                    await asyncio.sleep(random.uniform(1, 3))  # 随机延迟避免限流
                    
                    # 1. 更新姓名
                    if config.update_name:
                        first_name = None
                        last_name = ''
                        
                        if config.mode == 'random':
                            first_name, last_name = self.generate_random_name(country)
                        elif config.custom_names:
                            # 循环使用自定义姓名列表
                            full_name = config.custom_names[idx % len(config.custom_names)]
                            parts = full_name.split(' ', 1)
                            first_name = parts[0]
                            last_name = parts[1] if len(parts) > 1 else ''
                        
                        if first_name:
                            if await self.update_profile_name(client, first_name, last_name):
                                detail['actions'].append(f"✅ 姓名: {first_name} {last_name}")
                            else:
                                detail['actions'].append(f"❌ 姓名更新失败")
                    
                    # 2. 处理头像
                    if config.update_photo:
                        if config.photo_action == 'delete_all':
                            if await self.delete_profile_photos(client):
                                detail['actions'].append("✅ 删除所有头像")
                            else:
                                detail['actions'].append("❌ 删除头像失败")
                        elif config.photo_action == 'custom' and config.custom_photos:
                            photo_path = config.custom_photos[idx % len(config.custom_photos)]
                            if await self.update_profile_photo(client, photo_path):
                                detail['actions'].append(f"✅ 上传头像")
                            else:
                                detail['actions'].append("❌ 上传头像失败")
                    
                    # 3. 更新简介
                    if config.update_bio:
                        bio = ''
                        if config.bio_action == 'clear':
                            bio = ''
                        elif config.bio_action == 'random':
                            bio = self.generate_random_bio(country)
                        elif config.bio_action == 'custom' and config.custom_bios:
                            bio = config.custom_bios[idx % len(config.custom_bios)]
                        
                        if await self.update_profile_bio(client, bio):
                            detail['actions'].append(f"✅ 简介: {bio[:20]}...")
                        else:
                            detail['actions'].append("❌ 简介更新失败")
                    
                    # 4. 更新用户名
                    if config.update_username:
                        username = ''
                        if config.username_action == 'delete':
                            username = ''
                        elif config.username_action == 'random':
                            username = self.generate_random_username()
                        elif config.username_action == 'custom' and config.custom_usernames:
                            username = config.custom_usernames[idx % len(config.custom_usernames)]
                        
                        if await self.update_profile_username(client, username):
                            detail['actions'].append(f"✅ 用户名: {username if username else '已删除'}")
                        else:
                            detail['actions'].append("❌ 用户名更新失败")
                    
                    results['success'] += 1
                    results['details'].append(detail)
                    
                except Exception as e:
                    logger.error(f"处理账号 {account_name} 失败: {e}")
                    results['failed'] += 1
                    results['details'].append({
                        'account': account_name,
                        'error': str(e)
                    })
                finally:
                    if client:
                        await client.disconnect()
                    # 清理临时session文件
                    if session_path and session_path.startswith('/tmp/'):
                        try:
                            os.remove(session_path)
                        except:
                            pass
                
            except Exception as e:
                logger.error(f"批量更新过程错误: {e}")
                results['failed'] += 1
        
        return results

# ================================
# 资料修改辅助函数
# ================================

def generate_progress_bar(current: int, total: int, width: int = 20) -> str:
    """生成文本进度条
    
    Args:
        current: 当前进度
        total: 总数
        width: 进度条宽度（字符数）
        
    Returns:
        格式化的进度条字符串
    """
    if total == 0:
        return "░" * width + " 0.0%"
    
    # 输入验证
    if current < 0:
        current = 0
    
    percentage = current / total
    filled = int(width * percentage)
    empty = width - filled
    
    bar = "▓" * filled + "░" * empty
    percent_text = f"{percentage * 100:.1f}%"
    
    return f"{bar} {percent_text}"

def format_time(seconds: float) -> str:
    """格式化时间显示
    
    Args:
        seconds: 秒数
        
    Returns:
        格式化的时间字符串 (HH:MM:SS 或 MM:SS)
    """
    if seconds < 0:
        return "00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

def get_back_to_menu_keyboard(user_id: int = None):
    """返回主菜单按钮
    
    Args:
        user_id: User ID for language selection (optional)
    
    Returns:
        InlineKeyboardMarkup: 包含"返回主菜单"按钮的键盘布局
    """
    if user_id:
        button_text = t(user_id, 'btn_back_to_menu')
    else:
        button_text = "返回主菜单"  # Fallback to Chinese
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data="back_to_main")]
    ])

# ================================
# TData 处理辅助函数
# ================================

def extract_phone_from_path(path: str) -> Optional[str]:
    """从路径中提取手机号
    
    Args:
        path: 文件或目录路径
        
    Returns:
        提取的手机号，如果未找到则返回None
    """
    basename = os.path.basename(path.rstrip('/\\'))
    # 移除扩展名
    name = os.path.splitext(basename)[0]
    # 提取数字（手机号通常10-15位，使用单词边界确保匹配完整数字）
    match = re.search(r'\b\d{10,15}\b', name)
    return match.group() if match else None

def extract_phone_from_tdata_path(tdata_path: str) -> Optional[str]:
    """从 TData 路径提取手机号
    
    支持的路径结构：
    - /tmp/xxx/+8613812345678/tdata/D877F783D5D3EF8C
    - /tmp/xxx/+8613812345678/tdata
    - /tmp/xxx/8613812345678/tdata/D877F783D5D3EF8C
    
    Args:
        tdata_path: TData 路径（可能是 tdata 目录或其子目录）
        
    Returns:
        手机号（带+前缀），如果未找到则返回None
    """
    try:
        # 标准化路径分隔符
        path_parts = tdata_path.replace('\\', '/').split('/')
        
        # 从路径各部分查找手机号
        for part in path_parts:
            if not part:
                continue
            
            # 查找以 + 开头的文件夹名（手机号）
            if part.startswith('+') and len(part) > 5:
                # 验证去掉+后是否全是数字
                phone_digits = part[1:]
                if phone_digits.isdigit() and len(phone_digits) >= 10:
                    return part
            
            # 也支持纯数字格式（不带+）
            if part.isdigit() and len(part) >= 10:
                return '+' + part
        
        return None
    except Exception as e:
        logger.warning(f"从TData路径提取手机号失败: {e}")
        return None

def detect_tdata_structure(account_path: str) -> Optional[Tuple]:
    """检测 TData 目录结构类型
    
    Args:
        account_path: 账号目录路径
        
    Returns:
        ('type1', tdata_path) - key_datas在tdata目录内
        ('type2', tdata_path, key_datas_path) - key_datas与tdata同级
        None - 未找到有效的TData结构
    """
    tdata_path = os.path.join(account_path, 'tdata')
    
    # 方式1: key_datas 在 tdata 目录内
    key_in_tdata = os.path.join(tdata_path, 'key_datas')
    if os.path.exists(key_in_tdata):
        logger.info(f"检测到TData结构类型1: key_datas在tdata内 - {account_path}")
        return ('type1', tdata_path)
    
    # 方式2: key_datas 与 tdata 同级
    key_beside_tdata = os.path.join(account_path, 'key_datas')
    if os.path.exists(key_beside_tdata) and os.path.exists(tdata_path):
        logger.info(f"检测到TData结构类型2: key_datas与tdata同级 - {account_path}")
        return ('type2', tdata_path, key_beside_tdata)
    
    logger.warning(f"未找到有效的TData结构 - {account_path}")
    return None

def is_valid_tdata(tdata_path: str) -> bool:
    """
    检查 tdata 目录是否有效（支持 D877 目录嵌套最多5层深）
    
    有效的 tdata 目录应该包含:
    - 一个类似 D877F783D5D3EF8C 的子目录（可嵌套在最多5层子文件夹中）
    - key_datas 或 key_data 文件可以在：
      1. D877F783D5D3EF8C 子目录内（标准结构）
      2. 与 D877F783D5D3EF8C 同级（变体结构）
    
    Args:
        tdata_path: tdata 目录路径
        
    Returns:
        bool: 是否为有效的 tdata 目录
    """
    if not os.path.isdir(tdata_path):
        return False
    
    try:
        for root, dirs, files in os.walk(tdata_path):
            # 限制搜索深度为5层
            rel = os.path.relpath(root, tdata_path)
            depth = 0 if rel == '.' else len(rel.split(os.sep))
            if depth >= 5:
                dirs[:] = []  # 不再深入
                continue

            # 检查当前层级是否有 key_datas / key_data 文件（变体结构）
            if 'key_datas' in files or 'key_data' in files:
                return True

            # 检查当前层级是否有 D877 开头的目录
            for d in dirs:
                if d.startswith('D877'):
                    d877_path = os.path.join(root, d)
                    # 检查 D877 目录内（含子目录）是否有 key_datas / key_data
                    for d_root, _, d_files in os.walk(d877_path):
                        if 'key_datas' in d_files or 'key_data' in d_files:
                            return True

    except (OSError, PermissionError) as e:
        logger.warning(f"检查tdata目录失败 {tdata_path}: {e}")
        return False

    return False

def scan_tdata_accounts(base_path: str) -> list:
    """
    统一的 tdata 账号扫描函数
    
    灵活识别：只要手机号文件夹内包含有效的 tdata 相关文件即可识别
    支持多种路径结构：
    - ✅ +8613812345678/tdata/D877F783D5D3EF8C/key_datas (标准结构)
    - ✅ 79001234567/D877F783D5D3EF8C/key_datas (无tdata子目录)
    - ✅ 79001234567/其他子目录/tdata/D877F783D5D3EF8C/key_datas (深层嵌套)
    - ✅ 79001234567/key_datas (直接在根目录)
    
    关键要求：必须以手机号文件夹为根，不识别无手机号文件夹的账号
    
    以手机号文件夹为单位识别账号，每个手机号=一个账号
    
    Args:
        base_path: 解压后的根目录
        
    Returns:
        账号列表，每个账号包含:
        - phone: 手机号（文件夹名）
        - tdata_path: tdata 或账号根目录路径
        - account_path: 账号根目录（手机号文件夹）
    """
    accounts = []
    seen_phones = set()  # 用于去重
    
    def is_likely_phone_number(folder_name: str) -> bool:
        """检查文件夹名是否像手机号"""
        # 移除可能的+前缀
        clean_name = folder_name.lstrip('+')
        # 手机号通常是10-15位数字
        return clean_name.isdigit() and 10 <= len(clean_name) <= 15
    
    def has_tdata_files(dir_path: str) -> bool:
        """检查目录树中是否包含 tdata 相关文件（key_datas, key_data, D877F783D5D3EF8C等）"""
        try:
            for root, dirs, files in os.walk(dir_path):
                # 检查是否有 key_datas 或 key_data 文件
                if 'key_datas' in files or 'key_data' in files:
                    return True
                # 检查是否有 D877F783D5D3EF8C 目录
                for d in dirs:
                    if d.startswith('D877'):
                        # 检查 D877 目录下是否有 key_datas 或 key_data
                        d877_path = os.path.join(root, d)
                        if os.path.exists(os.path.join(d877_path, 'key_datas')) or \
                           os.path.exists(os.path.join(d877_path, 'key_data')):
                            return True
        except (OSError, PermissionError) as e:
            logger.warning(f"检查tdata文件失败 {dir_path}: {e}")
        return False
    
    def find_tdata_path(account_path: str) -> str:
        """在账号目录中查找 tdata 路径（支持嵌套最多5层），优先返回有效的 tdata 子目录，否则返回账号根目录"""
        # 优先查找直接子目录中的 tdata
        direct_tdata = os.path.join(account_path, 'tdata')
        if os.path.isdir(direct_tdata) and is_valid_tdata(direct_tdata):
            return direct_tdata

        # 搜索嵌套的 tdata 目录（最多5层深）
        for root, dirs, _ in os.walk(account_path):
            rel = os.path.relpath(root, account_path)
            depth = 0 if rel == '.' else len(rel.split(os.sep))
            if depth >= 5:
                dirs[:] = []  # 不再深入
                continue
            if 'tdata' in dirs:
                nested_tdata = os.path.join(root, 'tdata')
                if nested_tdata != direct_tdata and is_valid_tdata(nested_tdata):
                    return nested_tdata

        # 如果没有找到有效的 tdata 子目录，但账号目录本身包含 tdata 文件，返回账号根目录
        if has_tdata_files(account_path):
            return account_path

        return None
    
    def scan_directory(dir_path):
        """递归扫描目录"""
        if not os.path.isdir(dir_path):
            return
        
        try:
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                
                if not os.path.isdir(item_path):
                    continue
                
                # 检查文件夹名是否像手机号
                if is_likely_phone_number(item):
                    # 查找 tdata 路径
                    tdata_path = find_tdata_path(item_path)
                    if tdata_path:
                        phone = item  # 文件夹名就是手机号
                        
                        # 去重：同一个手机号只添加一次
                        if phone not in seen_phones:
                            seen_phones.add(phone)
                            accounts.append({
                                'phone': phone,
                                'tdata_path': tdata_path,
                                'account_path': item_path
                            })
                            logger.info(f"找到账号: {phone} -> {tdata_path}")
                    else:
                        # 虽然文件夹名像手机号，但不包含 tdata 文件，继续递归扫描
                        scan_directory(item_path)
                else:
                    # 不像手机号的文件夹，递归扫描子目录
                    scan_directory(item_path)
        except (OSError, PermissionError) as e:
            logger.warning(f"扫描目录失败 {dir_path}: {e}")
    
    scan_directory(base_path)
    logger.info(f"扫描完成: 共找到 {len(accounts)} 个唯一账号")
    return accounts

def copy_session_to_temp(session_path: str) -> Tuple[str, str]:
    """复制session文件到临时目录避免并发冲突
    
    Args:
        session_path: 原始session文件路径
        
    Returns:
        (temp_session_base, temp_dir): 临时session路径（不含.session后缀）和临时目录路径
        注意：返回的路径不包含.session后缀，与TelegramClient的使用方式一致
    """
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="session_temp_")
    
    # 生成唯一的session文件名（已包含.session后缀）
    temp_session_name = f"{uuid.uuid4().hex}.session"
    temp_session_path = os.path.join(temp_dir, temp_session_name)
    
    # 移除.session后缀（如果存在）因为我们需要复制所有相关文件
    # 使用rsplit来处理边缘情况
    if session_path.endswith('.session'):
        session_base = session_path.rsplit('.session', 1)[0]
    else:
        session_base = session_path
    
    # temp_session_path 一定以 .session 结尾（见1089行），所以直接移除
    temp_session_base = temp_session_path[:-8]  # 移除 '.session' (8个字符)
    
    try:
        # 复制主session文件
        if os.path.exists(f"{session_base}.session"):
            shutil.copy2(f"{session_base}.session", f"{temp_session_base}.session")
        
        # 复制journal文件（如果存在）
        if os.path.exists(f"{session_base}.session-journal"):
            shutil.copy2(f"{session_base}.session-journal", f"{temp_session_base}.session-journal")
        
        # 返回临时session路径（不含.session后缀）
        return temp_session_base, temp_dir
    except (OSError, IOError) as e:
        logger.error(f"复制session文件失败: {e}")
        # 如果复制失败，清理临时目录并返回原始路径
        shutil.rmtree(temp_dir, ignore_errors=True)
        return session_base, None
    except Exception as e:
        # 记录意外错误并重新抛出
        logger.error(f"复制session文件时发生意外错误: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

def cleanup_temp_session(temp_dir: Optional[str]):
    """清理临时session文件
    
    Args:
        temp_dir: 临时目录路径
    """
    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"已清理临时目录: {temp_dir}")
        except (OSError, IOError, PermissionError) as e:
            logger.warning(f"清理临时目录失败: {e}")

def process_accounts_with_dedup(accounts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """处理账号列表并去重
    
    Args:
        accounts: 账号列表 [(账号名, 路径), ...]
        
    Returns:
        去重后的账号列表
    """
    processed_phones = set()
    unique_accounts = []
    
    for account_name, account_path in accounts:
        phone = extract_phone_from_path(account_path)
        if phone and phone not in processed_phones:
            processed_phones.add(phone)
            unique_accounts.append((account_name, account_path))
            logger.info(f"添加账号: {phone}")
        else:
            logger.info(f"跳过重复手机号: {phone or account_name}")
    
    logger.info(f"去重完成: 原始 {len(accounts)} 个，去重后 {len(unique_accounts)} 个")
    return unique_accounts

def deduplicate_accounts_by_phone(accounts: List[Dict]) -> List[Dict]:
    """按手机号去重账号列表
    
    Args:
        accounts: 账号字典列表，每个字典包含 phone, session_path, original_path, format 等字段
        
    Returns:
        去重后的账号列表
    """
    seen_phones = set()
    unique_accounts = []
    
    for account in accounts:
        phone = account.get('phone')
        if phone and phone not in seen_phones:
            seen_phones.add(phone)
            unique_accounts.append(account)
        else:
            logger.warning(f"⚠️ 重复账号已跳过: {phone}")
    
    logger.info(f"去重完成: 原始 {len(accounts)} 个，去重后 {len(unique_accounts)} 个")
    return unique_accounts

def create_zip_with_unique_paths(accounts: List[Tuple[str, str]], output_path: str) -> bool:
    """创建ZIP，使用手机号作为前缀避免重名
    
    Args:
        accounts: 账号列表 [(账号名, 路径), ...]
        output_path: 输出ZIP文件路径
        
    Returns:
        是否成功
    """
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            added_paths = set()
            
            for account_name, account_path in accounts:
                phone = extract_phone_from_path(account_path) or account_name
                
                if os.path.isdir(account_path):
                    # 目录：遍历所有文件
                    for root, dirs, files in os.walk(account_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # 使用手机号作为前缀，确保唯一
                            # 计算相对于账号目录的路径
                            rel_path = os.path.relpath(file_path, account_path)
                            arc_name = f"{phone}/{rel_path}"
                            
                            if arc_name not in added_paths:
                                added_paths.add(arc_name)
                                zf.write(file_path, arc_name)
                                logger.debug(f"添加文件到ZIP: {arc_name}")
                else:
                    # 单文件
                    filename = os.path.basename(account_path)
                    arc_name = f"{phone}/{filename}"
                    
                    if arc_name not in added_paths:
                        added_paths.add(arc_name)
                        zf.write(account_path, arc_name)
                        logger.debug(f"添加文件到ZIP: {arc_name}")
        
        logger.info(f"ZIP创建成功: {output_path}，共 {len(added_paths)} 个文件")
        return True
    except Exception as e:
        logger.error(f"创建ZIP失败: {e}")
        return False

# ================================
# 并发处理辅助函数（新增）
# ================================

# 并发控制参数
MAX_CONCURRENT = 15  # 最大并发数
DELAY_BETWEEN = 0.3  # 任务间延迟（秒）

async def safe_process_with_retry(func, *args, max_retries=3, **kwargs):
    """带重试的安全执行
    
    Args:
        func: 要执行的异步函数
        *args: 位置参数
        max_retries: 最大重试次数
        **kwargs: 关键字参数
        
    Returns:
        函数执行结果
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            logger.warning(f"执行失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))  # 递增延迟
                continue
    raise last_error

async def _process_session_internal(session_path: str, api_id: int, api_hash: str, 
                                    proxy: Optional[Dict], profile_data: Dict,
                                    proxy_manager: 'ProxyManager' = None,
                                    db: 'Database' = None) -> Dict:
    """内部session处理函数（不含超时逻辑）
    
    Args:
        session_path: session 文件路径
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        proxy: 代理配置字典
        profile_data: 资料更新数据
        proxy_manager: 代理管理器实例（可选）
        db: 数据库实例（可选）
        
    Returns:
        处理结果字典
    """
    temp_dir = None
    temp_session = None
    client = None
    
    try:
        # 复制 session 到临时目录，避免并发冲突
        temp_session, temp_dir = copy_session_to_temp(session_path)
        
        # 创建代理配置（如果提供）
        proxy_dict = None
        if proxy:
            proxy_type_map = {
                'http': socks.HTTP,
                'socks4': socks.SOCKS4,
                'socks5': socks.SOCKS5
            }
            proxy_type = proxy_type_map.get(proxy.get('type', 'http').lower(), socks.HTTP)
            
            proxy_dict = {
                'proxy_type': proxy_type,
                'addr': proxy['host'],
                'port': proxy['port'],
                'username': proxy.get('username'),
                'password': proxy.get('password'),
                'rdns': True
            }
        
        # 使用临时 session 连接
        # 根据代理类型选择合适的超时时间
        timeout = 30 if proxy and proxy.get('is_residential', False) else 10
        
        client = TelegramClient(
            temp_session,
            api_id,
            api_hash,
            proxy=proxy_dict,
            timeout=timeout,
            connection_retries=3,
            retry_delay=1
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            return {'success': False, 'error': '账号未授权'}
        
        # 获取账号信息
        me = await client.get_me()
        phone = me.phone if hasattr(me, 'phone') else None
        
        # 修改资料
        result = {
            'success': True,
            'phone': phone,
            'actions': []
        }
        
        # 更新姓名
        if profile_data.get('update_name'):
            first_name = profile_data.get('first_name', '')
            last_name = profile_data.get('last_name', '')
            try:
                from telethon.tl.functions.account import UpdateProfileRequest
                await client(UpdateProfileRequest(
                    first_name=first_name,
                    last_name=last_name
                ))
                result['actions'].append(f"✅ 姓名: {first_name} {last_name}")
            except Exception as e:
                result['actions'].append(f"❌ 姓名更新失败: {str(e)[:50]}")
        
        # 更新简介
        if profile_data.get('update_bio'):
            bio = profile_data.get('bio', '')
            try:
                from telethon.tl.functions.account import UpdateProfileRequest
                await client(UpdateProfileRequest(about=bio))
                result['actions'].append(f"✅ 简介: {bio[:20]}...")
            except Exception as e:
                result['actions'].append(f"❌ 简介更新失败: {str(e)[:50]}")
        
        # 更新用户名
        if profile_data.get('update_username'):
            username = profile_data.get('username', '')
            try:
                from telethon.tl.functions.account import UpdateUsernameRequest
                await client(UpdateUsernameRequest(username=username))
                result['actions'].append(f"✅ 用户名: {username if username else '已删除'}")
            except UsernameOccupiedError:
                result['actions'].append(f"❌ 用户名已被占用")
            except UsernameInvalidError:
                result['actions'].append(f"❌ 用户名格式无效")
            except Exception as e:
                result['actions'].append(f"❌ 用户名更新失败: {str(e)[:50]}")
        
        # 更新头像
        if profile_data.get('update_photo'):
            photo_action = profile_data.get('photo_action', 'keep')
            if photo_action == 'delete_all':
                try:
                    from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
                    photos = await client(GetUserPhotosRequest(
                        user_id=me,
                        offset=0,
                        max_id=0,
                        limit=100
                    ))
                    if hasattr(photos, 'photos') and photos.photos:
                        await client(DeletePhotosRequest(id=list(photos.photos)))
                        result['actions'].append(f"✅ 删除所有头像")
                    else:
                        result['actions'].append("✅ 没有头像需要删除")
                except Exception as e:
                    result['actions'].append(f"❌ 删除头像失败: {str(e)[:50]}")
            elif photo_action == 'custom':
                photo_path = profile_data.get('photo_path')
                if photo_path and os.path.exists(photo_path):
                    try:
                        from telethon.tl.functions.photos import UploadProfilePhotoRequest
                        await client(UploadProfilePhotoRequest(
                            file=await client.upload_file(photo_path)
                        ))
                        result['actions'].append(f"✅ 上传头像")
                    except Exception as e:
                        result['actions'].append(f"❌ 上传头像失败: {str(e)[:50]}")
        
        await client.disconnect()
        return result
        
    except Exception as e:
        logger.error(f"处理session失败: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        # 清理临时目录
        if client:
            try:
                await client.disconnect()
            except:
                pass
        cleanup_temp_session(temp_dir)

async def safe_process_session(session_path: str, api_id: int, api_hash: str, 
                                proxy: Optional[Dict], profile_data: Dict,
                                proxy_manager: 'ProxyManager' = None,
                                db: 'Database' = None,
                                timeout: int = 30) -> Dict:
    """安全处理 session，避免数据库锁定，带超时保护
    
    Args:
        session_path: session 文件路径
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        proxy: 代理配置字典
        profile_data: 资料更新数据
        proxy_manager: 代理管理器实例（可选）
        db: 数据库实例（可选）
        timeout: 处理超时时间（秒），默认30秒
        
    Returns:
        处理结果字典
    """
    try:
        # 使用asyncio.wait_for添加超时保护
        result = await asyncio.wait_for(
            _process_session_internal(session_path, api_id, api_hash, proxy, profile_data, proxy_manager, db),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(f"账号处理超时（{timeout}秒）: {session_path}")
        return {
            'success': False,
            'error': f'操作超时（{timeout}秒）',
            'error_type': 'Timeout'
        }
    except Exception as e:
        logger.error(f"账号处理失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

async def batch_convert_tdata_to_session(tdata_list: List[Tuple[str, str]], 
                                         bot_instance: 'EnhancedBot') -> List[Dict]:
    """并发转换 TData 为 Session
    
    Args:
        tdata_list: TData文件列表 [(文件名, 文件路径), ...]
        bot_instance: EnhancedBot实例，用于访问convert_tdata_to_session方法
        
    Returns:
        转换结果列表
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results = []
    
    async def convert_with_limit(tdata_name: str, tdata_path: str):
        async with semaphore:
            try:
                await asyncio.sleep(DELAY_BETWEEN)  # 小延迟避免请求过快
                
                # 获取随机API凭据
                api_id, api_hash = bot_instance.device_params_manager.get_random_api_credentials()
                if not api_id or not api_hash:
                    api_id = 2040
                    api_hash = 'b18441a1ff607e10a989891a5462e627'
                
                # 添加30秒超时保护
                try:
                    status, info, name = await asyncio.wait_for(
                        bot_instance.convert_tdata_to_session(
                            tdata_path, tdata_name, api_id, api_hash
                        ),
                        timeout=TDATA_CONVERT_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    return {
                        'success': False, 
                        'error': f'TData转换超时（{TDATA_CONVERT_TIMEOUT}秒）', 
                        'error_type': 'Timeout',
                        'tdata': tdata_path,
                        'name': tdata_name
                    }
                
                if status == "转换成功":
                    # 从sessions目录查找转换后的session文件
                    # 文件名应该是手机号.session
                    phone = info.split('手机号: ')[1].split(' |')[0] if '手机号: ' in info else tdata_name
                    session_path = os.path.join(config.SESSIONS_DIR, f"{phone}.session")
                    
                    return {
                        'success': True, 
                        'session': session_path if os.path.exists(session_path) else None,
                        'tdata': tdata_path,
                        'name': tdata_name,
                        'info': info
                    }
                else:
                    return {
                        'success': False, 
                        'error': info, 
                        'tdata': tdata_path,
                        'name': tdata_name
                    }
            except Exception as e:
                logger.error(f"转换TData失败 {tdata_name}: {e}")
                return {
                    'success': False, 
                    'error': str(e), 
                    'tdata': tdata_path,
                    'name': tdata_name
                }
    
    # 并发执行所有转换
    tasks = [convert_with_limit(name, path) for name, path in tdata_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常结果
    processed_results = []
    for result in results:
        if isinstance(result, Exception):
            processed_results.append({
                'success': False,
                'error': str(result)
            })
        else:
            processed_results.append(result)
    
    return processed_results

async def batch_update_profiles_concurrent(session_list: List[Tuple[str, str]], 
                                          profile_config: ProfileUpdateConfig,
                                          profile_manager: 'ProfileManager',
                                          proxy_manager: 'ProxyManager',
                                          db: 'Database',
                                          device_params_manager: 'DeviceParamsManager') -> List[Dict]:
    """并发修改 Session 资料
    
    Args:
        session_list: Session文件列表 [(文件名, 文件路径), ...]
        profile_config: 资料更新配置
        profile_manager: 资料管理器实例
        proxy_manager: 代理管理器实例
        db: 数据库实例
        device_params_manager: 设备参数管理器实例
        
    Returns:
        更新结果列表
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results = []
    
    # 准备代理列表（如果启用）
    proxies = []
    if proxy_manager.is_proxy_mode_active(db):
        # 循环使用可用代理
        proxy_count = len(proxy_manager.proxies)
        if proxy_count > 0:
            proxies = [proxy_manager.get_next_proxy() for _ in range(len(session_list))]
    
    # 如果没有代理，使用None填充
    if not proxies:
        proxies = [None] * len(session_list)
    
    async def update_with_limit(idx: int, session_name: str, session_path: str, proxy: Optional[Dict]):
        async with semaphore:
            try:
                await asyncio.sleep(DELAY_BETWEEN)  # 小延迟避免请求过快
                
                # 获取随机API凭据
                api_id, api_hash = device_params_manager.get_random_api_credentials()
                if not api_id or not api_hash:
                    api_id = 2040
                    api_hash = 'b18441a1ff607e10a989891a5462e627'
                
                # 准备资料数据
                profile_data = {}
                
                # 处理姓名
                if profile_config.update_name:
                    if profile_config.mode == 'random':
                        # 需要获取账号的国家信息来生成对应语言的姓名
                        # 先快速连接获取手机号
                        temp_session, temp_dir = copy_session_to_temp(session_path)
                        try:
                            client = TelegramClient(temp_session, api_id, api_hash)
                            await client.connect()
                            if await client.is_user_authorized():
                                me = await client.get_me()
                                phone = me.phone if hasattr(me, 'phone') else None
                                country = profile_manager.get_country_from_phone(phone) if phone else 'US'
                                first_name, last_name = profile_manager.generate_random_name(country)
                                profile_data['first_name'] = first_name
                                profile_data['last_name'] = last_name
                            await client.disconnect()
                        finally:
                            cleanup_temp_session(temp_dir)
                    elif profile_config.custom_names:
                        # 循环使用自定义姓名
                        full_name = profile_config.custom_names[idx % len(profile_config.custom_names)]
                        parts = full_name.split(' ', 1)
                        profile_data['first_name'] = parts[0]
                        profile_data['last_name'] = parts[1] if len(parts) > 1 else ''
                    
                    profile_data['update_name'] = True
                
                # 处理简介
                if profile_config.update_bio:
                    if profile_config.bio_action == 'clear':
                        profile_data['bio'] = ''
                    elif profile_config.bio_action == 'random':
                        # 使用默认国家生成
                        profile_data['bio'] = profile_manager.generate_random_bio('US')
                    elif profile_config.bio_action == 'custom' and profile_config.custom_bios:
                        profile_data['bio'] = profile_config.custom_bios[idx % len(profile_config.custom_bios)]
                    
                    profile_data['update_bio'] = True
                
                # 处理用户名
                if profile_config.update_username:
                    if profile_config.username_action == 'delete':
                        profile_data['username'] = ''
                    elif profile_config.username_action == 'random':
                        profile_data['username'] = profile_manager.generate_random_username()
                    elif profile_config.username_action == 'custom' and profile_config.custom_usernames:
                        profile_data['username'] = profile_config.custom_usernames[idx % len(profile_config.custom_usernames)]
                    
                    profile_data['update_username'] = True
                
                # 处理头像
                if profile_config.update_photo:
                    profile_data['update_photo'] = True
                    profile_data['photo_action'] = profile_config.photo_action
                    
                    if profile_config.photo_action == 'custom' and profile_config.custom_photos:
                        profile_data['photo_path'] = profile_config.custom_photos[idx % len(profile_config.custom_photos)]
                
                # 使用safe_process_session处理
                result = await safe_process_session(
                    session_path, api_id, api_hash, proxy, profile_data,
                    proxy_manager, db
                )
                
                result['session'] = session_path
                result['name'] = session_name
                return result
                
            except Exception as e:
                logger.error(f"更新资料失败 {session_name}: {e}")
                return {
                    'success': False, 
                    'session': session_path,
                    'name': session_name, 
                    'error': str(e)
                }
    
    # 并发执行所有修改
    tasks = [
        update_with_limit(idx, name, path, proxy) 
        for idx, ((name, path), proxy) in enumerate(zip(session_list, proxies))
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常结果
    processed_results = []
    for result in results:
        if isinstance(result, Exception):
            processed_results.append({
                'success': False,
                'error': str(result)
            })
        else:
            processed_results.append(result)
    
    return processed_results

# ================================
# 设备参数管理器（新增）
# ================================




# ===== Handler Methods from EnhancedBot =====

    def get_zip_name_translation_key(self, status: str) -> str:
    """Map internal status to ZIP file name translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for ZIP file naming
    """
    zip_map = {
        "无限制": "zip_no_restriction",
        "垃圾邮件": "zip_spambot",
        "冻结": "zip_frozen",
        "封禁": "zip_banned",
        "连接错误": "zip_connection_error",
    }
    return zip_map.get(status, "zip_no_restriction")


    def sanitize_filename(self, filename: str) -> str:
    """清理文件名，保留 Emoji 和括号
    
    只移除文件系统不允许的字符，保留所有Unicode字符包括Emoji。
    
    移除的字符（Windows和Unix文件系统不允许）:
    - 反斜杠 (\)、正斜杠 (/)、冒号 (:)
    - 星号 (*)、问号 (?)、引号 (")
    - 小于号 (<)、大于号 (>)、竖线 (|)
    
    保留的字符:
    - Emoji (如 🇮🇳, 🎉)
    - 中文括号 （）
    - 所有Unicode字符（中文、日文、俄文等）
    - 加号 (+)、下划线 (_)、连字符 (-) 等
    
    示例:
    - '🇮🇳 随机混合国家（有密码）' -> '🇮🇳 随机混合国家（有密码）'
    - 'test/file:name' -> 'testfilename'
    """
    # 只移除文件系统不允许的字符
    # Windows和Unix都不允许这些字符: \ / : * ? " < > |
    invalid_chars = r'[\\/:*?"<>|]'
    filename = re.sub(invalid_chars, '', filename)
    
    # 限制长度（保留扩展名空间）
    max_length = 200
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    # 去除首尾空格和点号
    filename = filename.strip('. ')
    
    # 如果文件名为空，使用默认名
    if not filename:
        filename = 'unnamed_file'
    
    return filename


    def handle_photo(self, update: Update, context: CallbackContext):
    """处理图片上传（用于广播媒体和资料头像）"""
    user_id = update.effective_user.id
    
    # 检查用户状态
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return
        
        user_status = row[0]
        
        # 处理资料头像上传
        if user_status == "profile_custom_upload_photo":
            self.handle_profile_photo_upload(update, context, user_id)
            return
        
        # 处理广播媒体上传
        if user_status != "waiting_broadcast_media":
            # 不是在等待上传，忽略
            return
    except:
        return
    
    # 检查是否有待处理的广播任务
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 获取最大尺寸的图片
    photo = update.message.photo[-1]
    
    # 保存图片 file_id
    task['media_file_id'] = photo.file_id
    task['media_type'] = 'photo'
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 发送成功消息并返回编辑器
    self.safe_send_message(
        update,
        "✅ <b>图片已保存</b>\n\n返回编辑器继续设置",
        'HTML'
    )
    
    # 模拟 query 对象返回编辑器
    class FakeQuery:
        def __init__(self, user, chat):
            self.from_user = user
            self.message = type('obj', (object,), {'chat_id': chat.id, 'message_id': None})()
        def answer(self):
            pass
    
    fake_query = FakeQuery(update.effective_user, update.effective_chat)
    
    # 发送新消息显示编辑器
    self.show_broadcast_wizard_editor_as_new_message(update, context)


    def handle_rename_start(self, query):
    """开始文件重命名流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 初始化任务
    self.pending_rename[user_id] = {
        'temp_dir': None,
        'file_path': None,
        'orig_name': None,
        'ext': None
    }
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_rename_file"
    )
    
    text = f"""

    def handle_rename_file_upload(self, update: Update, context: CallbackContext, document):
    """处理重命名文件上传"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_rename:
        self.safe_send_message(update, t(user_id, 'rename_no_task'))
        return
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="temp_rename_")
    orig_name = document.file_name
    
    # 分离文件名和扩展名
    if '.' in orig_name:
        name_parts = orig_name.rsplit('.', 1)
        base_name = name_parts[0]
        ext = '.' + name_parts[1]
    else:
        base_name = orig_name
        ext = ''
    
    # 下载文件
    file_path = os.path.join(temp_dir, orig_name)
    try:
        document.get_file().download(file_path)
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'rename_download_failed').format(error=str(e)))
        shutil.rmtree(temp_dir, ignore_errors=True)
        return
    
    # 保存任务信息
    self.pending_rename[user_id]['temp_dir'] = temp_dir
    self.pending_rename[user_id]['file_path'] = file_path
    self.pending_rename[user_id]['orig_name'] = orig_name
    self.pending_rename[user_id]['ext'] = ext
    
    # 更新状态，等待新文件名
    self.db.save_user(
        user_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
        "waiting_rename_newname"
    )
    
    text = f"""

    def handle_rename_newname_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理新文件名输入"""
    if user_id not in self.pending_rename:
        self.safe_send_message(update, t(user_id, 'rename_no_task'))
        return
    
    task = self.pending_rename[user_id]
    
    # 调试日志：记录原始输入
    logger.debug(f"重命名输入 - 用户{user_id} - 原始文本: {repr(text)}")
    logger.debug(f"重命名输入 - 用户{user_id} - text.strip(): {repr(text.strip())}")
    
    # 清理并验证新文件名
    new_name = self.sanitize_filename(text.strip())
    logger.debug(f"重命名输入 - 用户{user_id} - 清理后: {repr(new_name)}")
    
    if not new_name:
        self.safe_send_message(update, t(user_id, 'rename_invalid_name'))
        return
    
    # 构建完整的新文件名
    new_filename = new_name + task['ext']
    new_file_path = os.path.join(task['temp_dir'], new_filename)
    
    # 重命名文件
    try:
        shutil.move(task['file_path'], new_file_path)
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'rename_failed').format(error=str(e)))
        self.cleanup_rename_task(user_id)
        return
    
    # 发送重命名后的文件
    # 注意：显式指定filename参数以确保Telegram使用正确的文件名
    old_name_html = f"<code>{task['orig_name']}</code>"
    new_name_html = f"<code>{new_filename}</code>"
    caption = (
        f"<b>{t(user_id, 'rename_success')}</b>\n\n"
        f"{t(user_id, 'rename_old_name').format(old_name=old_name_html)}\n"
        f"{t(user_id, 'rename_new_name').format(new_name=new_name_html)}\n\n"
        f"{t(user_id, 'rename_telegram_tip')}"
    )
    
    if self.send_document_safely(user_id, new_file_path, caption, new_filename):
        self.safe_send_message(update, f"<b>{t(user_id, 'rename_file_sent')}</b>", 'HTML')
    else:
        self.safe_send_message(update, t(user_id, 'rename_send_failed'))
    
    # 清理任务
    self.cleanup_rename_task(user_id)


    def _ask_for_group_names(self, update: Update, user_id: int):
    """询问群组名称和简介"""
    task = self.pending_batch_create[user_id]
    
    total_to_create = task['valid_accounts'] * task['count_per_account']
    
    admin_usernames = task.get('admin_usernames', [])
    admin_display = ', '.join([f"@{u}" for u in admin_usernames]) if admin_usernames else t(user_id, 'batch_create_admins_none')
    
    step3_title_key = 'batch_create_step3_title_group' if task['creation_type'] == 'group' else 'batch_create_step3_title_channel'
    step3_prompt_key = 'batch_create_step3_prompt' if task['creation_type'] == 'group' else 'batch_create_step3_prompt_channel'
    step3_format_key = 'batch_create_step3_format_group' if task['creation_type'] == 'group' else 'batch_create_step3_format_channel'
    
    text = f"""

    def handle_batch_create_names_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理群组名称和简介输入"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    try:
        lines = text.strip().split('\n')
        group_names = []
        group_descriptions = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if '|' in line:
                parts = line.split('|', 1)
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else ""
            else:
                name = line
                desc = ""
            
            if name:
                group_names.append(name)
                group_descriptions.append(desc)
        
        if not group_names:
            self.safe_send_message(update, "❌ 未找到有效的名称，请重新输入")
            return
        
        task['group_names'] = group_names
        task['group_descriptions'] = group_descriptions
        
        names_saved_key = 'batch_create_names_saved_group' if task['creation_type'] == 'group' else 'batch_create_names_saved_channel'
        step4_title_key = 'batch_create_step4_title_group' if task['creation_type'] == 'group' else 'batch_create_step4_title_channel'
        
        text = f"""

    def handle_batch_create_usernames_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理自定义用户名输入"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    try:
        lines = text.strip().split('\n')
        custom_usernames = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除 @ 前缀
            username = line.lstrip('@')
            if username:
                custom_usernames.append(username)
        
        if not custom_usernames:
            self.safe_send_message(update, "❌ 未找到有效的用户名，请重新输入")
            return
        
        task['custom_usernames'] = custom_usernames
        
        # 显示确认信息
        self._show_batch_create_confirm(update, user_id)
        
    except Exception as e:
        self.safe_send_message(update, f"❌ 解析失败：{str(e)}")


    def process_batch_create_names_file(self, update: Update, context: CallbackContext, document, user_id: int):
    """处理群组名称文件上传"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    try:
        # 下载文件
        file = document.get_file()
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8')
        file.download(temp_file.name)
        temp_file.close()
        
        # 读取文件内容
        with open(temp_file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 清理临时文件
        os.unlink(temp_file.name)
        
        # 使用现有的处理逻辑
        fake_update = self._create_fake_update(user_id)
        self.handle_batch_create_names_input(fake_update, context, user_id, content)
        
    except Exception as e:
        logger.error(f"处理名称文件失败: {e}")
        self.safe_send_message(update, f"❌ 文件处理失败：{str(e)}")


    def process_batch_create_usernames_file(self, update: Update, context: CallbackContext, document, user_id: int):
    """处理用户名文件上传"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    try:
        # 下载文件
        file = document.get_file()
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8')
        file.download(temp_file.name)
        temp_file.close()
        
        # 读取文件内容
        with open(temp_file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 清理临时文件
        os.unlink(temp_file.name)
        
        # 使用现有的处理逻辑
        fake_update = self._create_fake_update(user_id)
        self.handle_batch_create_usernames_input(fake_update, context, user_id, content)
        
    except Exception as e:
        logger.error(f"处理用户名文件失败: {e}")
        self.safe_send_message(update, f"❌ 文件处理失败：{str(e)}")




    def _generate_profile_update_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成资料修改详细报告和打包结果文件"""
    logger.info("📊 开始生成详细报告和打包文件...")
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    total = len(results['success']) + len(results['failed'])
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    
    # 统计错误类型
    error_stats = {}
    for file_path, file_name, detail in results['failed']:
        error_type = detail.get('error_type', 'Unknown')
        # 获取友好的错误名称
        if error_type in ERROR_TYPE_TO_TRANSLATION_KEY:
            error_name = get_profile_error_message(user_id, error_type)
        else:
            error_name = error_type
        
        if error_name not in error_stats:
            error_stats[error_name] = 0
        error_stats[error_name] += 1
    
    # ========================================
    # 1. 生成详细的TXT报告
    # ========================================
    report_lines = []
    
    report_lines.append("=" * 80)
    report_lines.append(t(user_id, 'profile_report_title'))
    report_lines.append("=" * 80)
    report_lines.append(f"{t(user_id, 'profile_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(t(user_id, 'profile_report_summary').format(total=total, success=success_count, failed=failed_count))
    report_lines.append("")
    
    # 成功的账号详情
    if results['success']:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_success_title').format(count=success_count))
        report_lines.append("=" * 80)
        for idx, (file_path, file_name, detail) in enumerate(results['success'], 1):
            report_lines.append(f"\n{idx}. {detail.get('phone', file_name)}")
            report_lines.append(f"   {t(user_id, 'profile_report_file')} {file_name}")
            
            # 显示变更详情 - 使用"修改前xxx 修改后xxx"格式
            changes = detail.get('changes', {})
            
            # 姓名修改
            if 'name' in changes and changes['name'].get('success'):
                old_name = changes['name'].get('old', '').strip()
                new_name = changes['name'].get('new', '').strip()
                if old_name and new_name:
                    report_lines.append(f"   {t(user_id, 'profile_report_name_change').format(before=old_name, after=new_name)}")
                elif new_name:
                    report_lines.append(f"   - {t(user_id, 'profile_config_name')} {t(user_id, 'profile_report_name_change').format(before='', after=new_name)}")
            
            # 头像修改
            if 'photo' in changes and changes['photo'].get('success'):
                action = changes['photo'].get('action', 'deleted')
                if action == 'deleted':
                    report_lines.append(f"   {t(user_id, 'profile_report_avatar_deleted')}")
                elif action == 'uploaded':
                    report_lines.append(f"   {t(user_id, 'profile_report_avatar_uploaded')}")
            
            # 简介修改
            if 'bio' in changes and changes['bio'].get('success'):
                old_bio = changes['bio'].get('old', '').strip()
                new_bio = changes['bio'].get('new', '').strip()
                if old_bio and new_bio:
                    # 限制显示长度，避免报告太长
                    old_bio_display = old_bio[:30] + '...' if len(old_bio) > 30 else old_bio
                    new_bio_display = new_bio[:30] + '...' if len(new_bio) > 30 else new_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=old_bio_display, after=new_bio_display)}")
                elif new_bio:
                    new_bio_display = new_bio[:30] + '...' if len(new_bio) > 30 else new_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=t(user_id, 'profile_none'), after=new_bio_display)}")
                elif old_bio:
                    old_bio_display = old_bio[:30] + '...' if len(old_bio) > 30 else old_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=old_bio_display, after=t(user_id, 'profile_bio_cleared_inline'))}")
                else:
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_cleared')}")
            
            # 用户名修改
            if 'username' in changes and changes['username'].get('success'):
                old_username = changes['username'].get('old', '').strip()
                new_username = changes['username'].get('new', '').strip()
                
                # 格式化用户名显示
                if old_username and old_username != '无':
                    old_display = old_username if old_username.startswith('@') else f"@{old_username}"
                else:
                    old_display = "(无)"
                
                if new_username and new_username != '已删除':
                    new_display = new_username if new_username.startswith('@') else f"@{new_username}"
                else:
                    new_display = "(已删除)"
                
                report_lines.append(f"   {t(user_id, 'profile_report_username_change').format(before=old_display, after=new_display)}")
        
        report_lines.append("")
    
    # 失败的账号详情
    if results['failed']:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_failed_title').format(count=failed_count))
        report_lines.append("=" * 80)
        for idx, (file_path, file_name, detail) in enumerate(results['failed'], 1):
            report_lines.append(f"\n{idx}. {detail.get('phone', file_name) if detail.get('phone') else file_name}")
            report_lines.append(f"   {t(user_id, 'profile_report_file')} {file_name}")
            error_type = detail.get('error_type', 'Unknown')
            error_message = detail.get('error', t(user_id, 'profile_error_unknown'))
            report_lines.append(f"   {t(user_id, 'profile_report_error_type')} {error_type}")
            report_lines.append(f"   {t(user_id, 'profile_report_error_reason')} {error_message}")
        
        report_lines.append("")
    
    # 错误统计
    if error_stats:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_error_stats'))
        report_lines.append("=" * 80)
        for error_name, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"• {error_name}: {count}")
        report_lines.append("")
    
    # 保存报告文件
    report_content = "\n".join(report_lines)
    report_path = os.path.join(config.RESULTS_DIR, f"profile_report_{timestamp}.txt")
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        logger.info(f"✅ 报告文件已生成: {report_path}")
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
    
    # ========================================
    # 2. 打包成功的账号文件
    # ========================================
    success_zip_path = None
    if results['success']:
        logger.info(f"📦 开始打包成功的账号文件...")
        success_zip_path = os.path.join(config.RESULTS_DIR, f"profile_success_{success_count}_{timestamp}.zip")
        
        try:
            with zipfile.ZipFile(success_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                added_paths = set()  # 追踪已添加的文件路径，避免重复
                
                for file_path, file_name, detail in results['success']:
                    original_file_path = detail.get('file_path', file_path)
                    # 提取手机号作为前缀
                    phone = extract_phone_from_path(original_file_path) or extract_phone_from_path(file_name) or file_name.replace('.session', '').replace('.json', '')
                    
                    try:
                        # 判断文件类型
                        if os.path.isdir(original_file_path):
                            # TData格式：打包整个目录，使用手机号作为前缀
                            # 获取目录名（通常是tdata）
                            tdata_dirname = os.path.basename(original_file_path)
                            
                            for root, dirs, files in os.walk(original_file_path):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(file_full_path, original_file_path)
                                    # 包含tdata目录名在路径中: 手机号/tdata/D877F783D5D3EF8C/...
                                    arc_name = f"{phone}/{tdata_dirname}/{rel_path}"
                                    
                                    if arc_name not in added_paths:
                                        added_paths.add(arc_name)
                                        zipf.write(file_full_path, arc_name)
                        else:
                            # Session格式：直接打包到ZIP根目录，使用手机号作为文件名
                            # 格式：手机号.session 和 手机号.json（不要手机号文件夹）
                            if os.path.exists(original_file_path):
                                arc_name = f"{phone}.session"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(original_file_path, arc_name)
                            
                            # Journal文件
                            journal_path = original_file_path + '-journal'
                            if os.path.exists(journal_path):
                                arc_name = f"{phone}.session-journal"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(journal_path, arc_name)
                            
                            # JSON文件
                            json_path = os.path.splitext(original_file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                arc_name = f"{phone}.json"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(json_path, arc_name)
                    except Exception as e:
                        logger.warning(f"⚠️ 打包文件失败 {file_name}: {e}")
            
            logger.info(f"✅ 成功账号已打包: {success_zip_path}")
        except Exception as e:
            logger.error(f"❌ 打包成功账号失败: {e}")
            success_zip_path = None
    
    # ========================================
    # 3. 打包失败的账号文件
    # ========================================
    failed_zip_path = None
    if results['failed']:
        logger.info(f"📦 开始打包失败的账号文件...")
        failed_zip_path = os.path.join(config.RESULTS_DIR, f"profile_failed_{failed_count}_{timestamp}.zip")
        
        try:
            with zipfile.ZipFile(failed_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                added_paths = set()  # 追踪已添加的文件路径，避免重复
                
                for file_path, file_name, detail in results['failed']:
                    original_file_path = detail.get('file_path', file_path)
                    # 提取手机号作为前缀
                    phone = extract_phone_from_path(original_file_path) or extract_phone_from_path(file_name) or file_name.replace('.session', '').replace('.json', '')
                    
                    try:
                        # 判断文件类型
                        if os.path.isdir(original_file_path):
                            # TData格式：打包整个目录，使用手机号作为前缀
                            # 获取目录名（通常是tdata）
                            tdata_dirname = os.path.basename(original_file_path)
                            
                            for root, dirs, files in os.walk(original_file_path):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(file_full_path, original_file_path)
                                    # 包含tdata目录名在路径中: 手机号/tdata/D877F783D5D3EF8C/...
                                    arc_name = f"{phone}/{tdata_dirname}/{rel_path}"
                                    
                                    if arc_name not in added_paths:
                                        added_paths.add(arc_name)
                                        zipf.write(file_full_path, arc_name)
                        else:
                            # Session格式：直接打包到ZIP根目录，使用手机号作为文件名
                            # 格式：手机号.session 和 手机号.json（不要手机号文件夹）
                            if os.path.exists(original_file_path):
                                arc_name = f"{phone}.session"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(original_file_path, arc_name)
                            
                            # Journal文件
                            journal_path = original_file_path + '-journal'
                            if os.path.exists(journal_path):
                                arc_name = f"{phone}.session-journal"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(journal_path, arc_name)
                            
                            # JSON文件
                            json_path = os.path.splitext(original_file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                arc_name = f"{phone}.json"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(json_path, arc_name)
                    except Exception as e:
                        logger.warning(f"⚠️ 打包文件失败 {file_name}: {e}")
            
            logger.info(f"✅ 失败账号已打包: {failed_zip_path}")
        except Exception as e:
            logger.error(f"❌ 打包失败账号失败: {e}")
            failed_zip_path = None
    
    # ========================================
    # 4. 发送报告文件
    # ========================================
    try:
        if os.path.exists(report_path):
            with open(report_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_report_{timestamp}.txt",
                    caption=t(user_id, 'profile_output_report'),
                    parse_mode='HTML'
                )
            logger.info("✅ 报告文件已发送")
    except Exception as e:
        logger.error(f"❌ 发送报告文件失败: {e}")
    
    # ========================================
    # 5. 发送成功账号ZIP
    # ========================================
    if success_zip_path and os.path.exists(success_zip_path):
        try:
            with open(success_zip_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_success_{success_count}.zip",
                    caption=t(user_id, 'profile_output_success').format(count=success_count),
                    parse_mode='HTML',
                    timeout=120
                )
            logger.info("✅ 成功账号ZIP已发送")
        except Exception as e:
            logger.error(f"❌ 发送成功账号ZIP失败: {e}")
    
    # ========================================
    # 6. 发送失败账号ZIP
    # ========================================
    if failed_zip_path and os.path.exists(failed_zip_path):
        try:
            with open(failed_zip_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_failed_{failed_count}.zip",
                    caption=t(user_id, 'profile_output_failed').format(count=failed_count),
                    parse_mode='HTML',
                    timeout=120
                )
            logger.info("✅ 失败账号ZIP已发送")
        except Exception as e:
            logger.error(f"❌ 发送失败账号ZIP失败: {e}")
    
    # ========================================
    # 7. 更新最终消息
    # ========================================
    error_stats_text = ""
    if error_stats:
        error_stats_text = f"\n\n<b>{t(user_id, 'profile_error_stats')}</b>\n"
        for error_name, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True):
            error_stats_text += f"• {error_name}: {count}\n"
    
    files_sent_text = f"\n\n<b>{t(user_id, 'profile_files_sent')}</b>\n{t(user_id, 'profile_file_report')} profile_report.txt"
    if success_zip_path:
        files_sent_text += f"\n{t(user_id, 'profile_file_success')} profile_success_{success_count}.zip"
    if failed_zip_path:
        files_sent_text += f"\n{t(user_id, 'profile_file_failed')} profile_failed_{failed_count}.zip"
    
    final_text = f"""<b>{t(user_id, 'profile_complete')}</b>


    def handle_profile_update_start(self, query):
    """处理修改资料开始"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查会员权限
    if not self.db.is_admin(user_id):
        is_member, level, expiry = self.db.check_membership(user_id)
        if not is_member:
            query.edit_message_text(
                text=t(user_id, 'profile_need_member'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(user_id, 'btn_vip_menu'), callback_data="vip_menu"),
                    InlineKeyboardButton(t(user_id, 'btn_back_to_menu'), callback_data="back_to_main")
                ]]),
                parse_mode='HTML'
            )
            return
    
    text = f"""

    def handle_profile_update_callbacks(self, update: Update, context: CallbackContext, query, data: str):
    """处理修改资料相关回调"""
    user_id = query.from_user.id
    
    if data == "profile_mode_random":
        self.handle_profile_random_mode(query, user_id)
    elif data == "profile_mode_custom":
        self.handle_profile_custom_mode(query, user_id)
    elif data == "profile_custom_back":
        # 返回自定义配置菜单
        if user_id in self.pending_profile_update:
            config = self.pending_profile_update[user_id]['config']
            self._show_custom_config_menu(query, user_id, config)
        else:
            query.answer(t(user_id, 'profile_session_expired'))
    elif data.startswith("profile_random_"):
        self.handle_profile_random_config(update, context, query, data, user_id)
    elif data.startswith("profile_custom_"):
        self.handle_profile_custom_config(update, context, query, data, user_id)
    elif data == "profile_execute":
        self.handle_profile_update_execute(update, context, query, user_id)
    elif data == "profile_confirm_execute":
        self.handle_profile_confirm_execute(update, context, query, user_id)
    elif data == "profile_cancel":
        query.answer()
        if user_id in self.pending_profile_update:
            self.cleanup_profile_update_task(user_id)
        self.show_main_menu(update, user_id)


    def handle_profile_random_mode(self, query, user_id: int):
    """处理随机生成模式"""
    query.answer()
    
    # 初始化配置
    config = ProfileUpdateConfig(mode='random')
    config.update_name = True
    config.photo_action = 'keep'
    config.bio_action = 'keep'
    config.username_action = 'keep'
    
    self.pending_profile_update[user_id] = {
        'config': config,
        'status': 'configuring'
    }
    
    self._show_random_config_menu(query, user_id, config)


    def handle_profile_random_config(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理随机模式配置选项"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    if data == "profile_random_photo":
        # 切换头像选项
        if config.photo_action == 'keep':
            config.photo_action = 'delete_all'
            config.update_photo = True
        else:
            config.photo_action = 'keep'
            config.update_photo = False
    elif data == "profile_random_bio":
        # 循环切换简介选项：keep -> clear -> random -> keep
        if config.bio_action == 'keep':
            config.bio_action = 'clear'
            config.update_bio = True
        elif config.bio_action == 'clear':
            config.bio_action = 'random'
            config.update_bio = True
        else:
            config.bio_action = 'keep'
            config.update_bio = False
    elif data == "profile_random_username":
        # 循环切换用户名选项：keep -> delete -> random -> keep
        if config.username_action == 'keep':
            config.username_action = 'delete'
            config.update_username = True
        elif config.username_action == 'delete':
            config.username_action = 'random'
            config.update_username = True
        else:
            config.username_action = 'keep'
            config.update_username = False
    
    # 刷新菜单
    self._show_random_config_menu(query, user_id, config)


    def handle_profile_custom_mode(self, query, user_id: int):
    """处理自定义生成模式"""
    query.answer()
    
    # 初始化配置
    config = ProfileUpdateConfig(mode='custom')
    config.update_name = False
    config.update_photo = False
    config.update_bio = False
    config.update_username = False
    
    self.pending_profile_update[user_id] = {
        'config': config,
        'status': 'configuring',
        'custom_input_field': None  # 当前正在配置的字段
    }
    
    self._show_custom_config_menu(query, user_id, config)


    def handle_profile_custom_config(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理自定义模式配置选项"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_custom_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    
    if data == "profile_custom_name":
        # 配置姓名
        self._show_custom_field_config(query, user_id, 'name', t(user_id, 'profile_field_name'))
    elif data == "profile_custom_photo":
        # 配置头像
        self._show_custom_field_config(query, user_id, 'photo', t(user_id, 'profile_field_avatar'))
    elif data == "profile_custom_bio":
        # 配置简介
        self._show_custom_field_config(query, user_id, 'bio', t(user_id, 'profile_field_bio'))
    elif data == "profile_custom_username":
        # 配置用户名
        self._show_custom_field_config(query, user_id, 'username', t(user_id, 'profile_field_username'))
    elif data.startswith("profile_custom_field_"):
        # 处理字段配置选项
        self._handle_custom_field_action(update, context, query, data, user_id)


    def handle_profile_custom_text_input(self, update: Update, context: CallbackContext, user_id: int, field_name: str, text: str):
    """处理自定义资料的文本输入"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    # 解析输入的文本（按行分割）
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not lines:
        self.safe_send_message(update, t(user_id, 'profile_custom_input_empty'), 'HTML')
        return
    
    # Helper function to get translated field display name
    def get_field_display(field):
        field_map = {
            'name': 'profile_field_name',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        return t(user_id, field_map.get(field, 'profile_field_name'))
    
    field_display = get_field_display(field_name)
    
    if field_name == 'name':
        config.custom_names = lines
        config.update_name = True
    elif field_name == 'bio':
        config.custom_bios = lines
        config.update_bio = True
        config.bio_action = 'custom'
    elif field_name == 'username':
        config.custom_usernames = lines
        config.update_username = True
        config.username_action = 'custom'
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "profile_custom_config")
    
    # 发送确认消息和返回按钮
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
    ]])
    
    self.safe_send_message(
        update,
        t(user_id, 'profile_custom_configured').format(count=len(lines), field=field_display),
        'HTML',
        reply_markup=keyboard
    )


    def _create_avatar_upload_dir(self, user_id: int) -> str:
    """创建头像上传目录并返回路径"""
    upload_dir = os.path.join(config.UPLOADS_DIR, f"avatars_{user_id}_{int(time.time())}")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


    def handle_profile_photo_upload(self, update: Update, context: CallbackContext, user_id: int):
    """处理资料头像的单张图片上传"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    progress_msg = self.safe_send_message(update, t(user_id, 'profile_photo_processing'), 'HTML')
    if not progress_msg:
        return
    
    try:
        # 获取最大尺寸的图片
        photo = update.message.photo[-1]
        
        # 创建上传目录
        upload_dir = self._create_avatar_upload_dir(user_id)
        
        # 下载图片
        file = photo.get_file()
        file_path = os.path.join(upload_dir, f"avatar_{user_id}.jpg")
        file.download(file_path)
        
        # 保存到配置
        config.custom_photos = [file_path]
        config.update_photo = True
        config.photo_action = 'custom'
        
        # 清除用户状态
        self.db.save_user(user_id, "", "", "profile_custom_config")
        
        # 显示确认消息
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
        ]])
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_photo_uploaded_success'),
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"处理资料头像上传失败: {e}")
        import traceback
        traceback.print_exc()
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_photo_upload_failed').format(error=str(e)),
            parse_mode='HTML'
        )


    def handle_profile_custom_file_upload(self, update: Update, context: CallbackContext, user_id: int, field_name: str, document):
    """处理自定义资料的文件上传"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    progress_msg = self.safe_send_message(update, t(user_id, 'processing_your_file'), 'HTML')
    if not progress_msg:
        return
    
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"profile_custom_{field_name}_")
        temp_file = os.path.join(temp_dir, document.file_name)
        
        # 下载文件
        document.get_file().download(temp_file)
        
        # Helper function to get translated field display name
        def get_field_display(field):
            field_map = {
                'name': 'profile_field_name',
                'photo': 'profile_field_avatar',
                'bio': 'profile_field_bio',
                'username': 'profile_field_username'
            }
            return t(user_id, field_map.get(field, 'profile_field_name'))
        
        field_display = get_field_display(field_name)
        
        if field_name == 'photo':
            # 处理图片文件
            items = []
            
            # 检查是否是图片文件
            if temp_file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                # 单个图片文件
                upload_dir = self._create_avatar_upload_dir(user_id)
                dest_path = os.path.join(upload_dir, document.file_name)
                shutil.copy(temp_file, dest_path)
                items.append(dest_path)
                
            elif temp_file.lower().endswith('.zip'):
                # ZIP文件，解压并提取图片
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # 查找所有图片文件
                upload_dir = self._create_avatar_upload_dir(user_id)
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                            file_path = os.path.join(root, file)
                            dest_path = os.path.join(upload_dir, file)
                            shutil.copy(file_path, dest_path)
                            items.append(dest_path)
            
            if not items:
                self.safe_edit_message_text(
                    progress_msg,
                    t(user_id, 'profile_custom_no_images'),
                    parse_mode='HTML'
                )
                return
            
            config.custom_photos = items
            config.update_photo = True
            config.photo_action = 'custom'
            
        else:
            # 处理文本文件（姓名、简介、用户名）
            # 验证是否为 .txt 文件
            if not temp_file.lower().endswith('.txt'):
                self.safe_edit_message_text(
                    progress_msg,
                    f"❌ <b>文件格式错误</b>\n\n请上传 .txt 文本文件，当前文件: {document.file_name}",
                    parse_mode='HTML'
                )
                return
            
            try:
                with open(temp_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    with open(temp_file, 'r', encoding='gbk') as f:
                        lines = [line.strip() for line in f if line.strip()]
                except:
                    self.safe_edit_message_text(
                        progress_msg,
                        t(user_id, 'profile_custom_encoding_error'),
                        parse_mode='HTML'
                    )
                    return
            
            if not lines:
                self.safe_edit_message_text(
                    progress_msg,
                    t(user_id, 'profile_custom_file_empty'),
                    parse_mode='HTML'
                )
                return
            
            # 根据字段类型保存
            if field_name == 'name':
                config.custom_names = lines
                config.update_name = True
            elif field_name == 'bio':
                config.custom_bios = lines
                config.update_bio = True
                config.bio_action = 'custom'
            elif field_name == 'username':
                config.custom_usernames = lines
                config.update_username = True
                config.username_action = 'custom'
            
            items = lines
        
        # 清除用户状态
        self.db.save_user(user_id, "", "", "profile_custom_config")
        
        # 显示确认消息
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
        ]])
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_custom_configured').format(count=len(items), field=field_display),
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"处理自定义资料文件上传失败: {e}")
        import traceback
        traceback.print_exc()
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_custom_processing_failed').format(error=str(e)),
            parse_mode='HTML'
        )
    finally:
        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


    def handle_profile_confirm_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理确认执行资料修改"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        self.safe_edit_message(query, t(user_id, 'profile_custom_task_expired'))
        return
    
    task = self.pending_profile_update[user_id]
    
    # 检查是否有文件信息
    if 'files' not in task or 'file_type' not in task or 'progress_msg' not in task:
        self.safe_edit_message(query, "❌ 任务信息不完整，请重新上传文件")
        return
    
    files = task['files']
    file_type = task['file_type']
    config = task['config']
    progress_msg = task['progress_msg']
    
    # 开始执行（使用线程运行异步任务，避免事件循环错误）
    def execute_profile_update():
        try:
            asyncio.run(self._execute_profile_update(user_id, files, file_type, config, context, progress_msg))
        except asyncio.CancelledError:
            logger.info(f"[profile_update] 任务被取消")
        except Exception as e:
            logger.error(f"[profile_update] 处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    thread = threading.Thread(target=execute_profile_update, daemon=True)
    thread.start()


    def handle_profile_update_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """开始执行资料修改"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        self.safe_edit_message(query, t(user_id, 'profile_session_expired'))
        return
    
    task = self.pending_profile_update[user_id]
    config = task['config']
    
    text = f"""



# ===== Handler Methods =====

    def get_zip_name_translation_key(self, status: str) -> str:
    """Map internal status to ZIP file name translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for ZIP file naming
    """
    zip_map = {
        "无限制": "zip_no_restriction",
        "垃圾邮件": "zip_spambot",
        "冻结": "zip_frozen",
        "封禁": "zip_banned",
        "连接错误": "zip_connection_error",
    }
    return zip_map.get(status, "zip_no_restriction")


    def sanitize_filename(self, filename: str) -> str:
    """清理文件名，保留 Emoji 和括号
    
    只移除文件系统不允许的字符，保留所有Unicode字符包括Emoji。
    
    移除的字符（Windows和Unix文件系统不允许）:
    - 反斜杠 (\)、正斜杠 (/)、冒号 (:)
    - 星号 (*)、问号 (?)、引号 (")
    - 小于号 (<)、大于号 (>)、竖线 (|)
    
    保留的字符:
    - Emoji (如 🇮🇳, 🎉)
    - 中文括号 （）
    - 所有Unicode字符（中文、日文、俄文等）
    - 加号 (+)、下划线 (_)、连字符 (-) 等
    
    示例:
    - '🇮🇳 随机混合国家（有密码）' -> '🇮🇳 随机混合国家（有密码）'
    - 'test/file:name' -> 'testfilename'
    """
    # 只移除文件系统不允许的字符
    # Windows和Unix都不允许这些字符: \ / : * ? " < > |
    invalid_chars = r'[\\/:*?"<>|]'
    filename = re.sub(invalid_chars, '', filename)
    
    # 限制长度（保留扩展名空间）
    max_length = 200
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    # 去除首尾空格和点号
    filename = filename.strip('. ')
    
    # 如果文件名为空，使用默认名
    if not filename:
        filename = 'unnamed_file'
    
    return filename


    def handle_photo(self, update: Update, context: CallbackContext):
    """处理图片上传（用于广播媒体和资料头像）"""
    user_id = update.effective_user.id
    
    # 检查用户状态
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return
        
        user_status = row[0]
        
        # 处理资料头像上传
        if user_status == "profile_custom_upload_photo":
            self.handle_profile_photo_upload(update, context, user_id)
            return
        
        # 处理广播媒体上传
        if user_status != "waiting_broadcast_media":
            # 不是在等待上传，忽略
            return
    except:
        return
    
    # 检查是否有待处理的广播任务
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 获取最大尺寸的图片
    photo = update.message.photo[-1]
    
    # 保存图片 file_id
    task['media_file_id'] = photo.file_id
    task['media_type'] = 'photo'
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 发送成功消息并返回编辑器
    self.safe_send_message(
        update,
        "✅ <b>图片已保存</b>\n\n返回编辑器继续设置",
        'HTML'
    )
    
    # 模拟 query 对象返回编辑器
    class FakeQuery:
        def __init__(self, user, chat):
            self.from_user = user
            self.message = type('obj', (object,), {'chat_id': chat.id, 'message_id': None})()
        def answer(self):
            pass
    
    fake_query = FakeQuery(update.effective_user, update.effective_chat)
    
    # 发送新消息显示编辑器
    self.show_broadcast_wizard_editor_as_new_message(update, context)


    def handle_rename_start(self, query):
    """开始文件重命名流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 初始化任务
    self.pending_rename[user_id] = {
        'temp_dir': None,
        'file_path': None,
        'orig_name': None,
        'ext': None
    }
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_rename_file"
    )
    
    text = f"""

    def handle_rename_file_upload(self, update: Update, context: CallbackContext, document):
    """处理重命名文件上传"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_rename:
        self.safe_send_message(update, t(user_id, 'rename_no_task'))
        return
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="temp_rename_")
    orig_name = document.file_name
    
    # 分离文件名和扩展名
    if '.' in orig_name:
        name_parts = orig_name.rsplit('.', 1)
        base_name = name_parts[0]
        ext = '.' + name_parts[1]
    else:
        base_name = orig_name
        ext = ''
    
    # 下载文件
    file_path = os.path.join(temp_dir, orig_name)
    try:
        document.get_file().download(file_path)
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'rename_download_failed').format(error=str(e)))
        shutil.rmtree(temp_dir, ignore_errors=True)
        return
    
    # 保存任务信息
    self.pending_rename[user_id]['temp_dir'] = temp_dir
    self.pending_rename[user_id]['file_path'] = file_path
    self.pending_rename[user_id]['orig_name'] = orig_name
    self.pending_rename[user_id]['ext'] = ext
    
    # 更新状态，等待新文件名
    self.db.save_user(
        user_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
        "waiting_rename_newname"
    )
    
    text = f"""

    def handle_rename_newname_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理新文件名输入"""
    if user_id not in self.pending_rename:
        self.safe_send_message(update, t(user_id, 'rename_no_task'))
        return
    
    task = self.pending_rename[user_id]
    
    # 调试日志：记录原始输入
    logger.debug(f"重命名输入 - 用户{user_id} - 原始文本: {repr(text)}")
    logger.debug(f"重命名输入 - 用户{user_id} - text.strip(): {repr(text.strip())}")
    
    # 清理并验证新文件名
    new_name = self.sanitize_filename(text.strip())
    logger.debug(f"重命名输入 - 用户{user_id} - 清理后: {repr(new_name)}")
    
    if not new_name:
        self.safe_send_message(update, t(user_id, 'rename_invalid_name'))
        return
    
    # 构建完整的新文件名
    new_filename = new_name + task['ext']
    new_file_path = os.path.join(task['temp_dir'], new_filename)
    
    # 重命名文件
    try:
        shutil.move(task['file_path'], new_file_path)
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'rename_failed').format(error=str(e)))
        self.cleanup_rename_task(user_id)
        return
    
    # 发送重命名后的文件
    # 注意：显式指定filename参数以确保Telegram使用正确的文件名
    old_name_html = f"<code>{task['orig_name']}</code>"
    new_name_html = f"<code>{new_filename}</code>"
    caption = (
        f"<b>{t(user_id, 'rename_success')}</b>\n\n"
        f"{t(user_id, 'rename_old_name').format(old_name=old_name_html)}\n"
        f"{t(user_id, 'rename_new_name').format(new_name=new_name_html)}\n\n"
        f"{t(user_id, 'rename_telegram_tip')}"
    )
    
    if self.send_document_safely(user_id, new_file_path, caption, new_filename):
        self.safe_send_message(update, f"<b>{t(user_id, 'rename_file_sent')}</b>", 'HTML')
    else:
        self.safe_send_message(update, t(user_id, 'rename_send_failed'))
    
    # 清理任务
    self.cleanup_rename_task(user_id)


    def _ask_for_group_names(self, update: Update, user_id: int):
    """询问群组名称和简介"""
    task = self.pending_batch_create[user_id]
    
    total_to_create = task['valid_accounts'] * task['count_per_account']
    
    admin_usernames = task.get('admin_usernames', [])
    admin_display = ', '.join([f"@{u}" for u in admin_usernames]) if admin_usernames else t(user_id, 'batch_create_admins_none')
    
    step3_title_key = 'batch_create_step3_title_group' if task['creation_type'] == 'group' else 'batch_create_step3_title_channel'
    step3_prompt_key = 'batch_create_step3_prompt' if task['creation_type'] == 'group' else 'batch_create_step3_prompt_channel'
    step3_format_key = 'batch_create_step3_format_group' if task['creation_type'] == 'group' else 'batch_create_step3_format_channel'
    
    text = f"""

    def handle_batch_create_names_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理群组名称和简介输入"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    try:
        lines = text.strip().split('\n')
        group_names = []
        group_descriptions = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if '|' in line:
                parts = line.split('|', 1)
                name = parts[0].strip()
                desc = parts[1].strip() if len(parts) > 1 else ""
            else:
                name = line
                desc = ""
            
            if name:
                group_names.append(name)
                group_descriptions.append(desc)
        
        if not group_names:
            self.safe_send_message(update, "❌ 未找到有效的名称，请重新输入")
            return
        
        task['group_names'] = group_names
        task['group_descriptions'] = group_descriptions
        
        names_saved_key = 'batch_create_names_saved_group' if task['creation_type'] == 'group' else 'batch_create_names_saved_channel'
        step4_title_key = 'batch_create_step4_title_group' if task['creation_type'] == 'group' else 'batch_create_step4_title_channel'
        
        text = f"""

    def handle_batch_create_usernames_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理自定义用户名输入"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    try:
        lines = text.strip().split('\n')
        custom_usernames = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除 @ 前缀
            username = line.lstrip('@')
            if username:
                custom_usernames.append(username)
        
        if not custom_usernames:
            self.safe_send_message(update, "❌ 未找到有效的用户名，请重新输入")
            return
        
        task['custom_usernames'] = custom_usernames
        
        # 显示确认信息
        self._show_batch_create_confirm(update, user_id)
        
    except Exception as e:
        self.safe_send_message(update, f"❌ 解析失败：{str(e)}")


    def process_batch_create_names_file(self, update: Update, context: CallbackContext, document, user_id: int):
    """处理群组名称文件上传"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    try:
        # 下载文件
        file = document.get_file()
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8')
        file.download(temp_file.name)
        temp_file.close()
        
        # 读取文件内容
        with open(temp_file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 清理临时文件
        os.unlink(temp_file.name)
        
        # 使用现有的处理逻辑
        fake_update = self._create_fake_update(user_id)
        self.handle_batch_create_names_input(fake_update, context, user_id, content)
        
    except Exception as e:
        logger.error(f"处理名称文件失败: {e}")
        self.safe_send_message(update, f"❌ 文件处理失败：{str(e)}")


    def process_batch_create_usernames_file(self, update: Update, context: CallbackContext, document, user_id: int):
    """处理用户名文件上传"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    try:
        # 下载文件
        file = document.get_file()
        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8')
        file.download(temp_file.name)
        temp_file.close()
        
        # 读取文件内容
        with open(temp_file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 清理临时文件
        os.unlink(temp_file.name)
        
        # 使用现有的处理逻辑
        fake_update = self._create_fake_update(user_id)
        self.handle_batch_create_usernames_input(fake_update, context, user_id, content)
        
    except Exception as e:
        logger.error(f"处理用户名文件失败: {e}")
        self.safe_send_message(update, f"❌ 文件处理失败：{str(e)}")




    def _generate_profile_update_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成资料修改详细报告和打包结果文件"""
    logger.info("📊 开始生成详细报告和打包文件...")
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    total = len(results['success']) + len(results['failed'])
    success_count = len(results['success'])
    failed_count = len(results['failed'])
    
    # 统计错误类型
    error_stats = {}
    for file_path, file_name, detail in results['failed']:
        error_type = detail.get('error_type', 'Unknown')
        # 获取友好的错误名称
        if error_type in ERROR_TYPE_TO_TRANSLATION_KEY:
            error_name = get_profile_error_message(user_id, error_type)
        else:
            error_name = error_type
        
        if error_name not in error_stats:
            error_stats[error_name] = 0
        error_stats[error_name] += 1
    
    # ========================================
    # 1. 生成详细的TXT报告
    # ========================================
    report_lines = []
    
    report_lines.append("=" * 80)
    report_lines.append(t(user_id, 'profile_report_title'))
    report_lines.append("=" * 80)
    report_lines.append(f"{t(user_id, 'profile_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(t(user_id, 'profile_report_summary').format(total=total, success=success_count, failed=failed_count))
    report_lines.append("")
    
    # 成功的账号详情
    if results['success']:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_success_title').format(count=success_count))
        report_lines.append("=" * 80)
        for idx, (file_path, file_name, detail) in enumerate(results['success'], 1):
            report_lines.append(f"\n{idx}. {detail.get('phone', file_name)}")
            report_lines.append(f"   {t(user_id, 'profile_report_file')} {file_name}")
            
            # 显示变更详情 - 使用"修改前xxx 修改后xxx"格式
            changes = detail.get('changes', {})
            
            # 姓名修改
            if 'name' in changes and changes['name'].get('success'):
                old_name = changes['name'].get('old', '').strip()
                new_name = changes['name'].get('new', '').strip()
                if old_name and new_name:
                    report_lines.append(f"   {t(user_id, 'profile_report_name_change').format(before=old_name, after=new_name)}")
                elif new_name:
                    report_lines.append(f"   - {t(user_id, 'profile_config_name')} {t(user_id, 'profile_report_name_change').format(before='', after=new_name)}")
            
            # 头像修改
            if 'photo' in changes and changes['photo'].get('success'):
                action = changes['photo'].get('action', 'deleted')
                if action == 'deleted':
                    report_lines.append(f"   {t(user_id, 'profile_report_avatar_deleted')}")
                elif action == 'uploaded':
                    report_lines.append(f"   {t(user_id, 'profile_report_avatar_uploaded')}")
            
            # 简介修改
            if 'bio' in changes and changes['bio'].get('success'):
                old_bio = changes['bio'].get('old', '').strip()
                new_bio = changes['bio'].get('new', '').strip()
                if old_bio and new_bio:
                    # 限制显示长度，避免报告太长
                    old_bio_display = old_bio[:30] + '...' if len(old_bio) > 30 else old_bio
                    new_bio_display = new_bio[:30] + '...' if len(new_bio) > 30 else new_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=old_bio_display, after=new_bio_display)}")
                elif new_bio:
                    new_bio_display = new_bio[:30] + '...' if len(new_bio) > 30 else new_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=t(user_id, 'profile_none'), after=new_bio_display)}")
                elif old_bio:
                    old_bio_display = old_bio[:30] + '...' if len(old_bio) > 30 else old_bio
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_change').format(before=old_bio_display, after=t(user_id, 'profile_bio_cleared_inline'))}")
                else:
                    report_lines.append(f"   {t(user_id, 'profile_report_bio_cleared')}")
            
            # 用户名修改
            if 'username' in changes and changes['username'].get('success'):
                old_username = changes['username'].get('old', '').strip()
                new_username = changes['username'].get('new', '').strip()
                
                # 格式化用户名显示
                if old_username and old_username != '无':
                    old_display = old_username if old_username.startswith('@') else f"@{old_username}"
                else:
                    old_display = "(无)"
                
                if new_username and new_username != '已删除':
                    new_display = new_username if new_username.startswith('@') else f"@{new_username}"
                else:
                    new_display = "(已删除)"
                
                report_lines.append(f"   {t(user_id, 'profile_report_username_change').format(before=old_display, after=new_display)}")
        
        report_lines.append("")
    
    # 失败的账号详情
    if results['failed']:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_failed_title').format(count=failed_count))
        report_lines.append("=" * 80)
        for idx, (file_path, file_name, detail) in enumerate(results['failed'], 1):
            report_lines.append(f"\n{idx}. {detail.get('phone', file_name) if detail.get('phone') else file_name}")
            report_lines.append(f"   {t(user_id, 'profile_report_file')} {file_name}")
            error_type = detail.get('error_type', 'Unknown')
            error_message = detail.get('error', t(user_id, 'profile_error_unknown'))
            report_lines.append(f"   {t(user_id, 'profile_report_error_type')} {error_type}")
            report_lines.append(f"   {t(user_id, 'profile_report_error_reason')} {error_message}")
        
        report_lines.append("")
    
    # 错误统计
    if error_stats:
        report_lines.append("=" * 80)
        report_lines.append(t(user_id, 'profile_report_error_stats'))
        report_lines.append("=" * 80)
        for error_name, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"• {error_name}: {count}")
        report_lines.append("")
    
    # 保存报告文件
    report_content = "\n".join(report_lines)
    report_path = os.path.join(config.RESULTS_DIR, f"profile_report_{timestamp}.txt")
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        logger.info(f"✅ 报告文件已生成: {report_path}")
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
    
    # ========================================
    # 2. 打包成功的账号文件
    # ========================================
    success_zip_path = None
    if results['success']:
        logger.info(f"📦 开始打包成功的账号文件...")
        success_zip_path = os.path.join(config.RESULTS_DIR, f"profile_success_{success_count}_{timestamp}.zip")
        
        try:
            with zipfile.ZipFile(success_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                added_paths = set()  # 追踪已添加的文件路径，避免重复
                
                for file_path, file_name, detail in results['success']:
                    original_file_path = detail.get('file_path', file_path)
                    # 提取手机号作为前缀
                    phone = extract_phone_from_path(original_file_path) or extract_phone_from_path(file_name) or file_name.replace('.session', '').replace('.json', '')
                    
                    try:
                        # 判断文件类型
                        if os.path.isdir(original_file_path):
                            # TData格式：打包整个目录，使用手机号作为前缀
                            # 获取目录名（通常是tdata）
                            tdata_dirname = os.path.basename(original_file_path)
                            
                            for root, dirs, files in os.walk(original_file_path):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(file_full_path, original_file_path)
                                    # 包含tdata目录名在路径中: 手机号/tdata/D877F783D5D3EF8C/...
                                    arc_name = f"{phone}/{tdata_dirname}/{rel_path}"
                                    
                                    if arc_name not in added_paths:
                                        added_paths.add(arc_name)
                                        zipf.write(file_full_path, arc_name)
                        else:
                            # Session格式：直接打包到ZIP根目录，使用手机号作为文件名
                            # 格式：手机号.session 和 手机号.json（不要手机号文件夹）
                            if os.path.exists(original_file_path):
                                arc_name = f"{phone}.session"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(original_file_path, arc_name)
                            
                            # Journal文件
                            journal_path = original_file_path + '-journal'
                            if os.path.exists(journal_path):
                                arc_name = f"{phone}.session-journal"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(journal_path, arc_name)
                            
                            # JSON文件
                            json_path = os.path.splitext(original_file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                arc_name = f"{phone}.json"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(json_path, arc_name)
                    except Exception as e:
                        logger.warning(f"⚠️ 打包文件失败 {file_name}: {e}")
            
            logger.info(f"✅ 成功账号已打包: {success_zip_path}")
        except Exception as e:
            logger.error(f"❌ 打包成功账号失败: {e}")
            success_zip_path = None
    
    # ========================================
    # 3. 打包失败的账号文件
    # ========================================
    failed_zip_path = None
    if results['failed']:
        logger.info(f"📦 开始打包失败的账号文件...")
        failed_zip_path = os.path.join(config.RESULTS_DIR, f"profile_failed_{failed_count}_{timestamp}.zip")
        
        try:
            with zipfile.ZipFile(failed_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                added_paths = set()  # 追踪已添加的文件路径，避免重复
                
                for file_path, file_name, detail in results['failed']:
                    original_file_path = detail.get('file_path', file_path)
                    # 提取手机号作为前缀
                    phone = extract_phone_from_path(original_file_path) or extract_phone_from_path(file_name) or file_name.replace('.session', '').replace('.json', '')
                    
                    try:
                        # 判断文件类型
                        if os.path.isdir(original_file_path):
                            # TData格式：打包整个目录，使用手机号作为前缀
                            # 获取目录名（通常是tdata）
                            tdata_dirname = os.path.basename(original_file_path)
                            
                            for root, dirs, files in os.walk(original_file_path):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(file_full_path, original_file_path)
                                    # 包含tdata目录名在路径中: 手机号/tdata/D877F783D5D3EF8C/...
                                    arc_name = f"{phone}/{tdata_dirname}/{rel_path}"
                                    
                                    if arc_name not in added_paths:
                                        added_paths.add(arc_name)
                                        zipf.write(file_full_path, arc_name)
                        else:
                            # Session格式：直接打包到ZIP根目录，使用手机号作为文件名
                            # 格式：手机号.session 和 手机号.json（不要手机号文件夹）
                            if os.path.exists(original_file_path):
                                arc_name = f"{phone}.session"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(original_file_path, arc_name)
                            
                            # Journal文件
                            journal_path = original_file_path + '-journal'
                            if os.path.exists(journal_path):
                                arc_name = f"{phone}.session-journal"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(journal_path, arc_name)
                            
                            # JSON文件
                            json_path = os.path.splitext(original_file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                arc_name = f"{phone}.json"
                                if arc_name not in added_paths:
                                    added_paths.add(arc_name)
                                    zipf.write(json_path, arc_name)
                    except Exception as e:
                        logger.warning(f"⚠️ 打包文件失败 {file_name}: {e}")
            
            logger.info(f"✅ 失败账号已打包: {failed_zip_path}")
        except Exception as e:
            logger.error(f"❌ 打包失败账号失败: {e}")
            failed_zip_path = None
    
    # ========================================
    # 4. 发送报告文件
    # ========================================
    try:
        if os.path.exists(report_path):
            with open(report_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_report_{timestamp}.txt",
                    caption=t(user_id, 'profile_output_report'),
                    parse_mode='HTML'
                )
            logger.info("✅ 报告文件已发送")
    except Exception as e:
        logger.error(f"❌ 发送报告文件失败: {e}")
    
    # ========================================
    # 5. 发送成功账号ZIP
    # ========================================
    if success_zip_path and os.path.exists(success_zip_path):
        try:
            with open(success_zip_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_success_{success_count}.zip",
                    caption=t(user_id, 'profile_output_success').format(count=success_count),
                    parse_mode='HTML',
                    timeout=120
                )
            logger.info("✅ 成功账号ZIP已发送")
        except Exception as e:
            logger.error(f"❌ 发送成功账号ZIP失败: {e}")
    
    # ========================================
    # 6. 发送失败账号ZIP
    # ========================================
    if failed_zip_path and os.path.exists(failed_zip_path):
        try:
            with open(failed_zip_path, 'rb') as f:
                context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"profile_failed_{failed_count}.zip",
                    caption=t(user_id, 'profile_output_failed').format(count=failed_count),
                    parse_mode='HTML',
                    timeout=120
                )
            logger.info("✅ 失败账号ZIP已发送")
        except Exception as e:
            logger.error(f"❌ 发送失败账号ZIP失败: {e}")
    
    # ========================================
    # 7. 更新最终消息
    # ========================================
    error_stats_text = ""
    if error_stats:
        error_stats_text = f"\n\n<b>{t(user_id, 'profile_error_stats')}</b>\n"
        for error_name, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True):
            error_stats_text += f"• {error_name}: {count}\n"
    
    files_sent_text = f"\n\n<b>{t(user_id, 'profile_files_sent')}</b>\n{t(user_id, 'profile_file_report')} profile_report.txt"
    if success_zip_path:
        files_sent_text += f"\n{t(user_id, 'profile_file_success')} profile_success_{success_count}.zip"
    if failed_zip_path:
        files_sent_text += f"\n{t(user_id, 'profile_file_failed')} profile_failed_{failed_count}.zip"
    
    final_text = f"""<b>{t(user_id, 'profile_complete')}</b>


    def handle_profile_update_start(self, query):
    """处理修改资料开始"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查会员权限
    if not self.db.is_admin(user_id):
        is_member, level, expiry = self.db.check_membership(user_id)
        if not is_member:
            query.edit_message_text(
                text=t(user_id, 'profile_need_member'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(user_id, 'btn_vip_menu'), callback_data="vip_menu"),
                    InlineKeyboardButton(t(user_id, 'btn_back_to_menu'), callback_data="back_to_main")
                ]]),
                parse_mode='HTML'
            )
            return
    
    text = f"""

    def handle_profile_update_callbacks(self, update: Update, context: CallbackContext, query, data: str):
    """处理修改资料相关回调"""
    user_id = query.from_user.id
    
    if data == "profile_mode_random":
        self.handle_profile_random_mode(query, user_id)
    elif data == "profile_mode_custom":
        self.handle_profile_custom_mode(query, user_id)
    elif data == "profile_custom_back":
        # 返回自定义配置菜单
        if user_id in self.pending_profile_update:
            config = self.pending_profile_update[user_id]['config']
            self._show_custom_config_menu(query, user_id, config)
        else:
            query.answer(t(user_id, 'profile_session_expired'))
    elif data.startswith("profile_random_"):
        self.handle_profile_random_config(update, context, query, data, user_id)
    elif data.startswith("profile_custom_"):
        self.handle_profile_custom_config(update, context, query, data, user_id)
    elif data == "profile_execute":
        self.handle_profile_update_execute(update, context, query, user_id)
    elif data == "profile_confirm_execute":
        self.handle_profile_confirm_execute(update, context, query, user_id)
    elif data == "profile_cancel":
        query.answer()
        if user_id in self.pending_profile_update:
            self.cleanup_profile_update_task(user_id)
        self.show_main_menu(update, user_id)


    def handle_profile_random_mode(self, query, user_id: int):
    """处理随机生成模式"""
    query.answer()
    
    # 初始化配置
    config = ProfileUpdateConfig(mode='random')
    config.update_name = True
    config.photo_action = 'keep'
    config.bio_action = 'keep'
    config.username_action = 'keep'
    
    self.pending_profile_update[user_id] = {
        'config': config,
        'status': 'configuring'
    }
    
    self._show_random_config_menu(query, user_id, config)


    def handle_profile_random_config(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理随机模式配置选项"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    if data == "profile_random_photo":
        # 切换头像选项
        if config.photo_action == 'keep':
            config.photo_action = 'delete_all'
            config.update_photo = True
        else:
            config.photo_action = 'keep'
            config.update_photo = False
    elif data == "profile_random_bio":
        # 循环切换简介选项：keep -> clear -> random -> keep
        if config.bio_action == 'keep':
            config.bio_action = 'clear'
            config.update_bio = True
        elif config.bio_action == 'clear':
            config.bio_action = 'random'
            config.update_bio = True
        else:
            config.bio_action = 'keep'
            config.update_bio = False
    elif data == "profile_random_username":
        # 循环切换用户名选项：keep -> delete -> random -> keep
        if config.username_action == 'keep':
            config.username_action = 'delete'
            config.update_username = True
        elif config.username_action == 'delete':
            config.username_action = 'random'
            config.update_username = True
        else:
            config.username_action = 'keep'
            config.update_username = False
    
    # 刷新菜单
    self._show_random_config_menu(query, user_id, config)


    def handle_profile_custom_mode(self, query, user_id: int):
    """处理自定义生成模式"""
    query.answer()
    
    # 初始化配置
    config = ProfileUpdateConfig(mode='custom')
    config.update_name = False
    config.update_photo = False
    config.update_bio = False
    config.update_username = False
    
    self.pending_profile_update[user_id] = {
        'config': config,
        'status': 'configuring',
        'custom_input_field': None  # 当前正在配置的字段
    }
    
    self._show_custom_config_menu(query, user_id, config)


    def handle_profile_custom_config(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理自定义模式配置选项"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_custom_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    
    if data == "profile_custom_name":
        # 配置姓名
        self._show_custom_field_config(query, user_id, 'name', t(user_id, 'profile_field_name'))
    elif data == "profile_custom_photo":
        # 配置头像
        self._show_custom_field_config(query, user_id, 'photo', t(user_id, 'profile_field_avatar'))
    elif data == "profile_custom_bio":
        # 配置简介
        self._show_custom_field_config(query, user_id, 'bio', t(user_id, 'profile_field_bio'))
    elif data == "profile_custom_username":
        # 配置用户名
        self._show_custom_field_config(query, user_id, 'username', t(user_id, 'profile_field_username'))
    elif data.startswith("profile_custom_field_"):
        # 处理字段配置选项
        self._handle_custom_field_action(update, context, query, data, user_id)


    def handle_profile_custom_text_input(self, update: Update, context: CallbackContext, user_id: int, field_name: str, text: str):
    """处理自定义资料的文本输入"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    # 解析输入的文本（按行分割）
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not lines:
        self.safe_send_message(update, t(user_id, 'profile_custom_input_empty'), 'HTML')
        return
    
    # Helper function to get translated field display name
    def get_field_display(field):
        field_map = {
            'name': 'profile_field_name',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        return t(user_id, field_map.get(field, 'profile_field_name'))
    
    field_display = get_field_display(field_name)
    
    if field_name == 'name':
        config.custom_names = lines
        config.update_name = True
    elif field_name == 'bio':
        config.custom_bios = lines
        config.update_bio = True
        config.bio_action = 'custom'
    elif field_name == 'username':
        config.custom_usernames = lines
        config.update_username = True
        config.username_action = 'custom'
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "profile_custom_config")
    
    # 发送确认消息和返回按钮
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
    ]])
    
    self.safe_send_message(
        update,
        t(user_id, 'profile_custom_configured').format(count=len(lines), field=field_display),
        'HTML',
        reply_markup=keyboard
    )


    def _create_avatar_upload_dir(self, user_id: int) -> str:
    """创建头像上传目录并返回路径"""
    upload_dir = os.path.join(config.UPLOADS_DIR, f"avatars_{user_id}_{int(time.time())}")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


    def handle_profile_photo_upload(self, update: Update, context: CallbackContext, user_id: int):
    """处理资料头像的单张图片上传"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    progress_msg = self.safe_send_message(update, t(user_id, 'profile_photo_processing'), 'HTML')
    if not progress_msg:
        return
    
    try:
        # 获取最大尺寸的图片
        photo = update.message.photo[-1]
        
        # 创建上传目录
        upload_dir = self._create_avatar_upload_dir(user_id)
        
        # 下载图片
        file = photo.get_file()
        file_path = os.path.join(upload_dir, f"avatar_{user_id}.jpg")
        file.download(file_path)
        
        # 保存到配置
        config.custom_photos = [file_path]
        config.update_photo = True
        config.photo_action = 'custom'
        
        # 清除用户状态
        self.db.save_user(user_id, "", "", "profile_custom_config")
        
        # 显示确认消息
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
        ]])
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_photo_uploaded_success'),
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"处理资料头像上传失败: {e}")
        import traceback
        traceback.print_exc()
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_photo_upload_failed').format(error=str(e)),
            parse_mode='HTML'
        )


    def handle_profile_custom_file_upload(self, update: Update, context: CallbackContext, user_id: int, field_name: str, document):
    """处理自定义资料的文件上传"""
    if user_id not in self.pending_profile_update:
        self.safe_send_message(update, t(user_id, 'profile_custom_session_expired_restart'), 'HTML')
        return
    
    config = self.pending_profile_update[user_id]['config']
    
    progress_msg = self.safe_send_message(update, t(user_id, 'processing_your_file'), 'HTML')
    if not progress_msg:
        return
    
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"profile_custom_{field_name}_")
        temp_file = os.path.join(temp_dir, document.file_name)
        
        # 下载文件
        document.get_file().download(temp_file)
        
        # Helper function to get translated field display name
        def get_field_display(field):
            field_map = {
                'name': 'profile_field_name',
                'photo': 'profile_field_avatar',
                'bio': 'profile_field_bio',
                'username': 'profile_field_username'
            }
            return t(user_id, field_map.get(field, 'profile_field_name'))
        
        field_display = get_field_display(field_name)
        
        if field_name == 'photo':
            # 处理图片文件
            items = []
            
            # 检查是否是图片文件
            if temp_file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                # 单个图片文件
                upload_dir = self._create_avatar_upload_dir(user_id)
                dest_path = os.path.join(upload_dir, document.file_name)
                shutil.copy(temp_file, dest_path)
                items.append(dest_path)
                
            elif temp_file.lower().endswith('.zip'):
                # ZIP文件，解压并提取图片
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # 查找所有图片文件
                upload_dir = self._create_avatar_upload_dir(user_id)
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                            file_path = os.path.join(root, file)
                            dest_path = os.path.join(upload_dir, file)
                            shutil.copy(file_path, dest_path)
                            items.append(dest_path)
            
            if not items:
                self.safe_edit_message_text(
                    progress_msg,
                    t(user_id, 'profile_custom_no_images'),
                    parse_mode='HTML'
                )
                return
            
            config.custom_photos = items
            config.update_photo = True
            config.photo_action = 'custom'
            
        else:
            # 处理文本文件（姓名、简介、用户名）
            # 验证是否为 .txt 文件
            if not temp_file.lower().endswith('.txt'):
                self.safe_edit_message_text(
                    progress_msg,
                    f"❌ <b>文件格式错误</b>\n\n请上传 .txt 文本文件，当前文件: {document.file_name}",
                    parse_mode='HTML'
                )
                return
            
            try:
                with open(temp_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    with open(temp_file, 'r', encoding='gbk') as f:
                        lines = [line.strip() for line in f if line.strip()]
                except:
                    self.safe_edit_message_text(
                        progress_msg,
                        t(user_id, 'profile_custom_encoding_error'),
                        parse_mode='HTML'
                    )
                    return
            
            if not lines:
                self.safe_edit_message_text(
                    progress_msg,
                    t(user_id, 'profile_custom_file_empty'),
                    parse_mode='HTML'
                )
                return
            
            # 根据字段类型保存
            if field_name == 'name':
                config.custom_names = lines
                config.update_name = True
            elif field_name == 'bio':
                config.custom_bios = lines
                config.update_bio = True
                config.bio_action = 'custom'
            elif field_name == 'username':
                config.custom_usernames = lines
                config.update_username = True
                config.username_action = 'custom'
            
            items = lines
        
        # 清除用户状态
        self.db.save_user(user_id, "", "", "profile_custom_config")
        
        # 显示确认消息
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")
        ]])
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_custom_configured').format(count=len(items), field=field_display),
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"处理自定义资料文件上传失败: {e}")
        import traceback
        traceback.print_exc()
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'profile_custom_processing_failed').format(error=str(e)),
            parse_mode='HTML'
        )
    finally:
        # 清理临时文件
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


    def handle_profile_confirm_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理确认执行资料修改"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        self.safe_edit_message(query, t(user_id, 'profile_custom_task_expired'))
        return
    
    task = self.pending_profile_update[user_id]
    
    # 检查是否有文件信息
    if 'files' not in task or 'file_type' not in task or 'progress_msg' not in task:
        self.safe_edit_message(query, "❌ 任务信息不完整，请重新上传文件")
        return
    
    files = task['files']
    file_type = task['file_type']
    config = task['config']
    progress_msg = task['progress_msg']
    
    # 开始执行（使用线程运行异步任务，避免事件循环错误）
    def execute_profile_update():
        try:
            asyncio.run(self._execute_profile_update(user_id, files, file_type, config, context, progress_msg))
        except asyncio.CancelledError:
            logger.info(f"[profile_update] 任务被取消")
        except Exception as e:
            logger.error(f"[profile_update] 处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    thread = threading.Thread(target=execute_profile_update, daemon=True)
    thread.start()


    def handle_profile_update_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """开始执行资料修改"""
    query.answer()
    
    if user_id not in self.pending_profile_update:
        self.safe_edit_message(query, t(user_id, 'profile_session_expired'))
        return
    
    task = self.pending_profile_update[user_id]
    config = task['config']
    
    text = f"""

