

# ===== Handler Methods from EnhancedBot =====

    def show_broadcast_wizard_editor_as_new_message(self, update, context):
    """以新消息的形式显示广播编辑器"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 状态指示器
    media_status = "✅" if task.get('media_file_id') else "⚪"
    text_status = "✅" if task.get('content') else "⚪"
    buttons_status = "✅" if task.get('buttons') else "⚪"
    
    text = f"""

    def handle_broadcast_callbacks_router(self, update: Update, context: CallbackContext):
    """
    专用广播回调路由器 - 处理所有 broadcast_* 回调
    注册为独立的 CallbackQueryHandler，优先级高于通用处理器
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # 始终先调用 query.answer() 避免 Telegram 超时和加载动画
    try:
        query.answer()
    except Exception as e:
        print(f"⚠️ query.answer() 失败: {e}")
    
    # 权限检查
    if not self.db.is_admin(user_id):
        try:
            query.answer("❌ 仅管理员可访问广播功能", show_alert=True)
        except:
            pass
        return
    
    # 分发表：将所有 broadcast_* 回调映射到对应的处理方法
    dispatch_table = {
        # 主菜单和向导
        "broadcast_menu": lambda: self.show_broadcast_menu(query),
        "broadcast_create": lambda: self.start_broadcast_wizard(query, update, context),
        "broadcast_history": lambda: self.show_broadcast_history(query),
        "broadcast_cancel": lambda: self.cancel_broadcast(query, user_id),
        "broadcast_edit": lambda: self.restart_broadcast_wizard(query, update, context),
        "broadcast_confirm_send": lambda: self.start_broadcast_sending(query, update, context),
        
        # 媒体操作
        "broadcast_media": lambda: self.handle_broadcast_media(query, update, context),
        "broadcast_media_view": lambda: self.handle_broadcast_media_view(query, update, context),
        "broadcast_media_clear": lambda: self.handle_broadcast_media_clear(query, update, context),
        
        # 文本操作
        "broadcast_text": lambda: self.handle_broadcast_text(query, update, context),
        "broadcast_text_view": lambda: self.handle_broadcast_text_view(query, update, context),
        
        # 按钮操作
        "broadcast_buttons": lambda: self.handle_broadcast_buttons(query, update, context),
        "broadcast_buttons_view": lambda: self.handle_broadcast_buttons_view(query, update, context),
        "broadcast_buttons_clear": lambda: self.handle_broadcast_buttons_clear(query, update, context),
        
        # 导航
        "broadcast_preview": lambda: self.handle_broadcast_preview(query, update, context),
        "broadcast_back": lambda: self.handle_broadcast_back(query, update, context),
        "broadcast_next": lambda: self.handle_broadcast_next(query, update, context),
    }
    
    # 处理简单的固定回调
    if data in dispatch_table:
        try:
            dispatch_table[data]()
        except Exception as e:
            print(f"❌ 广播回调处理失败 [{data}]: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.safe_edit_message(query, f"❌ 操作失败: {str(e)[:100]}")
            except:
                pass
        return
    
    # 处理带参数的回调（历史详情、目标选择等）
    try:
        if data.startswith("broadcast_history_detail_"):
            broadcast_id = int(data.split("_")[-1])
            self.show_broadcast_detail(query, broadcast_id)
        elif data.startswith("broadcast_target_"):
            target = data.split("_", 2)[-1]  # 支持 broadcast_target_active_7d 这种格式
            self.handle_broadcast_target_selection(query, update, context, target)
        elif data.startswith("broadcast_alert_"):
            # 广播消息中的自定义回调按钮
            self.handle_broadcast_alert_button(query, data)
        else:
            print(f"⚠️ 未识别的广播回调: {data}")
            try:
                query.answer("⚠️ 未识别的操作", show_alert=True)
            except:
                pass
    except Exception as e:
        print(f"❌ 广播回调处理失败 [{data}]: {e}")
        import traceback
        traceback.print_exc()
        try:
            self.safe_edit_message(query, f"❌ 操作失败: {str(e)[:100]}")
        except:
            pass


    def handle_broadcast_callbacks(self, update, context, query, data):
    """
    旧版广播回调处理器 - 保持向后兼容
    现在通过 handle_broadcast_callbacks_router 调用
    """
    user_id = query.from_user.id
    
    # 权限检查
    if not self.db.is_admin(user_id):
        try:
            query.answer("❌ 仅管理员可访问广播功能", show_alert=True)
        except:
            pass
        return
    
    # 调用新的路由器（去掉 query.answer，因为路由器已经处理）
    if data == "broadcast_menu":
        self.show_broadcast_menu(query)
    elif data == "broadcast_create":
        self.start_broadcast_wizard(query, update, context)
    elif data == "broadcast_history":
        self.show_broadcast_history(query)
    elif data.startswith("broadcast_history_detail_"):
        broadcast_id = int(data.split("_")[-1])
        self.show_broadcast_detail(query, broadcast_id)
    elif data.startswith("broadcast_target_"):
        target = data.split("_")[-1]
        self.handle_broadcast_target_selection(query, update, context, target)
    elif data == "broadcast_confirm_send":
        self.start_broadcast_sending(query, update, context)
    elif data == "broadcast_edit":
        self.restart_broadcast_wizard(query, update, context)
    elif data == "broadcast_cancel":
        self.cancel_broadcast(query, user_id)


    def show_broadcast_menu(self, query):
    """显示广播菜单"""
    try:
        query.answer()
    except:
        pass
    
    text = """

    def handle_broadcast_media(self, query, update, context):
    """处理媒体设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_media"
    )
    
    text = """

    def handle_broadcast_media_view(self, query, update, context):
    """查看当前设置的媒体"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if 'media_file_id' not in task or not task['media_file_id']:
        try:
            query.answer("⚠️ 尚未设置媒体", show_alert=True)
        except:
            pass
        return
    
    # 发送媒体预览
    try:
        context.bot.send_photo(
            chat_id=user_id,
            photo=task['media_file_id'],
            caption="📸 当前广播媒体预览"
        )
        try:
            query.answer("✅ 已发送媒体预览")
        except:
            pass
    except Exception as e:
        try:
            query.answer(f"❌ 预览失败: {str(e)[:50]}", show_alert=True)
        except:
            pass


    def handle_broadcast_media_clear(self, query, update, context):
    """清除媒体设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['media_file_id'] = None
    task['media_type'] = None
    
    try:
        query.answer("✅ 已清除媒体设置")
    except:
        pass
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_text(self, query, update, context):
    """处理文本设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_content"
    )
    
    text = """

    def handle_broadcast_text_view(self, query, update, context):
    """查看当前设置的文本"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if not task.get('content'):
        try:
            query.answer("⚠️ 尚未设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 显示文本预览
    preview = task['content'][:500]
    if len(task['content']) > 500:
        preview += "\n\n<i>... (内容过长，已截断)</i>"
    
    text = f"""

    def handle_broadcast_buttons(self, query, update, context):
    """处理按钮设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_buttons"
    )
    
    text = """

    def handle_broadcast_buttons_view(self, query, update, context):
    """查看当前设置的按钮"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if not task.get('buttons'):
        try:
            query.answer("⚠️ 尚未设置按钮", show_alert=True)
        except:
            pass
        return
    
    # 显示按钮列表
    text = "<b>🔘 按钮列表</b>\n\n"
    for i, btn in enumerate(task['buttons'], 1):
        if btn['type'] == 'url':
            text += f"{i}. {btn['text']} → {btn['url']}\n"
        else:
            text += f"{i}. {btn['text']} (回调)\n"
    
    self.safe_edit_message(query, text, 'HTML')
    try:
        query.answer(f"✅ 共 {len(task['buttons'])} 个按钮")
    except:
        pass


    def handle_broadcast_buttons_clear(self, query, update, context):
    """清除按钮设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['buttons'] = []
    
    try:
        query.answer("✅ 已清除所有按钮")
    except:
        pass
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_preview(self, query, update, context):
    """显示完整预览"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查必填项
    if not task.get('content'):
        try:
            query.answer("⚠️ 请先设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 发送预览消息
    try:
        # 构建按钮
        keyboard = None
        if task.get('buttons'):
            button_rows = []
            for btn in task['buttons']:
                if btn['type'] == 'url':
                    button_rows.append([InlineKeyboardButton(btn['text'], url=btn['url'])])
                else:
                    button_rows.append([InlineKeyboardButton(btn['text'], callback_data=btn['data'])])
            keyboard = InlineKeyboardMarkup(button_rows)
        
        # 发送预览
        if task.get('media_file_id'):
            context.bot.send_photo(
                chat_id=user_id,
                photo=task['media_file_id'],
                caption=f"<b>📢 预览</b>\n\n{task['content']}",
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            context.bot.send_message(
                chat_id=user_id,
                text=f"<b>📢 预览</b>\n\n{task['content']}",
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        try:
            query.answer("✅ 已发送预览")
        except:
            pass
    except Exception as e:
        try:
            query.answer(f"❌ 预览失败: {str(e)[:50]}", show_alert=True)
        except:
            pass


    def handle_broadcast_back(self, query, update, context):
    """返回上一步"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_next(self, query, update, context):
    """下一步：选择目标"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查必填项
    if not task.get('content'):
        try:
            query.answer("⚠️ 请先设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 进入目标选择
    self.show_target_selection(update, context, user_id)


    def handle_broadcast_alert_button(self, query, data):
    """处理广播消息中的自定义回调按钮"""
    # 从广播任务中查找对应的提示信息
    # 这里简化处理，直接显示通用提示
    try:
        query.answer("✨ 感谢您的关注！", show_alert=True)
    except:
        pass


    def show_broadcast_wizard_editor(self, query, update, context):
    """显示广播编辑器 - 两栏布局的 zh-CN UI"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 状态指示器
    media_status = "✅" if task.get('media_file_id') else "⚪"
    text_status = "✅" if task.get('content') else "⚪"
    buttons_status = "✅" if task.get('buttons') else "⚪"
    
    text = f"""

    def start_broadcast_wizard(self, query, update, context):
    """开始广播创建向导 - 新版两栏 UI"""
    user_id = query.from_user.id
    try:
        query.answer()
    except:
        pass
    
    # 初始化广播任务
    self.pending_broadcasts[user_id] = {
        'step': 'editor',
        'started_at': time.time(),
        'title': f"广播_{int(time.time())}",  # 自动生成标题
        'content': '',
        'buttons': [],
        'media_file_id': None,
        'media_type': None,
        'target': '',
        'preview_message_id': None,
        'broadcast_id': None
    }
    
    # 显示编辑器界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_title_input(self, update, context, user_id, title):
    """处理标题输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:  # 5分钟
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 验证标题
    title = title.strip()
    if not title:
        self.safe_send_message(update, "❌ 标题不能为空，请重新输入")
        return
    
    if len(title) > 100:
        self.safe_send_message(update, "❌ 标题过长（最多100字符），请重新输入")
        return
    
    # 保存标题并进入下一步
    task['title'] = title
    task['step'] = 'content'
    
    # 更新状态
    self.db.save_user(user_id, "", "", "waiting_broadcast_content")
    
    text = f"""

    def handle_broadcast_content_input(self, update, context, user_id, content):
    """处理内容输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 验证内容
    content = content.strip()
    if not content:
        self.safe_send_message(update, "❌ 内容不能为空，请重新输入")
        return
    
    # 保存内容
    task['content'] = content
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 返回编辑器
    self.safe_send_message(update, "✅ <b>内容已保存</b>\n\n返回编辑器继续设置", 'HTML')
    self.show_broadcast_wizard_editor_as_new_message(update, context)


    def handle_broadcast_buttons_input(self, update, context, user_id, buttons_text):
    """处理按钮输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 检查是否跳过
    buttons_text = buttons_text.strip()
    if buttons_text.lower() in ['跳过', 'skip', '']:
        task['buttons'] = []
        # 清空用户状态
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "✅ <b>已跳过按钮设置</b>\n\n返回编辑器继续设置", 'HTML')
        self.show_broadcast_wizard_editor_as_new_message(update, context)
        return
    
    # 解析按钮
    buttons = []
    lines = buttons_text.split('\n')[:4]  # 最多4个按钮
    
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            continue
        
        parts = line.split('|', 1)
        if len(parts) != 2:
            continue
        
        text = parts[0].strip()
        value = parts[1].strip()
        
        if not text or not value:
            continue
        
        # 判断按钮类型
        if value.startswith('callback:'):
            # 回调按钮
            callback_text = value[9:].strip()
            buttons.append({
                'type': 'callback',
                'text': text,
                'data': f'broadcast_alert_{len(buttons)}',
                'alert': callback_text
            })
        elif value.startswith('http://') or value.startswith('https://'):
            # URL按钮
            buttons.append({
                'type': 'url',
                'text': text,
                'url': value
            })
        else:
            # 尝试作为URL处理
            if '.' in value:
                buttons.append({
                    'type': 'url',
                    'text': text,
                    'url': f'https://{value}'
                })
    
    task['buttons'] = buttons
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 返回编辑器
    self.safe_send_message(update, f"✅ <b>已保存 {len(buttons)} 个按钮</b>\n\n返回编辑器继续设置", 'HTML')
    self.show_broadcast_wizard_editor_as_new_message(update, context)



    def handle_broadcast_target_selection(self, query, update, context, target):
    """处理目标选择"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['target'] = target
    
    # 获取目标用户列表
    target_users = self.db.get_target_users(target)
    
    if not target_users:
        self.safe_edit_message(query, "❌ 未找到符合条件的用户")
        return
    
    # 目标名称映射
    target_names = {
        'all': '全部用户',
        'members': '仅会员',
        'active_7d': '活跃用户(7天)',
        'new_7d': '新用户(7天)'
    }
    
    # 生成预览
    buttons_preview = ""
    if task['buttons']:
        buttons_preview = "\n\n<b>🔘 按钮:</b>\n"
        for i, btn in enumerate(task['buttons'], 1):
            if btn['type'] == 'url':
                buttons_preview += f"{i}. {btn['text']} → {btn['url']}\n"
            else:
                buttons_preview += f"{i}. {btn['text']} (点击提示)\n"
    
    text = f"""

    def start_broadcast_sending(self, query, update, context):
    """开始发送广播"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 插入广播记录
    buttons_json = json.dumps(task['buttons'], ensure_ascii=False)
    broadcast_id = self.db.insert_broadcast_record(
        task['title'],
        task['content'],
        buttons_json,
        task['target'],
        user_id
    )
    
    if not broadcast_id:
        self.safe_edit_message(query, "❌ 创建广播记录失败")
        return
    
    task['broadcast_id'] = broadcast_id
    
    # 启动异步发送
    def send_broadcast():
        asyncio.run(self.execute_broadcast_sending(update, context, user_id, broadcast_id))
    
    thread = threading.Thread(target=send_broadcast, daemon=True)
    thread.start()
    
    self.safe_edit_message(query, "📤 <b>开始发送广播...</b>\n\n正在初始化...", 'HTML')

