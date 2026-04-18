

# ===== Handler Methods from EnhancedBot =====

    def _is_network_error(self, error: Exception) -> bool:
    """判断异常是否是网络相关的错误
    
    Args:
        error: 要检查的异常
        
    Returns:
        如果是网络相关错误返回 True，否则返回 False
    """
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in self.NETWORK_ERROR_KEYWORDS)


    def __init__(self):
    print("🤖 初始化增强版机器人...")
    
    global config
    config = Config()
    if not config.validate():
        print("❌ 配置验证失败")
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
        print(f"⚠️ APIFormatConverter 带参构造失败：{e}，切换到兼容模式（无参+手动注入）")
        self.api_converter = APIFormatConverter()   # 老版本：无参
        self.api_converter.db = self.db
        self.api_converter.base_url = config.BASE_URL


    # API转换待处理任务池：上传ZIP后先问网页展示的2FA，等待用户回复
    self.pending_api_tasks: Dict[int, Dict[str, Any]] = {}

    # 启动验证码接收服务器（Flask）
    try:
        self.api_converter.start_web_server()
    except Exception as e:
        print(f"⚠️ 验证码服务器启动失败: {e}")

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
            print("✅ 批量创建服务初始化成功")
        except Exception as e:
            print(f"⚠️ 批量创建服务初始化失败: {e}")
            self.batch_creator = None
    else:
        self.batch_creator = None

    self.updater = Updater(config.TOKEN, use_context=True)
    self.dp = self.updater.dispatcher
    
    self.setup_handlers()
    
    print("✅ 增强版机器人初始化完成")


    def get_status_translation_key(self, status: str) -> str:
    """Map internal status to translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for the status
    """
    status_map = {
        "无限制": "status_no_restriction",
        "垃圾邮件": "status_spambot",
        "冻结": "status_frozen",
        "封禁": "status_banned",
        "连接错误": "status_connection_error",
    }
    return status_map.get(status, "status_no_restriction")


    def get_file_desc_translation_key(self, status: str) -> str:
    """Map internal status to file description translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for file description
    """
    desc_map = {
        "无限制": "file_desc_no_restriction",
        "垃圾邮件": "file_desc_spambot",
        "冻结": "file_desc_frozen",
        "封禁": "file_desc_banned",
        "连接错误": "file_desc_connection_error",
    }
    return desc_map.get(status, "file_desc_no_restriction")


    def get_translated_file_info(self, user_id: int, status: str, count: int) -> tuple:
    """Get translated filename and caption for a status file
    
    Args:
        user_id: User ID for language selection
        status: Internal status name (Chinese)
        count: Number of accounts
        
    Returns:
        Tuple of (filename, caption_text, check_time_display, check_mode)
    """
    zip_name_key = self.get_zip_name_translation_key(status)
    file_desc_key = self.get_file_desc_translation_key(status)
    
    zip_filename = f"{t(user_id, zip_name_key).format(count=count)}.zip"
    file_caption_text = t(user_id, file_desc_key).format(count=count)
    
    actual_proxy_mode = self.proxy_manager.is_proxy_mode_active(self.db)
    check_mode = t(user_id, 'check_mode_proxy') if actual_proxy_mode else t(user_id, 'check_mode_local')
    check_time_display = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')
    
    return zip_filename, file_caption_text, check_time_display, check_mode


    def setup_handlers(self):
    self.dp.add_handler(CommandHandler("start", self.start_command))
    self.dp.add_handler(CommandHandler("help", self.help_command))
    self.dp.add_handler(CommandHandler("addadmin", self.add_admin_command))
    self.dp.add_handler(CommandHandler("removeadmin", self.remove_admin_command))
    self.dp.add_handler(CommandHandler("listadmins", self.list_admins_command))
    self.dp.add_handler(CommandHandler("payment_stats", self.payment_stats_command))
    self.dp.add_handler(CommandHandler("proxy", self.proxy_command))
    self.dp.add_handler(CommandHandler("testproxy", self.test_proxy_command))
    self.dp.add_handler(CommandHandler("cleanproxy", self.clean_proxy_command))
    self.dp.add_handler(CommandHandler("convert", self.convert_command))
    # 新增：API格式转换命令
    self.dp.add_handler(CommandHandler("api", self.api_command))
    # 新增：账号分类命令
    self.dp.add_handler(CommandHandler("classify", self.classify_command))
    # 新增：返回主菜单（优先于通用回调）
    self.dp.add_handler(CallbackQueryHandler(self.on_back_to_main, pattern=r"^back_to_main$"))
    
    # 专用：广播消息回调处理器（必须在通用回调之前注册）
    self.dp.add_handler(CallbackQueryHandler(self.handle_broadcast_callbacks_router, pattern=r"^broadcast_"))

    # 通用回调处理（需放在特定回调之后）
    self.dp.add_handler(CallbackQueryHandler(self.handle_callbacks))
    self.dp.add_handler(MessageHandler(Filters.document, self.handle_file))
    # 新增：广播媒体上传处理
    self.dp.add_handler(MessageHandler(Filters.photo, self.handle_photo))
    self.dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_text))


    def safe_send_message(self, update, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全发送消息（带网络错误重试机制）
    
    Args:
        update: Telegram update 对象
        text: 要发送的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        发送的消息对象，失败时返回 None
    """
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # 检查 update.message 是否存在
            if update.message:
                return update.message.reply_text(
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            # 如果 update.message 不存在（例如来自回调查询），使用 bot.send_message
            elif update.effective_chat:
                return self.updater.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            else:
                print("❌ 无法发送消息: update 对象缺少 message 和 effective_chat")
                return None
                
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 发送消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 发送消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                try:
                    error_str = str(e) if str(e) else "(空错误消息)"
                    error_msg = f"❌ 发送消息失败: {type(e).__name__}: {error_str}"
                except:
                    error_msg = f"❌ 发送消息失败: {type(e).__name__} (无法获取错误详情)"
                print(error_msg, flush=True)
                import traceback
                import sys
                print(f"详细堆栈跟踪:", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 发送消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def safe_edit_message(self, query, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全编辑消息（带网络错误重试机制）
    
    Args:
        query: Telegram callback query 对象
        text: 要编辑的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        编辑后的消息对象，失败时返回 None
    """
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return query.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            print(f"❌ 编辑消息失败: {e}")
            return None
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                print(f"❌ 编辑消息失败: {e}")
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 编辑消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def safe_edit_message_text(self, message, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全编辑消息对象（带网络错误重试机制）
    
    Args:
        message: Telegram message 对象
        text: 要编辑的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        编辑后的消息对象，失败时返回 None
    """
    if not message:
        return None
        
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return message.edit_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return message
            print(f"❌ 编辑消息失败: {e}")
            return None
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                error_str = str(e) if str(e) else "(空错误消息)"
                print(f"❌ 编辑消息失败: {type(e).__name__}: {error_str}", flush=True)
                import traceback
                import sys
                print(f"详细堆栈跟踪:", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 编辑消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def send_document_safely(self, chat_id: int, file_path: str, caption: str = None, filename: str = None) -> bool:
    """安全发送文档，处理 RetryAfter 错误"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            with open(file_path, 'rb') as doc:
                self.updater.bot.send_document(
                    chat_id=chat_id,
                    document=doc,
                    caption=caption,
                    filename=filename,
                    parse_mode='HTML'
                )
            return True
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            retry_count += 1
        except Exception as e:
            print(f"❌ 发送文档失败: {e}")
            return False
    
    return False


    def create_status_count_separate_buttons(self, results: Dict[str, List], processed: int, total: int, user_id: int = None) -> InlineKeyboardMarkup:
    """创建状态|数量分离按钮布局"""
    buttons = []
    
    # Status names for results dictionary (internal keys, keep in Chinese for compatibility)
    status_info = [
        ("无限制", "🟢", len(results['无限制'])),
        ("垃圾邮件", "🟡", len(results['垃圾邮件'])),
        ("冻结", "🔴", len(results['冻结'])),
        ("封禁", "🟠", len(results['封禁'])),
        ("连接错误", "⚫", len(results['连接错误']))
    ]
    
    # 每一行显示：状态名称 | 数量
    for status, emoji, count in status_info:
        # Translate status text for display if user_id is provided
        if user_id:
            status_key = self.get_status_translation_key(status)
            status_display = t(user_id, status_key)
        else:
            status_display = status  # Fallback to Chinese if no user_id
        
        row = [
            InlineKeyboardButton(f"{emoji} {status_display}", callback_data=f"status_{status}"),
            InlineKeyboardButton(f"{count}", callback_data=f"count_{status}")
        ]
        buttons.append(row)
    
    return InlineKeyboardMarkup(buttons)

    def start_command(self, update: Update, context: CallbackContext):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""
    
    # 保存用户数据到数据库
    self.db.save_user(user_id, username, first_name, "")
    
    self.show_main_menu(update, user_id)


    def show_main_menu(self, update: Update, user_id: int):
    """显示主菜单（统一方法）"""
    # 获取用户信息
    if update.callback_query:
        first_name = update.callback_query.from_user.first_name or t(user_id, 'default_user')
    else:
        first_name = update.effective_user.first_name or t(user_id, 'default_user')
    
    # 获取会员状态（使用 check_membership 方法）
    is_member, level, expiry = self.db.check_membership(user_id)
    
    if self.db.is_admin(user_id):
        member_status = t(user_id, 'status_admin')
    elif is_member:
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        member_status = f"🎁 {translated_level}"
    else:
        member_status = t(user_id, 'status_no_member')
    
    # 翻译到期时间
    if expiry == "永久有效":
        expiry = t(user_id, 'expiry_permanent')
    
    # 构建翻译后的欢迎文本
    proxy_mode_text = t(user_id, 'proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'proxy_mode_local')
    proxy_count_text = t(user_id, 'proxy_count_value').format(count=len(self.proxy_manager.proxies))
    
    welcome_text = f"""

    def show_language_menu(self, update: Update, user_id: int):
    """显示语言选择菜单"""
    query = update.callback_query
    if query:
        query.answer()
    
    # 构建语言选择菜单
    menu_text = t(user_id, 'language_menu_title')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'language_chinese'), callback_data="set_language_zh")],
        [InlineKeyboardButton(t(user_id, 'language_english'), callback_data="set_language_en")],
        [InlineKeyboardButton(t(user_id, 'language_russian'), callback_data="set_language_ru")],
        [InlineKeyboardButton(t(user_id, 'btn_back_to_menu'), callback_data="back_to_main")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    try:
        query.edit_message_text(
            text=menu_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"⚠️ 编辑语言菜单失败: {e}")


    def api_command(self, update: Update, context: CallbackContext):
    """API格式转换命令"""
    user_id = update.effective_user.id

    # 权限检查
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限才能使用API转换功能")
        return

    if not 'FLASK_AVAILABLE' in globals() or not FLASK_AVAILABLE:
        self.safe_send_message(update, "❌ API转换功能不可用\n\n原因: Flask库未安装\n💡 请安装: pip install flask jinja2")
        return

    text = f"""

    def handle_api_conversion(self, query):
    """处理API转换选项"""
    query.answer()
    user_id = query.from_user.id

    # 权限检查
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用API转换功能")
        return

    if not 'FLASK_AVAILABLE' in globals() or not FLASK_AVAILABLE:
        self.safe_edit_message(query, "❌ API转换功能不可用\n\n原因: Flask库未安装\n💡 请安装: pip install flask jinja2")
        return

    text = f"""

    def help_command(self, update: Update, context: CallbackContext):
    """处理 /help 命令和帮助按钮"""
    user_id = update.effective_user.id
    
    help_text = """

    def proxy_command(self, update: Update, context: CallbackContext):
    """代理管理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    # 获取当前代理状态
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # 统计住宅代理数量
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    proxy_text = f"""

    def show_proxy_detailed_status(self, update: Update):
    """显示代理详细状态"""
    if self.proxy_manager.proxies:
        status_text = "<b>📡 代理详细状态</b>\n\n"
        # 隐藏代理详细地址，只显示数量和类型
        proxy_count = len(self.proxy_manager.proxies)
        proxy_types = {}
        for proxy in self.proxy_manager.proxies:
            ptype = proxy.get('type', 'http')
            proxy_types[ptype] = proxy_types.get(ptype, 0) + 1
        
        status_text += f"📊 已加载 {proxy_count} 个代理\n\n"
        for ptype, count in proxy_types.items():
            status_text += f"• {ptype.upper()}: {count}个\n"
        
        # 添加代理设置信息
        enabled, updated_time, updated_by = self.db.get_proxy_setting_info()
        status_text += f"\n<b>📊 代理开关状态</b>\n"
        status_text += f"• 当前状态: {'🟢启用' if enabled else '🔴禁用'}\n"
        status_text += f"• 更新时间: {updated_time}\n"
        if updated_by:
            status_text += f"• 操作人员: {updated_by}\n"
        
        self.safe_send_message(update, status_text, 'HTML')
    else:
        self.safe_send_message(update, "❌ 没有可用的代理")


    def test_proxy_command(self, update: Update, context: CallbackContext):
    """测试代理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not self.proxy_manager.proxies:
        self.safe_send_message(update, "❌ 没有可用的代理进行测试")
        return
    
    # 异步处理代理测试
    def process_test():
        asyncio.run(self.process_proxy_test(update, context))
    
    thread = threading.Thread(target=process_test)
    thread.start()
    
    self.safe_send_message(
        update, 
        f"🧪 开始测试 {len(self.proxy_manager.proxies)} 个代理...\n"
        f"⚡ 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}\n"
        f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT}\n\n"
        "请稍等，测试结果将自动发送..."
    )

async def process_proxy_test(self, update, context):
    """处理代理测试"""
    try:
        # 发送进度消息
        progress_msg = self.safe_send_message(
            update,
            "🧪 <b>代理测试中...</b>\n\n📊 正在初始化测试环境...",
            'HTML'
        )
        
        # 进度回调函数
        async def test_progress_callback(tested, total, stats):
            try:
                progress = int(tested / total * 100)
                elapsed = time.time() - stats['start_time']
                speed = tested / elapsed if elapsed > 0 else 0
                
                progress_text = f"""

    def handle_proxy_callbacks(self, query, data):
    """处理代理相关回调"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可以操作")
        return
    
    if data == "proxy_enable":
        # 启用代理
        if self.db.set_proxy_enabled(True, user_id):
            query.answer("✅ 代理已启用")
            self.refresh_proxy_panel(query)
        else:
            query.answer("❌ 启用失败")
    
    elif data == "proxy_disable":
        # 禁用代理
        if self.db.set_proxy_enabled(False, user_id):
            query.answer("✅ 代理已禁用")
            self.refresh_proxy_panel(query)
        else:
            query.answer("❌ 禁用失败")
    
    elif data == "proxy_reload":
        # 重新加载代理列表
        old_count = len(self.proxy_manager.proxies)
        self.proxy_manager.load_proxies()
        new_count = len(self.proxy_manager.proxies)
        
        query.answer(f"✅ 重新加载完成: {old_count}→{new_count}个代理")
        self.refresh_proxy_panel(query)
    
    elif data == "proxy_status":
        # 查看详细状态
        self.show_proxy_status_popup(query)
    
    elif data == "proxy_test":
        # 测试代理连接
        self.test_proxy_connection(query)
    
    elif data == "proxy_stats":
        # 显示代理统计
        self.show_proxy_statistics(query)
    
    elif data == "proxy_cleanup":
        # 清理失效代理
        self.show_cleanup_confirmation(query)
    
    elif data == "proxy_optimize":
        # 显示速度优化信息
        self.show_speed_optimization_info(query)


    def show_proxy_status_popup(self, query):
    """显示代理状态弹窗"""
    if self.proxy_manager.proxies:
        status_text = f"📡 可用代理: {len(self.proxy_manager.proxies)}个\n"
        enabled, updated_time, updated_by = self.db.get_proxy_setting_info()
        status_text += f"🔧 代理开关: {'启用' if enabled else '禁用'}\n"
        status_text += f"⏰ 更新时间: {updated_time}"
    else:
        status_text = "❌ 没有可用的代理"
    
    query.answer(status_text, show_alert=True)


    def test_proxy_connection(self, query):
    """测试代理连接"""
    if not self.proxy_manager.proxies:
        query.answer("❌ 没有可用的代理进行测试", show_alert=True)
        return
    
    # 简单测试：尝试获取一个代理
    proxy = self.proxy_manager.get_next_proxy()
    if proxy:
        # 隐藏代理详细地址
        query.answer(f"🧪 测试代理: {proxy['type'].upper()}代理", show_alert=True)
    else:
        query.answer("❌ 获取测试代理失败", show_alert=True)


    def show_proxy_statistics(self, query):
    """显示代理统计信息"""
    proxies = self.proxy_manager.proxies
    if not proxies:
        query.answer("❌ 没有代理数据", show_alert=True)
        return
    
    # 统计代理类型
    type_count = {}
    for proxy in proxies:
        proxy_type = proxy['type']
        type_count[proxy_type] = type_count.get(proxy_type, 0) + 1
    
    stats_text = f"📊 代理统计\n总数: {len(proxies)}个\n\n"
    for proxy_type, count in type_count.items():
        stats_text += f"{proxy_type.upper()}: {count}个\n"
    
    enabled, _, _ = self.db.get_proxy_setting_info()
    stats_text += f"\n状态: {'🟢启用' if enabled else '🔴禁用'}"
    
    query.answer(stats_text, show_alert=True)


    def show_speed_optimization_info(self, query):
    """显示速度优化信息"""
    query.answer()
    current_concurrent = config.PROXY_CHECK_CONCURRENT if config.PROXY_FAST_MODE else config.MAX_CONCURRENT_CHECKS
    current_timeout = config.PROXY_CHECK_TIMEOUT if config.PROXY_FAST_MODE else config.CHECK_TIMEOUT
    
    optimization_text = f"""

    def show_proxy_panel(self, update: Update, query):
    """Display Proxy Management Panel"""
    user_id = query.from_user.id
    
    # Permission check (Admin only)
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get proxy status information
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # Count residential proxies
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    # Build proxy management panel information
    proxy_text = f"""

    def handle_callbacks(self, update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id  # ← 添加这一行
    if data == "start_check":
        self.handle_start_check(query)
    elif data == "format_conversion":
        self.handle_format_conversion(query)
    elif data == "change_2fa":
        self.handle_change_2fa(query)
    elif data == "forget_2fa":
        self.handle_forget_2fa(query)
    elif data == "remove_2fa":
        self.handle_remove_2fa(query)
    elif data == "add_2fa":
        self.handle_add_2fa(query)
    elif data == "remove_2fa_auto":
        # 自动识别密码
        query.answer()
        user_id = query.from_user.id
        if user_id in self.two_factor_manager.pending_2fa_tasks:
            task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
            if task_info.get('operation') == 'remove':
                # 使用 None 表示自动识别
                def process_remove():
                    asyncio.run(self.complete_remove_2fa(update, context, user_id, None))
                threading.Thread(target=process_remove, daemon=True).start()
            else:
                query.answer("❌ 操作类型不匹配")
        else:
            query.answer("❌ 没有待处理的任务")
    elif data == "remove_2fa_manual":
        # 手动输入密码
        query.answer()
        user_id = query.from_user.id
        if user_id in self.two_factor_manager.pending_2fa_tasks:
            task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
            if task_info.get('operation') == 'remove':
                # 请求用户输入密码
                try:
                    progress_msg = task_info['progress_msg']
                    total_files = len(task_info['files'])
                    progress_msg.edit_text(
                        f"{t(user_id, 'delete_2fa_found_files').format(count=total_files)}\n\n"
                        f"{t(user_id, 'delete_2fa_enter_password')}\n\n"
                        f"{t(user_id, 'delete_2fa_enter_desc1')}\n"
                        f"{t(user_id, 'delete_2fa_enter_desc2')}\n"
                        f"{t(user_id, 'delete_2fa_enter_desc3')}\n\n"
                        f"{t(user_id, 'delete_2fa_cancel_hint')}",
                        parse_mode='HTML'
                    )
                    # 设置用户状态为等待输入密码
                    self.db.save_user(user_id, query.from_user.username or "", 
                                    query.from_user.first_name or "", "waiting_remove_2fa_input")
                except Exception as e:
                    print(f"❌ 更新消息失败: {e}")
                    query.answer("❌ 操作失败")
            else:
                query.answer("❌ 操作类型不匹配")
        else:
            query.answer("❌ 没有待处理的任务")
    elif data == "convert_tdata_to_session":
        self.handle_convert_tdata_to_session(query)
    elif data == "convert_session_to_tdata":
        self.handle_convert_session_to_tdata(query)
    elif data == "api_conversion":
        self.handle_api_conversion(query)
    elif data.startswith("classify_") or data == "classify_menu":
        self.handle_classify_callbacks(update, context, query, data)
    elif data == "rename_start":
        self.handle_rename_start(query)
    elif data == "merge_start":
        self.handle_merge_start(query)
    elif data == "merge_continue":
        self.handle_merge_continue(query)
    elif data == "merge_finish":
        self.handle_merge_finish(update, context, query)
    elif data == "merge_cancel":
        self.handle_merge_cancel(query)
    elif data == "cleanup_start":
        self.handle_cleanup_start(query)
    elif data == "cleanup_confirm":
        self.handle_cleanup_confirm(update, context, query)
    elif data == "cleanup_cancel":
        query.answer()
        # Clean up any pending cleanup task
        if user_id in self.pending_cleanup:
            self.cleanup_cleanup_task(user_id)
        self.show_main_menu(update, user_id)
    elif data == "batch_create_start":
        self.handle_batch_create_start(query)
    elif data.startswith("batch_create_"):
        self.handle_batch_create_callbacks(update, context, query, data)
    elif data == "reauthorize_start":
        self.handle_reauthorize_start(query)
    elif data.startswith("reauthorize_") or data.startswith("reauth_"):
        self.handle_reauthorize_callbacks(update, context, query, data)
    elif data == "check_registration_start":
        self.handle_check_registration_start(query)
    elif data.startswith("check_reg_"):
        self.handle_check_registration_callbacks(update, context, query, data)
    elif data == "profile_update_start":
        self.handle_profile_update_start(query)
    elif data.startswith("profile_"):
        self.handle_profile_update_callbacks(update, context, query, data)
    elif data == "check_contact_limit":
        self.handle_check_contact_limit(query)
    elif data == "language_menu":
        # 显示语言选择菜单
        self.show_language_menu(update, user_id)
    elif data.startswith("set_language_"):
        # 设置语言
        query.answer()
        if I18N_AVAILABLE:
            lang = data.replace("set_language_", "")
            set_user_language(user_id, lang)
            # 显示语言切换成功消息并刷新主菜单
            self.show_main_menu(update, user_id)
    elif query.data == "back_to_main":
        self.show_main_menu(update, user_id)
        # 返回主菜单 - 横排2x2布局
        query.answer()
        user = query.from_user
        user_id = user.id
        
        # 如果当前消息是图片消息（来自取消订单），先删除再发送新消息
        message_was_photo = query.message and query.message.photo
        if message_was_photo:
            try:
                query.message.delete()
            except Exception as e:
                logger.warning(f"删除图片消息失败: {e}")
        
        first_name = user.first_name or t(user_id, 'default_user')
        is_member, level, expiry = self.db.check_membership(user_id)
        
        if self.db.is_admin(user_id):
            member_status = t(user_id, 'status_admin')
        elif is_member:
            # 翻译会员等级
            if level == "会员":
                translated_level = t(user_id, 'member_level_member')
            elif level == "管理员":
                translated_level = t(user_id, 'member_level_admin')
            else:
                translated_level = level  # 保留其他未知等级
            member_status = f"🎁 {translated_level}"
        else:
            member_status = t(user_id, 'status_no_member')
        
        # 翻译到期时间
        if expiry == "永久有效":
            expiry = t(user_id, 'expiry_permanent')
        
        proxy_mode_text = t(user_id, 'proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'proxy_mode_local')
        proxy_count_text = t(user_id, 'proxy_count_value').format(count=len(self.proxy_manager.proxies))
        
        welcome_text = f"""

    def handle_help_callback(self, query):
    query.answer()
    help_text = """

    def handle_status_callback(self, query):
    query.answer()
    user_id = query.from_user.id
    
    status_text = f"""

    def handle_user_detail(self, query, target_user_id: int):
    """显示用户详细信息"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    query.answer()
    
    user_info = self.db.get_user_membership_info(target_user_id)
    
    if not user_info:
        self.safe_edit_message(query, f"❌ 找不到用户 {target_user_id}")
        return
    
    # 格式化显示
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    register_time = user_info.get('register_time', '')
    last_active = user_info.get('last_active', '')
    membership_level = user_info.get('membership_level', '')
    expiry_time = user_info.get('expiry_time', '')
    is_admin = user_info.get('is_admin', False)
    
    # 计算活跃度
    activity_status = "🔴 从未活跃"
    if last_active:
        try:
            # Database stores naive datetime strings, compare with naive Beijing time
            last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
            time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
            if time_diff.days == 0:
                activity_status = f"🟢 {time_diff.seconds//3600}小时前活跃"
            elif time_diff.days <= 7:
                activity_status = f"🟡 {time_diff.days}天前活跃"
            else:
                activity_status = f"🔴 {time_diff.days}天前活跃"
        except:
            activity_status = f"🔴 {last_active}"
    
    # 会员状态
    member_status = "❌ 无会员"
    if membership_level and membership_level != "无会员":
        if expiry_time:
            try:
                # Database stores naive datetime strings, compare with naive Beijing time
                expiry_dt = datetime.strptime(expiry_time, '%Y-%m-%d %H:%M:%S')
                if expiry_dt > datetime.now(BEIJING_TZ).replace(tzinfo=None):
                    member_status = f"🎁 {membership_level}（有效至 {expiry_time}）"
                else:
                    member_status = f"⏰ {membership_level}（已过期）"
            except:
                member_status = f"🎁 {membership_level}"
    
    text = f"""

    def handle_grant_membership(self, query, target_user_id: int):
    """授予用户体验会员"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查用户是否存在
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        query.answer("❌ 用户不存在")
        return
    
    # 授予体验会员
    success = self.db.save_membership(target_user_id, "体验会员")
    
    if success:
        query.answer("✅ 体验会员授予成功")
        # 刷新用户详情页面
        self.handle_user_detail(query, target_user_id)
    else:
        query.answer("❌ 授予失败")


    def handle_proxy_panel(self, query):
    """代理面板"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 直接调用刷新代理面板
    self.refresh_proxy_panel(query)


    def handle_file(self, update: Update, context: CallbackContext):
    """处理文件上传"""
    user_id = update.effective_user.id
    document = update.message.document

    if not document:
        self.safe_send_message(update, "❌ 请上传文件")
        return

    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()

        # 放行的状态，新增 waiting_api_file, waiting_rename_file, waiting_merge_files, waiting_cleanup_file, batch_create_upload, reauthorize_upload, registration_check_upload, profile_update_upload, waiting_contact_check_file
        allowed_states = [
            "waiting_file",
            "waiting_convert_tdata",
            "waiting_convert_session",
            "waiting_2fa_file",
            "waiting_api_file",
            "waiting_classify_file",
            "waiting_rename_file",
            "waiting_merge_files",
            "waiting_forget_2fa_file",
            "waiting_add_2fa_file",
            "waiting_remove_2fa_file",
            "waiting_cleanup_file",
            "batch_create_upload",
            "batch_create_names",
            "batch_create_usernames",
            "reauthorize_upload",
            "registration_check_upload",
            "profile_update_upload",
            "waiting_contact_check_file",
        ]
        
        # 添加自定义资料上传状态
        if row and row[0].startswith("profile_custom_upload_"):
            allowed_states.append(row[0])
        
        if not row or row[0] not in allowed_states:
            self.safe_send_message(update, f"❌ {t(user_id, 'error_click_function_button')}")
            return

        user_status = row[0]
    except Exception:
        self.safe_send_message(update, "❌ 系统错误，请重试")
        return
    
    # 文件重命名和账户合并不需要会员权限检查，也不需要ZIP格式检查
    if user_status == "waiting_rename_file":
        self.handle_rename_file_upload(update, context, document)
        return
    elif user_status == "waiting_merge_files":
        self.handle_merge_file_upload(update, context, document)
        return
    
    # 自定义资料上传不需要ZIP格式检查（支持txt和图片文件）
    if user_status.startswith("profile_custom_upload_"):
        field_name = user_status.replace("profile_custom_upload_", "")
        self.handle_profile_custom_file_upload(update, context, user_id, field_name, document)
        return
    
    # 其他功能需要ZIP格式
    if not document.file_name.lower().endswith('.zip'):
        self.safe_send_message(update, t(user_id, 'error_upload_zip_only'))
        return

    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限")
        return

    if document.file_size > 100 * 1024 * 1024:
        self.safe_send_message(update, "❌ 文件过大 (限制100MB)")
        return

    # 根据用户状态选择处理方式
    if user_status == "waiting_file":
        # 异步处理账号检测
        def process_file():
            try:
                asyncio.run(self.process_enhanced_check(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_file] 任务被取消")
            except Exception as e:
                print(f"[process_file] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_file)
        thread.start()

    elif user_status in ["waiting_convert_tdata", "waiting_convert_session"]:
        # 异步处理格式转换
        def process_conversion():
            try:
                asyncio.run(self.process_format_conversion(update, context, document, user_status))
            except asyncio.CancelledError:
                print(f"[process_conversion] 任务被取消")
            except Exception as e:
                print(f"[process_conversion] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_conversion)
        thread.start()

    elif user_status == "waiting_2fa_file":
        # 异步处理2FA密码修改
        def process_2fa():
            try:
                asyncio.run(self.process_2fa_change(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_2fa)
        thread.start()

    elif user_status == "waiting_api_file":
        # 新增：API转换处理
        def process_api_conversion():
            try:
                asyncio.run(self.process_api_conversion(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_api_conversion] 任务被取消")
            except Exception as e:
                print(f"[process_api_conversion] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_api_conversion)
        thread.start()
    elif user_status == "waiting_classify_file":
        # 账号分类处理
        def process_classify():
            try:
                asyncio.run(self.process_classify_stage1(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_classify] 任务被取消")
            except Exception as e:
                print(f"[process_classify] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_classify, daemon=True)
        thread.start()
    elif user_status == "waiting_forget_2fa_file":
        # 忘记2FA处理
        def process_forget_2fa():
            try:
                asyncio.run(self.process_forget_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_forget_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_forget_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_forget_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_add_2fa_file":
        # 添加2FA处理
        def process_add_2fa():
            try:
                asyncio.run(self.process_add_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_add_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_add_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_add_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_remove_2fa_file":
        # 删除2FA处理
        def process_remove_2fa():
            try:
                asyncio.run(self.process_remove_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_remove_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_remove_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_remove_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_cleanup_file":
        # 一键清理处理
        def process_cleanup():
            try:
                asyncio.run(self.process_cleanup(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_cleanup] 任务被取消")
            except Exception as e:
                print(f"[process_cleanup] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_cleanup, daemon=True)
        thread.start()
    elif user_status == "batch_create_upload":
        # 批量创建文件处理
        def process_batch_create():
            try:
                asyncio.run(self.process_batch_create_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_batch_create] 任务被取消")
            except Exception as e:
                print(f"[process_batch_create] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_batch_create, daemon=True)
        thread.start()
    elif user_status == "batch_create_names":
        # 处理群组名称文件上传
        self.process_batch_create_names_file(update, context, document, user_id)
    elif user_status == "batch_create_usernames":
        # 处理用户名文件上传
        self.process_batch_create_usernames_file(update, context, document, user_id)
    elif user_status == "reauthorize_upload":
        # 重新授权文件处理
        def process_reauthorize():
            try:
                asyncio.run(self.process_reauthorize_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_reauthorize] 任务被取消")
            except Exception as e:
                print(f"[process_reauthorize] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_reauthorize, daemon=True)
        thread.start()
    elif user_status == "registration_check_upload":
        # 查询注册时间文件处理
        def process_registration_check():
            try:
                asyncio.run(self.process_registration_check_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_registration_check] 任务被取消")
            except Exception as e:
                print(f"[process_registration_check] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_registration_check, daemon=True)
        thread.start()
    elif user_status == "profile_update_upload":
        # 资料修改文件处理
        def process_profile_update():
            try:
                asyncio.run(self.process_profile_update(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_profile_update] 任务被取消")
            except Exception as e:
                print(f"[process_profile_update] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_profile_update, daemon=True)
        thread.start()
    elif user_status == "waiting_contact_check_file":
        # 通讯录限制检测处理
        def process_contact_limit_check():
            try:
                asyncio.run(self.process_contact_limit_check(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_contact_limit_check] 任务被取消")
            except Exception as e:
                print(f"[process_contact_limit_check] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_contact_limit_check, daemon=True)
        thread.start()
    elif user_status.startswith("profile_custom_upload_"):
        # 自定义资料文件上传
        field_name = user_status.replace("profile_custom_upload_", "")
        self.handle_profile_custom_file_upload(update, context, user_id, field_name, document)
    # 清空用户状态
    self.db.save_user(
        user_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
        ""
    )


async def process_api_conversion(self, update, context, document):
    """API格式转换 - 阶段1：解析文件并询问网页展示的2FA"""
    user_id = update.effective_user.id
    start_time = time.time()
    task_id = f"{user_id}_{int(start_time)}"

    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'api_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return

    temp_zip = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="temp_api_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)

        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, task_id)
        if not files:
            try:
                progress_msg.edit_text("❌ <b>未找到有效文件</b>\n\n请确保ZIP包含Session或TData格式的文件", parse_mode='HTML')
            except:
                pass
            return

        total_files = len(files)
        file_type_upper = file_type.upper()
        file_type_key = 'api_type_session' if file_type.lower() == 'session' else 'api_type_tdata'
        
        try:
            progress_msg.edit_text(
                f"{t(user_id, 'api_found_accounts').format(count=total_files)}\n"
                f"{t(user_id, file_type_key)}\n\n"
                f"{t(user_id, 'api_enter_2fa')}\n"
                f"{t(user_id, 'api_2fa_example')}\n"
                f"{t(user_id, 'api_2fa_skip')}\n\n"
                f"{t(user_id, 'api_2fa_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass

        # 记录待处理任务，等待用户输入2FA
        self.pending_api_tasks[user_id] = {
            "files": files,
            "file_type": file_type,
            "extract_dir": extract_dir,
            "task_id": task_id,
            "progress_msg": progress_msg,
            "start_time": start_time,
            "temp_zip": temp_zip
        }
    except Exception as e:
        print(f"❌ API阶段1失败: {e}")
        try:
            progress_msg.edit_text(f"❌ 失败: {str(e)}", parse_mode='HTML')
        except:
            pass
        if temp_zip and os.path.exists(temp_zip):
            try:
                shutil.rmtree(os.path.dirname(temp_zip), ignore_errors=True)
            except:
                pass
async def continue_api_conversion(self, update, context, user_id: int, two_fa_input: Optional[str]):
    """API格式转换 - 阶段2：执行转换并生成仅含链接的TXT"""
    result_files = []
    task = self.pending_api_tasks.get(user_id)
    if not task:
        self.safe_send_message(update, "❌ 没有待处理的API转换任务")
        return

    files = task["files"]
    file_type = task["file_type"]
    extract_dir = task["extract_dir"]
    task_id = task["task_id"]
    progress_msg = task["progress_msg"]
    temp_zip = task["temp_zip"]
    start_time = task["start_time"]

    # Check if user wants to skip (supports both Chinese and English)
    override_two_fa = None if (not two_fa_input or two_fa_input.strip().lower() in [t(user_id, 'api_skip').lower(), "跳过", "skip"]) else two_fa_input.strip()

    # 更新提示
    try:
        tip = f"🔄 <b>{t(user_id, 'api_converting')}</b>\n\n"
        if override_two_fa:
            tip += f"🔐 {t(user_id, 'api_2fa_mode_manual')}: <code>{override_two_fa}</code>\n"
        else:
            tip += f"🔐 {t(user_id, 'api_2fa_mode_auto')}\n"
        progress_msg.edit_text(tip, parse_mode='HTML')
    except:
        pass

    try:
        # =================== 变量初始化 ===================
        total_files = len(files)
        api_accounts = []
        failed_accounts = []
        failure_reasons = {}
        
        # =================== 性能参数计算 ===================  
        max_concurrent = 15 if total_files > 100 else 10 if total_files > 50 else 5
        batch_size = min(20, max(5, total_files // 5))  # 统一的批次计算
        semaphore = asyncio.Semaphore(max_concurrent)
        
        print(f"🚀 并发转换参数: 文件={total_files}, 批次={batch_size}, 并发={max_concurrent}")
        
        file_type_key = 'api_file_type_session' if file_type.lower() == 'session' else 'api_file_type_tdata'
        mode_2fa_key = 'api_2fa_mode_manual' if override_two_fa else 'api_2fa_mode_auto'
        
        # =================== 进度提示 ===================
        try:
            progress_msg.edit_text(
                f"🔄 <b>{t(user_id, 'api_converting')}</b>\n\n"
                f"📊 {t(user_id, 'api_stat_total').format(count=total_files)}\n"
                f"{t(user_id, file_type_key)}\n"
                f"{t(user_id, mode_2fa_key)}\n"
                f"🚀 并发数: {max_concurrent} | 批次: {batch_size}\n\n"
                f"正在处理...",
                parse_mode='HTML'
            )
        except:
            pass

        # =================== 并发批处理循环 ===================
        for i in range(0, total_files, batch_size):
            batch_files = files[i:i + batch_size]
            
            # 更新进度
            try:
                processed = i
                progress = int(processed / total_files * 100)
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 and processed > 0 else 0
                remaining = (total_files - processed) / speed if speed > 0 else 0
                
                file_type_key = 'api_file_type_session' if file_type.lower() == 'session' else 'api_file_type_tdata'
                mode_2fa_key = 'api_2fa_mode_manual' if override_two_fa else 'api_2fa_mode_auto'
                
                # 生成失败原因统计
                failure_stats = ""
                if failure_reasons:
                    failure_stats = f"\n\n<b>{t(user_id, 'api_failure_stats')}</b>\n"
                    for reason, count in failure_reasons.items():
                        # 翻译失败原因
                        reason_key_map = {
                            "转换失败": "api_failure_reason_conversion_failed",
                            "未授权": "api_failure_reason_unauthorized",
                            "连接超时": "api_failure_reason_timeout",
                            "转换异常": "api_failure_reason_conversion_error",
                            "并发异常": "api_failure_reason_concurrent_error",
                            "文件不存在": "api_failure_reason_file_not_exist",
                            "文件损坏": "api_failure_reason_file_corrupted",
                            "目录不存在": "api_failure_reason_dir_not_exist",
                            "未知错误": "api_failure_reason_unknown",
                        }
                        reason_key = reason_key_map.get(reason, None)
                        translated_reason = t(user_id, reason_key) if reason_key else reason
                        failure_stats += f"• {translated_reason}: {count}\n"
                
                progress_text = f"""

    def handle_text(self, update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    # 检查广播消息输入
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            user_status = row[0]
            
            if user_status == "waiting_broadcast_title":
                self.handle_broadcast_title_input(update, context, user_id, text)
                return
            elif user_status == "waiting_broadcast_content":
                self.handle_broadcast_content_input(update, context, user_id, text)
                return
            elif user_status == "waiting_broadcast_buttons":
                self.handle_broadcast_buttons_input(update, context, user_id, text)
                return
            # VIP会员相关状态
            elif user_status == "waiting_redeem_code":
                self.handle_redeem_code_input(update, user_id, text)
                return
            elif user_status == "waiting_manual_user":
                self.handle_manual_user_input(update, user_id, text)
                return
            elif user_status == "waiting_revoke_user":
                self.handle_revoke_user_input(update, user_id, text)
                return
            elif user_status == "waiting_admin_query_date":
                self.handle_admin_date_query_result(update, user_id, text)
                return
            elif user_status == "waiting_admin_query_user":
                self.handle_admin_user_query_result(update, user_id, text)
                return
            elif user_status == "waiting_rename_newname":
                self.handle_rename_newname_input(update, context, user_id, text)
                return
            elif user_status == "waiting_add_2fa_input":
                self.handle_add_2fa_input(update, context, user_id, text)
                return
            elif user_status == "waiting_remove_2fa_input":
                # 处理删除2FA的手动密码输入
                if user_id in self.two_factor_manager.pending_2fa_tasks:
                    task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
                    if task_info.get('operation') == 'remove':
                        old_password = text.strip()
                        print(f"🗑️ 用户 {user_id} 输入删除2FA密码")
                        # 异步处理密码删除
                        def process_remove():
                            asyncio.run(self.complete_remove_2fa(update, context, user_id, old_password))
                        threading.Thread(target=process_remove, daemon=True).start()
                    else:
                        self.safe_send_message(update, "❌ 操作类型不匹配")
                else:
                    self.safe_send_message(update, "❌ 没有待处理的删除2FA任务")
                return
            elif user_status == "batch_create_count":
                self.handle_batch_create_count_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_admin":
                self.handle_batch_create_admin_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_names":
                self.handle_batch_create_names_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_usernames":
                self.handle_batch_create_usernames_input(update, context, user_id, text)
                return
            elif user_status == "reauthorize_old_password":
                self.handle_reauthorize_old_password_input(update, context, user_id, text)
                return
            elif user_status == "reauthorize_new_password":
                self.handle_reauthorize_new_password_input(update, context, user_id, text)
                return
            # 自定义资料输入状态
            elif user_status.startswith("profile_custom_input_"):
                field_name = user_status.replace("profile_custom_input_", "")
                self.handle_profile_custom_text_input(update, context, user_id, field_name, text)
                return
    except Exception as e:
        print(f"❌ 检查广播状态失败: {e}")
    
    # 处理添加2FA等待的密码输入（使用任务字典检查，不依赖数据库状态）
    if user_id in getattr(self, "pending_add_2fa_tasks", {}):
        self.handle_add_2fa_input(update, context, user_id, text)
        return
    
    # 新增：处理 API 转换等待的 2FA 输入
    if user_id in getattr(self, "pending_api_tasks", {}):
        two_fa_input = (text or "").strip()
        def go_next():
            asyncio.run(self.continue_api_conversion(update, context, user_id, two_fa_input))
        threading.Thread(target=go_next, daemon=True).start()
        return        
    # 检查是否是2FA密码输入
    if user_id in self.two_factor_manager.pending_2fa_tasks:
        # 用户正在等待输入密码
        parts = text.strip().split()
        
        if len(parts) == 1:
            # 格式1：仅新密码，让系统自动检测旧密码
            new_password = parts[0]
            old_password = None
            
            print(f"🔐 用户 {user_id} 输入新密码（自动检测旧密码）")
            
            # 异步处理密码修改
            def process_password_change():
                asyncio.run(self.complete_2fa_change_with_passwords(update, context, old_password, new_password))
            
            thread = threading.Thread(target=process_password_change)
            thread.start()
            
        elif len(parts) == 2:
            # 格式2：旧密码 新密码
            old_password = parts[0]
            new_password = parts[1]
            
            print(f"🔐 用户 {user_id} 输入旧密码和新密码")
            
            # 异步处理密码修改
            def process_password_change():
                asyncio.run(self.complete_2fa_change_with_passwords(update, context, old_password, new_password))
            
            thread = threading.Thread(target=process_password_change)
            thread.start()
            
        else:
            # 格式错误
            self.safe_send_message(
                update,
                "❌ <b>格式错误</b>\n\n"
                "请使用以下格式之一：\n\n"
                "1️⃣ 仅新密码（推荐）\n"
                "<code>NewPassword123</code>\n\n"
                "2️⃣ 旧密码 新密码\n"
                "<code>OldPass456 NewPassword123</code>\n\n"
                "两个密码之间用空格分隔",
                'HTML'
            )
        
        return
    
    # 检查是否是账号分类数量输入
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            user_status = row[0]
            
            # 单个数量拆分
            if user_status == "waiting_classify_qty_single":
                try:
                    qty = int(text.strip())
                    if qty <= 0:
                        self.safe_send_message(update, "❌ 请输入大于0的正整数")
                        return
                    
                    # 处理单个数量拆分
                    def process_single_qty():
                        asyncio.run(self._classify_split_single_qty(update, context, user_id, qty))
                    threading.Thread(target=process_single_qty, daemon=True).start()
                    return
                except ValueError:
                    self.safe_send_message(update, "❌ 请输入有效的正整数")
                    return
            
            # 多个数量拆分
            elif user_status == "waiting_classify_qty_multi":
                try:
                    parts = text.strip().split()
                    quantities = [int(p) for p in parts]
                    if any(q <= 0 for q in quantities):
                        self.safe_send_message(update, "❌ 所有数量必须大于0")
                        return
                    
                    # 处理多个数量拆分
                    def process_multi_qty():
                        asyncio.run(self._classify_split_multi_qty(update, context, user_id, quantities))
                    threading.Thread(target=process_multi_qty, daemon=True).start()
                    return
                except ValueError:
                    self.safe_send_message(update, "❌ 请输入有效的正整数，用空格分隔\n例如: 10 20 30")
                    return
    except Exception as e:
        print(f"❌ 检查分类状态失败: {e}")
    # 管理员搜索用户
    if user_status == "waiting_admin_search":
        if not self.db.is_admin(user_id):
            self.safe_send_message(update, "❌ 权限不足")
            return
        
        search_query = text.strip()
        if len(search_query) < 2:
            self.safe_send_message(update, "❌ 搜索关键词太短，请至少输入2个字符")
            return
        
        # 执行搜索
        search_results = self.db.search_user(search_query)
        
        if not search_results:
            self.safe_send_message(update, f"🔍 未找到匹配 '{search_query}' 的用户")
            # 清空状态
            self.db.save_user(user_id, update.effective_user.username or "", update.effective_user.first_name or "", "")
            return
        
        # 显示搜索结果
        result_text = f"🔍 <b>搜索结果：'{search_query}'</b>\n\n"
        
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(search_results[:10], 1):
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "🎁" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"用户{uid}"
            if len(display_name) > 20:
                display_name = display_name[:20] + "..."
            
            result_text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code>\n"
            result_text += f"   👤 {display_name}\n"
            if username:
                result_text += f"   📱 @{username}\n"
            
            # 活跃状态
            if last_active:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
                    if time_diff.days == 0:
                        result_text += f"   🕒 {time_diff.seconds//3600}小时前活跃\n"
                    else:
                        result_text += f"   🕒 {time_diff.days}天前活跃\n"
                except:
                    result_text += f"   🕒 {last_active}\n"
            else:
                result_text += f"   🕒 从未活跃\n"
            
            result_text += "\n"
        
        if len(search_results) > 10:
            result_text += f"\n... 还有 {len(search_results) - 10} 个结果未显示"
        
        # 创建详情按钮（只显示前5个用户的详情按钮）
        buttons = []
        for i, (uid, username, first_name, _, _, _) in enumerate(search_results[:5]):
            display_name = first_name or username or f"用户{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            buttons.append([InlineKeyboardButton(f"📋 {display_name} 详情", callback_data=f"user_detail_{uid}")])
        
        buttons.append([InlineKeyboardButton("🔙 返回用户管理", callback_data="admin_users")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        self.safe_send_message(update, result_text, 'HTML', keyboard)
        
        # 清空状态
        self.db.save_user(user_id, update.effective_user.username or "", update.effective_user.first_name or "", "")
        return        
    # 其他文本消息的处理
    text_lower = text.lower()
    if any(word in text_lower for word in ["你好", "hello", "hi"]):
        self.safe_send_message(update, "👋 你好！发送 /start 开始检测")
    elif "帮助" in text_lower or "help" in text_lower:
        self.safe_send_message(update, "📖 发送 /help 查看帮助")

# ================================
# 账号分类功能
# ================================


    def classify_command(self, update: Update, context: CallbackContext):
    """账号分类命令入口"""
    user_id = update.effective_user.id
    
    # 权限检查
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限才能使用账号分类功能")
        return
    
    if not CLASSIFY_AVAILABLE or not self.classifier:
        self.safe_send_message(update, "❌ 账号分类功能不可用\n\n请检查 account_classifier.py 模块和 phonenumbers 库是否正确安装")
        return
    
    self.handle_classify_menu(update.callback_query if hasattr(update, 'callback_query') else None, update)


    def handle_classify_menu(self, query, update=None):
    """显示账号分类菜单"""
    if update is None:
        update = query.message if query else None
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    # 权限检查
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        if query:
            self.safe_edit_message(query, "❌ 需要会员权限")
        else:
            self.safe_send_message(update, "❌ 需要会员权限")
        return
    
    if not CLASSIFY_AVAILABLE or not self.classifier:
        msg = "❌ 账号分类功能不可用\n\n请检查依赖库是否正确安装"
        if query:
            self.safe_edit_message(query, msg)
        else:
            self.safe_send_message(update, msg)
        return
    
    text = f"""

    def on_back_to_main(self, update: Update, context: CallbackContext):
    """处理"返回主菜单"按钮"""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        
        try:
            query.answer()
        except:
            pass
        
        # 清除用户状态 - 重置为空状态
        try:
            self.db.save_user(user_id, query.from_user.username or "", 
                            query.from_user.first_name or "", "")
        except Exception as e:
            logger.warning(f"清除用户状态失败: {e}")
        
        # 使用统一方法渲染主菜单（包含"📦 账号分类"按钮）
        self.show_main_menu(update, user_id)

    def _classify_buttons_split_type(self, user_id: int) -> InlineKeyboardMarkup:
    """生成拆分方式选择按钮"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, 'split_btn_country'), callback_data="classify_split_country")],
        [InlineKeyboardButton(t(user_id, 'split_btn_quantity'), callback_data="classify_split_quantity")],
        [InlineKeyboardButton(t(user_id, 'split_btn_cancel'), callback_data="back_to_main")]
    ])


    def _classify_buttons_qty_mode(self, user_id: int) -> InlineKeyboardMarkup:
    """生成数量模式选择按钮"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, 'split_btn_single'), callback_data="classify_qty_single")],
        [InlineKeyboardButton(t(user_id, 'split_btn_multiple'), callback_data="classify_qty_multi")],
        [InlineKeyboardButton(t(user_id, 'split_btn_back'), callback_data="classify_menu")]
    ])


    def handle_classify_callbacks(self, update, context, query, data):
    """处理分类相关的回调"""
    user_id = query.from_user.id
    
    if data == "classify_menu":
        self.handle_classify_menu(query)
    
    elif data == "classify_start":
        # 设置状态并提示上传
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_file"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_upload_prompt')}</b>\n\n"
                f"{t(user_id, 'split_formats')}\n"
                f"{t(user_id, 'split_format1')}\n"
                f"{t(user_id, 'split_format2')}\n"
                f"{t(user_id, 'split_format3')}\n\n"
                f"{t(user_id, 'split_size_limit')}\n"
                f"{t(user_id, 'split_timeout')}",
                parse_mode='HTML',
                reply_markup=get_back_to_menu_keyboard(user_id)
            )
        except:
            pass
    
    elif data == "classify_split_country":
        # 按国家拆分
        if user_id not in self.pending_classify_tasks:
            query.answer("❌ 任务已过期")
            return
        
        task = self.pending_classify_tasks[user_id]
        metas = task['metas']
        task_id = task['task_id']
        progress_msg = task['progress_msg']
        
        query.answer()
        
        def process_country():
            asyncio.run(self._classify_split_by_country(update, context, user_id))
        threading.Thread(target=process_country, daemon=True).start()
    
    elif data == "classify_split_quantity":
        # 按数量拆分 - 询问模式
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_quantity_mode')}</b>\n\n"
                f"<b>{t(user_id, 'split_single_quantity')}</b>\n"
                f"   {t(user_id, 'split_single_quantity_desc')}\n\n"
                f"<b>{t(user_id, 'split_multiple_quantity')}</b>\n"
                f"   {t(user_id, 'split_multiple_quantity_desc')}",
                parse_mode='HTML',
                reply_markup=self._classify_buttons_qty_mode(user_id)
            )
        except:
            pass
    
    elif data == "classify_qty_single":
        # 单个数量模式 - 等待输入
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_qty_single"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_enter_single')}</b>\n\n"
                f"{t(user_id, 'split_enter_single_example')}: <code>10</code>\n\n"
                f"{t(user_id, 'split_enter_single_desc')}\n"
                f"{t(user_id, 'split_enter_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass
    
    elif data == "classify_qty_multi":
        # 多个数量模式 - 等待输入
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_qty_multi"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_enter_multiple')}</b>\n\n"
                f"{t(user_id, 'split_enter_multiple_example')}: <code>10 20 30</code>\n\n"
                f"{t(user_id, 'split_enter_multiple_desc')}\n"
                f"{t(user_id, 'split_enter_multiple_remainder')}\n"
                f"{t(user_id, 'split_enter_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass

async def _classify_split_by_country(self, update, context, user_id):
    """按国家拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_country')}</b>\n\n{t(user_id, 'split_processing_country_desc')}",
                parse_mode='HTML'
            )
        except:
            pass
        
        bundles = self.classifier.split_by_country(metas, out_dir, t_func=lambda key: t(user_id, key))
        
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
            f"{t(user_id, 'split_result_total').format(count=len(metas))}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"{t(user_id, 'split_result_method_country')}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 国家拆分失败: {e}")
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

# ================================
# VIP会员功能
# ================================


    def handle_usdt_plan_select(self, query, plan_id: str):
    """处理套餐选择"""
    user_id = query.from_user.id
    query.answer()
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentConfig, OrderManager, PaymentDatabase, QRCodeGenerator
        from io import BytesIO
        
        # 创建订单
        payment_db = PaymentDatabase()
        order_manager = OrderManager(payment_db)
        
        order = order_manager.create_payment_order(user_id, plan_id)
        
        if not order:
            error_create_failed = t(user_id, 'payment_error_create_failed')
            self.safe_edit_message(query, error_create_failed, 'HTML')
            return
        
        # 获取套餐信息
        plan = PaymentConfig.PAYMENT_PLANS.get(plan_id, {})
        days = plan.get("days", 0)
        
        # 获取套餐名称 - 使用 i18n
        plan_name_key_map = {
            'plan_7d': 'payment_plan_name_7d',
            'plan_30d': 'payment_plan_name_30d',
            'plan_120d': 'payment_plan_name_120d',
            'plan_365d': 'payment_plan_name_365d',
        }
        plan_name_key = plan_name_key_map.get(plan_id, 'payment_plan_name_7d')
        plan_name = t(user_id, plan_name_key)
        
        # 生成二维码
        qr_bytes = QRCodeGenerator.generate_payment_qr(
            PaymentConfig.WALLET_ADDRESS,
            order.amount
        )
        
        # 计算过期时间
        from datetime import datetime, timezone, timedelta
        BEIJING_TZ = timezone(timedelta(hours=8))
        now = datetime.now(BEIJING_TZ)
        expires_at = order.expires_at.replace(tzinfo=BEIJING_TZ)
        
        # 计算剩余时间（分钟和秒）
        remaining_seconds = (expires_at - now).total_seconds()
        remaining_minutes = max(0, int(remaining_seconds // 60))
        remaining_secs = max(0, int(remaining_seconds % 60))
        
        # 使用 i18n 构建支付信息
        order_info_title = t(user_id, 'payment_order_info_title')
        order_id_label = t(user_id, 'payment_order_id')
        plan_label = t(user_id, 'payment_plan')
        days_label = t(user_id, 'payment_days')
        amount_label = t(user_id, 'payment_amount')
        valid_time_label = t(user_id, 'payment_valid_time')
        minutes_label = t(user_id, 'payment_minutes')
        seconds_label = t(user_id, 'payment_seconds')
        wallet_addr_label = t(user_id, 'payment_wallet_address')
        addr_click_copy = t(user_id, 'payment_address_click_copy')
        important_notice = t(user_id, 'payment_important_notice')
        notice_1 = t(user_id, 'payment_notice_1')
        notice_2 = t(user_id, 'payment_notice_2')
        notice_3 = t(user_id, 'payment_notice_3')
        notice_4 = t(user_id, 'payment_notice_4')
        scan_qr = t(user_id, 'payment_scan_qr')
        scan_desc = t(user_id, 'payment_scan_desc')
        
        # 发送二维码和支付信息
        caption = f"""

    def handle_cancel_order(self, query, order_id: str):
    """处理取消订单"""
    user_id = query.from_user.id
    query.answer()
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderManager, OrderStatus
        
        payment_db = PaymentDatabase()
        order_manager = OrderManager(payment_db)
        
        # 获取订单信息以验证权限
        order = payment_db.get_order(order_id)
        
        if not order:
            error_not_found = t(user_id, 'payment_error_not_found')
            query.answer(error_not_found, show_alert=True)
            return
        
        if order.user_id != user_id:
            query.answer("❌ 无权操作此订单", show_alert=True)
            return
        
        if order.status.value != 'pending':
            query.answer(f"❌ 订单状态为 {order.status.value}，无法取消", show_alert=True)
            return
        
        # 取消订单
        success = order_manager.cancel_order(order_id)
        
        if success:
            order_cancelled = t(user_id, 'payment_order_cancelled')
            query.answer(order_cancelled, show_alert=True)
            
            # 删除原订单消息（使用保存的 message_id）
            try:
                message_id = payment_db.get_order_message_id(order_id)
                if message_id:
                    query.bot.delete_message(chat_id=user_id, message_id=message_id)
                    logger.info(f"✅ 已删除订单消息: {message_id}")
            except Exception as e:
                logger.warning(f"删除订单消息失败: {e}")
            
            # 同时尝试删除当前回调消息
            try:
                query.message.delete()
            except Exception as e:
                logger.warning(f"删除当前消息失败: {e}")
            
            # 发送新的纯文本消息 - 使用 i18n
            try:
                from telegram import Bot
                bot = query.bot if hasattr(query, 'bot') else Bot(token=os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"))
                
                cancelled_title = t(user_id, 'payment_order_cancelled_title')
                order_id_label = t(user_id, 'payment_order_id')
                status_label = t(user_id, 'payment_status')
                cancelled_status = t(user_id, 'payment_order_cancelled_status')
                repurchase_hint = t(user_id, 'payment_repurchase_hint')
                repurchase_btn = t(user_id, 'btn_repurchase')
                back_main_btn = t(user_id, 'btn_back_main_menu')
                
                text = f"""

    def handle_redeem_code_input(self, update, user_id: int, code: str):
    """处理用户输入的兑换码"""
    # 清除状态
    self.db.save_user(user_id, "", "", "")
    
    # 验证兑换码
    code = code.strip()
    if len(code) > 10:
        self.safe_send_message(update, f"❌ {t(user_id, 'redeem_input_prompt')}")
        return
    
    # 执行兑换
    success, message, days = self.db.redeem_code(user_id, code)
    
    if success:
        # 获取新的会员状态
        is_member, level, expiry = self.db.check_membership(user_id)
        
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        
        text = f"""

    def handle_manual_user_input(self, update, admin_id: int, text: str):
    """处理管理员输入的用户信息"""
    # 清除状态
    self.db.save_user(admin_id, "", "", "")
    
    # 解析用户输入
    text = text.strip()
    target_user_id = None
    
    # 尝试作为用户ID解析
    if text.isdigit():
        target_user_id = int(text)
    else:
        # 尝试作为用户名解析
        username = text.replace("@", "")
        target_user_id = self.db.get_user_id_by_username(username)
    
    if not target_user_id:
        self.safe_send_message(
            update,
            "❌ <b>用户不存在</b>\n\n"
            "该用户未与机器人交互过，请确认：\n"
            "• 用户ID或用户名正确\n"
            "• 用户已发送过 /start 命令",
            'HTML'
        )
        return
    
    # 获取用户信息
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        self.safe_send_message(
            update,
            "❌ <b>用户不存在</b>\n\n"
            "该用户未与机器人交互过",
            'HTML'
        )
        return
    
    # 保存到待处理列表
    self.pending_manual_open[admin_id] = target_user_id
    
    # 获取用户会员信息
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    if is_member:
        member_status = f"💎 {level}\n• 到期: {expiry}"
    else:
        member_status = "❌ 暂无会员"
    
    text = f"""

    def handle_revoke_user_input(self, update, admin_id: int, text: str):
    """处理管理员输入的要撤销的用户信息"""
    # 清除状态
    self.db.save_user(admin_id, "", "", "")
    
    # 解析用户输入
    text = text.strip()
    target_user_id = None
    
    # 尝试作为用户ID解析
    if text.isdigit():
        target_user_id = int(text)
    else:
        # 尝试作为用户名解析
        username = text.replace("@", "")
        user_row = self.db.get_user_by_username(username)
        if user_row:
            target_user_id = user_row[0]
    
    if not target_user_id:
        self.safe_send_message(
            update,
            "❌ <b>未找到该用户</b>\n\n"
            "未找到该用户，请确认对方已与机器人对话入库",
            'HTML'
        )
        return
    
    # 获取用户信息
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        self.safe_send_message(
            update,
            "❌ <b>未找到该用户</b>\n\n"
            "未找到该用户，请确认对方已与机器人对话入库",
            'HTML'
        )
        return
    
    # 获取用户会员信息
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    if is_member:
        member_status = f"💎 {level}\n• 到期时间: {expiry}"
    else:
        member_status = "❌ 暂无会员"
    
    text = f"""

    def show_target_selection(self, update, context, user_id):
    """显示目标用户选择"""
    if user_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[user_id]
    task['step'] = 'target'
    
    # 更新状态
    self.db.save_user(user_id, "", "", "")
    
    # 获取各类用户数量
    all_users = len(self.db.get_target_users('all'))
    members = len(self.db.get_target_users('members'))
    active_7d = len(self.db.get_target_users('active_7d'))
    new_7d = len(self.db.get_target_users('new_7d'))
    
    text = f"""

    def extract_phone_from_json(self, json_path: str) -> Optional[str]:
    """从JSON文件中提取手机号"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            phone = data.get('phone', '')
            if phone:
                # 清理手机号格式：移除+号和其他非数字字符
                phone_clean = ''.join(c for c in phone if c.isdigit())
                if phone_clean and len(phone_clean) >= 10:
                    return phone_clean
    except Exception as e:
        print(f"⚠️ 从JSON提取手机号失败 {json_path}: {e}")
    return None


    def extract_phone_from_tdata_path(self, account_root: str, tdata_dir_name: str) -> Optional[str]:
    """从TData目录路径中提取手机号"""
    try:
        # 方法1: 检查tdata父目录名是否是手机号
        parent_dir = os.path.basename(account_root)
        phone_clean = parent_dir.lstrip('+')
        if phone_clean.isdigit() and len(phone_clean) >= 10:
            return phone_clean
        
        # 方法2: 检查account_root的上级目录
        path_parts = account_root.split(os.sep)
        for part in reversed(path_parts):
            if not part:
                continue
            phone_clean = part.lstrip('+')
            if phone_clean.isdigit() and len(phone_clean) >= 10:
                return phone_clean
    except Exception as e:
        print(f"⚠️ 从TData路径提取手机号失败: {e}")
    return None

async def process_merge_files(self, update, context, user_id: int):
    """处理账户文件合并 - 解压所有ZIP并递归扫描"""
    if user_id not in self.pending_merge:
        return
    
    task = self.pending_merge[user_id]
    temp_dir = task['temp_dir']
    files = task['files']
    
    # 创建解压工作目录
    extract_dir = os.path.join(temp_dir, 'extracted')
    os.makedirs(extract_dir, exist_ok=True)
    
    # 第一步：解压所有ZIP文件
    for filename in files:
        file_path = os.path.join(temp_dir, filename)
        if filename.lower().endswith('.zip'):
            try:
                # 为每个ZIP创建单独的子目录
                zip_extract_dir = os.path.join(extract_dir, filename.replace('.zip', ''))
                os.makedirs(zip_extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(zip_extract_dir)
            except Exception as e:
                print(f"❌ 解压失败 {filename}: {e}")
    
    # 第二步：递归扫描所有解压后的内容 - 使用统一扫描函数
    print("📂 开始扫描账号...")
    
    # 使用统一的 tdata 扫描函数
    tdata_accounts_unified = scan_tdata_accounts(extract_dir)
    
    # 转换为原有格式 (account_root, tdata_dir_name)
    tdata_accounts = []
    for account in tdata_accounts_unified:
        account_root = account['account_path']
        tdata_path_abs = account['tdata_path']
        # 计算 tdata 相对于账号根目录的路径（空字符串表示 tdata 就是账号根目录）
        if tdata_path_abs == account_root:
            tdata_dir_name = ''
        else:
            tdata_dir_name = os.path.relpath(tdata_path_abs, account_root)
        tdata_accounts.append((account_root, tdata_dir_name))
        print(f"📂 找到TData账号: {account['phone']} -> {tdata_path_abs}")
    
    # 扫描Session文件
    session_json_pairs = []  # 存储 Session+JSON 配对
    
    def scan_sessions(dir_path):
        """递归扫描Session文件"""
        try:
            for root, dirs, filenames in os.walk(dir_path):
                # 检查当前目录中的 Session 文件 (支持纯Session或Session+JSON配对)
                session_files = {}
                json_files = {}
                
                for fname in filenames:
                    if fname.lower().endswith('.session'):
                        # 过滤系统文件
                        if fname == 'tdata.session' or fname.startswith('batch_validate_') or fname.startswith('temp_') or fname.startswith('user_'):
                            continue
                        basename = fname[:-8]  # 去掉 .session
                        session_files[basename] = os.path.join(root, fname)
                    elif fname.lower().endswith('.json'):
                        basename = fname[:-5]  # 去掉 .json
                        json_files[basename] = os.path.join(root, fname)
                
                # 添加所有session文件，优先使用配对的JSON（如果有）
                # 元组格式: (session_path, json_path, basename) 其中 json_path 可以为 None
                for basename in session_files.keys():
                    session_path = session_files[basename]
                    json_path = json_files.get(basename, None)  # JSON可选，可能为None
                    session_json_pairs.append((session_path, json_path, basename))
        except Exception as e:
            print(f"❌ 扫描Session文件失败 {dir_path}: {e}")
    
    # 扫描所有Session文件
    scan_sessions(extract_dir)
    print(f"📱 找到 {len(session_json_pairs)} 个Session文件")
    
    # 第三步：提取手机号并去重 - 同时追踪重复项
    # 为TData账户提取手机号
    tdata_with_phones = {}  # phone -> (account_root, tdata_dir_name)
    tdata_without_phones = []  # 没有手机号的账户
    tdata_duplicates = []  # 重复的TData账户: [(phone, account_root, tdata_dir_name), ...]
    
    for account_root, tdata_dir_name in tdata_accounts:
        phone = self.extract_phone_from_tdata_path(account_root, tdata_dir_name)
        if phone:
            # 去重：如果手机号已存在，保留第一个，将重复的添加到duplicates
            if phone not in tdata_with_phones:
                tdata_with_phones[phone] = (account_root, tdata_dir_name)
            else:
                print(f"⚠️ 发现重复TData账户，手机号: {phone}，将单独打包")
                tdata_duplicates.append((phone, account_root, tdata_dir_name))
        else:
            tdata_without_phones.append((account_root, tdata_dir_name))
    
    # 为Session文件提取手机号 (支持纯Session或Session+JSON配对)
    session_json_with_phones = {}  # phone -> (session_path, json_path)
    session_json_duplicates = []  # 重复的Session文件: [(phone, session_path, json_path), ...]
    
    for session_path, json_path, basename in session_json_pairs:
        # 尝试从JSON提取手机号（如果JSON存在）
        phone = None
        if json_path:
            phone = self.extract_phone_from_json(json_path)
        
        if phone:
            # 去重：如果手机号已存在，保留第一个，将重复的添加到duplicates
            if phone not in session_json_with_phones:
                session_json_with_phones[phone] = (session_path, json_path)
            else:
                print(f"⚠️ 发现重复Session，手机号: {phone}，将单独打包")
                session_json_duplicates.append((phone, session_path, json_path))
        else:
            # 如果JSON中没有手机号或没有JSON，使用basename作为标识
            if basename not in session_json_with_phones:
                session_json_with_phones[basename] = (session_path, json_path)
                if not json_path:
                    print(f"ℹ️ 处理纯Session文件（无JSON）: {basename}")
    
    # 第四步：创建输出 ZIP 文件
    result_dir = os.path.join(temp_dir, 'results')
    os.makedirs(result_dir, exist_ok=True)
    
    timestamp = int(time.time())
    zip_files_created = []
    
    # 统计去重后的数量
    total_tdata = len(tdata_with_phones) + len(tdata_without_phones)
    total_session_json = len(session_json_with_phones)
    total_tdata_duplicates = len(tdata_duplicates)
    total_session_duplicates = len(session_json_duplicates)
    duplicates_removed = total_tdata_duplicates + total_session_duplicates
    
    # 打包 TData 账户（使用手机号作为目录名）
    if tdata_with_phones or tdata_without_phones:
        tdata_zip_path = os.path.join(result_dir, f'tdata_only_{timestamp}.zip')
        with zipfile.ZipFile(tdata_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 先处理有手机号的账户
            for phone, (account_root, tdata_dir_name) in tdata_with_phones.items():
                tdata_full_path = os.path.join(account_root, tdata_dir_name) if tdata_dir_name else account_root

                # 检查 tdata 同级目录是否有密码文件
                password_patterns = [
                    '2fa.txt', '2FA.txt', '2fa.TXT',
                    'twofa.txt', 'twoFA.txt', 'TwoFA.txt', 'TWOFA.txt',
                    'password.txt', 'Password.txt', 'PASSWORD.txt',
                    'pwd.txt', 'PWD.txt', 'Pwd.txt',
                    '两步验证.txt', '二步验证.txt', '密码.txt',
                    'pass.txt', 'Pass.txt', 'PASS.txt'
                ]
                for pwd_file in password_patterns:
                    pwd_path = os.path.join(account_root, pwd_file)
                    if os.path.isfile(pwd_path):
                        arcname = os.path.join(phone, pwd_file)
                        zf.write(pwd_path, arcname)
                        print(f"✅ 添加密码文件: {phone}/{pwd_file}")

                # 递归添加 tdata 目录下的所有文件
                for root, dirs, filenames in os.walk(tdata_full_path):
                    for fname in filenames:
                        file_path = os.path.join(root, fname)
                        # 计算相对路径
                        rel_path = os.path.relpath(file_path, account_root)
                        # 使用手机号作为目录名: phone/tdata/...
                        arcname = os.path.join(phone, rel_path)
                        zf.write(file_path, arcname)
            
            # 处理没有手机号的账户（使用account_N命名）
            for idx, (account_root, tdata_dir_name) in enumerate(tdata_without_phones, 1):
                account_name = f'account_{idx}'
                tdata_full_path = os.path.join(account_root, tdata_dir_name) if tdata_dir_name else account_root

                # 检查 tdata 同级目录是否有密码文件
                password_patterns = [
                    '2fa.txt', '2FA.txt', '2fa.TXT',
                    'twofa.txt', 'twoFA.txt', 'TwoFA.txt', 'TWOFA.txt',
                    'password.txt', 'Password.txt', 'PASSWORD.txt',
                    'pwd.txt', 'PWD.txt', 'Pwd.txt',
                    '两步验证.txt', '二步验证.txt', '密码.txt',
                    'pass.txt', 'Pass.txt', 'PASS.txt'
                ]
                for pwd_file in password_patterns:
                    pwd_path = os.path.join(account_root, pwd_file)
                    if os.path.isfile(pwd_path):
                        arcname = os.path.join(account_name, pwd_file)
                        zf.write(pwd_path, arcname)
                        print(f"✅ 添加密码文件: {account_name}/{pwd_file}")

                for root, dirs, filenames in os.walk(tdata_full_path):
                    for fname in filenames:
                        file_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(file_path, account_root)
                        arcname = os.path.join(account_name, rel_path)
                        zf.write(file_path, arcname)
        
        zip_files_created.append(('TData 账户', tdata_zip_path, total_tdata))
    
    # 打包 Session 文件（支持纯Session或Session+JSON配对，使用手机号作为文件名）
    if session_json_with_phones:
        session_json_zip_path = os.path.join(result_dir, f'session_json_{timestamp}.zip')
        with zipfile.ZipFile(session_json_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for phone, (session_path, json_path) in session_json_with_phones.items():
                # 使用手机号作为文件名
                zf.write(session_path, f'{phone}.session')
                # 只在JSON存在时添加JSON文件
                if json_path and os.path.exists(json_path):
                    zf.write(json_path, f'{phone}.json')
        
        zip_files_created.append(('Session 文件', session_json_zip_path, total_session_json))
    
    # 【新增】单独打包重复的 TData 账户
    if tdata_duplicates:
        tdata_dup_zip_path = os.path.join(result_dir, f'tdata_duplicates_{timestamp}.zip')
        with zipfile.ZipFile(tdata_dup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, (phone, account_root, tdata_dir_name) in enumerate(tdata_duplicates, 1):
                tdata_full_path = os.path.join(account_root, tdata_dir_name)
                
                # 使用 phone_duplicate_N 格式命名
                duplicate_name = f'{phone}_duplicate_{idx}'
                
                # 递归添加 tdata 目录下的所有文件
                for root, dirs, filenames in os.walk(tdata_full_path):
                    for fname in filenames:
                        file_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(file_path, account_root)
                        arcname = os.path.join(duplicate_name, rel_path)
                        zf.write(file_path, arcname)
        
        zip_files_created.append(('TData 重复账户', tdata_dup_zip_path, total_tdata_duplicates))
    
    # 【新增】单独打包重复的 Session 文件
    if session_json_duplicates:
        session_dup_zip_path = os.path.join(result_dir, f'session_duplicates_{timestamp}.zip')
        with zipfile.ZipFile(session_dup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, (phone, session_path, json_path) in enumerate(session_json_duplicates, 1):
                # 使用 phone_duplicate_N 格式命名
                duplicate_name = f'{phone}_duplicate_{idx}'
                
                zf.write(session_path, f'{duplicate_name}.session')
                if json_path and os.path.exists(json_path):
                    zf.write(json_path, f'{duplicate_name}.json')
        
        zip_files_created.append(('Session 重复文件', session_dup_zip_path, total_session_duplicates))
    
    # 发送结果
    duplicate_info = ""
    if duplicates_removed > 0:
        duplicate_info = f"""

    def is_tdata_zip(self, zip_path: str) -> bool:
    """检测 ZIP 文件是否包含 TData 标识（case-insensitive）"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # 检查是否包含 D877F783D5D3EF8C 目录（case-insensitive）
            namelist = zf.namelist()
            for name in namelist:
                if 'D877F783D5D3EF8C'.lower() in name.lower():
                    return True
        return False
    except:
        return False


    def _is_frozen_error(self, error: Exception) -> bool:
    """检查是否为冻结账户错误"""
    error_str = str(error).upper()
    return any(keyword in error_str for keyword in self.FROZEN_KEYWORDS)

async def _cleanup_single_account(self, client, account_name: str, file_path: str, progress_callback=None, user_id: int = None) -> Dict[str, Any]:
    """清理单个账号"""
    start_time = time.time()
    
    actions = []
    stats = {
        'profile_cleared': 0,
        'groups_left': 0,
        'channels_left': 0,
        'histories_deleted': 0,
        'contacts_deleted': 0,
        'dialogs_closed': 0,
        'errors': 0,
        'skipped': 0
    }
    
    # 用于详细报告的错误列表
    error_details = []
    
    try:
        # 0. 清理账号资料（头像、名字、简介）
        logger.info(f"清理账号资料: {account_name}")
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_profile'))
        
        try:
            # 添加超时保护
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                from telethon.tl.functions.account import UpdateProfileRequest
                from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
                
                # 获取当前账号信息
                me = await client.get_me()
            
            # 随机修改名字和简介为符号字母
            profile_cleared = False
            try:
                # 生成随机符号字母组合（使用secrets确保随机性）
                charset = string.ascii_letters + string.digits + '._-'
                random_chars = ''.join(secrets.choice(charset) for _ in range(secrets.randbelow(6) + 3))  # 3-8位
                random_bio = ''.join(secrets.choice(charset + ' ') for _ in range(secrets.randbelow(11) + 5))  # 5-15位
                
                await client(UpdateProfileRequest(
                    first_name=random_chars,  # 随机名字
                    last_name='',              # 清空姓氏
                    about=random_bio           # 随机简介
                ))
                logger.info(f"已修改名字和简介为随机字符: {random_chars}")
                profile_cleared = True
            except Exception as e:
                logger.warning(f"修改名字/简介失败: {e}")
                # 检查是否为冻结账户
                if self._is_frozen_error(e):
                    error_details.append(f"❄️ 账户已冻结 (FROZEN): {str(e)}")
                    logger.error(f"检测到冻结账户，终止清理: {account_name}")
                    return {
                        'success': False,
                        'error': 'FROZEN_ACCOUNT',
                        'error_message': f"账户已冻结: {str(e)}",
                        'statistics': stats,
                        'error_details': error_details,
                        'is_frozen': True
                    }
                error_details.append(f"修改资料失败: {str(e)}")
            
            # 删除所有头像
            try:
                photos = await client(GetUserPhotosRequest(
                    user_id=me,
                    offset=0,
                    max_id=0,
                    limit=100
                ))
                
                if hasattr(photos, 'photos') and photos.photos:
                    photo_ids = list(photos.photos)
                    await client(DeletePhotosRequest(id=photo_ids))
                    logger.info(f"已删除 {len(photo_ids)} 个头像")
                    if profile_cleared:
                        stats['profile_cleared'] = 1
            except Exception as e:
                logger.warning(f"删除头像失败: {e}")
            
            await asyncio.sleep(config.CLEANUP_ACTION_SLEEP)
            
        except asyncio.TimeoutError:
            logger.warning(f"清理账号资料超时 ({CLEANUP_OPERATION_TIMEOUT}秒)")
            stats['errors'] += 1
            error_details.append(f"清理账号资料超时")
        except Exception as e:
            logger.error(f"清理账号资料错误: {e}")
            stats['errors'] += 1
        
        # 1. 获取所有对话
        logger.info(f"获取对话列表: {account_name}")
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_get_dialogs'))
        
        dialogs = await client.get_dialogs()
        logger.info(f"找到 {len(dialogs)} 个对话")
        
        # 分类对话
        from telethon.tl.types import Channel, Chat, User
        groups = []
        channels = []
        users = []
        bots = []
        
        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, Channel):
                if entity.broadcast:
                    channels.append(dialog)
                else:
                    groups.append(dialog)
            elif isinstance(entity, Chat):
                groups.append(dialog)
            elif isinstance(entity, User):
                if entity.bot:
                    bots.append(dialog)
                else:
                    users.append(dialog)
        
        logger.info(f"分类: {len(groups)}群组, {len(channels)}频道, {len(users)}用户, {len(bots)}机器人")
        
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_found_dialogs').format(
                groups=len(groups), 
                channels=len(channels), 
                users=len(users)
            ))
        
        # 1. 离开群组和频道
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_leave_groups').format(
                count=len(groups) + len(channels)
            ))
        from telethon.tl.functions.channels import LeaveChannelRequest
        from telethon.tl.functions.messages import DeleteChatUserRequest
        
        # 添加超时保护，防止卡死
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                for dialog in groups + channels:
                    entity = dialog.entity
                    chat_id = entity.id
                    title = getattr(entity, 'title', 'Unknown')
                    chat_type = 'channel' if isinstance(entity, Channel) and entity.broadcast else 'group'
                    
                    action = CleanupAction(chat_id=chat_id, title=title, chat_type=chat_type)
                    
                    try:
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP + random.uniform(0, 0.2))
                        
                        if isinstance(entity, Channel):
                            await client(LeaveChannelRequest(entity))
                        else:
                            me = await client.get_me()
                            await client(DeleteChatUserRequest(chat_id, me))
                        
                        action.actions_done.append('left')
                        action.status = 'success'
                        
                        if chat_type == 'channel':
                            stats['channels_left'] += 1
                        else:
                            stats['groups_left'] += 1
                        
                        logger.debug(f"离开 {chat_type}: {title}")
                        
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait离开{title}: {e.seconds}秒 - 跳过以避免卡住")
                            action.status = 'skipped'
                            action.error = f"FloodWait {e.seconds}秒，已跳过"
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait离开{title}: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                if isinstance(entity, Channel):
                                    await client(LeaveChannelRequest(entity))
                                else:
                                    me = await client.get_me()
                                    await client(DeleteChatUserRequest(chat_id, me))
                                action.actions_done.append('left')
                                action.status = 'success'
                                if chat_type == 'channel':
                                    stats['channels_left'] += 1
                                else:
                                    stats['groups_left'] += 1
                            except Exception as retry_error:
                                action.status = 'failed'
                                action.error = f"重试失败: {str(retry_error)}"
                                stats['errors'] += 1
                        
                    except Exception as e:
                        action.status = 'failed'
                        action.error = str(e)
                        stats['errors'] += 1
                        logger.error(f"离开{title}错误: {e}")
                    
                    actions.append(action)
        
        except asyncio.TimeoutError:
            logger.warning(f"退出群组/频道操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已处理 {stats['groups_left'] + stats['channels_left']} 个")
            error_details.append(f"退出群组/频道超时")
            stats['skipped'] += 1
        
        # 2. 删除聊天记录
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_delete_histories').format(
                count=len(users) + len(bots)
            ))
        
        from telethon.tl.functions.messages import DeleteHistoryRequest
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                for dialog in users + bots:
                    entity = dialog.entity
                    chat_id = entity.id
                    
                    if hasattr(entity, 'first_name') and entity.first_name:
                        title = entity.first_name
                    elif hasattr(entity, 'username') and entity.username:
                        title = entity.username
                    else:
                        title = 'Unknown'
                    
                    chat_type = 'bot' if entity.bot else 'user'
                    action = CleanupAction(chat_id=chat_id, title=title, chat_type=chat_type)
                    
                    try:
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP + random.uniform(0, 0.2))
                        
                        # 尝试撤回删除
                        if config.CLEANUP_REVOKE_DEFAULT:
                            try:
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=True
                                ))
                                action.actions_done.extend(['history_deleted', 'revoked'])
                                action.status = 'success'
                            except Exception:
                                # 回退到单向删除
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=False
                                ))
                                action.actions_done.append('history_deleted')
                                action.status = 'partial'
                                action.error = '部分: 仅删除自己的消息'
                        else:
                            await client(DeleteHistoryRequest(
                                peer=entity,
                                max_id=0,
                                just_clear=False,
                                revoke=False
                            ))
                            action.actions_done.append('history_deleted')
                            action.status = 'success'
                        
                        stats['histories_deleted'] += 1
                        logger.debug(f"删除历史记录: {title}")
                        
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait删除{title}: {e.seconds}秒 - 跳过以避免卡住")
                            action.status = 'skipped'
                            action.error = f"FloodWait {e.seconds}秒，已跳过"
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait删除{title}: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=False
                                ))
                                action.actions_done.append('history_deleted')
                                action.status = 'success'
                                stats['histories_deleted'] += 1
                            except Exception as retry_error:
                                action.status = 'failed'
                                action.error = f"重试失败: {str(retry_error)}"
                                stats['errors'] += 1
                        
                    except Exception as e:
                        action.status = 'failed'
                        action.error = str(e)
                        stats['errors'] += 1
                        logger.error(f"删除{title}历史记录错误: {e}")
                    
                    actions.append(action)
        
        except asyncio.TimeoutError:
            logger.warning(f"删除对话记录操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已处理 {stats['histories_deleted']} 个")
            error_details.append(f"删除对话记录超时")
            stats['skipped'] += 1
        
        # 3. 删除联系人
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_delete_contacts'))
        
        from telethon.tl.functions.contacts import DeleteContactsRequest, GetContactsRequest
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                result = await client(GetContactsRequest(hash=0))
                
                if hasattr(result, 'users') and result.users:
                    contact_ids = [user.id for user in result.users]
                    logger.info(f"删除 {len(contact_ids)} 个联系人...")
                    
                    batch_size = 100
                    for i in range(0, len(contact_ids), batch_size):
                        batch = contact_ids[i:i + batch_size]
                        
                        try:
                            await client(DeleteContactsRequest(id=batch))
                            stats['contacts_deleted'] += len(batch)
                            logger.debug(f"已删除 {len(batch)} 个联系人")
                            
                            if i + batch_size < len(contact_ids):
                                await asyncio.sleep(config.CLEANUP_ACTION_SLEEP * 2)
                                
                        except FloodWaitError as e:
                            # 如果等待时间超过60秒，跳过以避免卡住
                            if e.seconds > 60:
                                logger.warning(f"FloodWait删除联系人: {e.seconds}秒 - 跳过以避免卡住")
                                stats['skipped'] += 1
                            else:
                                logger.warning(f"FloodWait删除联系人: {e.seconds}秒")
                                await asyncio.sleep(e.seconds)
                                try:
                                    await client(DeleteContactsRequest(id=batch))
                                    stats['contacts_deleted'] += len(batch)
                                except Exception:
                                    stats['errors'] += 1
                        
                        except Exception as e:
                            stats['errors'] += 1
                            logger.error(f"删除联系人批次错误: {e}")
                    
                    logger.info(f"已删除 {stats['contacts_deleted']} 个联系人")
        
        except asyncio.TimeoutError:
            logger.warning(f"删除联系人操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已删除 {stats['contacts_deleted']} 个")
            error_details.append(f"删除联系人超时")
            stats['skipped'] += 1
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"获取/删除联系人错误: {e}")
        
        # 4. 归档剩余对话
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_archive_dialogs'))
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                remaining_dialogs = await client.get_dialogs()
                archived_count = 0
                
                for dialog in remaining_dialogs:
                    try:
                        await client.edit_folder(dialog.entity, folder=1)
                        archived_count += 1
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP)
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait归档: {e.seconds}秒 - 跳过以避免卡住")
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait归档: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                await client.edit_folder(dialog.entity, folder=1)
                                archived_count += 1
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"无法归档对话: {e}")
                
                stats['dialogs_closed'] = archived_count
                logger.info(f"已归档 {archived_count} 个对话")
        
        except asyncio.TimeoutError:
            logger.warning(f"归档对话操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)")
            error_details.append(f"归档对话超时")
            stats['skipped'] += 1
        except Exception as e:
            logger.error(f"归档对话错误: {e}")
        
        # 返回清理结果（不生成单独报告）
        elapsed_time = time.time() - start_time
        
        return {
            'success': True,
            'elapsed_time': elapsed_time,
            'statistics': stats,
            'actions': actions  # 返回动作列表用于汇总报告
        }
        
    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'statistics': stats
        }


    def _create_fake_update(self, user_id: int):
    """创建一个假的update对象用于内部调用"""
    return type('obj', (object,), {
        'effective_chat': type('obj', (object,), {'id': user_id})(),
        'effective_user': type('obj', (object,), {'id': user_id})(),
        'message': None  # 设置为None，强制使用bot.send_message而不是reply_text
    })()


    def _estimate_registration_date_from_user_id(self, user_id: int) -> str:
    """
    基于用户ID估算注册日期（年-月-日格式）
    
    ⚠️ 警告：这个方法非常不准确，可能相差数年！
    Telegram用户ID不是严格按注册顺序递增的。
    
    仅当官方API和所有聊天记录方法都失败时使用此方法。
    
    返回格式: YYYY-MM-DD 或 YYYY-MM
    """
    # 基于历史数据的ID范围映射（这些是估算值，非精确值）
    # 已知的参考点（需要定期更新）
    reference_points = [
        (1, "2013-08"),           # Telegram 创始人
        (100000000, "2014-10"),   # 约1亿用户
        (500000000, "2017-06"),   # 约5亿用户
        (1000000000, "2020-01"),  # 约10亿用户
        (2000000000, "2021-09"),  # 约20亿用户
        (5000000000, "2023-01"),  # 约50亿用户
        (7000000000, "2024-06"),  # 约70亿用户
    ]
    
    user_id = int(user_id)
    
    # 找到最接近的参考点进行线性插值
    for i in range(len(reference_points) - 1):
        id1, date1 = reference_points[i]
        id2, date2 = reference_points[i + 1]
        
        if id1 <= user_id <= id2:
            # 线性插值
            ratio = (user_id - id1) / (id2 - id1)
            
            # 解析日期
            d1 = datetime.strptime(date1, "%Y-%m")
            d2 = datetime.strptime(date2, "%Y-%m")
            
            # 计算估算日期
            delta = d2 - d1
            estimated = d1 + delta * ratio
            
            return estimated.strftime("%Y-%m")
    
    # 如果超出范围，返回最近的参考点
    if user_id < reference_points[0][0]:
        return reference_points[0][1]
    else:
        return reference_points[-1][1]

# ================================
# 资料修改功能处理方法
# ================================


    def _show_random_config_menu(self, query, user_id: int, config: ProfileUpdateConfig):
    """显示随机模式配置菜单"""
    # 头像选项显示
    if config.photo_action == 'delete_all':
        photo_status = t(user_id, 'profile_display_delete_all')
    else:
        photo_status = t(user_id, 'profile_display_keep')
    
    # 简介选项显示
    if config.bio_action == 'clear':
        bio_status = t(user_id, 'profile_display_clear')
    elif config.bio_action == 'random':
        bio_status = t(user_id, 'profile_display_random')
    else:
        bio_status = t(user_id, 'profile_display_no_modify')
    
    # 用户名选项显示
    if config.username_action == 'delete':
        username_status = t(user_id, 'profile_display_delete')
    elif config.username_action == 'random':
        username_status = t(user_id, 'profile_display_random')
    else:
        username_status = t(user_id, 'profile_display_no_modify')
    
    text = f"""

    def _show_custom_config_menu(self, query, user_id: int, config: ProfileUpdateConfig):
    """显示自定义模式配置菜单"""
    # 姓名状态显示
    if config.update_name and config.custom_names:
        name_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_names))
    elif config.update_name:
        name_status = t(user_id, 'profile_custom_status_pending')
    else:
        name_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 头像状态显示
    if config.update_photo:
        if config.photo_action == 'delete_all':
            photo_status = t(user_id, 'profile_display_delete_all')
        elif config.photo_action == 'custom' and config.custom_photos:
            photo_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_photos))
        elif config.photo_action == 'custom':
            photo_status = t(user_id, 'profile_custom_status_pending')
        else:
            photo_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        photo_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 简介状态显示
    if config.update_bio:
        if config.bio_action == 'clear':
            bio_status = t(user_id, 'profile_display_clear')
        elif config.bio_action == 'custom' and config.custom_bios:
            bio_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_bios))
        elif config.bio_action == 'custom':
            bio_status = t(user_id, 'profile_custom_status_pending')
        else:
            bio_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        bio_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 用户名状态显示
    if config.update_username:
        if config.username_action == 'delete':
            username_status = t(user_id, 'profile_display_delete')
        elif config.username_action == 'custom' and config.custom_usernames:
            username_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_usernames))
        elif config.username_action == 'custom':
            username_status = t(user_id, 'profile_custom_status_pending')
        else:
            username_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        username_status = t(user_id, 'profile_custom_status_no_modify')
    
    text = f"""

    def _show_custom_field_config(self, query, user_id: int, field: str, field_name: str):
    """显示字段配置选项"""
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    
    # 记录当前正在配置的字段
    task['custom_input_field'] = field
    
    # 根据字段类型显示不同的选项
    text = f"<b>{t(user_id, 'profile_custom_field_config').format(field=field_name)}</b>\n\n{t(user_id, 'profile_custom_field_select')}"
    
    keyboard_buttons = []
    
    if field == 'name':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_names:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_names)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'photo':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_images'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_delete_all_avatar'), callback_data=f"profile_custom_field_{field}_delete")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_photos:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_photos)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'bio':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_bio'), callback_data=f"profile_custom_field_{field}_clear_bio")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_bios:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_bios)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'username':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_delete_username'), callback_data=f"profile_custom_field_{field}_delete_username")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_usernames:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_usernames)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    keyboard_buttons.append([InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


    def _handle_custom_field_action(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理字段配置动作"""
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    field = task.get('custom_input_field', '')
    
    # 解析动作
    parts = data.replace("profile_custom_field_", "").split("_", 1)
    
    # 如果没有动作（即只有字段名），则显示字段配置菜单（返回上一步）
    if len(parts) < 2 or parts[1] == "":
        field_name = parts[0]
        # 清除用户状态（从上传/输入状态返回）
        self.db.save_user(user_id, "", "", "profile_custom_config")
        # Helper function to get translated field display name
        field_map = {
            'name': 'profile_field_name',
            'photo': 'profile_field_avatar',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        field_display = t(user_id, field_map.get(field_name, 'profile_field_name'))
        self._show_custom_field_config(query, user_id, field_name, field_display)
        return
    
    field_name, action = parts[0], parts[1]
    
    # Helper function to get translated field display name
    def get_field_display(field):
        field_map = {
            'name': 'profile_field_name',
            'photo': 'profile_field_avatar',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        return t(user_id, field_map.get(field, 'profile_field_name'))
    
    if action == "upload":
        # 请求用户上传文件
        field_display = get_field_display(field_name)
        
        if field_name == 'photo':
            text = f"""

    def translate_contact_status_message(self, user_id, status, original_message):
    """翻译通讯录检测状态消息"""
    # 根据状态码返回翻译的消息
    if status == CONTACT_STATUS_NORMAL:
        return t(user_id, 'contact_limit_status_normal')
    elif status == CONTACT_STATUS_LIMITED:
        # 检查是否是FloodWait
        if 'FloodWait' in original_message or 'flood' in original_message.lower():
            return t(user_id, 'contact_limit_status_flood_wait')
        return t(user_id, 'contact_limit_status_limited')
    elif status == CONTACT_STATUS_BANNED:
        return t(user_id, 'contact_limit_status_banned')
    elif status == CONTACT_STATUS_UNAUTHORIZED:
        return t(user_id, 'contact_limit_status_auth_error')
    elif status == CONTACT_STATUS_ERROR:
        # 检查错误类型
        if '连接错误' in original_message or 'Connection' in original_message:
            # 提取错误信息
            error_part = original_message.split(':')[-1].strip() if ':' in original_message else original_message
            return t(user_id, 'contact_limit_status_connection_error').format(error=error_part[:30])
        return original_message  # 保留原始错误消息
    return original_message

async def generate_contact_limit_report(self, results, output_dir, user_id):
    """生成通讯录限制检测报告"""
    
    # 翻译所有结果中的status message
    translated_results = []
    for r in results:
        translated_r = r.copy()
        if 'message' in translated_r:
            translated_r['message'] = self.translate_contact_status_message(
                user_id, 
                r.get('status'), 
                r.get('message', '')
            )
        translated_results.append(translated_r)
    
    # 分类统计 - 使用常量
    normal = [r for r in translated_results if r.get('status') == CONTACT_STATUS_NORMAL]
    limited = [r for r in translated_results if r.get('status') == CONTACT_STATUS_LIMITED]
    banned = [r for r in translated_results if r.get('status') == CONTACT_STATUS_BANNED]
    failed = [r for r in translated_results if r.get('status') in [CONTACT_STATUS_ERROR, CONTACT_STATUS_UNAUTHORIZED]]
    
    # 生成报告文本
    report = f"""

    def _generate_registration_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成注册时间查询报告和打包结果（按年-月-日分类）"""
    logger.info("📊 开始生成报告和打包结果...")
    print("📊 开始生成报告和打包结果...", flush=True)
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    
    # 统计
    total = sum(len(v) for v in results.values())
    success_count = len(results['success'])
    error_count = len(results['error']) + len(results['frozen']) + len(results['banned'])
    
    # 按年-月-日（完整日期）分类
    by_date = {}
    for file_path, file_name, result in results['success']:
        reg_date = result.get('registration_date', '未知')
        if reg_date not in by_date:
            by_date[reg_date] = []
        by_date[reg_date].append((file_path, file_name, result))
    
    # 生成文本报告
    report_filename = f"registration_report_{timestamp}.txt"
    report_path = os.path.join(config.RESULTS_DIR, report_filename)
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_report_title')}\n")
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
            f.write(f"{t(user_id, 'regtime_report_total')} {total}\n")
            f.write(f"{t(user_id, 'regtime_report_success')} {success_count}\n")
            f.write(f"{t(user_id, 'regtime_report_failed')} {error_count}\n")
            f.write("=" * 80 + "\n\n")
            
            # 按日期统计（排序）
            f.write(f"{t(user_id, 'regtime_report_classify')}\n")
            f.write("-" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_source_title')}\n")
            f.write(f"{t(user_id, 'regtime_source_api')}\n")
            f.write(f"{t(user_id, 'regtime_source_all_chats')}\n")
            f.write(f"{t(user_id, 'regtime_source_telegram')}\n")
            f.write(f"{t(user_id, 'regtime_source_saved')}\n")
            f.write(f"{t(user_id, 'regtime_source_estimated')}\n")
            f.write("-" * 80 + "\n\n")
            
            for reg_date in sorted(by_date.keys()):
                f.write(f"\n{t(user_id, 'regtime_date_header').format(date=reg_date, count=len(by_date[reg_date]))}\n")
                f.write("-" * 40 + "\n")
                for file_path, file_name, result in by_date[reg_date]:
                    f.write(f"{t(user_id, 'regtime_field_file')} {file_name}\n")
                    f.write(f"{t(user_id, 'regtime_field_phone')} {result['phone']}\n")
                    f.write(f"{t(user_id, 'regtime_field_userid')} {result['user_id']}\n")
                    if result.get('username'):
                        f.write(f"{t(user_id, 'regtime_field_username')} @{result['username']}\n")
                    f.write(f"{t(user_id, 'regtime_field_name')} {result['first_name']} {result['last_name']}\n")
                    f.write(f"{t(user_id, 'regtime_field_common_groups')} {result['common_chats']}\n")
                    
                    # 显示数据来源，区分官方数据和估算数据
                    source = result.get('registration_source', 'estimated')
                    if source in ['telegram_api', 'full_user_api']:
                        # 官方API数据 - 最准确
                        source_display = t(user_id, 'regtime_source_api').replace('• telegram_api / full_user_api: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'all_chats':
                        # 从所有对话扫描获取
                        source_display = t(user_id, 'regtime_source_all_chats').replace('• all_chats: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'telegram_chat':
                        # 从Telegram官方对话获取
                        source_display = t(user_id, 'regtime_source_telegram').replace('• telegram_chat: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'saved_messages':
                        # 从收藏夹获取
                        source_display = t(user_id, 'regtime_source_saved').replace('• saved_messages: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    else:
                        # ID估算 - 不准确，添加警告
                        source_display = t(user_id, 'regtime_source_estimated').replace('• estimated: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    f.write("\n")
            
            # 失败的账号
            if error_count > 0:
                f.write(f"\n{t(user_id, 'regtime_failed_accounts')}\n")
                f.write("-" * 80 + "\n")
                for category in ['error', 'frozen', 'banned']:
                    if results[category]:
                        f.write(f"\n{t(user_id, 'regtime_error_label')} {category.upper()}:\n")
                        for file_path, file_name, result in results[category]:
                            f.write(f"{t(user_id, 'regtime_field_file')} {file_name}\n")
                            f.write(f"{t(user_id, 'regtime_error_field')} {result.get('error', '未知错误')}\n\n")
        
        logger.info(f"✅ 报告文件已生成: {report_path}")
        print(f"✅ 报告文件已生成: {report_path}", flush=True)
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
        print(f"❌ 生成报告文件失败: {e}", flush=True)
    
    # 按日期打包成功的账号 - 统一打包到一个ZIP文件中
    logger.info(f"📦 开始打包所有账号到单个ZIP文件...")
    print(f"📦 开始打包所有账号到单个ZIP文件...", flush=True)
    
    # 创建一个统一的ZIP文件
    all_accounts_zip = os.path.join(config.RESULTS_DIR, f"registration_all_{timestamp}.zip")
    
    try:
        with zipfile.ZipFile(all_accounts_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历每个日期
            for reg_date, items in sorted(by_date.items()):
                if items:
                    logger.info(f"📦 打包 {reg_date} 的 {len(items)} 个账号...")
                    print(f"📦 打包 {reg_date} 的 {len(items)} 个账号...", flush=True)
                    
                    # 创建日期文件夹名称：如 "2025-09-26 注册的账号 (16 个)"
                    date_folder = t(user_id, 'regtime_folder_name').format(date=reg_date, count=len(items))
                    
                    for file_path, file_name, result in items:
                        phone = result.get('phone', 'unknown')
                        result_file_type = result.get('file_type', 'session')
                        # 使用原始文件路径进行打包
                        original_path = result.get('original_file_path', file_path)
                        
                        try:
                            if result_file_type == 'tdata':
                                # TData格式：使用原始上传的文件，保持原始文件结构
                                # 结构: ZIP/日期文件夹/手机号/tdata/D877.../文件
                                if os.path.isdir(original_path):
                                    # 我们需要找到包含tdata结构的正确父目录
                                    # original_path 可能是以下几种情况：
                                    # 1. /path/to/phone/tdata/D877... (最常见)
                                    # 2. /path/to/phone/D877... (无tdata包装)
                                    # 3. /path/to/tdata/D877... (tdata在根)
                                    # 4. /path/to/D877... (直接D877)
                                    
                                    # 向上查找以确定结构
                                    tdata_parent = None
                                    current = original_path
                                    
                                    # 最多向上查找3层
                                    for _ in range(3):
                                        parent = os.path.dirname(current)
                                        parent_name = os.path.basename(parent)
                                        current_name = os.path.basename(current)
                                        
                                        # 检查是否找到tdata目录
                                        if current_name.lower() == 'tdata':
                                            # 找到tdata目录，使用其父目录作为基准
                                            tdata_parent = parent
                                            break
                                        
                                        # 检查当前目录的父目录是否是tdata
                                        if parent_name.lower() == 'tdata':
                                            # 当前是D877，父目录是tdata
                                            # 使用tdata的父目录作为基准
                                            tdata_parent = os.path.dirname(parent)
                                            break
                                        
                                        current = parent
                                    
                                    # 如果没有找到tdata结构，使用original_path的父目录
                                    if not tdata_parent:
                                        # 没有tdata包装，从D877的父目录开始
                                        # 结构变成: ZIP/日期文件夹/手机号/D877.../文件
                                        tdata_parent = os.path.dirname(original_path)
                                    
                                    # 遍历所有文件并保持相对结构
                                    for root, dirs, files in os.walk(original_path):
                                        for file in files:
                                            file_full_path = os.path.join(root, file)
                                            # 计算相对于tdata_parent的路径
                                            try:
                                                rel_path = os.path.relpath(file_full_path, tdata_parent)
                                            except ValueError:
                                                # 如果路径在不同驱动器，使用从original_path开始的相对路径
                                                rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                            
                                            # 构建压缩包内的路径：日期文件夹/手机号/rel_path
                                            # rel_path 现在应该包含 tdata/D877... 或 D877... 结构
                                            arc_path = os.path.join(date_folder, phone, rel_path)
                                            zipf.write(file_full_path, arc_path)
                            else:
                                # Session格式：使用原始上传的文件
                                # 结构: ZIP/日期文件夹/session文件和json文件（不用手机号子文件夹）
                                if os.path.exists(original_path):
                                    # 直接将session文件放在日期文件夹下
                                    arc_path = os.path.join(date_folder, file_name)
                                    zipf.write(original_path, arc_path)
                                
                                # Journal文件
                                journal_path = original_path + '-journal'
                                if os.path.exists(journal_path):
                                    arc_path = os.path.join(date_folder, file_name + '-journal')
                                    zipf.write(journal_path, arc_path)
                                
                                # JSON文件
                                json_path = os.path.splitext(original_path)[0] + '.json'
                                if os.path.exists(json_path):
                                    json_name = os.path.splitext(file_name)[0] + '.json'
                                    arc_path = os.path.join(date_folder, json_name)
                                    zipf.write(json_path, arc_path)
                        except Exception as e:
                            logger.error(f"❌ 打包文件失败 {file_name}: {e}")
                            print(f"❌ 打包文件失败 {file_name}: {e}", flush=True)
        
        logger.info(f"✅ 所有账号已打包到: {all_accounts_zip}")
        print(f"✅ 所有账号已打包到: {all_accounts_zip}", flush=True)
        
        # 准备发送的ZIP文件信息
        zip_files = [("all", all_accounts_zip, success_count)]
        
    except Exception as e:
        logger.error(f"❌ 打包失败: {e}")
        print(f"❌ 打包失败: {e}", flush=True)
        zip_files = []
    
    # 打包失败的账号到单独的ZIP文件
    if error_count > 0:
        logger.info(f"📦 开始打包失败的账号...")
        print(f"📦 开始打包失败的账号...", flush=True)
        
        failed_zip = os.path.join(config.RESULTS_DIR, f"{t(user_id, 'regtime_fail_zip_name')}_{timestamp}.zip")
        failed_details = []
        
        try:
            with zipfile.ZipFile(failed_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 创建详细失败原因文件
                for category in ['frozen', 'banned', 'error']:
                    if results[category]:
                        for file_path, file_name, result in results[category]:
                            error_msg = result.get('error', '未知错误')
                            result_file_type = result.get('file_type', 'session')
                            # 使用原始文件路径（与成功账号相同）
                            original_path = result.get('original_file_path', file_path)
                            
                            # 记录失败信息
                            failed_details.append({
                                'file_name': file_name,
                                'category': category,
                                'error': error_msg,
                                'file_type': result_file_type
                            })
                            
                            # 打包原始文件
                            try:
                                if result_file_type == 'tdata':
                                    # TData格式：打包整个目录，保持tdata结构
                                    if os.path.isdir(original_path):
                                        # 查找tdata结构的父目录（与成功账号相同的逻辑）
                                        tdata_parent = None
                                        current = original_path
                                        
                                        for _ in range(3):
                                            parent = os.path.dirname(current)
                                            parent_name = os.path.basename(parent)
                                            current_name = os.path.basename(current)
                                            
                                            if current_name.lower() == 'tdata':
                                                tdata_parent = parent
                                                break
                                            
                                            if parent_name.lower() == 'tdata':
                                                tdata_parent = os.path.dirname(parent)
                                                break
                                            
                                            current = parent
                                        
                                        if not tdata_parent:
                                            tdata_parent = os.path.dirname(original_path)
                                        
                                        for root, dirs, files in os.walk(original_path):
                                            for file in files:
                                                file_full_path = os.path.join(root, file)
                                                try:
                                                    rel_path = os.path.relpath(file_full_path, tdata_parent)
                                                except ValueError:
                                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                                
                                                arc_path = os.path.join(file_name, rel_path)
                                                zipf.write(file_full_path, arc_path)
                                else:
                                    # Session格式：打包session及相关文件
                                    if os.path.exists(original_path):
                                        zipf.write(original_path, file_name)
                                    
                                    # Journal文件
                                    journal_path = original_path + '-journal'
                                    if os.path.exists(journal_path):
                                        zipf.write(journal_path, file_name + '-journal')
                                    
                                    # JSON文件
                                    json_path = os.path.splitext(original_path)[0] + '.json'
                                    if os.path.exists(json_path):
                                        json_name = os.path.splitext(file_name)[0] + '.json'
                                        zipf.write(json_path, json_name)
                            except Exception as e:
                                logger.warning(f"⚠️ 打包失败文件失败 {file_name}: {e}")
                
                # 创建失败原因详细说明文件
                failed_report = f"{t(user_id, 'regtime_fail_report_title')}\n"
                failed_report += "=" * 80 + "\n"
                failed_report += f"{t(user_id, 'regtime_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n"
                failed_report += f"{t(user_id, 'regtime_fail_total')} {error_count}\n"
                failed_report += "=" * 80 + "\n\n"
                
                # 按类别分组
                category_keys = {
                    'frozen': 'regtime_fail_frozen',
                    'banned': 'regtime_fail_banned',
                    'error': 'regtime_fail_other_errors'
                }
                
                for category in ['frozen', 'banned', 'error']:
                    category_items = [d for d in failed_details if d['category'] == category]
                    if category_items:
                        failed_report += f"\n{t(user_id, category_keys[category]).format(count=len(category_items))}\n"
                        failed_report += "-" * 80 + "\n"
                        for item in category_items:
                            failed_report += f"{t(user_id, 'regtime_field_file')} {item['file_name']}\n"
                            failed_report += f"{t(user_id, 'regtime_fail_type')} {item['file_type']}\n"
                            failed_report += f"{t(user_id, 'regtime_fail_reason')} {item['error']}\n"
                            failed_report += "\n"
                
                # 将失败原因文件添加到ZIP
                zipf.writestr(t(user_id, 'regtime_fail_detail_file'), failed_report.encode('utf-8'))
            
            logger.info(f"✅ 失败账号已打包到: {failed_zip}")
            print(f"✅ 失败账号已打包到: {failed_zip}", flush=True)
            
            # 添加到发送列表
            zip_files.append(("failed", failed_zip, error_count))
            
        except Exception as e:
            logger.error(f"❌ 打包失败账号失败: {e}")
            print(f"❌ 打包失败账号失败: {e}", flush=True)
    
    # 发送统计信息
    summary = f"""

    def run(self):
    print("🚀 启动增强版机器人（速度优化版）...")
    print(f"📡 代理模式: {'启用' if config.USE_PROXY else '禁用'}")
    print(f"🔢 可用代理: {len(self.proxy_manager.proxies)}个")
    print(f"⚡ 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}")
    print(f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT if config.PROXY_FAST_MODE else config.MAX_CONCURRENT_CHECKS}个")
    print(f"⏱️ 检测超时: {config.PROXY_CHECK_TIMEOUT if config.PROXY_FAST_MODE else config.CHECK_TIMEOUT}秒")
    print(f"🔄 智能重试: {config.PROXY_RETRY_COUNT}次")
    print(f"🧹 自动清理: {'启用' if config.PROXY_AUTO_CLEANUP else '禁用'}")
    print("✅ 管理员系统: 启用")
    print("✅ 速度优化: 预计提升3-5倍")
    print("🛑 按 Ctrl+C 停止机器人")
    print("-" * 50)
    
    try:
        self.updater.start_polling()
        self.updater.idle()
    except KeyboardInterrupt:
        print("\n👋 机器人已停止")
    except Exception as e:
        print(f"\n❌ 运行错误: {e}")

# ================================
# 创建示例代理文件
# ================================




# ===== Handler Methods =====

    def _is_network_error(self, error: Exception) -> bool:
    """判断异常是否是网络相关的错误
    
    Args:
        error: 要检查的异常
        
    Returns:
        如果是网络相关错误返回 True，否则返回 False
    """
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in self.NETWORK_ERROR_KEYWORDS)


    def get_status_translation_key(self, status: str) -> str:
    """Map internal status to translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for the status
    """
    status_map = {
        "无限制": "status_no_restriction",
        "垃圾邮件": "status_spambot",
        "冻结": "status_frozen",
        "封禁": "status_banned",
        "连接错误": "status_connection_error",
    }
    return status_map.get(status, "status_no_restriction")


    def get_file_desc_translation_key(self, status: str) -> str:
    """Map internal status to file description translation key
    
    Args:
        status: Internal status name (Chinese)
        
    Returns:
        Translation key for file description
    """
    desc_map = {
        "无限制": "file_desc_no_restriction",
        "垃圾邮件": "file_desc_spambot",
        "冻结": "file_desc_frozen",
        "封禁": "file_desc_banned",
        "连接错误": "file_desc_connection_error",
    }
    return desc_map.get(status, "file_desc_no_restriction")


    def get_translated_file_info(self, user_id: int, status: str, count: int) -> tuple:
    """Get translated filename and caption for a status file
    
    Args:
        user_id: User ID for language selection
        status: Internal status name (Chinese)
        count: Number of accounts
        
    Returns:
        Tuple of (filename, caption_text, check_time_display, check_mode)
    """
    zip_name_key = self.get_zip_name_translation_key(status)
    file_desc_key = self.get_file_desc_translation_key(status)
    
    zip_filename = f"{t(user_id, zip_name_key).format(count=count)}.zip"
    file_caption_text = t(user_id, file_desc_key).format(count=count)
    
    actual_proxy_mode = self.proxy_manager.is_proxy_mode_active(self.db)
    check_mode = t(user_id, 'check_mode_proxy') if actual_proxy_mode else t(user_id, 'check_mode_local')
    check_time_display = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')
    
    return zip_filename, file_caption_text, check_time_display, check_mode


    def setup_handlers(self):
    self.dp.add_handler(CommandHandler("start", self.start_command))
    self.dp.add_handler(CommandHandler("help", self.help_command))
    self.dp.add_handler(CommandHandler("addadmin", self.add_admin_command))
    self.dp.add_handler(CommandHandler("removeadmin", self.remove_admin_command))
    self.dp.add_handler(CommandHandler("listadmins", self.list_admins_command))
    self.dp.add_handler(CommandHandler("payment_stats", self.payment_stats_command))
    self.dp.add_handler(CommandHandler("proxy", self.proxy_command))
    self.dp.add_handler(CommandHandler("testproxy", self.test_proxy_command))
    self.dp.add_handler(CommandHandler("cleanproxy", self.clean_proxy_command))
    self.dp.add_handler(CommandHandler("convert", self.convert_command))
    # 新增：API格式转换命令
    self.dp.add_handler(CommandHandler("api", self.api_command))
    # 新增：账号分类命令
    self.dp.add_handler(CommandHandler("classify", self.classify_command))
    # 新增：返回主菜单（优先于通用回调）
    self.dp.add_handler(CallbackQueryHandler(self.on_back_to_main, pattern=r"^back_to_main$"))
    
    # 专用：广播消息回调处理器（必须在通用回调之前注册）
    self.dp.add_handler(CallbackQueryHandler(self.handle_broadcast_callbacks_router, pattern=r"^broadcast_"))

    # 通用回调处理（需放在特定回调之后）
    self.dp.add_handler(CallbackQueryHandler(self.handle_callbacks))
    self.dp.add_handler(MessageHandler(Filters.document, self.handle_file))
    # 新增：广播媒体上传处理
    self.dp.add_handler(MessageHandler(Filters.photo, self.handle_photo))
    self.dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_text))


    def safe_send_message(self, update, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全发送消息（带网络错误重试机制）
    
    Args:
        update: Telegram update 对象
        text: 要发送的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        发送的消息对象，失败时返回 None
    """
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # 检查 update.message 是否存在
            if update.message:
                return update.message.reply_text(
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            # 如果 update.message 不存在（例如来自回调查询），使用 bot.send_message
            elif update.effective_chat:
                return self.updater.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            else:
                print("❌ 无法发送消息: update 对象缺少 message 和 effective_chat")
                return None
                
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 发送消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 发送消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                try:
                    error_str = str(e) if str(e) else "(空错误消息)"
                    error_msg = f"❌ 发送消息失败: {type(e).__name__}: {error_str}"
                except:
                    error_msg = f"❌ 发送消息失败: {type(e).__name__} (无法获取错误详情)"
                print(error_msg, flush=True)
                import traceback
                import sys
                print(f"详细堆栈跟踪:", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 发送消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def safe_edit_message(self, query, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全编辑消息（带网络错误重试机制）
    
    Args:
        query: Telegram callback query 对象
        text: 要编辑的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        编辑后的消息对象，失败时返回 None
    """
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return query.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            print(f"❌ 编辑消息失败: {e}")
            return None
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                print(f"❌ 编辑消息失败: {e}")
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 编辑消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def safe_edit_message_text(self, message, text, parse_mode=None, reply_markup=None, max_retries=None):
    """安全编辑消息对象（带网络错误重试机制）
    
    Args:
        message: Telegram message 对象
        text: 要编辑的消息文本
        parse_mode: 解析模式（如 'HTML'）
        reply_markup: 回复键盘标记
        max_retries: 最大重试次数（默认使用 MESSAGE_RETRY_MAX）
        
    Returns:
        编辑后的消息对象，失败时返回 None
    """
    if not message:
        return None
        
    if max_retries is None:
        max_retries = self.MESSAGE_RETRY_MAX
        
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return message.edit_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            last_error = e
            continue
            
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return message
            print(f"❌ 编辑消息失败: {e}")
            return None
            
        except (NetworkError, TimedOut) as e:
            # 网络错误，使用指数退避重试
            last_error = e
            if attempt < max_retries - 1:
                wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                print(f"⚠️ 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                return None
                
        except Exception as e:
            # 检查是否是网络相关的错误（urllib3, ConnectionError等）
            if self._is_network_error(e):
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = self.MESSAGE_RETRY_BACKOFF ** attempt
                    print(f"⚠️ 连接错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 编辑消息失败（已重试{max_retries}次）: {e}")
                    return None
            else:
                # 非网络错误，直接返回
                error_str = str(e) if str(e) else "(空错误消息)"
                print(f"❌ 编辑消息失败: {type(e).__name__}: {error_str}", flush=True)
                import traceback
                import sys
                print(f"详细堆栈跟踪:", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
                return None
    
    # 所有重试都失败
    if last_error:
        print(f"❌ 编辑消息失败（已重试{max_retries}次）: {last_error}")
    return None


    def send_document_safely(self, chat_id: int, file_path: str, caption: str = None, filename: str = None) -> bool:
    """安全发送文档，处理 RetryAfter 错误"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            with open(file_path, 'rb') as doc:
                self.updater.bot.send_document(
                    chat_id=chat_id,
                    document=doc,
                    caption=caption,
                    filename=filename,
                    parse_mode='HTML'
                )
            return True
        except RetryAfter as e:
            print(f"⚠️ 频率限制，等待 {e.retry_after} 秒")
            time.sleep(e.retry_after + 1)
            retry_count += 1
        except Exception as e:
            print(f"❌ 发送文档失败: {e}")
            return False
    
    return False


    def create_status_count_separate_buttons(self, results: Dict[str, List], processed: int, total: int, user_id: int = None) -> InlineKeyboardMarkup:
    """创建状态|数量分离按钮布局"""
    buttons = []
    
    # Status names for results dictionary (internal keys, keep in Chinese for compatibility)
    status_info = [
        ("无限制", "🟢", len(results['无限制'])),
        ("垃圾邮件", "🟡", len(results['垃圾邮件'])),
        ("冻结", "🔴", len(results['冻结'])),
        ("封禁", "🟠", len(results['封禁'])),
        ("连接错误", "⚫", len(results['连接错误']))
    ]
    
    # 每一行显示：状态名称 | 数量
    for status, emoji, count in status_info:
        # Translate status text for display if user_id is provided
        if user_id:
            status_key = self.get_status_translation_key(status)
            status_display = t(user_id, status_key)
        else:
            status_display = status  # Fallback to Chinese if no user_id
        
        row = [
            InlineKeyboardButton(f"{emoji} {status_display}", callback_data=f"status_{status}"),
            InlineKeyboardButton(f"{count}", callback_data=f"count_{status}")
        ]
        buttons.append(row)
    
    return InlineKeyboardMarkup(buttons)

    def start_command(self, update: Update, context: CallbackContext):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""
    
    # 保存用户数据到数据库
    self.db.save_user(user_id, username, first_name, "")
    
    self.show_main_menu(update, user_id)


    def show_main_menu(self, update: Update, user_id: int):
    """显示主菜单（统一方法）"""
    # 获取用户信息
    if update.callback_query:
        first_name = update.callback_query.from_user.first_name or t(user_id, 'default_user')
    else:
        first_name = update.effective_user.first_name or t(user_id, 'default_user')
    
    # 获取会员状态（使用 check_membership 方法）
    is_member, level, expiry = self.db.check_membership(user_id)
    
    if self.db.is_admin(user_id):
        member_status = t(user_id, 'status_admin')
    elif is_member:
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        member_status = f"🎁 {translated_level}"
    else:
        member_status = t(user_id, 'status_no_member')
    
    # 翻译到期时间
    if expiry == "永久有效":
        expiry = t(user_id, 'expiry_permanent')
    
    # 构建翻译后的欢迎文本
    proxy_mode_text = t(user_id, 'proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'proxy_mode_local')
    proxy_count_text = t(user_id, 'proxy_count_value').format(count=len(self.proxy_manager.proxies))
    
    welcome_text = f"""

    def show_language_menu(self, update: Update, user_id: int):
    """显示语言选择菜单"""
    query = update.callback_query
    if query:
        query.answer()
    
    # 构建语言选择菜单
    menu_text = t(user_id, 'language_menu_title')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'language_chinese'), callback_data="set_language_zh")],
        [InlineKeyboardButton(t(user_id, 'language_english'), callback_data="set_language_en")],
        [InlineKeyboardButton(t(user_id, 'language_russian'), callback_data="set_language_ru")],
        [InlineKeyboardButton(t(user_id, 'btn_back_to_menu'), callback_data="back_to_main")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    try:
        query.edit_message_text(
            text=menu_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"⚠️ 编辑语言菜单失败: {e}")


    def api_command(self, update: Update, context: CallbackContext):
    """API格式转换命令"""
    user_id = update.effective_user.id

    # 权限检查
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限才能使用API转换功能")
        return

    if not 'FLASK_AVAILABLE' in globals() or not FLASK_AVAILABLE:
        self.safe_send_message(update, "❌ API转换功能不可用\n\n原因: Flask库未安装\n💡 请安装: pip install flask jinja2")
        return

    text = f"""

    def handle_api_conversion(self, query):
    """处理API转换选项"""
    query.answer()
    user_id = query.from_user.id

    # 权限检查
    is_member, level, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(query, "❌ 需要会员权限才能使用API转换功能")
        return

    if not 'FLASK_AVAILABLE' in globals() or not FLASK_AVAILABLE:
        self.safe_edit_message(query, "❌ API转换功能不可用\n\n原因: Flask库未安装\n💡 请安装: pip install flask jinja2")
        return

    text = f"""

    def help_command(self, update: Update, context: CallbackContext):
    """处理 /help 命令和帮助按钮"""
    user_id = update.effective_user.id
    
    help_text = """

    def proxy_command(self, update: Update, context: CallbackContext):
    """代理管理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    # 获取当前代理状态
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # 统计住宅代理数量
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    proxy_text = f"""

    def show_proxy_detailed_status(self, update: Update):
    """显示代理详细状态"""
    if self.proxy_manager.proxies:
        status_text = "<b>📡 代理详细状态</b>\n\n"
        # 隐藏代理详细地址，只显示数量和类型
        proxy_count = len(self.proxy_manager.proxies)
        proxy_types = {}
        for proxy in self.proxy_manager.proxies:
            ptype = proxy.get('type', 'http')
            proxy_types[ptype] = proxy_types.get(ptype, 0) + 1
        
        status_text += f"📊 已加载 {proxy_count} 个代理\n\n"
        for ptype, count in proxy_types.items():
            status_text += f"• {ptype.upper()}: {count}个\n"
        
        # 添加代理设置信息
        enabled, updated_time, updated_by = self.db.get_proxy_setting_info()
        status_text += f"\n<b>📊 代理开关状态</b>\n"
        status_text += f"• 当前状态: {'🟢启用' if enabled else '🔴禁用'}\n"
        status_text += f"• 更新时间: {updated_time}\n"
        if updated_by:
            status_text += f"• 操作人员: {updated_by}\n"
        
        self.safe_send_message(update, status_text, 'HTML')
    else:
        self.safe_send_message(update, "❌ 没有可用的代理")


    def test_proxy_command(self, update: Update, context: CallbackContext):
    """测试代理命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not self.proxy_manager.proxies:
        self.safe_send_message(update, "❌ 没有可用的代理进行测试")
        return
    
    # 异步处理代理测试
    def process_test():
        asyncio.run(self.process_proxy_test(update, context))
    
    thread = threading.Thread(target=process_test)
    thread.start()
    
    self.safe_send_message(
        update, 
        f"🧪 开始测试 {len(self.proxy_manager.proxies)} 个代理...\n"
        f"⚡ 快速模式: {'开启' if config.PROXY_FAST_MODE else '关闭'}\n"
        f"🚀 并发数: {config.PROXY_CHECK_CONCURRENT}\n\n"
        "请稍等，测试结果将自动发送..."
    )

async def process_proxy_test(self, update, context):
    """处理代理测试"""
    try:
        # 发送进度消息
        progress_msg = self.safe_send_message(
            update,
            "🧪 <b>代理测试中...</b>\n\n📊 正在初始化测试环境...",
            'HTML'
        )
        
        # 进度回调函数
        async def test_progress_callback(tested, total, stats):
            try:
                progress = int(tested / total * 100)
                elapsed = time.time() - stats['start_time']
                speed = tested / elapsed if elapsed > 0 else 0
                
                progress_text = f"""

    def handle_proxy_callbacks(self, query, data):
    """处理代理相关回调"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可以操作")
        return
    
    if data == "proxy_enable":
        # 启用代理
        if self.db.set_proxy_enabled(True, user_id):
            query.answer("✅ 代理已启用")
            self.refresh_proxy_panel(query)
        else:
            query.answer("❌ 启用失败")
    
    elif data == "proxy_disable":
        # 禁用代理
        if self.db.set_proxy_enabled(False, user_id):
            query.answer("✅ 代理已禁用")
            self.refresh_proxy_panel(query)
        else:
            query.answer("❌ 禁用失败")
    
    elif data == "proxy_reload":
        # 重新加载代理列表
        old_count = len(self.proxy_manager.proxies)
        self.proxy_manager.load_proxies()
        new_count = len(self.proxy_manager.proxies)
        
        query.answer(f"✅ 重新加载完成: {old_count}→{new_count}个代理")
        self.refresh_proxy_panel(query)
    
    elif data == "proxy_status":
        # 查看详细状态
        self.show_proxy_status_popup(query)
    
    elif data == "proxy_test":
        # 测试代理连接
        self.test_proxy_connection(query)
    
    elif data == "proxy_stats":
        # 显示代理统计
        self.show_proxy_statistics(query)
    
    elif data == "proxy_cleanup":
        # 清理失效代理
        self.show_cleanup_confirmation(query)
    
    elif data == "proxy_optimize":
        # 显示速度优化信息
        self.show_speed_optimization_info(query)


    def show_proxy_status_popup(self, query):
    """显示代理状态弹窗"""
    if self.proxy_manager.proxies:
        status_text = f"📡 可用代理: {len(self.proxy_manager.proxies)}个\n"
        enabled, updated_time, updated_by = self.db.get_proxy_setting_info()
        status_text += f"🔧 代理开关: {'启用' if enabled else '禁用'}\n"
        status_text += f"⏰ 更新时间: {updated_time}"
    else:
        status_text = "❌ 没有可用的代理"
    
    query.answer(status_text, show_alert=True)


    def test_proxy_connection(self, query):
    """测试代理连接"""
    if not self.proxy_manager.proxies:
        query.answer("❌ 没有可用的代理进行测试", show_alert=True)
        return
    
    # 简单测试：尝试获取一个代理
    proxy = self.proxy_manager.get_next_proxy()
    if proxy:
        # 隐藏代理详细地址
        query.answer(f"🧪 测试代理: {proxy['type'].upper()}代理", show_alert=True)
    else:
        query.answer("❌ 获取测试代理失败", show_alert=True)


    def show_proxy_statistics(self, query):
    """显示代理统计信息"""
    proxies = self.proxy_manager.proxies
    if not proxies:
        query.answer("❌ 没有代理数据", show_alert=True)
        return
    
    # 统计代理类型
    type_count = {}
    for proxy in proxies:
        proxy_type = proxy['type']
        type_count[proxy_type] = type_count.get(proxy_type, 0) + 1
    
    stats_text = f"📊 代理统计\n总数: {len(proxies)}个\n\n"
    for proxy_type, count in type_count.items():
        stats_text += f"{proxy_type.upper()}: {count}个\n"
    
    enabled, _, _ = self.db.get_proxy_setting_info()
    stats_text += f"\n状态: {'🟢启用' if enabled else '🔴禁用'}"
    
    query.answer(stats_text, show_alert=True)


    def show_speed_optimization_info(self, query):
    """显示速度优化信息"""
    query.answer()
    current_concurrent = config.PROXY_CHECK_CONCURRENT if config.PROXY_FAST_MODE else config.MAX_CONCURRENT_CHECKS
    current_timeout = config.PROXY_CHECK_TIMEOUT if config.PROXY_FAST_MODE else config.CHECK_TIMEOUT
    
    optimization_text = f"""

    def show_proxy_panel(self, update: Update, query):
    """Display Proxy Management Panel"""
    user_id = query.from_user.id
    
    # Permission check (Admin only)
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get proxy status information
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # Count residential proxies
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    # Build proxy management panel information
    proxy_text = f"""

    def handle_callbacks(self, update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id  # ← 添加这一行
    if data == "start_check":
        self.handle_start_check(query)
    elif data == "format_conversion":
        self.handle_format_conversion(query)
    elif data == "change_2fa":
        self.handle_change_2fa(query)
    elif data == "forget_2fa":
        self.handle_forget_2fa(query)
    elif data == "remove_2fa":
        self.handle_remove_2fa(query)
    elif data == "add_2fa":
        self.handle_add_2fa(query)
    elif data == "remove_2fa_auto":
        # 自动识别密码
        query.answer()
        user_id = query.from_user.id
        if user_id in self.two_factor_manager.pending_2fa_tasks:
            task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
            if task_info.get('operation') == 'remove':
                # 使用 None 表示自动识别
                def process_remove():
                    asyncio.run(self.complete_remove_2fa(update, context, user_id, None))
                threading.Thread(target=process_remove, daemon=True).start()
            else:
                query.answer("❌ 操作类型不匹配")
        else:
            query.answer("❌ 没有待处理的任务")
    elif data == "remove_2fa_manual":
        # 手动输入密码
        query.answer()
        user_id = query.from_user.id
        if user_id in self.two_factor_manager.pending_2fa_tasks:
            task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
            if task_info.get('operation') == 'remove':
                # 请求用户输入密码
                try:
                    progress_msg = task_info['progress_msg']
                    total_files = len(task_info['files'])
                    progress_msg.edit_text(
                        f"{t(user_id, 'delete_2fa_found_files').format(count=total_files)}\n\n"
                        f"{t(user_id, 'delete_2fa_enter_password')}\n\n"
                        f"{t(user_id, 'delete_2fa_enter_desc1')}\n"
                        f"{t(user_id, 'delete_2fa_enter_desc2')}\n"
                        f"{t(user_id, 'delete_2fa_enter_desc3')}\n\n"
                        f"{t(user_id, 'delete_2fa_cancel_hint')}",
                        parse_mode='HTML'
                    )
                    # 设置用户状态为等待输入密码
                    self.db.save_user(user_id, query.from_user.username or "", 
                                    query.from_user.first_name or "", "waiting_remove_2fa_input")
                except Exception as e:
                    print(f"❌ 更新消息失败: {e}")
                    query.answer("❌ 操作失败")
            else:
                query.answer("❌ 操作类型不匹配")
        else:
            query.answer("❌ 没有待处理的任务")
    elif data == "convert_tdata_to_session":
        self.handle_convert_tdata_to_session(query)
    elif data == "convert_session_to_tdata":
        self.handle_convert_session_to_tdata(query)
    elif data == "api_conversion":
        self.handle_api_conversion(query)
    elif data.startswith("classify_") or data == "classify_menu":
        self.handle_classify_callbacks(update, context, query, data)
    elif data == "rename_start":
        self.handle_rename_start(query)
    elif data == "merge_start":
        self.handle_merge_start(query)
    elif data == "merge_continue":
        self.handle_merge_continue(query)
    elif data == "merge_finish":
        self.handle_merge_finish(update, context, query)
    elif data == "merge_cancel":
        self.handle_merge_cancel(query)
    elif data == "cleanup_start":
        self.handle_cleanup_start(query)
    elif data == "cleanup_confirm":
        self.handle_cleanup_confirm(update, context, query)
    elif data == "cleanup_cancel":
        query.answer()
        # Clean up any pending cleanup task
        if user_id in self.pending_cleanup:
            self.cleanup_cleanup_task(user_id)
        self.show_main_menu(update, user_id)
    elif data == "batch_create_start":
        self.handle_batch_create_start(query)
    elif data.startswith("batch_create_"):
        self.handle_batch_create_callbacks(update, context, query, data)
    elif data == "reauthorize_start":
        self.handle_reauthorize_start(query)
    elif data.startswith("reauthorize_") or data.startswith("reauth_"):
        self.handle_reauthorize_callbacks(update, context, query, data)
    elif data == "check_registration_start":
        self.handle_check_registration_start(query)
    elif data.startswith("check_reg_"):
        self.handle_check_registration_callbacks(update, context, query, data)
    elif data == "profile_update_start":
        self.handle_profile_update_start(query)
    elif data.startswith("profile_"):
        self.handle_profile_update_callbacks(update, context, query, data)
    elif data == "check_contact_limit":
        self.handle_check_contact_limit(query)
    elif data == "language_menu":
        # 显示语言选择菜单
        self.show_language_menu(update, user_id)
    elif data.startswith("set_language_"):
        # 设置语言
        query.answer()
        if I18N_AVAILABLE:
            lang = data.replace("set_language_", "")
            set_user_language(user_id, lang)
            # 显示语言切换成功消息并刷新主菜单
            self.show_main_menu(update, user_id)
    elif query.data == "back_to_main":
        self.show_main_menu(update, user_id)
        # 返回主菜单 - 横排2x2布局
        query.answer()
        user = query.from_user
        user_id = user.id
        
        # 如果当前消息是图片消息（来自取消订单），先删除再发送新消息
        message_was_photo = query.message and query.message.photo
        if message_was_photo:
            try:
                query.message.delete()
            except Exception as e:
                logger.warning(f"删除图片消息失败: {e}")
        
        first_name = user.first_name or t(user_id, 'default_user')
        is_member, level, expiry = self.db.check_membership(user_id)
        
        if self.db.is_admin(user_id):
            member_status = t(user_id, 'status_admin')
        elif is_member:
            # 翻译会员等级
            if level == "会员":
                translated_level = t(user_id, 'member_level_member')
            elif level == "管理员":
                translated_level = t(user_id, 'member_level_admin')
            else:
                translated_level = level  # 保留其他未知等级
            member_status = f"🎁 {translated_level}"
        else:
            member_status = t(user_id, 'status_no_member')
        
        # 翻译到期时间
        if expiry == "永久有效":
            expiry = t(user_id, 'expiry_permanent')
        
        proxy_mode_text = t(user_id, 'proxy_mode_enabled') if self.proxy_manager.is_proxy_mode_active(self.db) else t(user_id, 'proxy_mode_local')
        proxy_count_text = t(user_id, 'proxy_count_value').format(count=len(self.proxy_manager.proxies))
        
        welcome_text = f"""

    def handle_help_callback(self, query):
    query.answer()
    help_text = """

    def handle_status_callback(self, query):
    query.answer()
    user_id = query.from_user.id
    
    status_text = f"""

    def handle_user_detail(self, query, target_user_id: int):
    """显示用户详细信息"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    query.answer()
    
    user_info = self.db.get_user_membership_info(target_user_id)
    
    if not user_info:
        self.safe_edit_message(query, f"❌ 找不到用户 {target_user_id}")
        return
    
    # 格式化显示
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    register_time = user_info.get('register_time', '')
    last_active = user_info.get('last_active', '')
    membership_level = user_info.get('membership_level', '')
    expiry_time = user_info.get('expiry_time', '')
    is_admin = user_info.get('is_admin', False)
    
    # 计算活跃度
    activity_status = "🔴 从未活跃"
    if last_active:
        try:
            # Database stores naive datetime strings, compare with naive Beijing time
            last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
            time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
            if time_diff.days == 0:
                activity_status = f"🟢 {time_diff.seconds//3600}小时前活跃"
            elif time_diff.days <= 7:
                activity_status = f"🟡 {time_diff.days}天前活跃"
            else:
                activity_status = f"🔴 {time_diff.days}天前活跃"
        except:
            activity_status = f"🔴 {last_active}"
    
    # 会员状态
    member_status = "❌ 无会员"
    if membership_level and membership_level != "无会员":
        if expiry_time:
            try:
                # Database stores naive datetime strings, compare with naive Beijing time
                expiry_dt = datetime.strptime(expiry_time, '%Y-%m-%d %H:%M:%S')
                if expiry_dt > datetime.now(BEIJING_TZ).replace(tzinfo=None):
                    member_status = f"🎁 {membership_level}（有效至 {expiry_time}）"
                else:
                    member_status = f"⏰ {membership_level}（已过期）"
            except:
                member_status = f"🎁 {membership_level}"
    
    text = f"""

    def handle_grant_membership(self, query, target_user_id: int):
    """授予用户体验会员"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查用户是否存在
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        query.answer("❌ 用户不存在")
        return
    
    # 授予体验会员
    success = self.db.save_membership(target_user_id, "体验会员")
    
    if success:
        query.answer("✅ 体验会员授予成功")
        # 刷新用户详情页面
        self.handle_user_detail(query, target_user_id)
    else:
        query.answer("❌ 授予失败")


    def handle_proxy_panel(self, query):
    """代理面板"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 直接调用刷新代理面板
    self.refresh_proxy_panel(query)


    def handle_file(self, update: Update, context: CallbackContext):
    """处理文件上传"""
    user_id = update.effective_user.id
    document = update.message.document

    if not document:
        self.safe_send_message(update, "❌ 请上传文件")
        return

    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()

        # 放行的状态，新增 waiting_api_file, waiting_rename_file, waiting_merge_files, waiting_cleanup_file, batch_create_upload, reauthorize_upload, registration_check_upload, profile_update_upload, waiting_contact_check_file
        allowed_states = [
            "waiting_file",
            "waiting_convert_tdata",
            "waiting_convert_session",
            "waiting_2fa_file",
            "waiting_api_file",
            "waiting_classify_file",
            "waiting_rename_file",
            "waiting_merge_files",
            "waiting_forget_2fa_file",
            "waiting_add_2fa_file",
            "waiting_remove_2fa_file",
            "waiting_cleanup_file",
            "batch_create_upload",
            "batch_create_names",
            "batch_create_usernames",
            "reauthorize_upload",
            "registration_check_upload",
            "profile_update_upload",
            "waiting_contact_check_file",
        ]
        
        # 添加自定义资料上传状态
        if row and row[0].startswith("profile_custom_upload_"):
            allowed_states.append(row[0])
        
        if not row or row[0] not in allowed_states:
            self.safe_send_message(update, f"❌ {t(user_id, 'error_click_function_button')}")
            return

        user_status = row[0]
    except Exception:
        self.safe_send_message(update, "❌ 系统错误，请重试")
        return
    
    # 文件重命名和账户合并不需要会员权限检查，也不需要ZIP格式检查
    if user_status == "waiting_rename_file":
        self.handle_rename_file_upload(update, context, document)
        return
    elif user_status == "waiting_merge_files":
        self.handle_merge_file_upload(update, context, document)
        return
    
    # 自定义资料上传不需要ZIP格式检查（支持txt和图片文件）
    if user_status.startswith("profile_custom_upload_"):
        field_name = user_status.replace("profile_custom_upload_", "")
        self.handle_profile_custom_file_upload(update, context, user_id, field_name, document)
        return
    
    # 其他功能需要ZIP格式
    if not document.file_name.lower().endswith('.zip'):
        self.safe_send_message(update, t(user_id, 'error_upload_zip_only'))
        return

    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限")
        return

    if document.file_size > 100 * 1024 * 1024:
        self.safe_send_message(update, "❌ 文件过大 (限制100MB)")
        return

    # 根据用户状态选择处理方式
    if user_status == "waiting_file":
        # 异步处理账号检测
        def process_file():
            try:
                asyncio.run(self.process_enhanced_check(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_file] 任务被取消")
            except Exception as e:
                print(f"[process_file] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_file)
        thread.start()

    elif user_status in ["waiting_convert_tdata", "waiting_convert_session"]:
        # 异步处理格式转换
        def process_conversion():
            try:
                asyncio.run(self.process_format_conversion(update, context, document, user_status))
            except asyncio.CancelledError:
                print(f"[process_conversion] 任务被取消")
            except Exception as e:
                print(f"[process_conversion] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_conversion)
        thread.start()

    elif user_status == "waiting_2fa_file":
        # 异步处理2FA密码修改
        def process_2fa():
            try:
                asyncio.run(self.process_2fa_change(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_2fa)
        thread.start()

    elif user_status == "waiting_api_file":
        # 新增：API转换处理
        def process_api_conversion():
            try:
                asyncio.run(self.process_api_conversion(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_api_conversion] 任务被取消")
            except Exception as e:
                print(f"[process_api_conversion] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_api_conversion)
        thread.start()
    elif user_status == "waiting_classify_file":
        # 账号分类处理
        def process_classify():
            try:
                asyncio.run(self.process_classify_stage1(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_classify] 任务被取消")
            except Exception as e:
                print(f"[process_classify] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_classify, daemon=True)
        thread.start()
    elif user_status == "waiting_forget_2fa_file":
        # 忘记2FA处理
        def process_forget_2fa():
            try:
                asyncio.run(self.process_forget_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_forget_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_forget_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_forget_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_add_2fa_file":
        # 添加2FA处理
        def process_add_2fa():
            try:
                asyncio.run(self.process_add_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_add_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_add_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_add_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_remove_2fa_file":
        # 删除2FA处理
        def process_remove_2fa():
            try:
                asyncio.run(self.process_remove_2fa(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_remove_2fa] 任务被取消")
            except Exception as e:
                print(f"[process_remove_2fa] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_remove_2fa, daemon=True)
        thread.start()
    elif user_status == "waiting_cleanup_file":
        # 一键清理处理
        def process_cleanup():
            try:
                asyncio.run(self.process_cleanup(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_cleanup] 任务被取消")
            except Exception as e:
                print(f"[process_cleanup] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_cleanup, daemon=True)
        thread.start()
    elif user_status == "batch_create_upload":
        # 批量创建文件处理
        def process_batch_create():
            try:
                asyncio.run(self.process_batch_create_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_batch_create] 任务被取消")
            except Exception as e:
                print(f"[process_batch_create] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_batch_create, daemon=True)
        thread.start()
    elif user_status == "batch_create_names":
        # 处理群组名称文件上传
        self.process_batch_create_names_file(update, context, document, user_id)
    elif user_status == "batch_create_usernames":
        # 处理用户名文件上传
        self.process_batch_create_usernames_file(update, context, document, user_id)
    elif user_status == "reauthorize_upload":
        # 重新授权文件处理
        def process_reauthorize():
            try:
                asyncio.run(self.process_reauthorize_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_reauthorize] 任务被取消")
            except Exception as e:
                print(f"[process_reauthorize] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_reauthorize, daemon=True)
        thread.start()
    elif user_status == "registration_check_upload":
        # 查询注册时间文件处理
        def process_registration_check():
            try:
                asyncio.run(self.process_registration_check_upload(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_registration_check] 任务被取消")
            except Exception as e:
                print(f"[process_registration_check] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_registration_check, daemon=True)
        thread.start()
    elif user_status == "profile_update_upload":
        # 资料修改文件处理
        def process_profile_update():
            try:
                asyncio.run(self.process_profile_update(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_profile_update] 任务被取消")
            except Exception as e:
                print(f"[process_profile_update] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_profile_update, daemon=True)
        thread.start()
    elif user_status == "waiting_contact_check_file":
        # 通讯录限制检测处理
        def process_contact_limit_check():
            try:
                asyncio.run(self.process_contact_limit_check(update, context, document))
            except asyncio.CancelledError:
                print(f"[process_contact_limit_check] 任务被取消")
            except Exception as e:
                print(f"[process_contact_limit_check] 处理异常: {e}")
                import traceback
                traceback.print_exc()
        thread = threading.Thread(target=process_contact_limit_check, daemon=True)
        thread.start()
    elif user_status.startswith("profile_custom_upload_"):
        # 自定义资料文件上传
        field_name = user_status.replace("profile_custom_upload_", "")
        self.handle_profile_custom_file_upload(update, context, user_id, field_name, document)
    # 清空用户状态
    self.db.save_user(
        user_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
        ""
    )


async def process_api_conversion(self, update, context, document):
    """API格式转换 - 阶段1：解析文件并询问网页展示的2FA"""
    user_id = update.effective_user.id
    start_time = time.time()
    task_id = f"{user_id}_{int(start_time)}"

    progress_msg = self.safe_send_message(update, f"📥 <b>{t(user_id, 'api_processing_file')}...</b>", 'HTML')
    if not progress_msg:
        return

    temp_zip = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="temp_api_")
        temp_zip = os.path.join(temp_dir, document.file_name)
        document.get_file().download(temp_zip)

        files, extract_dir, file_type = self.processor.scan_zip_file(temp_zip, user_id, task_id)
        if not files:
            try:
                progress_msg.edit_text("❌ <b>未找到有效文件</b>\n\n请确保ZIP包含Session或TData格式的文件", parse_mode='HTML')
            except:
                pass
            return

        total_files = len(files)
        file_type_upper = file_type.upper()
        file_type_key = 'api_type_session' if file_type.lower() == 'session' else 'api_type_tdata'
        
        try:
            progress_msg.edit_text(
                f"{t(user_id, 'api_found_accounts').format(count=total_files)}\n"
                f"{t(user_id, file_type_key)}\n\n"
                f"{t(user_id, 'api_enter_2fa')}\n"
                f"{t(user_id, 'api_2fa_example')}\n"
                f"{t(user_id, 'api_2fa_skip')}\n\n"
                f"{t(user_id, 'api_2fa_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass

        # 记录待处理任务，等待用户输入2FA
        self.pending_api_tasks[user_id] = {
            "files": files,
            "file_type": file_type,
            "extract_dir": extract_dir,
            "task_id": task_id,
            "progress_msg": progress_msg,
            "start_time": start_time,
            "temp_zip": temp_zip
        }
    except Exception as e:
        print(f"❌ API阶段1失败: {e}")
        try:
            progress_msg.edit_text(f"❌ 失败: {str(e)}", parse_mode='HTML')
        except:
            pass
        if temp_zip and os.path.exists(temp_zip):
            try:
                shutil.rmtree(os.path.dirname(temp_zip), ignore_errors=True)
            except:
                pass
async def continue_api_conversion(self, update, context, user_id: int, two_fa_input: Optional[str]):
    """API格式转换 - 阶段2：执行转换并生成仅含链接的TXT"""
    result_files = []
    task = self.pending_api_tasks.get(user_id)
    if not task:
        self.safe_send_message(update, "❌ 没有待处理的API转换任务")
        return

    files = task["files"]
    file_type = task["file_type"]
    extract_dir = task["extract_dir"]
    task_id = task["task_id"]
    progress_msg = task["progress_msg"]
    temp_zip = task["temp_zip"]
    start_time = task["start_time"]

    # Check if user wants to skip (supports both Chinese and English)
    override_two_fa = None if (not two_fa_input or two_fa_input.strip().lower() in [t(user_id, 'api_skip').lower(), "跳过", "skip"]) else two_fa_input.strip()

    # 更新提示
    try:
        tip = f"🔄 <b>{t(user_id, 'api_converting')}</b>\n\n"
        if override_two_fa:
            tip += f"🔐 {t(user_id, 'api_2fa_mode_manual')}: <code>{override_two_fa}</code>\n"
        else:
            tip += f"🔐 {t(user_id, 'api_2fa_mode_auto')}\n"
        progress_msg.edit_text(tip, parse_mode='HTML')
    except:
        pass

    try:
        # =================== 变量初始化 ===================
        total_files = len(files)
        api_accounts = []
        failed_accounts = []
        failure_reasons = {}
        
        # =================== 性能参数计算 ===================  
        max_concurrent = 15 if total_files > 100 else 10 if total_files > 50 else 5
        batch_size = min(20, max(5, total_files // 5))  # 统一的批次计算
        semaphore = asyncio.Semaphore(max_concurrent)
        
        print(f"🚀 并发转换参数: 文件={total_files}, 批次={batch_size}, 并发={max_concurrent}")
        
        file_type_key = 'api_file_type_session' if file_type.lower() == 'session' else 'api_file_type_tdata'
        mode_2fa_key = 'api_2fa_mode_manual' if override_two_fa else 'api_2fa_mode_auto'
        
        # =================== 进度提示 ===================
        try:
            progress_msg.edit_text(
                f"🔄 <b>{t(user_id, 'api_converting')}</b>\n\n"
                f"📊 {t(user_id, 'api_stat_total').format(count=total_files)}\n"
                f"{t(user_id, file_type_key)}\n"
                f"{t(user_id, mode_2fa_key)}\n"
                f"🚀 并发数: {max_concurrent} | 批次: {batch_size}\n\n"
                f"正在处理...",
                parse_mode='HTML'
            )
        except:
            pass

        # =================== 并发批处理循环 ===================
        for i in range(0, total_files, batch_size):
            batch_files = files[i:i + batch_size]
            
            # 更新进度
            try:
                processed = i
                progress = int(processed / total_files * 100)
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 and processed > 0 else 0
                remaining = (total_files - processed) / speed if speed > 0 else 0
                
                file_type_key = 'api_file_type_session' if file_type.lower() == 'session' else 'api_file_type_tdata'
                mode_2fa_key = 'api_2fa_mode_manual' if override_two_fa else 'api_2fa_mode_auto'
                
                # 生成失败原因统计
                failure_stats = ""
                if failure_reasons:
                    failure_stats = f"\n\n<b>{t(user_id, 'api_failure_stats')}</b>\n"
                    for reason, count in failure_reasons.items():
                        # 翻译失败原因
                        reason_key_map = {
                            "转换失败": "api_failure_reason_conversion_failed",
                            "未授权": "api_failure_reason_unauthorized",
                            "连接超时": "api_failure_reason_timeout",
                            "转换异常": "api_failure_reason_conversion_error",
                            "并发异常": "api_failure_reason_concurrent_error",
                            "文件不存在": "api_failure_reason_file_not_exist",
                            "文件损坏": "api_failure_reason_file_corrupted",
                            "目录不存在": "api_failure_reason_dir_not_exist",
                            "未知错误": "api_failure_reason_unknown",
                        }
                        reason_key = reason_key_map.get(reason, None)
                        translated_reason = t(user_id, reason_key) if reason_key else reason
                        failure_stats += f"• {translated_reason}: {count}\n"
                
                progress_text = f"""

    def handle_text(self, update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    # 检查广播消息输入
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            user_status = row[0]
            
            if user_status == "waiting_broadcast_title":
                self.handle_broadcast_title_input(update, context, user_id, text)
                return
            elif user_status == "waiting_broadcast_content":
                self.handle_broadcast_content_input(update, context, user_id, text)
                return
            elif user_status == "waiting_broadcast_buttons":
                self.handle_broadcast_buttons_input(update, context, user_id, text)
                return
            # VIP会员相关状态
            elif user_status == "waiting_redeem_code":
                self.handle_redeem_code_input(update, user_id, text)
                return
            elif user_status == "waiting_manual_user":
                self.handle_manual_user_input(update, user_id, text)
                return
            elif user_status == "waiting_revoke_user":
                self.handle_revoke_user_input(update, user_id, text)
                return
            elif user_status == "waiting_admin_query_date":
                self.handle_admin_date_query_result(update, user_id, text)
                return
            elif user_status == "waiting_admin_query_user":
                self.handle_admin_user_query_result(update, user_id, text)
                return
            elif user_status == "waiting_rename_newname":
                self.handle_rename_newname_input(update, context, user_id, text)
                return
            elif user_status == "waiting_add_2fa_input":
                self.handle_add_2fa_input(update, context, user_id, text)
                return
            elif user_status == "waiting_remove_2fa_input":
                # 处理删除2FA的手动密码输入
                if user_id in self.two_factor_manager.pending_2fa_tasks:
                    task_info = self.two_factor_manager.pending_2fa_tasks[user_id]
                    if task_info.get('operation') == 'remove':
                        old_password = text.strip()
                        print(f"🗑️ 用户 {user_id} 输入删除2FA密码")
                        # 异步处理密码删除
                        def process_remove():
                            asyncio.run(self.complete_remove_2fa(update, context, user_id, old_password))
                        threading.Thread(target=process_remove, daemon=True).start()
                    else:
                        self.safe_send_message(update, "❌ 操作类型不匹配")
                else:
                    self.safe_send_message(update, "❌ 没有待处理的删除2FA任务")
                return
            elif user_status == "batch_create_count":
                self.handle_batch_create_count_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_admin":
                self.handle_batch_create_admin_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_names":
                self.handle_batch_create_names_input(update, context, user_id, text)
                return
            elif user_status == "batch_create_usernames":
                self.handle_batch_create_usernames_input(update, context, user_id, text)
                return
            elif user_status == "reauthorize_old_password":
                self.handle_reauthorize_old_password_input(update, context, user_id, text)
                return
            elif user_status == "reauthorize_new_password":
                self.handle_reauthorize_new_password_input(update, context, user_id, text)
                return
            # 自定义资料输入状态
            elif user_status.startswith("profile_custom_input_"):
                field_name = user_status.replace("profile_custom_input_", "")
                self.handle_profile_custom_text_input(update, context, user_id, field_name, text)
                return
    except Exception as e:
        print(f"❌ 检查广播状态失败: {e}")
    
    # 处理添加2FA等待的密码输入（使用任务字典检查，不依赖数据库状态）
    if user_id in getattr(self, "pending_add_2fa_tasks", {}):
        self.handle_add_2fa_input(update, context, user_id, text)
        return
    
    # 新增：处理 API 转换等待的 2FA 输入
    if user_id in getattr(self, "pending_api_tasks", {}):
        two_fa_input = (text or "").strip()
        def go_next():
            asyncio.run(self.continue_api_conversion(update, context, user_id, two_fa_input))
        threading.Thread(target=go_next, daemon=True).start()
        return        
    # 检查是否是2FA密码输入
    if user_id in self.two_factor_manager.pending_2fa_tasks:
        # 用户正在等待输入密码
        parts = text.strip().split()
        
        if len(parts) == 1:
            # 格式1：仅新密码，让系统自动检测旧密码
            new_password = parts[0]
            old_password = None
            
            print(f"🔐 用户 {user_id} 输入新密码（自动检测旧密码）")
            
            # 异步处理密码修改
            def process_password_change():
                asyncio.run(self.complete_2fa_change_with_passwords(update, context, old_password, new_password))
            
            thread = threading.Thread(target=process_password_change)
            thread.start()
            
        elif len(parts) == 2:
            # 格式2：旧密码 新密码
            old_password = parts[0]
            new_password = parts[1]
            
            print(f"🔐 用户 {user_id} 输入旧密码和新密码")
            
            # 异步处理密码修改
            def process_password_change():
                asyncio.run(self.complete_2fa_change_with_passwords(update, context, old_password, new_password))
            
            thread = threading.Thread(target=process_password_change)
            thread.start()
            
        else:
            # 格式错误
            self.safe_send_message(
                update,
                "❌ <b>格式错误</b>\n\n"
                "请使用以下格式之一：\n\n"
                "1️⃣ 仅新密码（推荐）\n"
                "<code>NewPassword123</code>\n\n"
                "2️⃣ 旧密码 新密码\n"
                "<code>OldPass456 NewPassword123</code>\n\n"
                "两个密码之间用空格分隔",
                'HTML'
            )
        
        return
    
    # 检查是否是账号分类数量输入
    try:
        conn = sqlite3.connect(config.DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            user_status = row[0]
            
            # 单个数量拆分
            if user_status == "waiting_classify_qty_single":
                try:
                    qty = int(text.strip())
                    if qty <= 0:
                        self.safe_send_message(update, "❌ 请输入大于0的正整数")
                        return
                    
                    # 处理单个数量拆分
                    def process_single_qty():
                        asyncio.run(self._classify_split_single_qty(update, context, user_id, qty))
                    threading.Thread(target=process_single_qty, daemon=True).start()
                    return
                except ValueError:
                    self.safe_send_message(update, "❌ 请输入有效的正整数")
                    return
            
            # 多个数量拆分
            elif user_status == "waiting_classify_qty_multi":
                try:
                    parts = text.strip().split()
                    quantities = [int(p) for p in parts]
                    if any(q <= 0 for q in quantities):
                        self.safe_send_message(update, "❌ 所有数量必须大于0")
                        return
                    
                    # 处理多个数量拆分
                    def process_multi_qty():
                        asyncio.run(self._classify_split_multi_qty(update, context, user_id, quantities))
                    threading.Thread(target=process_multi_qty, daemon=True).start()
                    return
                except ValueError:
                    self.safe_send_message(update, "❌ 请输入有效的正整数，用空格分隔\n例如: 10 20 30")
                    return
    except Exception as e:
        print(f"❌ 检查分类状态失败: {e}")
    # 管理员搜索用户
    if user_status == "waiting_admin_search":
        if not self.db.is_admin(user_id):
            self.safe_send_message(update, "❌ 权限不足")
            return
        
        search_query = text.strip()
        if len(search_query) < 2:
            self.safe_send_message(update, "❌ 搜索关键词太短，请至少输入2个字符")
            return
        
        # 执行搜索
        search_results = self.db.search_user(search_query)
        
        if not search_results:
            self.safe_send_message(update, f"🔍 未找到匹配 '{search_query}' 的用户")
            # 清空状态
            self.db.save_user(user_id, update.effective_user.username or "", update.effective_user.first_name or "", "")
            return
        
        # 显示搜索结果
        result_text = f"🔍 <b>搜索结果：'{search_query}'</b>\n\n"
        
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(search_results[:10], 1):
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "🎁" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"用户{uid}"
            if len(display_name) > 20:
                display_name = display_name[:20] + "..."
            
            result_text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code>\n"
            result_text += f"   👤 {display_name}\n"
            if username:
                result_text += f"   📱 @{username}\n"
            
            # 活跃状态
            if last_active:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
                    if time_diff.days == 0:
                        result_text += f"   🕒 {time_diff.seconds//3600}小时前活跃\n"
                    else:
                        result_text += f"   🕒 {time_diff.days}天前活跃\n"
                except:
                    result_text += f"   🕒 {last_active}\n"
            else:
                result_text += f"   🕒 从未活跃\n"
            
            result_text += "\n"
        
        if len(search_results) > 10:
            result_text += f"\n... 还有 {len(search_results) - 10} 个结果未显示"
        
        # 创建详情按钮（只显示前5个用户的详情按钮）
        buttons = []
        for i, (uid, username, first_name, _, _, _) in enumerate(search_results[:5]):
            display_name = first_name or username or f"用户{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            buttons.append([InlineKeyboardButton(f"📋 {display_name} 详情", callback_data=f"user_detail_{uid}")])
        
        buttons.append([InlineKeyboardButton("🔙 返回用户管理", callback_data="admin_users")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        self.safe_send_message(update, result_text, 'HTML', keyboard)
        
        # 清空状态
        self.db.save_user(user_id, update.effective_user.username or "", update.effective_user.first_name or "", "")
        return        
    # 其他文本消息的处理
    text_lower = text.lower()
    if any(word in text_lower for word in ["你好", "hello", "hi"]):
        self.safe_send_message(update, "👋 你好！发送 /start 开始检测")
    elif "帮助" in text_lower or "help" in text_lower:
        self.safe_send_message(update, "📖 发送 /help 查看帮助")

# ================================
# 账号分类功能
# ================================


    def classify_command(self, update: Update, context: CallbackContext):
    """账号分类命令入口"""
    user_id = update.effective_user.id
    
    # 权限检查
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 需要会员权限才能使用账号分类功能")
        return
    
    if not CLASSIFY_AVAILABLE or not self.classifier:
        self.safe_send_message(update, "❌ 账号分类功能不可用\n\n请检查 account_classifier.py 模块和 phonenumbers 库是否正确安装")
        return
    
    self.handle_classify_menu(update.callback_query if hasattr(update, 'callback_query') else None, update)


    def handle_classify_menu(self, query, update=None):
    """显示账号分类菜单"""
    if update is None:
        update = query.message if query else None
    
    user_id = query.from_user.id if query else update.effective_user.id
    
    # 权限检查
    is_member, _, _ = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        if query:
            self.safe_edit_message(query, "❌ 需要会员权限")
        else:
            self.safe_send_message(update, "❌ 需要会员权限")
        return
    
    if not CLASSIFY_AVAILABLE or not self.classifier:
        msg = "❌ 账号分类功能不可用\n\n请检查依赖库是否正确安装"
        if query:
            self.safe_edit_message(query, msg)
        else:
            self.safe_send_message(update, msg)
        return
    
    text = f"""

    def on_back_to_main(self, update: Update, context: CallbackContext):
    """处理"返回主菜单"按钮"""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        
        try:
            query.answer()
        except:
            pass
        
        # 清除用户状态 - 重置为空状态
        try:
            self.db.save_user(user_id, query.from_user.username or "", 
                            query.from_user.first_name or "", "")
        except Exception as e:
            logger.warning(f"清除用户状态失败: {e}")
        
        # 使用统一方法渲染主菜单（包含"📦 账号分类"按钮）
        self.show_main_menu(update, user_id)

    def _classify_buttons_split_type(self, user_id: int) -> InlineKeyboardMarkup:
    """生成拆分方式选择按钮"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, 'split_btn_country'), callback_data="classify_split_country")],
        [InlineKeyboardButton(t(user_id, 'split_btn_quantity'), callback_data="classify_split_quantity")],
        [InlineKeyboardButton(t(user_id, 'split_btn_cancel'), callback_data="back_to_main")]
    ])


    def _classify_buttons_qty_mode(self, user_id: int) -> InlineKeyboardMarkup:
    """生成数量模式选择按钮"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, 'split_btn_single'), callback_data="classify_qty_single")],
        [InlineKeyboardButton(t(user_id, 'split_btn_multiple'), callback_data="classify_qty_multi")],
        [InlineKeyboardButton(t(user_id, 'split_btn_back'), callback_data="classify_menu")]
    ])


    def handle_classify_callbacks(self, update, context, query, data):
    """处理分类相关的回调"""
    user_id = query.from_user.id
    
    if data == "classify_menu":
        self.handle_classify_menu(query)
    
    elif data == "classify_start":
        # 设置状态并提示上传
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_file"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_upload_prompt')}</b>\n\n"
                f"{t(user_id, 'split_formats')}\n"
                f"{t(user_id, 'split_format1')}\n"
                f"{t(user_id, 'split_format2')}\n"
                f"{t(user_id, 'split_format3')}\n\n"
                f"{t(user_id, 'split_size_limit')}\n"
                f"{t(user_id, 'split_timeout')}",
                parse_mode='HTML',
                reply_markup=get_back_to_menu_keyboard(user_id)
            )
        except:
            pass
    
    elif data == "classify_split_country":
        # 按国家拆分
        if user_id not in self.pending_classify_tasks:
            query.answer("❌ 任务已过期")
            return
        
        task = self.pending_classify_tasks[user_id]
        metas = task['metas']
        task_id = task['task_id']
        progress_msg = task['progress_msg']
        
        query.answer()
        
        def process_country():
            asyncio.run(self._classify_split_by_country(update, context, user_id))
        threading.Thread(target=process_country, daemon=True).start()
    
    elif data == "classify_split_quantity":
        # 按数量拆分 - 询问模式
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_quantity_mode')}</b>\n\n"
                f"<b>{t(user_id, 'split_single_quantity')}</b>\n"
                f"   {t(user_id, 'split_single_quantity_desc')}\n\n"
                f"<b>{t(user_id, 'split_multiple_quantity')}</b>\n"
                f"   {t(user_id, 'split_multiple_quantity_desc')}",
                parse_mode='HTML',
                reply_markup=self._classify_buttons_qty_mode(user_id)
            )
        except:
            pass
    
    elif data == "classify_qty_single":
        # 单个数量模式 - 等待输入
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_qty_single"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_enter_single')}</b>\n\n"
                f"{t(user_id, 'split_enter_single_example')}: <code>10</code>\n\n"
                f"{t(user_id, 'split_enter_single_desc')}\n"
                f"{t(user_id, 'split_enter_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass
    
    elif data == "classify_qty_multi":
        # 多个数量模式 - 等待输入
        self.db.save_user(
            user_id,
            query.from_user.username or "",
            query.from_user.first_name or "",
            "waiting_classify_qty_multi"
        )
        query.answer()
        try:
            query.edit_message_text(
                f"<b>{t(user_id, 'split_enter_multiple')}</b>\n\n"
                f"{t(user_id, 'split_enter_multiple_example')}: <code>10 20 30</code>\n\n"
                f"{t(user_id, 'split_enter_multiple_desc')}\n"
                f"{t(user_id, 'split_enter_multiple_remainder')}\n"
                f"{t(user_id, 'split_enter_timeout')}",
                parse_mode='HTML'
            )
        except:
            pass

async def _classify_split_by_country(self, update, context, user_id):
    """按国家拆分"""
    if user_id not in self.pending_classify_tasks:
        self.safe_send_message(update, t(user_id, 'split_error_no_task'))
        return
    
    task = self.pending_classify_tasks[user_id]
    metas = task['metas']
    task_id = task['task_id']
    progress_msg = task['progress_msg']
    
    out_dir = os.path.join(config.RESULTS_DIR, f"classify_{task_id}")
    try:
        # 更新提示
        try:
            progress_msg.edit_text(
                f"<b>{t(user_id, 'split_processing_country')}</b>\n\n{t(user_id, 'split_processing_country_desc')}",
                parse_mode='HTML'
            )
        except:
            pass
        
        bundles = self.classifier.split_by_country(metas, out_dir, t_func=lambda key: t(user_id, key))
        
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
            f"{t(user_id, 'split_result_total').format(count=len(metas))}\n"
            f"{t(user_id, 'split_result_sent').format(count=sent)}\n"
            f"{t(user_id, 'split_result_method_country')}\n\n"
            f"{t(user_id, 'split_use_again')}",
            'HTML'
        )
    
    except Exception as e:
        print(f"❌ 国家拆分失败: {e}")
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

# ================================
# VIP会员功能
# ================================


    def handle_usdt_plan_select(self, query, plan_id: str):
    """处理套餐选择"""
    user_id = query.from_user.id
    query.answer()
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentConfig, OrderManager, PaymentDatabase, QRCodeGenerator
        from io import BytesIO
        
        # 创建订单
        payment_db = PaymentDatabase()
        order_manager = OrderManager(payment_db)
        
        order = order_manager.create_payment_order(user_id, plan_id)
        
        if not order:
            error_create_failed = t(user_id, 'payment_error_create_failed')
            self.safe_edit_message(query, error_create_failed, 'HTML')
            return
        
        # 获取套餐信息
        plan = PaymentConfig.PAYMENT_PLANS.get(plan_id, {})
        days = plan.get("days", 0)
        
        # 获取套餐名称 - 使用 i18n
        plan_name_key_map = {
            'plan_7d': 'payment_plan_name_7d',
            'plan_30d': 'payment_plan_name_30d',
            'plan_120d': 'payment_plan_name_120d',
            'plan_365d': 'payment_plan_name_365d',
        }
        plan_name_key = plan_name_key_map.get(plan_id, 'payment_plan_name_7d')
        plan_name = t(user_id, plan_name_key)
        
        # 生成二维码
        qr_bytes = QRCodeGenerator.generate_payment_qr(
            PaymentConfig.WALLET_ADDRESS,
            order.amount
        )
        
        # 计算过期时间
        from datetime import datetime, timezone, timedelta
        BEIJING_TZ = timezone(timedelta(hours=8))
        now = datetime.now(BEIJING_TZ)
        expires_at = order.expires_at.replace(tzinfo=BEIJING_TZ)
        
        # 计算剩余时间（分钟和秒）
        remaining_seconds = (expires_at - now).total_seconds()
        remaining_minutes = max(0, int(remaining_seconds // 60))
        remaining_secs = max(0, int(remaining_seconds % 60))
        
        # 使用 i18n 构建支付信息
        order_info_title = t(user_id, 'payment_order_info_title')
        order_id_label = t(user_id, 'payment_order_id')
        plan_label = t(user_id, 'payment_plan')
        days_label = t(user_id, 'payment_days')
        amount_label = t(user_id, 'payment_amount')
        valid_time_label = t(user_id, 'payment_valid_time')
        minutes_label = t(user_id, 'payment_minutes')
        seconds_label = t(user_id, 'payment_seconds')
        wallet_addr_label = t(user_id, 'payment_wallet_address')
        addr_click_copy = t(user_id, 'payment_address_click_copy')
        important_notice = t(user_id, 'payment_important_notice')
        notice_1 = t(user_id, 'payment_notice_1')
        notice_2 = t(user_id, 'payment_notice_2')
        notice_3 = t(user_id, 'payment_notice_3')
        notice_4 = t(user_id, 'payment_notice_4')
        scan_qr = t(user_id, 'payment_scan_qr')
        scan_desc = t(user_id, 'payment_scan_desc')
        
        # 发送二维码和支付信息
        caption = f"""

    def handle_cancel_order(self, query, order_id: str):
    """处理取消订单"""
    user_id = query.from_user.id
    query.answer()
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderManager, OrderStatus
        
        payment_db = PaymentDatabase()
        order_manager = OrderManager(payment_db)
        
        # 获取订单信息以验证权限
        order = payment_db.get_order(order_id)
        
        if not order:
            error_not_found = t(user_id, 'payment_error_not_found')
            query.answer(error_not_found, show_alert=True)
            return
        
        if order.user_id != user_id:
            query.answer("❌ 无权操作此订单", show_alert=True)
            return
        
        if order.status.value != 'pending':
            query.answer(f"❌ 订单状态为 {order.status.value}，无法取消", show_alert=True)
            return
        
        # 取消订单
        success = order_manager.cancel_order(order_id)
        
        if success:
            order_cancelled = t(user_id, 'payment_order_cancelled')
            query.answer(order_cancelled, show_alert=True)
            
            # 删除原订单消息（使用保存的 message_id）
            try:
                message_id = payment_db.get_order_message_id(order_id)
                if message_id:
                    query.bot.delete_message(chat_id=user_id, message_id=message_id)
                    logger.info(f"✅ 已删除订单消息: {message_id}")
            except Exception as e:
                logger.warning(f"删除订单消息失败: {e}")
            
            # 同时尝试删除当前回调消息
            try:
                query.message.delete()
            except Exception as e:
                logger.warning(f"删除当前消息失败: {e}")
            
            # 发送新的纯文本消息 - 使用 i18n
            try:
                from telegram import Bot
                bot = query.bot if hasattr(query, 'bot') else Bot(token=os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"))
                
                cancelled_title = t(user_id, 'payment_order_cancelled_title')
                order_id_label = t(user_id, 'payment_order_id')
                status_label = t(user_id, 'payment_status')
                cancelled_status = t(user_id, 'payment_order_cancelled_status')
                repurchase_hint = t(user_id, 'payment_repurchase_hint')
                repurchase_btn = t(user_id, 'btn_repurchase')
                back_main_btn = t(user_id, 'btn_back_main_menu')
                
                text = f"""

    def handle_redeem_code_input(self, update, user_id: int, code: str):
    """处理用户输入的兑换码"""
    # 清除状态
    self.db.save_user(user_id, "", "", "")
    
    # 验证兑换码
    code = code.strip()
    if len(code) > 10:
        self.safe_send_message(update, f"❌ {t(user_id, 'redeem_input_prompt')}")
        return
    
    # 执行兑换
    success, message, days = self.db.redeem_code(user_id, code)
    
    if success:
        # 获取新的会员状态
        is_member, level, expiry = self.db.check_membership(user_id)
        
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        
        text = f"""

    def handle_manual_user_input(self, update, admin_id: int, text: str):
    """处理管理员输入的用户信息"""
    # 清除状态
    self.db.save_user(admin_id, "", "", "")
    
    # 解析用户输入
    text = text.strip()
    target_user_id = None
    
    # 尝试作为用户ID解析
    if text.isdigit():
        target_user_id = int(text)
    else:
        # 尝试作为用户名解析
        username = text.replace("@", "")
        target_user_id = self.db.get_user_id_by_username(username)
    
    if not target_user_id:
        self.safe_send_message(
            update,
            "❌ <b>用户不存在</b>\n\n"
            "该用户未与机器人交互过，请确认：\n"
            "• 用户ID或用户名正确\n"
            "• 用户已发送过 /start 命令",
            'HTML'
        )
        return
    
    # 获取用户信息
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        self.safe_send_message(
            update,
            "❌ <b>用户不存在</b>\n\n"
            "该用户未与机器人交互过",
            'HTML'
        )
        return
    
    # 保存到待处理列表
    self.pending_manual_open[admin_id] = target_user_id
    
    # 获取用户会员信息
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    if is_member:
        member_status = f"💎 {level}\n• 到期: {expiry}"
    else:
        member_status = "❌ 暂无会员"
    
    text = f"""

    def handle_revoke_user_input(self, update, admin_id: int, text: str):
    """处理管理员输入的要撤销的用户信息"""
    # 清除状态
    self.db.save_user(admin_id, "", "", "")
    
    # 解析用户输入
    text = text.strip()
    target_user_id = None
    
    # 尝试作为用户ID解析
    if text.isdigit():
        target_user_id = int(text)
    else:
        # 尝试作为用户名解析
        username = text.replace("@", "")
        user_row = self.db.get_user_by_username(username)
        if user_row:
            target_user_id = user_row[0]
    
    if not target_user_id:
        self.safe_send_message(
            update,
            "❌ <b>未找到该用户</b>\n\n"
            "未找到该用户，请确认对方已与机器人对话入库",
            'HTML'
        )
        return
    
    # 获取用户信息
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        self.safe_send_message(
            update,
            "❌ <b>未找到该用户</b>\n\n"
            "未找到该用户，请确认对方已与机器人对话入库",
            'HTML'
        )
        return
    
    # 获取用户会员信息
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    if is_member:
        member_status = f"💎 {level}\n• 到期时间: {expiry}"
    else:
        member_status = "❌ 暂无会员"
    
    text = f"""

    def show_target_selection(self, update, context, user_id):
    """显示目标用户选择"""
    if user_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[user_id]
    task['step'] = 'target'
    
    # 更新状态
    self.db.save_user(user_id, "", "", "")
    
    # 获取各类用户数量
    all_users = len(self.db.get_target_users('all'))
    members = len(self.db.get_target_users('members'))
    active_7d = len(self.db.get_target_users('active_7d'))
    new_7d = len(self.db.get_target_users('new_7d'))
    
    text = f"""

    def extract_phone_from_json(self, json_path: str) -> Optional[str]:
    """从JSON文件中提取手机号"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            phone = data.get('phone', '')
            if phone:
                # 清理手机号格式：移除+号和其他非数字字符
                phone_clean = ''.join(c for c in phone if c.isdigit())
                if phone_clean and len(phone_clean) >= 10:
                    return phone_clean
    except Exception as e:
        print(f"⚠️ 从JSON提取手机号失败 {json_path}: {e}")
    return None


    def _is_frozen_error(self, error: Exception) -> bool:
    """检查是否为冻结账户错误"""
    error_str = str(error).upper()
    return any(keyword in error_str for keyword in self.FROZEN_KEYWORDS)

async def _cleanup_single_account(self, client, account_name: str, file_path: str, progress_callback=None, user_id: int = None) -> Dict[str, Any]:
    """清理单个账号"""
    start_time = time.time()
    
    actions = []
    stats = {
        'profile_cleared': 0,
        'groups_left': 0,
        'channels_left': 0,
        'histories_deleted': 0,
        'contacts_deleted': 0,
        'dialogs_closed': 0,
        'errors': 0,
        'skipped': 0
    }
    
    # 用于详细报告的错误列表
    error_details = []
    
    try:
        # 0. 清理账号资料（头像、名字、简介）
        logger.info(f"清理账号资料: {account_name}")
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_profile'))
        
        try:
            # 添加超时保护
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                from telethon.tl.functions.account import UpdateProfileRequest
                from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
                
                # 获取当前账号信息
                me = await client.get_me()
            
            # 随机修改名字和简介为符号字母
            profile_cleared = False
            try:
                # 生成随机符号字母组合（使用secrets确保随机性）
                charset = string.ascii_letters + string.digits + '._-'
                random_chars = ''.join(secrets.choice(charset) for _ in range(secrets.randbelow(6) + 3))  # 3-8位
                random_bio = ''.join(secrets.choice(charset + ' ') for _ in range(secrets.randbelow(11) + 5))  # 5-15位
                
                await client(UpdateProfileRequest(
                    first_name=random_chars,  # 随机名字
                    last_name='',              # 清空姓氏
                    about=random_bio           # 随机简介
                ))
                logger.info(f"已修改名字和简介为随机字符: {random_chars}")
                profile_cleared = True
            except Exception as e:
                logger.warning(f"修改名字/简介失败: {e}")
                # 检查是否为冻结账户
                if self._is_frozen_error(e):
                    error_details.append(f"❄️ 账户已冻结 (FROZEN): {str(e)}")
                    logger.error(f"检测到冻结账户，终止清理: {account_name}")
                    return {
                        'success': False,
                        'error': 'FROZEN_ACCOUNT',
                        'error_message': f"账户已冻结: {str(e)}",
                        'statistics': stats,
                        'error_details': error_details,
                        'is_frozen': True
                    }
                error_details.append(f"修改资料失败: {str(e)}")
            
            # 删除所有头像
            try:
                photos = await client(GetUserPhotosRequest(
                    user_id=me,
                    offset=0,
                    max_id=0,
                    limit=100
                ))
                
                if hasattr(photos, 'photos') and photos.photos:
                    photo_ids = list(photos.photos)
                    await client(DeletePhotosRequest(id=photo_ids))
                    logger.info(f"已删除 {len(photo_ids)} 个头像")
                    if profile_cleared:
                        stats['profile_cleared'] = 1
            except Exception as e:
                logger.warning(f"删除头像失败: {e}")
            
            await asyncio.sleep(config.CLEANUP_ACTION_SLEEP)
            
        except asyncio.TimeoutError:
            logger.warning(f"清理账号资料超时 ({CLEANUP_OPERATION_TIMEOUT}秒)")
            stats['errors'] += 1
            error_details.append(f"清理账号资料超时")
        except Exception as e:
            logger.error(f"清理账号资料错误: {e}")
            stats['errors'] += 1
        
        # 1. 获取所有对话
        logger.info(f"获取对话列表: {account_name}")
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_get_dialogs'))
        
        dialogs = await client.get_dialogs()
        logger.info(f"找到 {len(dialogs)} 个对话")
        
        # 分类对话
        from telethon.tl.types import Channel, Chat, User
        groups = []
        channels = []
        users = []
        bots = []
        
        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, Channel):
                if entity.broadcast:
                    channels.append(dialog)
                else:
                    groups.append(dialog)
            elif isinstance(entity, Chat):
                groups.append(dialog)
            elif isinstance(entity, User):
                if entity.bot:
                    bots.append(dialog)
                else:
                    users.append(dialog)
        
        logger.info(f"分类: {len(groups)}群组, {len(channels)}频道, {len(users)}用户, {len(bots)}机器人")
        
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_found_dialogs').format(
                groups=len(groups), 
                channels=len(channels), 
                users=len(users)
            ))
        
        # 1. 离开群组和频道
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_leave_groups').format(
                count=len(groups) + len(channels)
            ))
        from telethon.tl.functions.channels import LeaveChannelRequest
        from telethon.tl.functions.messages import DeleteChatUserRequest
        
        # 添加超时保护，防止卡死
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                for dialog in groups + channels:
                    entity = dialog.entity
                    chat_id = entity.id
                    title = getattr(entity, 'title', 'Unknown')
                    chat_type = 'channel' if isinstance(entity, Channel) and entity.broadcast else 'group'
                    
                    action = CleanupAction(chat_id=chat_id, title=title, chat_type=chat_type)
                    
                    try:
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP + random.uniform(0, 0.2))
                        
                        if isinstance(entity, Channel):
                            await client(LeaveChannelRequest(entity))
                        else:
                            me = await client.get_me()
                            await client(DeleteChatUserRequest(chat_id, me))
                        
                        action.actions_done.append('left')
                        action.status = 'success'
                        
                        if chat_type == 'channel':
                            stats['channels_left'] += 1
                        else:
                            stats['groups_left'] += 1
                        
                        logger.debug(f"离开 {chat_type}: {title}")
                        
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait离开{title}: {e.seconds}秒 - 跳过以避免卡住")
                            action.status = 'skipped'
                            action.error = f"FloodWait {e.seconds}秒，已跳过"
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait离开{title}: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                if isinstance(entity, Channel):
                                    await client(LeaveChannelRequest(entity))
                                else:
                                    me = await client.get_me()
                                    await client(DeleteChatUserRequest(chat_id, me))
                                action.actions_done.append('left')
                                action.status = 'success'
                                if chat_type == 'channel':
                                    stats['channels_left'] += 1
                                else:
                                    stats['groups_left'] += 1
                            except Exception as retry_error:
                                action.status = 'failed'
                                action.error = f"重试失败: {str(retry_error)}"
                                stats['errors'] += 1
                        
                    except Exception as e:
                        action.status = 'failed'
                        action.error = str(e)
                        stats['errors'] += 1
                        logger.error(f"离开{title}错误: {e}")
                    
                    actions.append(action)
        
        except asyncio.TimeoutError:
            logger.warning(f"退出群组/频道操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已处理 {stats['groups_left'] + stats['channels_left']} 个")
            error_details.append(f"退出群组/频道超时")
            stats['skipped'] += 1
        
        # 2. 删除聊天记录
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_delete_histories').format(
                count=len(users) + len(bots)
            ))
        
        from telethon.tl.functions.messages import DeleteHistoryRequest
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                for dialog in users + bots:
                    entity = dialog.entity
                    chat_id = entity.id
                    
                    if hasattr(entity, 'first_name') and entity.first_name:
                        title = entity.first_name
                    elif hasattr(entity, 'username') and entity.username:
                        title = entity.username
                    else:
                        title = 'Unknown'
                    
                    chat_type = 'bot' if entity.bot else 'user'
                    action = CleanupAction(chat_id=chat_id, title=title, chat_type=chat_type)
                    
                    try:
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP + random.uniform(0, 0.2))
                        
                        # 尝试撤回删除
                        if config.CLEANUP_REVOKE_DEFAULT:
                            try:
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=True
                                ))
                                action.actions_done.extend(['history_deleted', 'revoked'])
                                action.status = 'success'
                            except Exception:
                                # 回退到单向删除
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=False
                                ))
                                action.actions_done.append('history_deleted')
                                action.status = 'partial'
                                action.error = '部分: 仅删除自己的消息'
                        else:
                            await client(DeleteHistoryRequest(
                                peer=entity,
                                max_id=0,
                                just_clear=False,
                                revoke=False
                            ))
                            action.actions_done.append('history_deleted')
                            action.status = 'success'
                        
                        stats['histories_deleted'] += 1
                        logger.debug(f"删除历史记录: {title}")
                        
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait删除{title}: {e.seconds}秒 - 跳过以避免卡住")
                            action.status = 'skipped'
                            action.error = f"FloodWait {e.seconds}秒，已跳过"
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait删除{title}: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                await client(DeleteHistoryRequest(
                                    peer=entity,
                                    max_id=0,
                                    just_clear=False,
                                    revoke=False
                                ))
                                action.actions_done.append('history_deleted')
                                action.status = 'success'
                                stats['histories_deleted'] += 1
                            except Exception as retry_error:
                                action.status = 'failed'
                                action.error = f"重试失败: {str(retry_error)}"
                                stats['errors'] += 1
                        
                    except Exception as e:
                        action.status = 'failed'
                        action.error = str(e)
                        stats['errors'] += 1
                        logger.error(f"删除{title}历史记录错误: {e}")
                    
                    actions.append(action)
        
        except asyncio.TimeoutError:
            logger.warning(f"删除对话记录操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已处理 {stats['histories_deleted']} 个")
            error_details.append(f"删除对话记录超时")
            stats['skipped'] += 1
        
        # 3. 删除联系人
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_delete_contacts'))
        
        from telethon.tl.functions.contacts import DeleteContactsRequest, GetContactsRequest
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                result = await client(GetContactsRequest(hash=0))
                
                if hasattr(result, 'users') and result.users:
                    contact_ids = [user.id for user in result.users]
                    logger.info(f"删除 {len(contact_ids)} 个联系人...")
                    
                    batch_size = 100
                    for i in range(0, len(contact_ids), batch_size):
                        batch = contact_ids[i:i + batch_size]
                        
                        try:
                            await client(DeleteContactsRequest(id=batch))
                            stats['contacts_deleted'] += len(batch)
                            logger.debug(f"已删除 {len(batch)} 个联系人")
                            
                            if i + batch_size < len(contact_ids):
                                await asyncio.sleep(config.CLEANUP_ACTION_SLEEP * 2)
                                
                        except FloodWaitError as e:
                            # 如果等待时间超过60秒，跳过以避免卡住
                            if e.seconds > 60:
                                logger.warning(f"FloodWait删除联系人: {e.seconds}秒 - 跳过以避免卡住")
                                stats['skipped'] += 1
                            else:
                                logger.warning(f"FloodWait删除联系人: {e.seconds}秒")
                                await asyncio.sleep(e.seconds)
                                try:
                                    await client(DeleteContactsRequest(id=batch))
                                    stats['contacts_deleted'] += len(batch)
                                except Exception:
                                    stats['errors'] += 1
                        
                        except Exception as e:
                            stats['errors'] += 1
                            logger.error(f"删除联系人批次错误: {e}")
                    
                    logger.info(f"已删除 {stats['contacts_deleted']} 个联系人")
        
        except asyncio.TimeoutError:
            logger.warning(f"删除联系人操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)，已删除 {stats['contacts_deleted']} 个")
            error_details.append(f"删除联系人超时")
            stats['skipped'] += 1
        except Exception as e:
            stats['errors'] += 1
            logger.error(f"获取/删除联系人错误: {e}")
        
        # 4. 归档剩余对话
        if progress_callback and user_id:
            await progress_callback(t(user_id, 'cleanup_status_archive_dialogs'))
        
        # 添加超时保护
        try:
            async with asyncio.timeout(CLEANUP_OPERATION_TIMEOUT):
                remaining_dialogs = await client.get_dialogs()
                archived_count = 0
                
                for dialog in remaining_dialogs:
                    try:
                        await client.edit_folder(dialog.entity, folder=1)
                        archived_count += 1
                        await asyncio.sleep(config.CLEANUP_ACTION_SLEEP)
                    except FloodWaitError as e:
                        # 如果等待时间超过60秒，跳过以避免卡住
                        if e.seconds > 60:
                            logger.warning(f"FloodWait归档: {e.seconds}秒 - 跳过以避免卡住")
                            stats['skipped'] += 1
                        else:
                            logger.warning(f"FloodWait归档: {e.seconds}秒")
                            await asyncio.sleep(e.seconds)
                            try:
                                await client.edit_folder(dialog.entity, folder=1)
                                archived_count += 1
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"无法归档对话: {e}")
                
                stats['dialogs_closed'] = archived_count
                logger.info(f"已归档 {archived_count} 个对话")
        
        except asyncio.TimeoutError:
            logger.warning(f"归档对话操作超时 ({CLEANUP_OPERATION_TIMEOUT}秒)")
            error_details.append(f"归档对话超时")
            stats['skipped'] += 1
        except Exception as e:
            logger.error(f"归档对话错误: {e}")
        
        # 返回清理结果（不生成单独报告）
        elapsed_time = time.time() - start_time
        
        return {
            'success': True,
            'elapsed_time': elapsed_time,
            'statistics': stats,
            'actions': actions  # 返回动作列表用于汇总报告
        }
        
    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'statistics': stats
        }


    def _create_fake_update(self, user_id: int):
    """创建一个假的update对象用于内部调用"""
    return type('obj', (object,), {
        'effective_chat': type('obj', (object,), {'id': user_id})(),
        'effective_user': type('obj', (object,), {'id': user_id})(),
        'message': None  # 设置为None，强制使用bot.send_message而不是reply_text
    })()


    def _estimate_registration_date_from_user_id(self, user_id: int) -> str:
    """
    基于用户ID估算注册日期（年-月-日格式）
    
    ⚠️ 警告：这个方法非常不准确，可能相差数年！
    Telegram用户ID不是严格按注册顺序递增的。
    
    仅当官方API和所有聊天记录方法都失败时使用此方法。
    
    返回格式: YYYY-MM-DD 或 YYYY-MM
    """
    # 基于历史数据的ID范围映射（这些是估算值，非精确值）
    # 已知的参考点（需要定期更新）
    reference_points = [
        (1, "2013-08"),           # Telegram 创始人
        (100000000, "2014-10"),   # 约1亿用户
        (500000000, "2017-06"),   # 约5亿用户
        (1000000000, "2020-01"),  # 约10亿用户
        (2000000000, "2021-09"),  # 约20亿用户
        (5000000000, "2023-01"),  # 约50亿用户
        (7000000000, "2024-06"),  # 约70亿用户
    ]
    
    user_id = int(user_id)
    
    # 找到最接近的参考点进行线性插值
    for i in range(len(reference_points) - 1):
        id1, date1 = reference_points[i]
        id2, date2 = reference_points[i + 1]
        
        if id1 <= user_id <= id2:
            # 线性插值
            ratio = (user_id - id1) / (id2 - id1)
            
            # 解析日期
            d1 = datetime.strptime(date1, "%Y-%m")
            d2 = datetime.strptime(date2, "%Y-%m")
            
            # 计算估算日期
            delta = d2 - d1
            estimated = d1 + delta * ratio
            
            return estimated.strftime("%Y-%m")
    
    # 如果超出范围，返回最近的参考点
    if user_id < reference_points[0][0]:
        return reference_points[0][1]
    else:
        return reference_points[-1][1]

# ================================
# 资料修改功能处理方法
# ================================


    def _show_random_config_menu(self, query, user_id: int, config: ProfileUpdateConfig):
    """显示随机模式配置菜单"""
    # 头像选项显示
    if config.photo_action == 'delete_all':
        photo_status = t(user_id, 'profile_display_delete_all')
    else:
        photo_status = t(user_id, 'profile_display_keep')
    
    # 简介选项显示
    if config.bio_action == 'clear':
        bio_status = t(user_id, 'profile_display_clear')
    elif config.bio_action == 'random':
        bio_status = t(user_id, 'profile_display_random')
    else:
        bio_status = t(user_id, 'profile_display_no_modify')
    
    # 用户名选项显示
    if config.username_action == 'delete':
        username_status = t(user_id, 'profile_display_delete')
    elif config.username_action == 'random':
        username_status = t(user_id, 'profile_display_random')
    else:
        username_status = t(user_id, 'profile_display_no_modify')
    
    text = f"""

    def _show_custom_config_menu(self, query, user_id: int, config: ProfileUpdateConfig):
    """显示自定义模式配置菜单"""
    # 姓名状态显示
    if config.update_name and config.custom_names:
        name_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_names))
    elif config.update_name:
        name_status = t(user_id, 'profile_custom_status_pending')
    else:
        name_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 头像状态显示
    if config.update_photo:
        if config.photo_action == 'delete_all':
            photo_status = t(user_id, 'profile_display_delete_all')
        elif config.photo_action == 'custom' and config.custom_photos:
            photo_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_photos))
        elif config.photo_action == 'custom':
            photo_status = t(user_id, 'profile_custom_status_pending')
        else:
            photo_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        photo_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 简介状态显示
    if config.update_bio:
        if config.bio_action == 'clear':
            bio_status = t(user_id, 'profile_display_clear')
        elif config.bio_action == 'custom' and config.custom_bios:
            bio_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_bios))
        elif config.bio_action == 'custom':
            bio_status = t(user_id, 'profile_custom_status_pending')
        else:
            bio_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        bio_status = t(user_id, 'profile_custom_status_no_modify')
    
    # 用户名状态显示
    if config.update_username:
        if config.username_action == 'delete':
            username_status = t(user_id, 'profile_display_delete')
        elif config.username_action == 'custom' and config.custom_usernames:
            username_status = t(user_id, 'profile_custom_status_configured').format(count=len(config.custom_usernames))
        elif config.username_action == 'custom':
            username_status = t(user_id, 'profile_custom_status_pending')
        else:
            username_status = t(user_id, 'profile_custom_status_no_modify')
    else:
        username_status = t(user_id, 'profile_custom_status_no_modify')
    
    text = f"""

    def _show_custom_field_config(self, query, user_id: int, field: str, field_name: str):
    """显示字段配置选项"""
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    
    # 记录当前正在配置的字段
    task['custom_input_field'] = field
    
    # 根据字段类型显示不同的选项
    text = f"<b>{t(user_id, 'profile_custom_field_config').format(field=field_name)}</b>\n\n{t(user_id, 'profile_custom_field_select')}"
    
    keyboard_buttons = []
    
    if field == 'name':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_names:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_names)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'photo':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_images'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_delete_all_avatar'), callback_data=f"profile_custom_field_{field}_delete")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_photos:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_photos)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'bio':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_bio'), callback_data=f"profile_custom_field_{field}_clear_bio")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_bios:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_bios)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    elif field == 'username':
        keyboard_buttons = [
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_upload_txt'), callback_data=f"profile_custom_field_{field}_upload")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_manual_input'), callback_data=f"profile_custom_field_{field}_manual")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_delete_username'), callback_data=f"profile_custom_field_{field}_delete_username")],
            [InlineKeyboardButton(t(user_id, 'profile_custom_field_no_modify'), callback_data=f"profile_custom_field_{field}_skip")],
        ]
        if config.custom_usernames:
            keyboard_buttons.insert(0, [InlineKeyboardButton(t(user_id, 'profile_custom_field_view_configured').format(count=len(config.custom_usernames)), callback_data=f"profile_custom_field_{field}_view")])
            keyboard_buttons.insert(1, [InlineKeyboardButton(t(user_id, 'profile_custom_field_clear_config'), callback_data=f"profile_custom_field_{field}_clear")])
    
    keyboard_buttons.append([InlineKeyboardButton(t(user_id, 'profile_custom_field_back_to_menu'), callback_data="profile_custom_back")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )


    def _handle_custom_field_action(self, update: Update, context: CallbackContext, query, data: str, user_id: int):
    """处理字段配置动作"""
    if user_id not in self.pending_profile_update:
        query.answer(t(user_id, 'profile_session_expired'))
        return
    
    config = self.pending_profile_update[user_id]['config']
    task = self.pending_profile_update[user_id]
    field = task.get('custom_input_field', '')
    
    # 解析动作
    parts = data.replace("profile_custom_field_", "").split("_", 1)
    
    # 如果没有动作（即只有字段名），则显示字段配置菜单（返回上一步）
    if len(parts) < 2 or parts[1] == "":
        field_name = parts[0]
        # 清除用户状态（从上传/输入状态返回）
        self.db.save_user(user_id, "", "", "profile_custom_config")
        # Helper function to get translated field display name
        field_map = {
            'name': 'profile_field_name',
            'photo': 'profile_field_avatar',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        field_display = t(user_id, field_map.get(field_name, 'profile_field_name'))
        self._show_custom_field_config(query, user_id, field_name, field_display)
        return
    
    field_name, action = parts[0], parts[1]
    
    # Helper function to get translated field display name
    def get_field_display(field):
        field_map = {
            'name': 'profile_field_name',
            'photo': 'profile_field_avatar',
            'bio': 'profile_field_bio',
            'username': 'profile_field_username'
        }
        return t(user_id, field_map.get(field, 'profile_field_name'))
    
    if action == "upload":
        # 请求用户上传文件
        field_display = get_field_display(field_name)
        
        if field_name == 'photo':
            text = f"""

    def translate_contact_status_message(self, user_id, status, original_message):
    """翻译通讯录检测状态消息"""
    # 根据状态码返回翻译的消息
    if status == CONTACT_STATUS_NORMAL:
        return t(user_id, 'contact_limit_status_normal')
    elif status == CONTACT_STATUS_LIMITED:
        # 检查是否是FloodWait
        if 'FloodWait' in original_message or 'flood' in original_message.lower():
            return t(user_id, 'contact_limit_status_flood_wait')
        return t(user_id, 'contact_limit_status_limited')
    elif status == CONTACT_STATUS_BANNED:
        return t(user_id, 'contact_limit_status_banned')
    elif status == CONTACT_STATUS_UNAUTHORIZED:
        return t(user_id, 'contact_limit_status_auth_error')
    elif status == CONTACT_STATUS_ERROR:
        # 检查错误类型
        if '连接错误' in original_message or 'Connection' in original_message:
            # 提取错误信息
            error_part = original_message.split(':')[-1].strip() if ':' in original_message else original_message
            return t(user_id, 'contact_limit_status_connection_error').format(error=error_part[:30])
        return original_message  # 保留原始错误消息
    return original_message

async def generate_contact_limit_report(self, results, output_dir, user_id):
    """生成通讯录限制检测报告"""
    
    # 翻译所有结果中的status message
    translated_results = []
    for r in results:
        translated_r = r.copy()
        if 'message' in translated_r:
            translated_r['message'] = self.translate_contact_status_message(
                user_id, 
                r.get('status'), 
                r.get('message', '')
            )
        translated_results.append(translated_r)
    
    # 分类统计 - 使用常量
    normal = [r for r in translated_results if r.get('status') == CONTACT_STATUS_NORMAL]
    limited = [r for r in translated_results if r.get('status') == CONTACT_STATUS_LIMITED]
    banned = [r for r in translated_results if r.get('status') == CONTACT_STATUS_BANNED]
    failed = [r for r in translated_results if r.get('status') in [CONTACT_STATUS_ERROR, CONTACT_STATUS_UNAUTHORIZED]]
    
    # 生成报告文本
    report = f"""

    def _generate_registration_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成注册时间查询报告和打包结果（按年-月-日分类）"""
    logger.info("📊 开始生成报告和打包结果...")
    print("📊 开始生成报告和打包结果...", flush=True)
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    
    # 统计
    total = sum(len(v) for v in results.values())
    success_count = len(results['success'])
    error_count = len(results['error']) + len(results['frozen']) + len(results['banned'])
    
    # 按年-月-日（完整日期）分类
    by_date = {}
    for file_path, file_name, result in results['success']:
        reg_date = result.get('registration_date', '未知')
        if reg_date not in by_date:
            by_date[reg_date] = []
        by_date[reg_date].append((file_path, file_name, result))
    
    # 生成文本报告
    report_filename = f"registration_report_{timestamp}.txt"
    report_path = os.path.join(config.RESULTS_DIR, report_filename)
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_report_title')}\n")
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
            f.write(f"{t(user_id, 'regtime_report_total')} {total}\n")
            f.write(f"{t(user_id, 'regtime_report_success')} {success_count}\n")
            f.write(f"{t(user_id, 'regtime_report_failed')} {error_count}\n")
            f.write("=" * 80 + "\n\n")
            
            # 按日期统计（排序）
            f.write(f"{t(user_id, 'regtime_report_classify')}\n")
            f.write("-" * 80 + "\n")
            f.write(f"{t(user_id, 'regtime_source_title')}\n")
            f.write(f"{t(user_id, 'regtime_source_api')}\n")
            f.write(f"{t(user_id, 'regtime_source_all_chats')}\n")
            f.write(f"{t(user_id, 'regtime_source_telegram')}\n")
            f.write(f"{t(user_id, 'regtime_source_saved')}\n")
            f.write(f"{t(user_id, 'regtime_source_estimated')}\n")
            f.write("-" * 80 + "\n\n")
            
            for reg_date in sorted(by_date.keys()):
                f.write(f"\n{t(user_id, 'regtime_date_header').format(date=reg_date, count=len(by_date[reg_date]))}\n")
                f.write("-" * 40 + "\n")
                for file_path, file_name, result in by_date[reg_date]:
                    f.write(f"{t(user_id, 'regtime_field_file')} {file_name}\n")
                    f.write(f"{t(user_id, 'regtime_field_phone')} {result['phone']}\n")
                    f.write(f"{t(user_id, 'regtime_field_userid')} {result['user_id']}\n")
                    if result.get('username'):
                        f.write(f"{t(user_id, 'regtime_field_username')} @{result['username']}\n")
                    f.write(f"{t(user_id, 'regtime_field_name')} {result['first_name']} {result['last_name']}\n")
                    f.write(f"{t(user_id, 'regtime_field_common_groups')} {result['common_chats']}\n")
                    
                    # 显示数据来源，区分官方数据和估算数据
                    source = result.get('registration_source', 'estimated')
                    if source in ['telegram_api', 'full_user_api']:
                        # 官方API数据 - 最准确
                        source_display = t(user_id, 'regtime_source_api').replace('• telegram_api / full_user_api: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'all_chats':
                        # 从所有对话扫描获取
                        source_display = t(user_id, 'regtime_source_all_chats').replace('• all_chats: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'telegram_chat':
                        # 从Telegram官方对话获取
                        source_display = t(user_id, 'regtime_source_telegram').replace('• telegram_chat: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    elif source == 'saved_messages':
                        # 从收藏夹获取
                        source_display = t(user_id, 'regtime_source_saved').replace('• saved_messages: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    else:
                        # ID估算 - 不准确，添加警告
                        source_display = t(user_id, 'regtime_source_estimated').replace('• estimated: ', '')
                        f.write(f"{t(user_id, 'regtime_field_source')} {source_display}\n")
                    f.write("\n")
            
            # 失败的账号
            if error_count > 0:
                f.write(f"\n{t(user_id, 'regtime_failed_accounts')}\n")
                f.write("-" * 80 + "\n")
                for category in ['error', 'frozen', 'banned']:
                    if results[category]:
                        f.write(f"\n{t(user_id, 'regtime_error_label')} {category.upper()}:\n")
                        for file_path, file_name, result in results[category]:
                            f.write(f"{t(user_id, 'regtime_field_file')} {file_name}\n")
                            f.write(f"{t(user_id, 'regtime_error_field')} {result.get('error', '未知错误')}\n\n")
        
        logger.info(f"✅ 报告文件已生成: {report_path}")
        print(f"✅ 报告文件已生成: {report_path}", flush=True)
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
        print(f"❌ 生成报告文件失败: {e}", flush=True)
    
    # 按日期打包成功的账号 - 统一打包到一个ZIP文件中
    logger.info(f"📦 开始打包所有账号到单个ZIP文件...")
    print(f"📦 开始打包所有账号到单个ZIP文件...", flush=True)
    
    # 创建一个统一的ZIP文件
    all_accounts_zip = os.path.join(config.RESULTS_DIR, f"registration_all_{timestamp}.zip")
    
    try:
        with zipfile.ZipFile(all_accounts_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历每个日期
            for reg_date, items in sorted(by_date.items()):
                if items:
                    logger.info(f"📦 打包 {reg_date} 的 {len(items)} 个账号...")
                    print(f"📦 打包 {reg_date} 的 {len(items)} 个账号...", flush=True)
                    
                    # 创建日期文件夹名称：如 "2025-09-26 注册的账号 (16 个)"
                    date_folder = t(user_id, 'regtime_folder_name').format(date=reg_date, count=len(items))
                    
                    for file_path, file_name, result in items:
                        phone = result.get('phone', 'unknown')
                        result_file_type = result.get('file_type', 'session')
                        # 使用原始文件路径进行打包
                        original_path = result.get('original_file_path', file_path)
                        
                        try:
                            if result_file_type == 'tdata':
                                # TData格式：使用原始上传的文件，保持原始文件结构
                                # 结构: ZIP/日期文件夹/手机号/tdata/D877.../文件
                                if os.path.isdir(original_path):
                                    # 我们需要找到包含tdata结构的正确父目录
                                    # original_path 可能是以下几种情况：
                                    # 1. /path/to/phone/tdata/D877... (最常见)
                                    # 2. /path/to/phone/D877... (无tdata包装)
                                    # 3. /path/to/tdata/D877... (tdata在根)
                                    # 4. /path/to/D877... (直接D877)
                                    
                                    # 向上查找以确定结构
                                    tdata_parent = None
                                    current = original_path
                                    
                                    # 最多向上查找3层
                                    for _ in range(3):
                                        parent = os.path.dirname(current)
                                        parent_name = os.path.basename(parent)
                                        current_name = os.path.basename(current)
                                        
                                        # 检查是否找到tdata目录
                                        if current_name.lower() == 'tdata':
                                            # 找到tdata目录，使用其父目录作为基准
                                            tdata_parent = parent
                                            break
                                        
                                        # 检查当前目录的父目录是否是tdata
                                        if parent_name.lower() == 'tdata':
                                            # 当前是D877，父目录是tdata
                                            # 使用tdata的父目录作为基准
                                            tdata_parent = os.path.dirname(parent)
                                            break
                                        
                                        current = parent
                                    
                                    # 如果没有找到tdata结构，使用original_path的父目录
                                    if not tdata_parent:
                                        # 没有tdata包装，从D877的父目录开始
                                        # 结构变成: ZIP/日期文件夹/手机号/D877.../文件
                                        tdata_parent = os.path.dirname(original_path)
                                    
                                    # 遍历所有文件并保持相对结构
                                    for root, dirs, files in os.walk(original_path):
                                        for file in files:
                                            file_full_path = os.path.join(root, file)
                                            # 计算相对于tdata_parent的路径
                                            try:
                                                rel_path = os.path.relpath(file_full_path, tdata_parent)
                                            except ValueError:
                                                # 如果路径在不同驱动器，使用从original_path开始的相对路径
                                                rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                            
                                            # 构建压缩包内的路径：日期文件夹/手机号/rel_path
                                            # rel_path 现在应该包含 tdata/D877... 或 D877... 结构
                                            arc_path = os.path.join(date_folder, phone, rel_path)
                                            zipf.write(file_full_path, arc_path)
                            else:
                                # Session格式：使用原始上传的文件
                                # 结构: ZIP/日期文件夹/session文件和json文件（不用手机号子文件夹）
                                if os.path.exists(original_path):
                                    # 直接将session文件放在日期文件夹下
                                    arc_path = os.path.join(date_folder, file_name)
                                    zipf.write(original_path, arc_path)
                                
                                # Journal文件
                                journal_path = original_path + '-journal'
                                if os.path.exists(journal_path):
                                    arc_path = os.path.join(date_folder, file_name + '-journal')
                                    zipf.write(journal_path, arc_path)
                                
                                # JSON文件
                                json_path = os.path.splitext(original_path)[0] + '.json'
                                if os.path.exists(json_path):
                                    json_name = os.path.splitext(file_name)[0] + '.json'
                                    arc_path = os.path.join(date_folder, json_name)
                                    zipf.write(json_path, arc_path)
                        except Exception as e:
                            logger.error(f"❌ 打包文件失败 {file_name}: {e}")
                            print(f"❌ 打包文件失败 {file_name}: {e}", flush=True)
        
        logger.info(f"✅ 所有账号已打包到: {all_accounts_zip}")
        print(f"✅ 所有账号已打包到: {all_accounts_zip}", flush=True)
        
        # 准备发送的ZIP文件信息
        zip_files = [("all", all_accounts_zip, success_count)]
        
    except Exception as e:
        logger.error(f"❌ 打包失败: {e}")
        print(f"❌ 打包失败: {e}", flush=True)
        zip_files = []
    
    # 打包失败的账号到单独的ZIP文件
    if error_count > 0:
        logger.info(f"📦 开始打包失败的账号...")
        print(f"📦 开始打包失败的账号...", flush=True)
        
        failed_zip = os.path.join(config.RESULTS_DIR, f"{t(user_id, 'regtime_fail_zip_name')}_{timestamp}.zip")
        failed_details = []
        
        try:
            with zipfile.ZipFile(failed_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 创建详细失败原因文件
                for category in ['frozen', 'banned', 'error']:
                    if results[category]:
                        for file_path, file_name, result in results[category]:
                            error_msg = result.get('error', '未知错误')
                            result_file_type = result.get('file_type', 'session')
                            # 使用原始文件路径（与成功账号相同）
                            original_path = result.get('original_file_path', file_path)
                            
                            # 记录失败信息
                            failed_details.append({
                                'file_name': file_name,
                                'category': category,
                                'error': error_msg,
                                'file_type': result_file_type
                            })
                            
                            # 打包原始文件
                            try:
                                if result_file_type == 'tdata':
                                    # TData格式：打包整个目录，保持tdata结构
                                    if os.path.isdir(original_path):
                                        # 查找tdata结构的父目录（与成功账号相同的逻辑）
                                        tdata_parent = None
                                        current = original_path
                                        
                                        for _ in range(3):
                                            parent = os.path.dirname(current)
                                            parent_name = os.path.basename(parent)
                                            current_name = os.path.basename(current)
                                            
                                            if current_name.lower() == 'tdata':
                                                tdata_parent = parent
                                                break
                                            
                                            if parent_name.lower() == 'tdata':
                                                tdata_parent = os.path.dirname(parent)
                                                break
                                            
                                            current = parent
                                        
                                        if not tdata_parent:
                                            tdata_parent = os.path.dirname(original_path)
                                        
                                        for root, dirs, files in os.walk(original_path):
                                            for file in files:
                                                file_full_path = os.path.join(root, file)
                                                try:
                                                    rel_path = os.path.relpath(file_full_path, tdata_parent)
                                                except ValueError:
                                                    rel_path = os.path.relpath(file_full_path, os.path.dirname(original_path))
                                                
                                                arc_path = os.path.join(file_name, rel_path)
                                                zipf.write(file_full_path, arc_path)
                                else:
                                    # Session格式：打包session及相关文件
                                    if os.path.exists(original_path):
                                        zipf.write(original_path, file_name)
                                    
                                    # Journal文件
                                    journal_path = original_path + '-journal'
                                    if os.path.exists(journal_path):
                                        zipf.write(journal_path, file_name + '-journal')
                                    
                                    # JSON文件
                                    json_path = os.path.splitext(original_path)[0] + '.json'
                                    if os.path.exists(json_path):
                                        json_name = os.path.splitext(file_name)[0] + '.json'
                                        zipf.write(json_path, json_name)
                            except Exception as e:
                                logger.warning(f"⚠️ 打包失败文件失败 {file_name}: {e}")
                
                # 创建失败原因详细说明文件
                failed_report = f"{t(user_id, 'regtime_fail_report_title')}\n"
                failed_report += "=" * 80 + "\n"
                failed_report += f"{t(user_id, 'regtime_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n"
                failed_report += f"{t(user_id, 'regtime_fail_total')} {error_count}\n"
                failed_report += "=" * 80 + "\n\n"
                
                # 按类别分组
                category_keys = {
                    'frozen': 'regtime_fail_frozen',
                    'banned': 'regtime_fail_banned',
                    'error': 'regtime_fail_other_errors'
                }
                
                for category in ['frozen', 'banned', 'error']:
                    category_items = [d for d in failed_details if d['category'] == category]
                    if category_items:
                        failed_report += f"\n{t(user_id, category_keys[category]).format(count=len(category_items))}\n"
                        failed_report += "-" * 80 + "\n"
                        for item in category_items:
                            failed_report += f"{t(user_id, 'regtime_field_file')} {item['file_name']}\n"
                            failed_report += f"{t(user_id, 'regtime_fail_type')} {item['file_type']}\n"
                            failed_report += f"{t(user_id, 'regtime_fail_reason')} {item['error']}\n"
                            failed_report += "\n"
                
                # 将失败原因文件添加到ZIP
                zipf.writestr(t(user_id, 'regtime_fail_detail_file'), failed_report.encode('utf-8'))
            
            logger.info(f"✅ 失败账号已打包到: {failed_zip}")
            print(f"✅ 失败账号已打包到: {failed_zip}", flush=True)
            
            # 添加到发送列表
            zip_files.append(("failed", failed_zip, error_count))
            
        except Exception as e:
            logger.error(f"❌ 打包失败账号失败: {e}")
            print(f"❌ 打包失败账号失败: {e}", flush=True)
    
    # 发送统计信息
    summary = f"""

