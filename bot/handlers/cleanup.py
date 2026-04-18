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

class CleanupAction:
    """清理操作记录"""
    chat_id: int
    title: str
    chat_type: str  # 'user', 'group', 'channel', 'bot'
    actions_done: List[str] = field(default_factory=list)
    status: str = 'pending'  # 'pending', 'success', 'partial', 'failed', 'skipped'
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(BEIJING_TZ).isoformat())

@dataclass



# ===== Handler Methods from EnhancedBot =====

    def clean_proxy_command(self, update: Update, context: CallbackContext):
    """清理代理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not self.proxy_manager.proxies:
        self.safe_send_message(update, "❌ 没有可用的代理进行清理")
        return
    
    # 检查是否有确认参数
    auto_confirm = len(context.args) > 0 and context.args[0].lower() in ['yes', 'y', 'confirm']
    
    if not auto_confirm:
        # 显示确认界面
        confirm_text = f"""

    def _execute_proxy_cleanup(self, update, context, confirmed: bool):
    """执行代理清理"""
    if not confirmed:
        self.safe_send_message(update, "❌ 代理清理已取消")
        return
    
    # 异步处理代理清理
    def process_cleanup():
        asyncio.run(self.process_proxy_cleanup(update, context))
    
    thread = threading.Thread(target=process_cleanup)
    thread.start()
    
    self.safe_send_message(
        update, 
        f"🧹 开始清理 {len(self.proxy_manager.proxies)} 个代理...\n"
        f"⚡ 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}\n"
        f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT}\n\n"
        "请稍等，清理过程可能需要几分钟..."
    )

async def process_proxy_cleanup(self, update, context):
    """处理代理清理过程"""
    try:
        # 发送进度消息
        progress_msg = self.safe_send_message(
            update,
            "🧹 <b>代理清理中...</b>\n\n📊 正在备份原始文件...",
            'HTML'
        )
        
        # 执行清理
        success, result_msg = await self.proxy_tester.cleanup_and_update_proxies(auto_confirm=True)
        
        if success:
            # 显示成功结果
            if progress_msg:
                try:
                    progress_msg.edit_text(
                        f"🎉 <b>代理清理成功！</b>\n\n{result_msg}",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            # 发送额外的总结信息
            summary_text = f"""

    def show_cleanup_confirmation(self, query):
    """显示清理确认对话框"""
    query.answer()
    confirm_text = f"""

    def _classify_cleanup(self, user_id):
    """清理分类任务"""
    if user_id in self.pending_classify_tasks:
        task = self.pending_classify_tasks[user_id]
        # 清理临时文件
        if 'temp_zip' in task and task['temp_zip'] and os.path.exists(task['temp_zip']):
            try:
                shutil.rmtree(os.path.dirname(task['temp_zip']), ignore_errors=True)
            except:
                pass
        if 'extract_dir' in task and task['extract_dir'] and os.path.exists(task['extract_dir']):
            try:
                shutil.rmtree(task['extract_dir'], ignore_errors=True)
            except:
                pass
        del self.pending_classify_tasks[user_id]
    
    # 清空数据库状态
    self.db.save_user(user_id, "", "", "")

async def _classify_send_bundles(self, update, context, bundles, user_id, prefix=""):
    """统一发送ZIP包并节流"""
    sent_count = 0
    for zip_path, display_name, count in bundles:
        if os.path.exists(zip_path):
            try:
                with open(zip_path, 'rb') as f:
                    caption = f"📦 <b>{prefix}{display_name}</b>\n{t(user_id, 'split_file_contains').format(count=count)}"
                    context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=display_name,
                        caption=caption,
                        parse_mode='HTML'
                    )
                sent_count += 1
                print(f"📤 已发送: {display_name}")
                await asyncio.sleep(1.0)  # 节流
                
                # 发送后删除
                try:
                    os.remove(zip_path)
                except:
                    pass
            except Exception as e:
                print(f"❌ 发送文件失败: {display_name} - {e}")
    
    return sent_count