async def execute_broadcast_sending(self, update, context, admin_id, broadcast_id):
    """执行广播发送"""
    if admin_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[admin_id]
    start_time = time.time()
    
    # 获取目标用户
    target_users = self.db.get_target_users(task['target'])
    total = len(target_users)
    
    if total == 0:
        context.bot.send_message(
            chat_id=admin_id,
            text="❌ 未找到符合条件的用户",
            parse_mode='HTML'
        )
        del self.pending_broadcasts[admin_id]
        return
    
    # 构建按钮
    keyboard = None
    if task['buttons']:
        button_rows = []
        for btn in task['buttons']:
            if btn['type'] == 'url':
                button_rows.append([InlineKeyboardButton(btn['text'], url=btn['url'])])
            else:
                button_rows.append([InlineKeyboardButton(btn['text'], callback_data=btn['data'])])
        keyboard = InlineKeyboardMarkup(button_rows)
    
    # 发送统计
    success_count = 0
    failed_count = 0
    
    # 批量发送
    batch_size = 25
    progress_msg = None
    
    try:
        # 发送进度消息
        progress_msg = context.bot.send_message(
            chat_id=admin_id,
            text=f"📤 <b>广播发送中...</b>\n\n• 目标: {total} 人\n• 进度: 0/{total}\n• 成功: 0\n• 失败: 0",
            parse_mode='HTML'
        )
        
        for i in range(0, total, batch_size):
            batch = target_users[i:i + batch_size]
            batch_start = time.time()
            
            for user_id in batch:
                try:
                    context.bot.send_message(
                        chat_id=user_id,
                        text=task['content'],
                        parse_mode='HTML',
                        reply_markup=keyboard
                    )
                    success_count += 1
                    self.db.add_broadcast_log(broadcast_id, user_id, 'success')
                except RetryAfter as e:
                    # 处理速率限制
                    await asyncio.sleep(e.retry_after + 1)
                    try:
                        context.bot.send_message(
                            chat_id=user_id,
                            text=task['content'],
                            parse_mode='HTML',
                            reply_markup=keyboard
                        )
                        success_count += 1
                        self.db.add_broadcast_log(broadcast_id, user_id, 'success')
                    except Exception as retry_err:
                        failed_count += 1
                        self.db.add_broadcast_log(broadcast_id, user_id, 'failed', str(retry_err))
                except BadRequest as e:
                    # 用户屏蔽机器人或其他错误
                    failed_count += 1
                    error_msg = str(e)
                    if 'bot was blocked' in error_msg.lower():
                        self.db.add_broadcast_log(broadcast_id, user_id, 'blocked', 'User blocked bot')
                    else:
                        self.db.add_broadcast_log(broadcast_id, user_id, 'failed', error_msg)
                except Exception as e:
                    failed_count += 1
                    self.db.add_broadcast_log(broadcast_id, user_id, 'failed', str(e))
            
            # 更新进度
            processed = success_count + failed_count
            elapsed = time.time() - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / speed if speed > 0 else 0
            
            if progress_msg and processed % batch_size == 0:
                try:
                    progress_msg.edit_text(
                        f"📤 <b>广播发送中...</b>\n\n"
                        f"• 目标: {total} 人\n"
                        f"• 进度: {processed}/{total} ({processed/total*100:.1f}%)\n"
                        f"• 成功: {success_count}\n"
                        f"• 失败: {failed_count}\n"
                        f"• 速度: {speed:.1f} 人/秒\n"
                        f"• 预计剩余: {int(eta)} 秒",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            # 批次间延迟
            if i + batch_size < total:
                await asyncio.sleep(random.uniform(0.8, 1.2))
        
        # 完成
        duration = time.time() - start_time
        self.db.update_broadcast_progress(
            broadcast_id, success_count, failed_count, 'completed', duration
        )
        
        # 发送完成消息
        success_rate = (success_count / total * 100) if total > 0 else 0
        final_text = f"""

    def show_broadcast_history(self, query):
    """显示广播历史"""
    query.answer()
    
    history = self.db.get_broadcast_history(10)
    
    if not history:
        text = """

    def show_broadcast_detail(self, query, broadcast_id):
    """显示广播详情"""
    query.answer()
    
    detail = self.db.get_broadcast_detail(broadcast_id)
    
    if not detail:
        self.safe_edit_message(query, "❌ 未找到广播记录")
        return
    
    # 状态图标
    status_icon = {
        'pending': '⏳ 待发送',
        'completed': '✅ 已完成',
        'failed': '❌ 失败'
    }.get(detail['status'], '❓ 未知')
    
    # 目标名称
    target_names = {
        'all': '全部用户',
        'members': '仅会员',
        'active_7d': '活跃用户(7天)',
        'new_7d': '新用户(7天)'
    }
    target_name = target_names.get(detail['target'], detail['target'])
    
    # 按钮信息
    buttons_info = ""
    if detail['buttons_json']:
        try:
            buttons = json.loads(detail['buttons_json'])
            if buttons:
                buttons_info = "\n\n<b>🔘 按钮:</b>\n"
                for i, btn in enumerate(buttons, 1):
                    if btn['type'] == 'url':
                        buttons_info += f"{i}. {btn['text']} → {btn['url']}\n"
                    else:
                        buttons_info += f"{i}. {btn['text']} (回调)\n"
        except:
            pass
    
    success_rate = (detail['success'] / detail['total'] * 100) if detail['total'] > 0 else 0
    
    text = f"""

    def cancel_broadcast(self, query, user_id):
    """取消广播"""
    query.answer()
    
    if user_id in self.pending_broadcasts:
        del self.pending_broadcasts[user_id]
    
    self.db.save_user(user_id, "", "", "")
    
    text = "❌ <b>已取消创建广播</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 返回", callback_data="broadcast_menu")]
    ])
    
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def restart_broadcast_wizard(self, query, update, context):
    """重新开始广播向导"""
    user_id = query.from_user.id
    
    if user_id in self.pending_broadcasts:
        del self.pending_broadcasts[user_id]
    
    self.start_broadcast_wizard(query, update, context)

# ================================
# 文件重命名功能
# ================================




# ===== Handler Methods =====

    def show_broadcast_wizard_editor_as_new_message(self, update, context):
    """以新消息的形式显示广播编辑器"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 状态指示器
    media_status = "✅" if task.get('media_file_id') else "⚪"
    text_status = "✅" if task.get('content') else "⚪"
    buttons_status = "✅" if task.get('buttons') else "⚪"
    
    text = f"""

    def handle_broadcast_callbacks_router(self, update: Update, context: CallbackContext):
    """
    专用广播回调路由器 - 处理所有 broadcast_* 回调
    注册为独立的 CallbackQueryHandler，优先级高于通用处理器
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # 始终先调用 query.answer() 避免 Telegram 超时和加载动画
    try:
        query.answer()
    except Exception as e:
        print(f"⚠️ query.answer() 失败: {e}")
    
    # 权限检查
    if not self.db.is_admin(user_id):
        try:
            query.answer("❌ 仅管理员可访问广播功能", show_alert=True)
        except:
            pass
        return
    
    # 分发表：将所有 broadcast_* 回调映射到对应的处理方法
    dispatch_table = {
        # 主菜单和向导
        "broadcast_menu": lambda: self.show_broadcast_menu(query),
        "broadcast_create": lambda: self.start_broadcast_wizard(query, update, context),
        "broadcast_history": lambda: self.show_broadcast_history(query),
        "broadcast_cancel": lambda: self.cancel_broadcast(query, user_id),
        "broadcast_edit": lambda: self.restart_broadcast_wizard(query, update, context),
        "broadcast_confirm_send": lambda: self.start_broadcast_sending(query, update, context),
        
        # 媒体操作
        "broadcast_media": lambda: self.handle_broadcast_media(query, update, context),
        "broadcast_media_view": lambda: self.handle_broadcast_media_view(query, update, context),
        "broadcast_media_clear": lambda: self.handle_broadcast_media_clear(query, update, context),
        
        # 文本操作
        "broadcast_text": lambda: self.handle_broadcast_text(query, update, context),
        "broadcast_text_view": lambda: self.handle_broadcast_text_view(query, update, context),
        
        # 按钮操作
        "broadcast_buttons": lambda: self.handle_broadcast_buttons(query, update, context),
        "broadcast_buttons_view": lambda: self.handle_broadcast_buttons_view(query, update, context),
        "broadcast_buttons_clear": lambda: self.handle_broadcast_buttons_clear(query, update, context),
        
        # 导航
        "broadcast_preview": lambda: self.handle_broadcast_preview(query, update, context),
        "broadcast_back": lambda: self.handle_broadcast_back(query, update, context),
        "broadcast_next": lambda: self.handle_broadcast_next(query, update, context),
    }
    
    # 处理简单的固定回调
    if data in dispatch_table:
        try:
            dispatch_table[data]()
        except Exception as e:
            print(f"❌ 广播回调处理失败 [{data}]: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.safe_edit_message(query, f"❌ 操作失败: {str(e)[:100]}")
            except:
                pass
        return
    
    # 处理带参数的回调（历史详情、目标选择等）
    try:
        if data.startswith("broadcast_history_detail_"):
            broadcast_id = int(data.split("_")[-1])
            self.show_broadcast_detail(query, broadcast_id)
        elif data.startswith("broadcast_target_"):
            target = data.split("_", 2)[-1]  # 支持 broadcast_target_active_7d 这种格式
            self.handle_broadcast_target_selection(query, update, context, target)
        elif data.startswith("broadcast_alert_"):
            # 广播消息中的自定义回调按钮
            self.handle_broadcast_alert_button(query, data)
        else:
            print(f"⚠️ 未识别的广播回调: {data}")
            try:
                query.answer("⚠️ 未识别的操作", show_alert=True)
            except:
                pass
    except Exception as e:
        print(f"❌ 广播回调处理失败 [{data}]: {e}")
        import traceback
        traceback.print_exc()
        try:
            self.safe_edit_message(query, f"❌ 操作失败: {str(e)[:100]}")
        except:
            pass


    def handle_broadcast_callbacks(self, update, context, query, data):
    """
    旧版广播回调处理器 - 保持向后兼容
    现在通过 handle_broadcast_callbacks_router 调用
    """
    user_id = query.from_user.id
    
    # 权限检查
    if not self.db.is_admin(user_id):
        try:
            query.answer("❌ 仅管理员可访问广播功能", show_alert=True)
        except:
            pass
        return
    
    # 调用新的路由器（去掉 query.answer，因为路由器已经处理）
    if data == "broadcast_menu":
        self.show_broadcast_menu(query)
    elif data == "broadcast_create":
        self.start_broadcast_wizard(query, update, context)
    elif data == "broadcast_history":
        self.show_broadcast_history(query)
    elif data.startswith("broadcast_history_detail_"):
        broadcast_id = int(data.split("_")[-1])
        self.show_broadcast_detail(query, broadcast_id)
    elif data.startswith("broadcast_target_"):
        target = data.split("_")[-1]
        self.handle_broadcast_target_selection(query, update, context, target)
    elif data == "broadcast_confirm_send":
        self.start_broadcast_sending(query, update, context)
    elif data == "broadcast_edit":
        self.restart_broadcast_wizard(query, update, context)
    elif data == "broadcast_cancel":
        self.cancel_broadcast(query, user_id)


    def show_broadcast_menu(self, query):
    """显示广播菜单"""
    try:
        query.answer()
    except:
        pass
    
    text = """

    def handle_broadcast_media(self, query, update, context):
    """处理媒体设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_media"
    )
    
    text = """

    def handle_broadcast_media_view(self, query, update, context):
    """查看当前设置的媒体"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if 'media_file_id' not in task or not task['media_file_id']:
        try:
            query.answer("⚠️ 尚未设置媒体", show_alert=True)
        except:
            pass
        return
    
    # 发送媒体预览
    try:
        context.bot.send_photo(
            chat_id=user_id,
            photo=task['media_file_id'],
            caption="📸 当前广播媒体预览"
        )
        try:
            query.answer("✅ 已发送媒体预览")
        except:
            pass
    except Exception as e:
        try:
            query.answer(f"❌ 预览失败: {str(e)[:50]}", show_alert=True)
        except:
            pass


    def handle_broadcast_media_clear(self, query, update, context):
    """清除媒体设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['media_file_id'] = None
    task['media_type'] = None
    
    try:
        query.answer("✅ 已清除媒体设置")
    except:
        pass
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_text(self, query, update, context):
    """处理文本设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_content"
    )
    
    text = """

    def handle_broadcast_text_view(self, query, update, context):
    """查看当前设置的文本"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if not task.get('content'):
        try:
            query.answer("⚠️ 尚未设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 显示文本预览
    preview = task['content'][:500]
    if len(task['content']) > 500:
        preview += "\n\n<i>... (内容过长，已截断)</i>"
    
    text = f"""

    def handle_broadcast_buttons(self, query, update, context):
    """处理按钮设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 更新用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_broadcast_buttons"
    )
    
    text = """

    def handle_broadcast_buttons_view(self, query, update, context):
    """查看当前设置的按钮"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    if not task.get('buttons'):
        try:
            query.answer("⚠️ 尚未设置按钮", show_alert=True)
        except:
            pass
        return
    
    # 显示按钮列表
    text = "<b>🔘 按钮列表</b>\n\n"
    for i, btn in enumerate(task['buttons'], 1):
        if btn['type'] == 'url':
            text += f"{i}. {btn['text']} → {btn['url']}\n"
        else:
            text += f"{i}. {btn['text']} (回调)\n"
    
    self.safe_edit_message(query, text, 'HTML')
    try:
        query.answer(f"✅ 共 {len(task['buttons'])} 个按钮")
    except:
        pass


    def handle_broadcast_buttons_clear(self, query, update, context):
    """清除按钮设置"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['buttons'] = []
    
    try:
        query.answer("✅ 已清除所有按钮")
    except:
        pass
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_preview(self, query, update, context):
    """显示完整预览"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查必填项
    if not task.get('content'):
        try:
            query.answer("⚠️ 请先设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 发送预览消息
    try:
        # 构建按钮
        keyboard = None
        if task.get('buttons'):
            button_rows = []
            for btn in task['buttons']:
                if btn['type'] == 'url':
                    button_rows.append([InlineKeyboardButton(btn['text'], url=btn['url'])])
                else:
                    button_rows.append([InlineKeyboardButton(btn['text'], callback_data=btn['data'])])
            keyboard = InlineKeyboardMarkup(button_rows)
        
        # 发送预览
        if task.get('media_file_id'):
            context.bot.send_photo(
                chat_id=user_id,
                photo=task['media_file_id'],
                caption=f"<b>📢 预览</b>\n\n{task['content']}",
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            context.bot.send_message(
                chat_id=user_id,
                text=f"<b>📢 预览</b>\n\n{task['content']}",
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        try:
            query.answer("✅ 已发送预览")
        except:
            pass
    except Exception as e:
        try:
            query.answer(f"❌ 预览失败: {str(e)[:50]}", show_alert=True)
        except:
            pass


    def handle_broadcast_back(self, query, update, context):
    """返回上一步"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    # 返回编辑界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_next(self, query, update, context):
    """下一步：选择目标"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查必填项
    if not task.get('content'):
        try:
            query.answer("⚠️ 请先设置文本内容", show_alert=True)
        except:
            pass
        return
    
    # 进入目标选择
    self.show_target_selection(update, context, user_id)


    def handle_broadcast_alert_button(self, query, data):
    """处理广播消息中的自定义回调按钮"""
    # 从广播任务中查找对应的提示信息
    # 这里简化处理，直接显示通用提示
    try:
        query.answer("✨ 感谢您的关注！", show_alert=True)
    except:
        pass


    def show_broadcast_wizard_editor(self, query, update, context):
    """显示广播编辑器 - 两栏布局的 zh-CN UI"""
    user_id = query.from_user.id
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 状态指示器
    media_status = "✅" if task.get('media_file_id') else "⚪"
    text_status = "✅" if task.get('content') else "⚪"
    buttons_status = "✅" if task.get('buttons') else "⚪"
    
    text = f"""

    def start_broadcast_wizard(self, query, update, context):
    """开始广播创建向导 - 新版两栏 UI"""
    user_id = query.from_user.id
    try:
        query.answer()
    except:
        pass
    
    # 初始化广播任务
    self.pending_broadcasts[user_id] = {
        'step': 'editor',
        'started_at': time.time(),
        'title': f"广播_{int(time.time())}",  # 自动生成标题
        'content': '',
        'buttons': [],
        'media_file_id': None,
        'media_type': None,
        'target': '',
        'preview_message_id': None,
        'broadcast_id': None
    }
    
    # 显示编辑器界面
    self.show_broadcast_wizard_editor(query, update, context)


    def handle_broadcast_title_input(self, update, context, user_id, title):
    """处理标题输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:  # 5分钟
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 验证标题
    title = title.strip()
    if not title:
        self.safe_send_message(update, "❌ 标题不能为空，请重新输入")
        return
    
    if len(title) > 100:
        self.safe_send_message(update, "❌ 标题过长（最多100字符），请重新输入")
        return
    
    # 保存标题并进入下一步
    task['title'] = title
    task['step'] = 'content'
    
    # 更新状态
    self.db.save_user(user_id, "", "", "waiting_broadcast_content")
    
    text = f"""

    def handle_broadcast_content_input(self, update, context, user_id, content):
    """处理内容输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 验证内容
    content = content.strip()
    if not content:
        self.safe_send_message(update, "❌ 内容不能为空，请重新输入")
        return
    
    # 保存内容
    task['content'] = content
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 返回编辑器
    self.safe_send_message(update, "✅ <b>内容已保存</b>\n\n返回编辑器继续设置", 'HTML')
    self.show_broadcast_wizard_editor_as_new_message(update, context)


    def handle_broadcast_buttons_input(self, update, context, user_id, buttons_text):
    """处理按钮输入"""
    if user_id not in self.pending_broadcasts:
        self.safe_send_message(update, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 检查超时
    if time.time() - task['started_at'] > 300:
        del self.pending_broadcasts[user_id]
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "❌ 操作超时，请重新开始")
        return
    
    # 检查是否跳过
    buttons_text = buttons_text.strip()
    if buttons_text.lower() in ['跳过', 'skip', '']:
        task['buttons'] = []
        # 清空用户状态
        self.db.save_user(user_id, "", "", "")
        self.safe_send_message(update, "✅ <b>已跳过按钮设置</b>\n\n返回编辑器继续设置", 'HTML')
        self.show_broadcast_wizard_editor_as_new_message(update, context)
        return
    
    # 解析按钮
    buttons = []
    lines = buttons_text.split('\n')[:4]  # 最多4个按钮
    
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            continue
        
        parts = line.split('|', 1)
        if len(parts) != 2:
            continue
        
        text = parts[0].strip()
        value = parts[1].strip()
        
        if not text or not value:
            continue
        
        # 判断按钮类型
        if value.startswith('callback:'):
            # 回调按钮
            callback_text = value[9:].strip()
            buttons.append({
                'type': 'callback',
                'text': text,
                'data': f'broadcast_alert_{len(buttons)}',
                'alert': callback_text
            })
        elif value.startswith('http://') or value.startswith('https://'):
            # URL按钮
            buttons.append({
                'type': 'url',
                'text': text,
                'url': value
            })
        else:
            # 尝试作为URL处理
            if '.' in value:
                buttons.append({
                    'type': 'url',
                    'text': text,
                    'url': f'https://{value}'
                })
    
    task['buttons'] = buttons
    
    # 清空用户状态
    self.db.save_user(user_id, "", "", "")
    
    # 返回编辑器
    self.safe_send_message(update, f"✅ <b>已保存 {len(buttons)} 个按钮</b>\n\n返回编辑器继续设置", 'HTML')
    self.show_broadcast_wizard_editor_as_new_message(update, context)



    def handle_broadcast_target_selection(self, query, update, context, target):
    """处理目标选择"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    task['target'] = target
    
    # 获取目标用户列表
    target_users = self.db.get_target_users(target)
    
    if not target_users:
        self.safe_edit_message(query, "❌ 未找到符合条件的用户")
        return
    
    # 目标名称映射
    target_names = {
        'all': '全部用户',
        'members': '仅会员',
        'active_7d': '活跃用户(7天)',
        'new_7d': '新用户(7天)'
    }
    
    # 生成预览
    buttons_preview = ""
    if task['buttons']:
        buttons_preview = "\n\n<b>🔘 按钮:</b>\n"
        for i, btn in enumerate(task['buttons'], 1):
            if btn['type'] == 'url':
                buttons_preview += f"{i}. {btn['text']} → {btn['url']}\n"
            else:
                buttons_preview += f"{i}. {btn['text']} (点击提示)\n"
    
    text = f"""

    def start_broadcast_sending(self, query, update, context):
    """开始发送广播"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_broadcasts:
        self.safe_edit_message(query, "❌ 没有待处理的广播任务")
        return
    
    task = self.pending_broadcasts[user_id]
    
    # 插入广播记录
    buttons_json = json.dumps(task['buttons'], ensure_ascii=False)
    broadcast_id = self.db.insert_broadcast_record(
        task['title'],
        task['content'],
        buttons_json,
        task['target'],
        user_id
    )
    
    if not broadcast_id:
        self.safe_edit_message(query, "❌ 创建广播记录失败")
        return
    
    task['broadcast_id'] = broadcast_id
    
    # 启动异步发送
    def send_broadcast():
        asyncio.run(self.execute_broadcast_sending(update, context, user_id, broadcast_id))
    
    thread = threading.Thread(target=send_broadcast, daemon=True)
    thread.start()
    
    self.safe_edit_message(query, "📤 <b>开始发送广播...</b>\n\n正在初始化...", 'HTML')

async def execute_broadcast_sending(self, update, context, admin_id, broadcast_id):
    """执行广播发送"""
    if admin_id not in self.pending_broadcasts:
        return
    
    task = self.pending_broadcasts[admin_id]
    start_time = time.time()
    
    # 获取目标用户
    target_users = self.db.get_target_users(task['target'])
    total = len(target_users)
    
    if total == 0:
        context.bot.send_message(
            chat_id=admin_id,
            text="❌ 未找到符合条件的用户",
            parse_mode='HTML'
        )
        del self.pending_broadcasts[admin_id]
        return
    
    # 构建按钮
    keyboard = None
    if task['buttons']:
        button_rows = []
        for btn in task['buttons']:
            if btn['type'] == 'url':
                button_rows.append([InlineKeyboardButton(btn['text'], url=btn['url'])])
            else:
                button_rows.append([InlineKeyboardButton(btn['text'], callback_data=btn['data'])])
        keyboard = InlineKeyboardMarkup(button_rows)
    
    # 发送统计
    success_count = 0
    failed_count = 0
    
    # 批量发送
    batch_size = 25
    progress_msg = None
    
    try:
        # 发送进度消息
        progress_msg = context.bot.send_message(
            chat_id=admin_id,
            text=f"📤 <b>广播发送中...</b>\n\n• 目标: {total} 人\n• 进度: 0/{total}\n• 成功: 0\n• 失败: 0",
            parse_mode='HTML'
        )
        
        for i in range(0, total, batch_size):
            batch = target_users[i:i + batch_size]
            batch_start = time.time()
            
            for user_id in batch:
                try:
                    context.bot.send_message(
                        chat_id=user_id,
                        text=task['content'],
                        parse_mode='HTML',
                        reply_markup=keyboard
                    )
                    success_count += 1
                    self.db.add_broadcast_log(broadcast_id, user_id, 'success')
                except RetryAfter as e:
                    # 处理速率限制
                    await asyncio.sleep(e.retry_after + 1)
                    try:
                        context.bot.send_message(
                            chat_id=user_id,
                            text=task['content'],
                            parse_mode='HTML',
                            reply_markup=keyboard
                        )
                        success_count += 1
                        self.db.add_broadcast_log(broadcast_id, user_id, 'success')
                    except Exception as retry_err:
                        failed_count += 1
                        self.db.add_broadcast_log(broadcast_id, user_id, 'failed', str(retry_err))
                except BadRequest as e:
                    # 用户屏蔽机器人或其他错误
                    failed_count += 1
                    error_msg = str(e)
                    if 'bot was blocked' in error_msg.lower():
                        self.db.add_broadcast_log(broadcast_id, user_id, 'blocked', 'User blocked bot')
                    else:
                        self.db.add_broadcast_log(broadcast_id, user_id, 'failed', error_msg)
                except Exception as e:
                    failed_count += 1
                    self.db.add_broadcast_log(broadcast_id, user_id, 'failed', str(e))
            
            # 更新进度
            processed = success_count + failed_count
            elapsed = time.time() - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / speed if speed > 0 else 0
            
            if progress_msg and processed % batch_size == 0:
                try:
                    progress_msg.edit_text(
                        f"📤 <b>广播发送中...</b>\n\n"
                        f"• 目标: {total} 人\n"
                        f"• 进度: {processed}/{total} ({processed/total*100:.1f}%)\n"
                        f"• 成功: {success_count}\n"
                        f"• 失败: {failed_count}\n"
                        f"• 速度: {speed:.1f} 人/秒\n"
                        f"• 预计剩余: {int(eta)} 秒",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            # 批次间延迟
            if i + batch_size < total:
                await asyncio.sleep(random.uniform(0.8, 1.2))
        
        # 完成
        duration = time.time() - start_time
        self.db.update_broadcast_progress(
            broadcast_id, success_count, failed_count, 'completed', duration
        )
        
        # 发送完成消息
        success_rate = (success_count / total * 100) if total > 0 else 0
        final_text = f"""

    def show_broadcast_history(self, query):
    """显示广播历史"""
    query.answer()
    
    history = self.db.get_broadcast_history(10)
    
    if not history:
        text = """

    def show_broadcast_detail(self, query, broadcast_id):
    """显示广播详情"""
    query.answer()
    
    detail = self.db.get_broadcast_detail(broadcast_id)
    
    if not detail:
        self.safe_edit_message(query, "❌ 未找到广播记录")
        return
    
    # 状态图标
    status_icon = {
        'pending': '⏳ 待发送',
        'completed': '✅ 已完成',
        'failed': '❌ 失败'
    }.get(detail['status'], '❓ 未知')
    
    # 目标名称
    target_names = {
        'all': '全部用户',
        'members': '仅会员',
        'active_7d': '活跃用户(7天)',
        'new_7d': '新用户(7天)'
    }
    target_name = target_names.get(detail['target'], detail['target'])
    
    # 按钮信息
    buttons_info = ""
    if detail['buttons_json']:
        try:
            buttons = json.loads(detail['buttons_json'])
            if buttons:
                buttons_info = "\n\n<b>🔘 按钮:</b>\n"
                for i, btn in enumerate(buttons, 1):
                    if btn['type'] == 'url':
                        buttons_info += f"{i}. {btn['text']} → {btn['url']}\n"
                    else:
                        buttons_info += f"{i}. {btn['text']} (回调)\n"
        except:
            pass
    
    success_rate = (detail['success'] / detail['total'] * 100) if detail['total'] > 0 else 0
    
    text = f"""

    def cancel_broadcast(self, query, user_id):
    """取消广播"""
    query.answer()
    
    if user_id in self.pending_broadcasts:
        del self.pending_broadcasts[user_id]
    
    self.db.save_user(user_id, "", "", "")
    
    text = "❌ <b>已取消创建广播</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 返回", callback_data="broadcast_menu")]
    ])
    
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def restart_broadcast_wizard(self, query, update, context):
    """重新开始广播向导"""
    user_id = query.from_user.id
    
    if user_id in self.pending_broadcasts:
        del self.pending_broadcasts[user_id]
    
    self.start_broadcast_wizard(query, update, context)

# ================================
# 文件重命名功能
# ================================