async def _classify_split_single_qty(self, update, context, user_id, qty):
    """按单个数量拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    total = len(metas)
    if qty > total:
        self.safe_send_message(update, t(user_id, 'split_error_qty_exceeds').format(qty=qty, total=total))
        return
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_quantity_single')}</b>\n\n{t(user_id, 'split_processing_quantity_single_desc').format(qty=qty)}\n{t(user_id, 'split_processing_quantity_multi_total').format(total=total)}",
                parse_mode='HTML'
            )
        except:
            pass
        
        # 计算需要多少个包
        num_bundles = (total + qty - 1) // qty
        sizes = [qty] * (num_bundles - 1) + [total - (num_bundles - 1) * qty]
        
        bundles = self.classifier.split_by_quantities(metas, sizes, out_dir, t_func=lambda key: t(user_id, key))
        
        # 发送结果
        try:
            progress_msg.edit_text(f"<b>{t(user_id, 'split_sending_results')}</b>", parse_mode='HTML')
        except:
            pass
        
        sent = await self._classify_send_bundles(update, context, bundles, user_id)
        
        # 完成提示
        self.safe_send_message(
            update,
            f"<b>{t(user_id, 'split_complete')}</b>\n\n"
            f"{t(user_id, 'split_result_total').format(count=total)}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"• {t(user_id, 'split_method_quantity')}: {qty} {t(user_id, 'accounts_unit')}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 单数量拆分失败: {e}")
        import traceback
        traceback.print_exc()
        self.safe_send_message(update, f"❌ 拆分失败: {str(e)}")
    finally:
        # 清理输出目录
        try:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
        except:
            pass
        # 清理上传的临时文件和解压目录
        self._classify_cleanup(user_id)

async def _classify_split_multi_qty(self, update, context, user_id, quantities):
    """按多个数量拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        total = len(metas)
        total_requested = sum(quantities)
        
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_quantity_multi')}</b>\n\n"
                f"{t(user_id, 'split_processing_quantity_multi_sequence').format(sequence=' '.join(map(str, quantities)))}\n"
                f"{t(user_id, 'split_processing_quantity_multi_total').format(total=total)}\n"
                f"{t(user_id, 'split_processing_quantity_multi_requested').format(requested=total_requested)}",
                parse_mode='HTML'
            )
        except:
            pass
        
        bundles = self.classifier.split_by_quantities(metas, quantities, out_dir, t_func=lambda key: t(user_id, key))
        
        # 余数提示
        remainder = total - total_requested
        remainder_msg = ""
        if remainder > 0:
            remainder_msg = f"\n\n{t(user_id, 'split_remainder_unallocated').format(remainder=remainder)}"
        elif remainder < 0:
            remainder_msg = f"\n\n{t(user_id, 'split_remainder_exceeded')}"
        
        # 发送结果
        try:
            progress_msg.edit_text(f"<b>{t(user_id, 'split_sending_results')}</b>", parse_mode='HTML')
        except:
            pass
        
        sent = await self._classify_send_bundles(update, context, bundles, user_id)
        
        # 完成提示
        self.safe_send_message(
            update,
            f"<b>{t(user_id, 'split_complete')}</b>\n\n"
            f"{t(user_id, 'split_result_total').format(count=total)}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"{t(user_id, 'split_result_sequence').format(sequence=' '.join(map(str, quantities)))}{remainder_msg}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 多数量拆分失败: {e}")
        import traceback
        traceback.print_exc()
        self.safe_send_message(update, f"❌ 拆分失败: {str(e)}")
    finally:
        # 清理输出目录
        try:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
        except:
            pass
        # 清理上传的临时文件和解压目录
        self._classify_cleanup(user_id)


    def cleanup_rename_task(self, user_id: int):
    """清理重命名任务"""
    if user_id in self.pending_rename:
        task = self.pending_rename[user_id]
        if task['temp_dir'] and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_rename[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 账户合并功能
# ================================


    def cleanup_merge_task(self, user_id: int):
    """清理合并任务"""
    if user_id in self.pending_merge:
        task = self.pending_merge[user_id]
        if task['temp_dir'] and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_merge[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 一键清理功能
# ================================


    def handle_cleanup_start(self, query):
    """开始一键清理流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 检查是否启用
    if not config.ENABLE_ONE_CLICK_CLEANUP:
        self.safe_edit_message(query, t(user_id, 'cleanup_feature_disabled'))
        return
    
    # 检查会员权限
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, t(user_id, 'cleanup_need_member'))
        return
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_cleanup_file"
    )
    
    text = f"""

    def handle_cleanup_confirm(self, update, context, query):
    """确认清理"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_cleanup:
        self.safe_edit_message(query, t(user_id, 'cleanup_no_pending_task'))
        return
    
    task = self.pending_cleanup[user_id]
    
    # 检查超时（10分钟）
    if time.time() - task['started_at'] > 600:
        self.cleanup_cleanup_task(user_id)
        self.safe_edit_message(query, t(user_id, 'cleanup_operation_timeout'))
        return
    
    # 启动异步清理
    def execute_cleanup():
        asyncio.run(self.execute_cleanup(update, context, user_id))
    
    thread = threading.Thread(target=execute_cleanup, daemon=True)
    thread.start()
    
    self.safe_edit_message(query, f"🧹 <b>{t(user_id, 'cleanup_starting')}...</b>\n\n{t(user_id, 'cleanup_initializing')}", 'HTML')

async def _process_single_account_full(self, file_info: tuple, file_type: str, progress_msg, all_files_count: int, completed_count: dict, lock: asyncio.Lock, start_time: float, user_id: int) -> dict:
    """处理单个账户的完整流程（包含连接和清理）"""
    file_path, file_name = file_info
    result_data = {
        'file_path': file_path,
        'file_name': file_name,
        'original_path': file_path,  # 保存原始文件路径用于打包
        'file_type': file_type,  # 保存文件类型
        'success': False,
        'error': None,
        'is_frozen': False,
        'statistics': {},
        'error_details': []
    }
    
    client = None
    try:
        # 如果是TData，需要先转换为Session
        if file_type == 'tdata':
            # 提取手机号用于日志
            phone_for_log = extract_phone_from_tdata_path(file_path) or file_name
            
            # 使用安全转换函数，带超时和错误处理
            session_path, error_msg = await safe_convert_tdata(file_path, phone_for_log)
            
            if session_path is None:
                # 转换失败，跳过该账号
                logger.warning(f"⚠️ 跳过账号 {phone_for_log}，转换失败: {error_msg}")
                result_data['error'] = error_msg
                result_data['error_details'].append(error_msg)
                return result_data
            
            # 使用转换后的session创建不接收更新的客户端以提升清理速度
            try:
                from telethon import TelegramClient as TelethonClient
                client = TelethonClient(
                    os.path.splitext(session_path)[0],
                    int(config.API_ID),
                    str(config.API_HASH),
                    receive_updates=False
                )
                await client.connect()
                
                # 检查授权
                if not await client.is_user_authorized():
                    logger.warning(f"Session not authorized after conversion: {file_name}")
                    result_data['error'] = "转换后Session未授权"
                    await client.disconnect()
                    return result_data
                    
            except Exception as e:
                logger.error(f"Failed to connect after TData conversion for {file_name}: {e}")
                # 检查是否为冻结账户错误
                if self._is_frozen_error(e):
                    result_data['error'] = 'FROZEN_ACCOUNT'
                    result_data['error_message'] = f"账户已冻结: {str(e)}"
                    result_data['is_frozen'] = True
                    logger.info(f"❄️ 转换后连接时检测到冻结账户: {file_name}")
                else:
                    result_data['error'] = f"转换后连接失败: {str(e)}"
                return result_data
        else:
            # 直接使用Session
            session_path = os.path.splitext(file_path)[0]
            
            # 获取代理配置
            proxy_dict = None
            proxy_enabled = self.db.get_proxy_enabled() if self.db else True
            use_proxy = config.USE_PROXY and proxy_enabled and self.proxy_manager.proxies
            
            if use_proxy:
                proxy_info = self.proxy_manager.get_next_proxy()
                if proxy_info:
                    proxy_dict = self.checker.create_proxy_dict(proxy_info)
                    logger.info(f"使用代理连接账号: {file_name}")
            
            try:
                client = TelegramClient(
                    session_path,
                    int(config.API_ID),
                    str(config.API_HASH),
                    proxy=proxy_dict,
                    receive_updates=False  # 禁用更新接收，提升清理速度
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    logger.warning(f"Session not authorized: {file_name}")
                    result_data['error'] = "Session未授权"
                    await client.disconnect()
                    return result_data
            except Exception as e:
                logger.error(f"Session connection failed for {file_name}: {e}")
                # 检查是否为冻结账户错误
                if self._is_frozen_error(e):
                    result_data['error'] = 'FROZEN_ACCOUNT'
                    result_data['error_message'] = f"账户已冻结: {str(e)}"
                    result_data['is_frozen'] = True
                    logger.info(f"❄️ 连接时检测到冻结账户: {file_name}")
                else:
                    result_data['error'] = f"连接失败: {str(e)}"
                return result_data
        
        # 进度更新节流（避免触发 Telegram 限制）- 改为基于时间而非账号数量
        last_update_time = {'value': 0}  # 上次更新的时间戳
        PROGRESS_UPDATE_INTERVAL = 10  # 每10秒更新一次进度
        
        # 创建进度回调函数
        async def update_progress(status_text):
            current_idx = completed_count['value'] + 1
            
            if not progress_msg:
                return
            
            current_time = time.time()
            time_since_last_update = current_time - last_update_time['value']
            
            # 节流逻辑：只在以下情况更新
            # 1. 距离上次更新已超过10秒
            # 2. 是第一个账户
            # 3. 是最后一个账户
            should_update = (
                time_since_last_update >= PROGRESS_UPDATE_INTERVAL or
                current_idx == 1 or
                current_idx == all_files_count
            )
            
            if not should_update:
                return
            
            async with lock:
                try:
                    progress_percent = int((current_idx / all_files_count) * 100)
                    
                    # 更新时间戳
                    last_update_time['value'] = current_time
                    
                    filled = int(progress_percent / 10)
                    empty = 10 - filled
                    progress_bar = "█" * filled + "░" * empty
                    
                    status_display = status_text[:30] + '...' if len(status_text) > 30 else status_text
                    
                    # 计算预计完成时间
                    elapsed_time = time.time() - start_time
                    if current_idx > 0:
                        avg_time_per_account = elapsed_time / current_idx
                        remaining_accounts = all_files_count - current_idx
                        estimated_remaining_seconds = avg_time_per_account * remaining_accounts
                        
                        hours = int(estimated_remaining_seconds // 3600)
                        minutes = int((estimated_remaining_seconds % 3600) // 60)
                        seconds = int(estimated_remaining_seconds % 60)
                        
                        if hours > 0:
                            time_remaining = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        else:
                            time_remaining = f"{minutes:02d}:{seconds:02d}"
                    else:
                        time_remaining = t(user_id, 'cleanup_initializing')
                    
                    message_text = (
                        f"<b>{t(user_id, 'cleanup_in_progress')}</b>\n\n"
                        f"{t(user_id, 'cleanup_current').format(filename=file_name)}\n"
                        f"{t(user_id, 'cleanup_total_progress').format(current=current_idx, total=all_files_count, percent=progress_percent)}\n"
                        f"⚙️ [{progress_bar}]\n"
                        f"{t(user_id, 'cleanup_eta').format(time=time_remaining)}"
                    )
                    
                    # 移除按钮，直接显示进度信息，减少刷新频率避免限流
                    progress_msg.edit_text(
                        message_text,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    # 如果是限流错误，静默处理
                    if "too many requests" in str(e).lower() or "retry after" in str(e).lower():
                        logger.warning(f"进度更新触发限流: {e}")
                    pass
        
        # 执行清理 - 添加整体超时保护
        try:
            cleanup_result = await asyncio.wait_for(
                self._cleanup_single_account(
                    client=client,
                    account_name=file_name,
                    file_path=file_path,
                    progress_callback=update_progress,
                    user_id=user_id
                ),
                timeout=CLEANUP_SINGLE_ACCOUNT_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"账号 {file_name} 清理超时 ({CLEANUP_SINGLE_ACCOUNT_TIMEOUT}秒)")
            cleanup_result = {
                'success': False,
                'error': f'清理超时 ({CLEANUP_SINGLE_ACCOUNT_TIMEOUT}秒)',
                'statistics': {},
                'error_details': [f'整个清理过程超时']
            }
        
        # 断开客户端
        try:
            await client.disconnect()
        except:
            pass
        
        # 更新完成计数
        async with lock:
            completed_count['value'] += 1
        
        # 合并结果
        result_data.update(cleanup_result)
        return result_data
        
    except Exception as e:
        logger.error(f"处理账户失败 {file_name}: {e}")
        import traceback
        traceback.print_exc()
        result_data['error'] = str(e)
        
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        return result_data

async def execute_cleanup(self, update, context, user_id: int):
    """执行一键清理（并发版本）"""
    if user_id not in self.pending_cleanup:
        return
    
    task = self.pending_cleanup[user_id]
    files = task['files']
    file_type = task['file_type']
    extract_dir = task['extract_dir']
    progress_msg = task.get('progress_msg')
    
    results_summary = {
        'total': len(files),
        'success': 0,
        'failed': 0,
        'frozen': 0,
        'reports': [],
        'success_files': [],
        'failed_files': [],
        'frozen_files': [],
        'detailed_results': []
    }
    
    # 初始化变量，确保在 finally 块中可用
    summary_report_path = None
    result_zips = []
    
    try:
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(config.CLEANUP_ACCOUNT_CONCURRENCY)
        lock = asyncio.Lock()
        completed_count = {'value': 0}
        start_time = time.time()
        
        async def process_with_semaphore(file_info):
            async with semaphore:
                return await self._process_single_account_full(
                    file_info, file_type, progress_msg, len(files), completed_count, lock, start_time, user_id
                )
        
        # 并发处理所有账户
        logger.info(f"开始并发清理 {len(files)} 个账户，并发数: {config.CLEANUP_ACCOUNT_CONCURRENCY}")
        tasks = [process_with_semaphore(file_info) for file_info in files]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 汇总结果
        for idx, result in enumerate(all_results, 1):
            if isinstance(result, BaseException):
                logger.error(f"处理异常: {result}")
                results_summary['failed'] += 1
                # 从原始files列表获取文件信息，包含file_type
                results_summary['failed_files'].append((files[idx-1][0], files[idx-1][1], files[idx-1][0], file_type))
                results_summary['detailed_results'].append({
                    'file_name': files[idx-1][1],
                    'status': 'failed',
                    'error': str(result)
                })
                continue
            
            # 保存详细结果
            results_summary['detailed_results'].append({
                'file_name': result['file_name'],
                'status': 'frozen' if result.get('is_frozen') else ('success' if result.get('success') else 'failed'),
                'error': result.get('error'),
                'error_details': result.get('error_details', []),
                'statistics': result.get('statistics', {})
            })
            
            # 分类统计
            # 冻结账户直接归类为失败账户（符合issue要求）
            # 注意：冻结账户会同时计入frozen和failed，这是有意为之：
            # - frozen_files用于统计和报告冻结账户数量
            # - failed_files用于将冻结账户打包到失败账户zip中
            if result.get('is_frozen'):
                results_summary['frozen'] += 1
                results_summary['frozen_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                # 冻结账户同时加入失败列表，以便打包到失败zip中
                results_summary['failed'] += 1
                results_summary['failed_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"❄️ 冻结账户（归类为失败）: {result['file_name']}")
            elif result.get('success'):
                results_summary['success'] += 1
                results_summary['success_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"✅ 清理成功: {result['file_name']}")
            else:
                results_summary['failed'] += 1
                results_summary['failed_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"❌ 清理失败: {result['file_name']}")
        
        # 生成详细的TXT报告
        timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
        summary_report_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleanup_summary_{timestamp}.txt")
        
        with open(summary_report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"              {t(user_id, 'cleanup_report_title')}\n")
            f.write("=" * 80 + "\n\n")
            
            success_rate = (results_summary['success'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            frozen_rate = (results_summary['frozen'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            
            f.write(f"{t(user_id, 'cleanup_report_time')}: {timestamp}\n")
            f.write(f"{t(user_id, 'cleanup_report_concurrency')}: {config.CLEANUP_ACCOUNT_CONCURRENCY} {t(user_id, 'cleanup_report_concurrent_accounts')}\n")
            f.write(f"{t(user_id, 'cleanup_report_total')}: {results_summary['total']}\n")
            f.write(f"✅ {t(user_id, 'cleanup_report_success')}: {results_summary['success']} ({success_rate:.1f}%)\n")
            f.write(f"❄️ {t(user_id, 'cleanup_report_frozen')}: {results_summary['frozen']} ({frozen_rate:.1f}%)\n")
            f.write(f"❌ {t(user_id, 'cleanup_report_failed')}: {results_summary['failed']}\n\n")
            
            # 详细结果
            f.write("=" * 80 + "\n")
            f.write(f"                    {t(user_id, 'cleanup_report_details')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, detail in enumerate(results_summary['detailed_results'], 1):
                status_icon = "✅" if detail['status'] == 'success' else ("❄️" if detail['status'] == 'frozen' else "❌")
                status_text = t(user_id, 'cleanup_report_status_success') if detail['status'] == 'success' else (t(user_id, 'cleanup_report_status_frozen') if detail['status'] == 'frozen' else t(user_id, 'cleanup_report_status_failed'))
                
                f.write(f"{idx}. {status_icon} {detail['file_name']} - {status_text}\n")
                
                if detail.get('error'):
                    f.write(f"   {t(user_id, 'cleanup_report_error')} {detail['error']}\n")
                
                if detail.get('error_details'):
                    f.write(f"   {t(user_id, 'cleanup_report_error_details')}\n")
                    for err in detail['error_details']:
                        f.write(f"   - {err}\n")
                
                stats = detail.get('statistics', {})
                if stats:
                    f.write(f"   {t(user_id, 'cleanup_report_stats')} ")
                    stat_parts = []
                    if stats.get('profile_cleared'): stat_parts.append(t(user_id, 'cleanup_report_profile_cleared'))
                    if stats.get('groups_left'): stat_parts.append(t(user_id, 'cleanup_report_groups_left').format(count=stats['groups_left']))
                    if stats.get('channels_left'): stat_parts.append(t(user_id, 'cleanup_report_channels_left').format(count=stats['channels_left']))
                    if stats.get('histories_deleted'): stat_parts.append(t(user_id, 'cleanup_report_histories_deleted').format(count=stats['histories_deleted']))
                    if stats.get('contacts_deleted'): stat_parts.append(t(user_id, 'cleanup_report_contacts_deleted_label').format(count=stats['contacts_deleted']))
                    if stat_parts:
                        f.write(", ".join(stat_parts))
                    f.write("\n")
                
                f.write("\n")
            
            # 分类汇总
            if results_summary['success_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_success_list')} ({len(results_summary['success_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['success_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ✅ {fname}\n")
                f.write("\n")
            
            if results_summary['frozen_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_frozen_accounts')} ({len(results_summary['frozen_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['frozen_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ❄️ {fname}\n")
                f.write("\n")
            
            if results_summary['failed_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_failed_list')} ({len(results_summary['failed_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['failed_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ❌ {fname}\n")
                f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'cleanup_report_concurrent_mode').format(count=config.CLEANUP_ACCOUNT_CONCURRENCY)}\n")
            f.write("=" * 80 + "\n")
        
        # 打包成功和失败的账户文件
        result_zips = []
        
        # 打包成功清理的账户
        if results_summary['success_files']:
            success_zip_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleaned_success_{timestamp}.zip")
            with zipfile.ZipFile(success_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in results_summary['success_files']:
                    file_path = file_info[0]
                    file_name = file_info[1]
                    original_path = file_info[2] if len(file_info) > 2 else file_path
                    item_file_type = file_info[3] if len(file_info) > 3 else 'session'
                    
                    if item_file_type == 'tdata':
                        # TData格式：每个账号独立打包到 手机号/tdata/... 结构
                        # 提取手机号作为账号标识
                        phone = extract_phone_from_tdata_path(original_path) or file_name
                        # 去除特殊字符，确保是有效的目录名
                        phone = str(phone).replace('.zip', '').replace('/', '_').replace('\\', '_')
                        
                        if os.path.isdir(original_path):
                            # 遍历TData目录下的所有文件
                            for root, dirs, files_in_dir in os.walk(original_path):
                                for file in files_in_dir:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对路径，保留TData目录结构
                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                    # 添加手机号前缀，格式：手机号/tdata/...
                                    arc_path = os.path.join(phone, rel_path)
                                    zipf.write(file_full_path, arc_path)
                    else:
                        # Session格式：添加session文件及相关文件
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 如果有对应的session-journal文件也添加
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 如果有对应的json文件也添加
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            
            result_zips.append(('success', success_zip_path, len(results_summary['success_files'])))
        
        # 打包失败的账户
        if results_summary['failed_files']:
            failed_zip_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleaned_failed_{timestamp}.zip")
            with zipfile.ZipFile(failed_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in results_summary['failed_files']:
                    file_path = file_info[0]
                    file_name = file_info[1]
                    original_path = file_info[2] if len(file_info) > 2 else file_path
                    item_file_type = file_info[3] if len(file_info) > 3 else 'session'
                    
                    if item_file_type == 'tdata':
                        # TData格式：每个账号独立打包到 手机号/tdata/... 结构
                        # 提取手机号作为账号标识
                        phone = extract_phone_from_tdata_path(original_path) or file_name
                        # 去除特殊字符，确保是有效的目录名
                        phone = str(phone).replace('.zip', '').replace('/', '_').replace('\\', '_')
                        
                        if os.path.isdir(original_path):
                            # 遍历TData目录下的所有文件
                            for root, dirs, files_in_dir in os.walk(original_path):
                                for file in files_in_dir:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对路径，保留TData目录结构
                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                    # 添加手机号前缀，格式：手机号/tdata/...
                                    arc_path = os.path.join(phone, rel_path)
                                    zipf.write(file_full_path, arc_path)
                    else:
                        # Session格式：添加session文件及相关文件
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 如果有对应的session-journal文件也添加
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 如果有对应的json文件也添加
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            
            result_zips.append(('failed', failed_zip_path, len(results_summary['failed_files'])))
        
    except Exception as e:
        logger.error(f"Cleanup execution failed: {e}")
        import traceback
        traceback.print_exc()
        
        # 标记清理过程失败
        results_summary['cleanup_error'] = str(e)
    
    finally:
        # 无论如何都要发送清理结果
        try:
            # 检查实际处理的账号数
            actual_processed = results_summary['success'] + results_summary['failed']
            is_complete = (actual_processed == results_summary['total'])
            
            # 发送完成消息
            success_rate = (results_summary['success'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            frozen_rate = (results_summary['frozen'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            
            if results_summary.get('cleanup_error'):
                # 清理过程出错，发送错误消息但仍尝试发送已有的结果
                final_text = f"""

    def cleanup_cleanup_task(self, user_id: int):
    """清理一键清理任务"""
    if user_id in self.pending_cleanup:
        task = self.pending_cleanup[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_cleanup[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")


    def _cleanup_user_temp_sessions(self, user_id: int):
    """清理指定用户的临时session文件和旧上传目录
    
    这确保每次上传只使用当前上传的账号，不会重复登录之前的账号
    """
    try:
        # 1. 清理临时session文件
        if os.path.exists(config.SESSIONS_BAK_DIR):
            user_prefix = f"user_{user_id}_"
            cleaned_count = 0
            
            for filename in os.listdir(config.SESSIONS_BAK_DIR):
                if filename.startswith(user_prefix):
                    file_path = os.path.join(config.SESSIONS_BAK_DIR, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            cleaned_count += 1
                            logger.info(f"🧹 清理旧临时文件: {filename}")
                    except Exception as e:
                        logger.warning(f"⚠️ 清理文件失败 {filename}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"✅ 清理了 {cleaned_count} 个用户 {user_id} 的旧临时session文件")
                print(f"✅ 清理了 {cleaned_count} 个用户 {user_id} 的旧临时session文件")
        
        # 2. 【新增】清理用户的旧上传目录（防止累积）
        if os.path.exists(config.UPLOADS_DIR):
            # 匹配两种格式: task_{user_id}_batch (旧格式) 和 task_{user_id}_batch_{timestamp} (新格式)
            old_prefix = f"task_{user_id}_batch"
            cleaned_dirs = 0
            
            for dirname in os.listdir(config.UPLOADS_DIR):
                if dirname.startswith(old_prefix):
                    dir_path = os.path.join(config.UPLOADS_DIR, dirname)
                    try:
                        if os.path.isdir(dir_path):
                            shutil.rmtree(dir_path)
                            cleaned_dirs += 1
                            logger.info(f"🧹 清理旧上传目录: {dirname}")
                    except Exception as e:
                        logger.warning(f"⚠️ 清理目录失败 {dirname}: {e}")
            
            if cleaned_dirs > 0:
                logger.info(f"✅ 清理了 {cleaned_dirs} 个用户 {user_id} 的旧上传目录")
                print(f"✅ 清理了 {cleaned_dirs} 个用户 {user_id} 的旧上传目录")
    except Exception as e:
        logger.error(f"❌ 清理临时文件失败: {e}")

# ================================
# 批量创建群组/频道功能
# ================================

async def process_batch_create_upload(self, update: Update, context: CallbackContext, document):
    """处理批量创建文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, t(user_id, 'processing_file'), 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 【关键修复】在处理新上传前，清理该用户的旧临时session文件
        # 这确保每次上传只使用当前上传的账号，不会重复登录之前的账号
        self._cleanup_user_temp_sessions(user_id)
        
        # 【关键修复】为每次上传创建唯一的任务ID，确保完全隔离
        # 使用时间戳确保每次上传都有独立的目录，不会混淆
        unique_task_id = f"{user_id}_batch_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="batch_create_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件 - 使用唯一任务ID，确保只提取当前上传的账号
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, "❌ <b>未找到有效文件</b>\n\n请确保ZIP包含Session或TData格式的文件", parse_mode='HTML')
            return
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'batch_create_found_files').format(count=len(files)) + f"\n\n{t(user_id, 'batch_create_verifying')}",
            parse_mode='HTML'
        )
        
        # 验证账号
        accounts = []
        valid_count = 0
        total_remaining = 0
        
        # 获取设备参数和代理
        device_config = self.device_loader.get_random_device_config()
        api_id = device_config.get('api_id', config.API_ID)
        api_hash = device_config.get('api_hash', config.API_HASH)
        
        for i, (file_path, file_name) in enumerate(files):
            # 更新进度
            if (i + 1) % 5 == 0:
                self.safe_edit_message_text(
                    progress_msg,
                    f"{t(user_id, 'batch_create_verifying')}\n\n{t(user_id, 'batch_create_verifying_progress').format(done=i + 1, total=len(files))}",
                    parse_mode='HTML'
                )
            
            # 创建账号信息
            account = BatchAccountInfo(
                session_path=file_path,
                file_name=file_name,
                file_type=file_type
            )
            
            # 获取代理
            proxy_dict = None
            if self.proxy_manager.is_proxy_mode_active(self.db):
                proxy_info = self.proxy_manager.get_next_proxy()
                if proxy_info:
                    proxy_dict = (
                        socks.SOCKS5 if proxy_info['type'] == 'socks5' else socks.HTTP,
                        proxy_info['host'],
                        proxy_info['port'],
                        True,
                        proxy_info.get('username'),
                        proxy_info.get('password')
                    )
            
            # 验证账号（传入user_id以确保临时文件隔离）
            is_valid, error = await self.batch_creator.validate_account(
                account, api_id, api_hash, proxy_dict, user_id
            )
            
            accounts.append(account)
            
            if is_valid:
                valid_count += 1
                total_remaining += account.daily_remaining
        
        # 保存任务信息
        self.pending_batch_create[user_id] = {
            'accounts': accounts,
            'total_accounts': len(accounts),
            'valid_accounts': valid_count,
            'total_remaining': total_remaining,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir
        }
        
        # 显示验证结果
        text = f"""

    def cleanup_reauthorize_task(self, user_id: int):
    """清理重新授权任务"""
    if user_id in self.pending_reauthorize:
        task = self.pending_reauthorize[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_reauthorize[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

async def process_reauthorize_upload(self, update: Update, context: CallbackContext, document):
    """处理重新授权文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'reauth_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 清理旧的临时文件
        self._cleanup_user_temp_sessions(user_id)
        
        # 创建唯一任务ID
        unique_task_id = f"{user_id}_reauth_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="reauthorize_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, f"❌ <b>{t(user_id, 'reauth_no_valid_files')}</b>\n\n{t(user_id, 'reauth_ensure_format')}", parse_mode='HTML')
            return
        
        # 保存任务信息
        self.pending_reauthorize[user_id] = {
            'files': files,
            'file_type': file_type,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir,
            'total_files': len(files)
        }
        
        # 显示选择密码输入方式的按钮
        text = f"""{t(user_id, 'reauth_found_accounts').format(count=len(files))}


    def cleanup_registration_check_task(self, user_id: int):
    """清理查询注册时间任务"""
    if user_id in self.pending_registration_check:
        task = self.pending_registration_check[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_registration_check[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

async def process_registration_check_upload(self, update: Update, context: CallbackContext, document):
    """处理查询注册时间文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'regtime_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 清理旧的临时文件
        self._cleanup_user_temp_sessions(user_id)
        
        # 创建唯一任务ID
        unique_task_id = f"{user_id}_regcheck_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="registration_check_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, t(user_id, 'regtime_no_valid_files'), parse_mode='HTML')
            return
        
        # 保存任务信息
        self.pending_registration_check[user_id] = {
            'files': files,
            'file_type': file_type,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir,
            'total_files': len(files),
            'progress_msg': progress_msg
        }
        
        # 显示确认按钮
        file_type_str = t(user_id, 'regtime_file_type_session') if file_type == 'session' else t(user_id, 'regtime_file_type_tdata')
        text = f"""{t(user_id, 'regtime_found_accounts').format(count=len(files))}


    def cleanup_profile_update_task(self, user_id: int):
    """清理资料修改任务"""
    if user_id in self.pending_profile_update:
        task = self.pending_profile_update[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_profile_update[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 通讯录限制检测功能
# ================================




# ===== Handler Methods =====

    def clean_proxy_command(self, update: Update, context: CallbackContext):
    """清理代理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not self.proxy_manager.proxies:
        self.safe_send_message(update, "❌ 没有可用的代理进行清理")
        return
    
    # 检查是否有确认参数
    auto_confirm = len(context.args) > 0 and context.args[0].lower() in ['yes', 'y', 'confirm']
    
    if not auto_confirm:
        # 显示确认界面
        confirm_text = f"""

    def _execute_proxy_cleanup(self, update, context, confirmed: bool):
    """执行代理清理"""
    if not confirmed:
        self.safe_send_message(update, "❌ 代理清理已取消")
        return
    
    # 异步处理代理清理
    def process_cleanup():
        asyncio.run(self.process_proxy_cleanup(update, context))
    
    thread = threading.Thread(target=process_cleanup)
    thread.start()
    
    self.safe_send_message(
        update, 
        f"🧹 开始清理 {len(self.proxy_manager.proxies)} 个代理...\n"
        f"⚡ 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}\n"
        f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT}\n\n"
        "请稍等，清理过程可能需要几分钟..."
    )

async def process_proxy_cleanup(self, update, context):
    """处理代理清理过程"""
    try:
        # 发送进度消息
        progress_msg = self.safe_send_message(
            update,
            "🧹 <b>代理清理中...</b>\n\n📊 正在备份原始文件...",
            'HTML'
        )
        
        # 执行清理
        success, result_msg = await self.proxy_tester.cleanup_and_update_proxies(auto_confirm=True)
        
        if success:
            # 显示成功结果
            if progress_msg:
                try:
                    progress_msg.edit_text(
                        f"🎉 <b>代理清理成功！</b>\n\n{result_msg}",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            # 发送额外的总结信息
            summary_text = f"""

    def show_cleanup_confirmation(self, query):
    """显示清理确认对话框"""
    query.answer()
    confirm_text = f"""

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

    def _classify_cleanup(self, user_id):
    """清理分类任务"""
    if user_id in self.pending_classify_tasks:
        task = self.pending_classify_tasks[user_id]
        # 清理临时文件
        if 'temp_zip' in task and task['temp_zip'] and os.path.exists(task['temp_zip']):
            try:
                shutil.rmtree(os.path.dirname(task['temp_zip']), ignore_errors=True)
            except:
                pass
        if 'extract_dir' in task and task['extract_dir'] and os.path.exists(task['extract_dir']):
            try:
                shutil.rmtree(task['extract_dir'], ignore_errors=True)
            except:
                pass
        del self.pending_classify_tasks[user_id]
    
    # 清空数据库状态
    self.db.save_user(user_id, "", "", "")

async def _classify_send_bundles(self, update, context, bundles, user_id, prefix=""):
    """统一发送ZIP包并节流"""
    sent_count = 0
    for zip_path, display_name, count in bundles:
        if os.path.exists(zip_path):
            try:
                with open(zip_path, 'rb') as f:
                    caption = f"📦 <b>{prefix}{display_name}</b>\n{t(user_id, 'split_file_contains').format(count=count)}"
                    context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=display_name,
                        caption=caption,
                        parse_mode='HTML'
                    )
                sent_count += 1
                print(f"📤 已发送: {display_name}")
                await asyncio.sleep(1.0)  # 节流
                
                # 发送后删除
                try:
                    os.remove(zip_path)
                except:
                    pass
            except Exception as e:
                print(f"❌ 发送文件失败: {display_name} - {e}")
    
    return sent_count

async def _classify_split_single_qty(self, update, context, user_id, qty):
    """按单个数量拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    total = len(metas)
    if qty > total:
        self.safe_send_message(update, t(user_id, 'split_error_qty_exceeds').format(qty=qty, total=total))
        return
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_quantity_single')}</b>\n\n{t(user_id, 'split_processing_quantity_single_desc').format(qty=qty)}\n{t(user_id, 'split_processing_quantity_multi_total').format(total=total)}",
                parse_mode='HTML'
            )
        except:
            pass
        
        # 计算需要多少个包
        num_bundles = (total + qty - 1) // qty
        sizes = [qty] * (num_bundles - 1) + [total - (num_bundles - 1) * qty]
        
        bundles = self.classifier.split_by_quantities(metas, sizes, out_dir, t_func=lambda key: t(user_id, key))
        
        # 发送结果
        try:
            progress_msg.edit_text(f"<b>{t(user_id, 'split_sending_results')}</b>", parse_mode='HTML')
        except:
            pass
        
        sent = await self._classify_send_bundles(update, context, bundles, user_id)
        
        # 完成提示
        self.safe_send_message(
            update,
            f"<b>{t(user_id, 'split_complete')}</b>\n\n"
            f"{t(user_id, 'split_result_total').format(count=total)}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"• {t(user_id, 'split_method_quantity')}: {qty} {t(user_id, 'accounts_unit')}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 单数量拆分失败: {e}")
        import traceback
        traceback.print_exc()
        self.safe_send_message(update, f"❌ 拆分失败: {str(e)}")
    finally:
        # 清理输出目录
        try:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
        except:
            pass
        # 清理上传的临时文件和解压目录
        self._classify_cleanup(user_id)

async def _classify_split_multi_qty(self, update, context, user_id, quantities):
    """按多个数量拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        total = len(metas)
        total_requested = sum(quantities)
        
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_quantity_multi')}</b>\n\n"
                f"{t(user_id, 'split_processing_quantity_multi_sequence').format(sequence=' '.join(map(str, quantities)))}\n"
                f"{t(user_id, 'split_processing_quantity_multi_total').format(total=total)}\n"
                f"{t(user_id, 'split_processing_quantity_multi_requested').format(requested=total_requested)}",
                parse_mode='HTML'
            )
        except:
            pass
        
        bundles = self.classifier.split_by_quantities(metas, quantities, out_dir, t_func=lambda key: t(user_id, key))
        
        # 余数提示
        remainder = total - total_requested
        remainder_msg = ""
        if remainder > 0:
            remainder_msg = f"\n\n{t(user_id, 'split_remainder_unallocated').format(remainder=remainder)}"
        elif remainder < 0:
            remainder_msg = f"\n\n{t(user_id, 'split_remainder_exceeded')}"
        
        # 发送结果
        try:
            progress_msg.edit_text(f"<b>{t(user_id, 'split_sending_results')}</b>", parse_mode='HTML')
        except:
            pass
        
        sent = await self._classify_send_bundles(update, context, bundles, user_id)
        
        # 完成提示
        self.safe_send_message(
            update,
            f"<b>{t(user_id, 'split_complete')}</b>\n\n"
            f"{t(user_id, 'split_result_total').format(count=total)}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"{t(user_id, 'split_result_sequence').format(sequence=' '.join(map(str, quantities)))}{remainder_msg}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 多数量拆分失败: {e}")
        import traceback
        traceback.print_exc()
        self.safe_send_message(update, f"❌ 拆分失败: {str(e)}")
    finally:
        # 清理输出目录
        try:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir, ignore_errors=True)
        except:
            pass
        # 清理上传的临时文件和解压目录
        self._classify_cleanup(user_id)


    def cleanup_rename_task(self, user_id: int):
    """清理重命名任务"""
    if user_id in self.pending_rename:
        task = self.pending_rename[user_id]
        if task['temp_dir'] and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_rename[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 账户合并功能
# ================================


    def cleanup_merge_task(self, user_id: int):
    """清理合并任务"""
    if user_id in self.pending_merge:
        task = self.pending_merge[user_id]
        if task['temp_dir'] and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_merge[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 一键清理功能
# ================================


    def handle_cleanup_start(self, query):
    """开始一键清理流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 检查是否启用
    if not config.ENABLE_ONE_CLICK_CLEANUP:
        self.safe_edit_message(query, t(user_id, 'cleanup_feature_disabled'))
        return
    
    # 检查会员权限
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, t(user_id, 'cleanup_need_member'))
        return
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_cleanup_file"
    )
    
    text = f"""

    def handle_cleanup_confirm(self, update, context, query):
    """确认清理"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_cleanup:
        self.safe_edit_message(query, t(user_id, 'cleanup_no_pending_task'))
        return
    
    task = self.pending_cleanup[user_id]
    
    # 检查超时（10分钟）
    if time.time() - task['started_at'] > 600:
        self.cleanup_cleanup_task(user_id)
        self.safe_edit_message(query, t(user_id, 'cleanup_operation_timeout'))
        return
    
    # 启动异步清理
    def execute_cleanup():
        asyncio.run(self.execute_cleanup(update, context, user_id))
    
    thread = threading.Thread(target=execute_cleanup, daemon=True)
    thread.start()
    
    self.safe_edit_message(query, f"🧹 <b>{t(user_id, 'cleanup_starting')}...</b>\n\n{t(user_id, 'cleanup_initializing')}", 'HTML')

async def _process_single_account_full(self, file_info: tuple, file_type: str, progress_msg, all_files_count: int, completed_count: dict, lock: asyncio.Lock, start_time: float, user_id: int) -> dict:
    """处理单个账户的完整流程（包含连接和清理）"""
    file_path, file_name = file_info
    result_data = {
        'file_path': file_path,
        'file_name': file_name,
        'original_path': file_path,  # 保存原始文件路径用于打包
        'file_type': file_type,  # 保存文件类型
        'success': False,
        'error': None,
        'is_frozen': False,
        'statistics': {},
        'error_details': []
    }
    
    client = None
    try:
        # 如果是TData，需要先转换为Session
        if file_type == 'tdata':
            # 提取手机号用于日志
            phone_for_log = extract_phone_from_tdata_path(file_path) or file_name
            
            # 使用安全转换函数，带超时和错误处理
            session_path, error_msg = await safe_convert_tdata(file_path, phone_for_log)
            
            if session_path is None:
                # 转换失败，跳过该账号
                logger.warning(f"⚠️ 跳过账号 {phone_for_log}，转换失败: {error_msg}")
                result_data['error'] = error_msg
                result_data['error_details'].append(error_msg)
                return result_data
            
            # 使用转换后的session创建不接收更新的客户端以提升清理速度
            try:
                from telethon import TelegramClient as TelethonClient
                client = TelethonClient(
                    os.path.splitext(session_path)[0],
                    int(config.API_ID),
                    str(config.API_HASH),
                    receive_updates=False
                )
                await client.connect()
                
                # 检查授权
                if not await client.is_user_authorized():
                    logger.warning(f"Session not authorized after conversion: {file_name}")
                    result_data['error'] = "转换后Session未授权"
                    await client.disconnect()
                    return result_data
                    
            except Exception as e:
                logger.error(f"Failed to connect after TData conversion for {file_name}: {e}")
                # 检查是否为冻结账户错误
                if self._is_frozen_error(e):
                    result_data['error'] = 'FROZEN_ACCOUNT'
                    result_data['error_message'] = f"账户已冻结: {str(e)}"
                    result_data['is_frozen'] = True
                    logger.info(f"❄️ 转换后连接时检测到冻结账户: {file_name}")
                else:
                    result_data['error'] = f"转换后连接失败: {str(e)}"
                return result_data
        else:
            # 直接使用Session
            session_path = os.path.splitext(file_path)[0]
            
            # 获取代理配置
            proxy_dict = None
            proxy_enabled = self.db.get_proxy_enabled() if self.db else True
            use_proxy = config.USE_PROXY and proxy_enabled and self.proxy_manager.proxies
            
            if use_proxy:
                proxy_info = self.proxy_manager.get_next_proxy()
                if proxy_info:
                    proxy_dict = self.checker.create_proxy_dict(proxy_info)
                    logger.info(f"使用代理连接账号: {file_name}")
            
            try:
                client = TelegramClient(
                    session_path,
                    int(config.API_ID),
                    str(config.API_HASH),
                    proxy=proxy_dict,
                    receive_updates=False  # 禁用更新接收，提升清理速度
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    logger.warning(f"Session not authorized: {file_name}")
                    result_data['error'] = "Session未授权"
                    await client.disconnect()
                    return result_data
            except Exception as e:
                logger.error(f"Session connection failed for {file_name}: {e}")
                # 检查是否为冻结账户错误
                if self._is_frozen_error(e):
                    result_data['error'] = 'FROZEN_ACCOUNT'
                    result_data['error_message'] = f"账户已冻结: {str(e)}"
                    result_data['is_frozen'] = True
                    logger.info(f"❄️ 连接时检测到冻结账户: {file_name}")
                else:
                    result_data['error'] = f"连接失败: {str(e)}"
                return result_data
        
        # 进度更新节流（避免触发 Telegram 限制）- 改为基于时间而非账号数量
        last_update_time = {'value': 0}  # 上次更新的时间戳
        PROGRESS_UPDATE_INTERVAL = 10  # 每10秒更新一次进度
        
        # 创建进度回调函数
        async def update_progress(status_text):
            current_idx = completed_count['value'] + 1
            
            if not progress_msg:
                return
            
            current_time = time.time()
            time_since_last_update = current_time - last_update_time['value']
            
            # 节流逻辑：只在以下情况更新
            # 1. 距离上次更新已超过10秒
            # 2. 是第一个账户
            # 3. 是最后一个账户
            should_update = (
                time_since_last_update >= PROGRESS_UPDATE_INTERVAL or
                current_idx == 1 or
                current_idx == all_files_count
            )
            
            if not should_update:
                return
            
            async with lock:
                try:
                    progress_percent = int((current_idx / all_files_count) * 100)
                    
                    # 更新时间戳
                    last_update_time['value'] = current_time
                    
                    filled = int(progress_percent / 10)
                    empty = 10 - filled
                    progress_bar = "█" * filled + "░" * empty
                    
                    status_display = status_text[:30] + '...' if len(status_text) > 30 else status_text
                    
                    # 计算预计完成时间
                    elapsed_time = time.time() - start_time
                    if current_idx > 0:
                        avg_time_per_account = elapsed_time / current_idx
                        remaining_accounts = all_files_count - current_idx
                        estimated_remaining_seconds = avg_time_per_account * remaining_accounts
                        
                        hours = int(estimated_remaining_seconds // 3600)
                        minutes = int((estimated_remaining_seconds % 3600) // 60)
                        seconds = int(estimated_remaining_seconds % 60)
                        
                        if hours > 0:
                            time_remaining = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        else:
                            time_remaining = f"{minutes:02d}:{seconds:02d}"
                    else:
                        time_remaining = t(user_id, 'cleanup_initializing')
                    
                    message_text = (
                        f"<b>{t(user_id, 'cleanup_in_progress')}</b>\n\n"
                        f"{t(user_id, 'cleanup_current').format(filename=file_name)}\n"
                        f"{t(user_id, 'cleanup_total_progress').format(current=current_idx, total=all_files_count, percent=progress_percent)}\n"
                        f"⚙️ [{progress_bar}]\n"
                        f"{t(user_id, 'cleanup_eta').format(time=time_remaining)}"
                    )
                    
                    # 移除按钮，直接显示进度信息，减少刷新频率避免限流
                    progress_msg.edit_text(
                        message_text,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    # 如果是限流错误，静默处理
                    if "too many requests" in str(e).lower() or "retry after" in str(e).lower():
                        logger.warning(f"进度更新触发限流: {e}")
                    pass
        
        # 执行清理 - 添加整体超时保护
        try:
            cleanup_result = await asyncio.wait_for(
                self._cleanup_single_account(
                    client=client,
                    account_name=file_name,
                    file_path=file_path,
                    progress_callback=update_progress,
                    user_id=user_id
                ),
                timeout=CLEANUP_SINGLE_ACCOUNT_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"账号 {file_name} 清理超时 ({CLEANUP_SINGLE_ACCOUNT_TIMEOUT}秒)")
            cleanup_result = {
                'success': False,
                'error': f'清理超时 ({CLEANUP_SINGLE_ACCOUNT_TIMEOUT}秒)',
                'statistics': {},
                'error_details': [f'整个清理过程超时']
            }
        
        # 断开客户端
        try:
            await client.disconnect()
        except:
            pass
        
        # 更新完成计数
        async with lock:
            completed_count['value'] += 1
        
        # 合并结果
        result_data.update(cleanup_result)
        return result_data
        
    except Exception as e:
        logger.error(f"处理账户失败 {file_name}: {e}")
        import traceback
        traceback.print_exc()
        result_data['error'] = str(e)
        
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        return result_data

async def execute_cleanup(self, update, context, user_id: int):
    """执行一键清理（并发版本）"""
    if user_id not in self.pending_cleanup:
        return
    
    task = self.pending_cleanup[user_id]
    files = task['files']
    file_type = task['file_type']
    extract_dir = task['extract_dir']
    progress_msg = task.get('progress_msg')
    
    results_summary = {
        'total': len(files),
        'success': 0,
        'failed': 0,
        'frozen': 0,
        'reports': [],
        'success_files': [],
        'failed_files': [],
        'frozen_files': [],
        'detailed_results': []
    }
    
    # 初始化变量，确保在 finally 块中可用
    summary_report_path = None
    result_zips = []
    
    try:
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(config.CLEANUP_ACCOUNT_CONCURRENCY)
        lock = asyncio.Lock()
        completed_count = {'value': 0}
        start_time = time.time()
        
        async def process_with_semaphore(file_info):
            async with semaphore:
                return await self._process_single_account_full(
                    file_info, file_type, progress_msg, len(files), completed_count, lock, start_time, user_id
                )
        
        # 并发处理所有账户
        logger.info(f"开始并发清理 {len(files)} 个账户，并发数: {config.CLEANUP_ACCOUNT_CONCURRENCY}")
        tasks = [process_with_semaphore(file_info) for file_info in files]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 汇总结果
        for idx, result in enumerate(all_results, 1):
            if isinstance(result, BaseException):
                logger.error(f"处理异常: {result}")
                results_summary['failed'] += 1
                # 从原始files列表获取文件信息，包含file_type
                results_summary['failed_files'].append((files[idx-1][0], files[idx-1][1], files[idx-1][0], file_type))
                results_summary['detailed_results'].append({
                    'file_name': files[idx-1][1],
                    'status': 'failed',
                    'error': str(result)
                })
                continue
            
            # 保存详细结果
            results_summary['detailed_results'].append({
                'file_name': result['file_name'],
                'status': 'frozen' if result.get('is_frozen') else ('success' if result.get('success') else 'failed'),
                'error': result.get('error'),
                'error_details': result.get('error_details', []),
                'statistics': result.get('statistics', {})
            })
            
            # 分类统计
            # 冻结账户直接归类为失败账户（符合issue要求）
            # 注意：冻结账户会同时计入frozen和failed，这是有意为之：
            # - frozen_files用于统计和报告冻结账户数量
            # - failed_files用于将冻结账户打包到失败账户zip中
            if result.get('is_frozen'):
                results_summary['frozen'] += 1
                results_summary['frozen_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                # 冻结账户同时加入失败列表，以便打包到失败zip中
                results_summary['failed'] += 1
                results_summary['failed_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"❄️ 冻结账户（归类为失败）: {result['file_name']}")
            elif result.get('success'):
                results_summary['success'] += 1
                results_summary['success_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"✅ 清理成功: {result['file_name']}")
            else:
                results_summary['failed'] += 1
                results_summary['failed_files'].append((result['file_path'], result['file_name'], result.get('original_path'), result.get('file_type')))
                logger.info(f"❌ 清理失败: {result['file_name']}")
        
        # 生成详细的TXT报告
        timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
        summary_report_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleanup_summary_{timestamp}.txt")
        
        with open(summary_report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"              {t(user_id, 'cleanup_report_title')}\n")
            f.write("=" * 80 + "\n\n")
            
            success_rate = (results_summary['success'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            frozen_rate = (results_summary['frozen'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            
            f.write(f"{t(user_id, 'cleanup_report_time')}: {timestamp}\n")
            f.write(f"{t(user_id, 'cleanup_report_concurrency')}: {config.CLEANUP_ACCOUNT_CONCURRENCY} {t(user_id, 'cleanup_report_concurrent_accounts')}\n")
            f.write(f"{t(user_id, 'cleanup_report_total')}: {results_summary['total']}\n")
            f.write(f"✅ {t(user_id, 'cleanup_report_success')}: {results_summary['success']} ({success_rate:.1f}%)\n")
            f.write(f"❄️ {t(user_id, 'cleanup_report_frozen')}: {results_summary['frozen']} ({frozen_rate:.1f}%)\n")
            f.write(f"❌ {t(user_id, 'cleanup_report_failed')}: {results_summary['failed']}\n\n")
            
            # 详细结果
            f.write("=" * 80 + "\n")
            f.write(f"                    {t(user_id, 'cleanup_report_details')}\n")
            f.write("=" * 80 + "\n\n")
            
            for idx, detail in enumerate(results_summary['detailed_results'], 1):
                status_icon = "✅" if detail['status'] == 'success' else ("❄️" if detail['status'] == 'frozen' else "❌")
                status_text = t(user_id, 'cleanup_report_status_success') if detail['status'] == 'success' else (t(user_id, 'cleanup_report_status_frozen') if detail['status'] == 'frozen' else t(user_id, 'cleanup_report_status_failed'))
                
                f.write(f"{idx}. {status_icon} {detail['file_name']} - {status_text}\n")
                
                if detail.get('error'):
                    f.write(f"   {t(user_id, 'cleanup_report_error')} {detail['error']}\n")
                
                if detail.get('error_details'):
                    f.write(f"   {t(user_id, 'cleanup_report_error_details')}\n")
                    for err in detail['error_details']:
                        f.write(f"   - {err}\n")
                
                stats = detail.get('statistics', {})
                if stats:
                    f.write(f"   {t(user_id, 'cleanup_report_stats')} ")
                    stat_parts = []
                    if stats.get('profile_cleared'): stat_parts.append(t(user_id, 'cleanup_report_profile_cleared'))
                    if stats.get('groups_left'): stat_parts.append(t(user_id, 'cleanup_report_groups_left').format(count=stats['groups_left']))
                    if stats.get('channels_left'): stat_parts.append(t(user_id, 'cleanup_report_channels_left').format(count=stats['channels_left']))
                    if stats.get('histories_deleted'): stat_parts.append(t(user_id, 'cleanup_report_histories_deleted').format(count=stats['histories_deleted']))
                    if stats.get('contacts_deleted'): stat_parts.append(t(user_id, 'cleanup_report_contacts_deleted_label').format(count=stats['contacts_deleted']))
                    if stat_parts:
                        f.write(", ".join(stat_parts))
                    f.write("\n")
                
                f.write("\n")
            
            # 分类汇总
            if results_summary['success_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_success_list')} ({len(results_summary['success_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['success_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ✅ {fname}\n")
                f.write("\n")
            
            if results_summary['frozen_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_frozen_accounts')} ({len(results_summary['frozen_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['frozen_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ❄️ {fname}\n")
                f.write("\n")
            
            if results_summary['failed_files']:
                f.write("-" * 80 + "\n")
                f.write(f"{t(user_id, 'cleanup_report_failed_list')} ({len(results_summary['failed_files'])})\n")
                f.write("-" * 80 + "\n")
                for idx, file_info in enumerate(results_summary['failed_files'], 1):
                    fname = file_info[1] if len(file_info) > 1 else file_info[0]
                    f.write(f"{idx}. ❌ {fname}\n")
                f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'cleanup_report_concurrent_mode').format(count=config.CLEANUP_ACCOUNT_CONCURRENCY)}\n")
            f.write("=" * 80 + "\n")
        
        # 打包成功和失败的账户文件
        result_zips = []
        
        # 打包成功清理的账户
        if results_summary['success_files']:
            success_zip_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleaned_success_{timestamp}.zip")
            with zipfile.ZipFile(success_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in results_summary['success_files']:
                    file_path = file_info[0]
                    file_name = file_info[1]
                    original_path = file_info[2] if len(file_info) > 2 else file_path
                    item_file_type = file_info[3] if len(file_info) > 3 else 'session'
                    
                    if item_file_type == 'tdata':
                        # TData格式：每个账号独立打包到 手机号/tdata/... 结构
                        # 提取手机号作为账号标识
                        phone = extract_phone_from_tdata_path(original_path) or file_name
                        # 去除特殊字符，确保是有效的目录名
                        phone = str(phone).replace('.zip', '').replace('/', '_').replace('\\', '_')
                        
                        if os.path.isdir(original_path):
                            # 遍历TData目录下的所有文件
                            for root, dirs, files_in_dir in os.walk(original_path):
                                for file in files_in_dir:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对路径，保留TData目录结构
                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                    # 添加手机号前缀，格式：手机号/tdata/...
                                    arc_path = os.path.join(phone, rel_path)
                                    zipf.write(file_full_path, arc_path)
                    else:
                        # Session格式：添加session文件及相关文件
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 如果有对应的session-journal文件也添加
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 如果有对应的json文件也添加
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            
            result_zips.append(('success', success_zip_path, len(results_summary['success_files'])))
        
        # 打包失败的账户
        if results_summary['failed_files']:
            failed_zip_path = os.path.join(config.CLEANUP_REPORTS_DIR, f"cleaned_failed_{timestamp}.zip")
            with zipfile.ZipFile(failed_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in results_summary['failed_files']:
                    file_path = file_info[0]
                    file_name = file_info[1]
                    original_path = file_info[2] if len(file_info) > 2 else file_path
                    item_file_type = file_info[3] if len(file_info) > 3 else 'session'
                    
                    if item_file_type == 'tdata':
                        # TData格式：每个账号独立打包到 手机号/tdata/... 结构
                        # 提取手机号作为账号标识
                        phone = extract_phone_from_tdata_path(original_path) or file_name
                        # 去除特殊字符，确保是有效的目录名
                        phone = str(phone).replace('.zip', '').replace('/', '_').replace('\\', '_')
                        
                        if os.path.isdir(original_path):
                            # 遍历TData目录下的所有文件
                            for root, dirs, files_in_dir in os.walk(original_path):
                                for file in files_in_dir:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对路径，保留TData目录结构
                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                    # 添加手机号前缀，格式：手机号/tdata/...
                                    arc_path = os.path.join(phone, rel_path)
                                    zipf.write(file_full_path, arc_path)
                    else:
                        # Session格式：添加session文件及相关文件
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 如果有对应的session-journal文件也添加
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 如果有对应的json文件也添加
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            
            result_zips.append(('failed', failed_zip_path, len(results_summary['failed_files'])))
        
    except Exception as e:
        logger.error(f"Cleanup execution failed: {e}")
        import traceback
        traceback.print_exc()
        
        # 标记清理过程失败
        results_summary['cleanup_error'] = str(e)
    
    finally:
        # 无论如何都要发送清理结果
        try:
            # 检查实际处理的账号数
            actual_processed = results_summary['success'] + results_summary['failed']
            is_complete = (actual_processed == results_summary['total'])
            
            # 发送完成消息
            success_rate = (results_summary['success'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            frozen_rate = (results_summary['frozen'] / results_summary['total'] * 100) if results_summary['total'] > 0 else 0
            
            if results_summary.get('cleanup_error'):
                # 清理过程出错，发送错误消息但仍尝试发送已有的结果
                final_text = f"""

    def cleanup_cleanup_task(self, user_id: int):
    """清理一键清理任务"""
    if user_id in self.pending_cleanup:
        task = self.pending_cleanup[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_cleanup[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")


    def _cleanup_user_temp_sessions(self, user_id: int):
    """清理指定用户的临时session文件和旧上传目录
    
    这确保每次上传只使用当前上传的账号，不会重复登录之前的账号
    """
    try:
        # 1. 清理临时session文件
        if os.path.exists(config.SESSIONS_BAK_DIR):
            user_prefix = f"user_{user_id}_"
            cleaned_count = 0
            
            for filename in os.listdir(config.SESSIONS_BAK_DIR):
                if filename.startswith(user_prefix):
                    file_path = os.path.join(config.SESSIONS_BAK_DIR, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            cleaned_count += 1
                            logger.info(f"🧹 清理旧临时文件: {filename}")
                    except Exception as e:
                        logger.warning(f"⚠️ 清理文件失败 {filename}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"✅ 清理了 {cleaned_count} 个用户 {user_id} 的旧临时session文件")
                print(f"✅ 清理了 {cleaned_count} 个用户 {user_id} 的旧临时session文件")
        
        # 2. 【新增】清理用户的旧上传目录（防止累积）
        if os.path.exists(config.UPLOADS_DIR):
            # 匹配两种格式: task_{user_id}_batch (旧格式) 和 task_{user_id}_batch_{timestamp} (新格式)
            old_prefix = f"task_{user_id}_batch"
            cleaned_dirs = 0
            
            for dirname in os.listdir(config.UPLOADS_DIR):
                if dirname.startswith(old_prefix):
                    dir_path = os.path.join(config.UPLOADS_DIR, dirname)
                    try:
                        if os.path.isdir(dir_path):
                            shutil.rmtree(dir_path)
                            cleaned_dirs += 1
                            logger.info(f"🧹 清理旧上传目录: {dirname}")
                    except Exception as e:
                        logger.warning(f"⚠️ 清理目录失败 {dirname}: {e}")
            
            if cleaned_dirs > 0:
                logger.info(f"✅ 清理了 {cleaned_dirs} 个用户 {user_id} 的旧上传目录")
                print(f"✅ 清理了 {cleaned_dirs} 个用户 {user_id} 的旧上传目录")
    except Exception as e:
        logger.error(f"❌ 清理临时文件失败: {e}")

# ================================
# 批量创建群组/频道功能
# ================================

async def process_batch_create_upload(self, update: Update, context: CallbackContext, document):
    """处理批量创建文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, t(user_id, 'processing_file'), 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 【关键修复】在处理新上传前，清理该用户的旧临时session文件
        # 这确保每次上传只使用当前上传的账号，不会重复登录之前的账号
        self._cleanup_user_temp_sessions(user_id)
        
        # 【关键修复】为每次上传创建唯一的任务ID，确保完全隔离
        # 使用时间戳确保每次上传都有独立的目录，不会混淆
        unique_task_id = f"{user_id}_batch_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="batch_create_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件 - 使用唯一任务ID，确保只提取当前上传的账号
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, "❌ <b>未找到有效文件</b>\n\n请确保ZIP包含Session或TData格式的文件", parse_mode='HTML')
            return
        
        self.safe_edit_message_text(
            progress_msg,
            t(user_id, 'batch_create_found_files').format(count=len(files)) + f"\n\n{t(user_id, 'batch_create_verifying')}",
            parse_mode='HTML'
        )
        
        # 验证账号
        accounts = []
        valid_count = 0
        total_remaining = 0
        
        # 获取设备参数和代理
        device_config = self.device_loader.get_random_device_config()
        api_id = device_config.get('api_id', config.API_ID)
        api_hash = device_config.get('api_hash', config.API_HASH)
        
        for i, (file_path, file_name) in enumerate(files):
            # 更新进度
            if (i + 1) % 5 == 0:
                self.safe_edit_message_text(
                    progress_msg,
                    f"{t(user_id, 'batch_create_verifying')}\n\n{t(user_id, 'batch_create_verifying_progress').format(done=i + 1, total=len(files))}",
                    parse_mode='HTML'
                )
            
            # 创建账号信息
            account = BatchAccountInfo(
                session_path=file_path,
                file_name=file_name,
                file_type=file_type
            )
            
            # 获取代理
            proxy_dict = None
            if self.proxy_manager.is_proxy_mode_active(self.db):
                proxy_info = self.proxy_manager.get_next_proxy()
                if proxy_info:
                    proxy_dict = (
                        socks.SOCKS5 if proxy_info['type'] == 'socks5' else socks.HTTP,
                        proxy_info['host'],
                        proxy_info['port'],
                        True,
                        proxy_info.get('username'),
                        proxy_info.get('password')
                    )
            
            # 验证账号（传入user_id以确保临时文件隔离）
            is_valid, error = await self.batch_creator.validate_account(
                account, api_id, api_hash, proxy_dict, user_id
            )
            
            accounts.append(account)
            
            if is_valid:
                valid_count += 1
                total_remaining += account.daily_remaining
        
        # 保存任务信息
        self.pending_batch_create[user_id] = {
            'accounts': accounts,
            'total_accounts': len(accounts),
            'valid_accounts': valid_count,
            'total_remaining': total_remaining,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir
        }
        
        # 显示验证结果
        text = f"""

    def cleanup_reauthorize_task(self, user_id: int):
    """清理重新授权任务"""
    if user_id in self.pending_reauthorize:
        task = self.pending_reauthorize[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_reauthorize[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

async def process_reauthorize_upload(self, update: Update, context: CallbackContext, document):
    """处理重新授权文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'reauth_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 清理旧的临时文件
        self._cleanup_user_temp_sessions(user_id)
        
        # 创建唯一任务ID
        unique_task_id = f"{user_id}_reauth_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="reauthorize_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, f"❌ <b>{t(user_id, 'reauth_no_valid_files')}</b>\n\n{t(user_id, 'reauth_ensure_format')}", parse_mode='HTML')
            return
        
        # 保存任务信息
        self.pending_reauthorize[user_id] = {
            'files': files,
            'file_type': file_type,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir,
            'total_files': len(files)
        }
        
        # 显示选择密码输入方式的按钮
        text = f"""{t(user_id, 'reauth_found_accounts').format(count=len(files))}


    def cleanup_registration_check_task(self, user_id: int):
    """清理查询注册时间任务"""
    if user_id in self.pending_registration_check:
        task = self.pending_registration_check[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_registration_check[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

async def process_registration_check_upload(self, update: Update, context: CallbackContext, document):
    """处理查询注册时间文件上传"""
    user_id = update.effective_user.id
    
    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'regtime_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return
    
    temp_zip = None
    try:
        # 清理旧的临时文件
        self._cleanup_user_temp_sessions(user_id)
        
        # 创建唯一任务ID
        unique_task_id = f"{user_id}_regcheck_{int(time.time() * 1000)}"
        
        # 下载文件
        temp_dir = tempfile.mkdtemp(prefix="registration_check_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)
        
        # 扫描文件
        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, unique_task_id)
        
        if not files:
            self.safe_edit_message_text(progress_msg, t(user_id, 'regtime_no_valid_files'), parse_mode='HTML')
            return
        
        # 保存任务信息
        self.pending_registration_check[user_id] = {
            'files': files,
            'file_type': file_type,
            'temp_dir': temp_dir,
            'extract_dir': extract_dir,
            'total_files': len(files),
            'progress_msg': progress_msg
        }
        
        # 显示确认按钮
        file_type_str = t(user_id, 'regtime_file_type_session') if file_type == 'session' else t(user_id, 'regtime_file_type_tdata')
        text = f"""{t(user_id, 'regtime_found_accounts').format(count=len(files))}


    def cleanup_profile_update_task(self, user_id: int):
    """清理资料修改任务"""
    if user_id in self.pending_profile_update:
        task = self.pending_profile_update[user_id]
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)
        del self.pending_profile_update[user_id]
    
    # 清除用户状态
    self.db.save_user(user_id, "", "", "")

# ================================
# 通讯录限制检测功能
# ================================


