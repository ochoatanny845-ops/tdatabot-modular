

# ===== Handler Methods from EnhancedBot =====

    def add_admin_command(self, update: Update, context: CallbackContext):
    """添加管理员命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not context.args:
        self.safe_send_message(update, 
            "📝 使用方法:\n"
            "/addadmin [用户ID]\n"
            "/addadmin [用户名]\n\n"
            "示例:\n"
            "/addadmin 123456789\n"
            "/addadmin @username"
        )
        return
    
    target = context.args[0].strip()
    
    # 尝试解析为用户ID
    try:
        target_user_id = int(target)
        target_username = "未知"
        target_first_name = "未知"
    except ValueError:
        # 尝试按用户名查找
        target = target.replace("@", "")
        user_info = self.db.get_user_by_username(target)
        if not user_info:
            self.safe_send_message(update, f"❌ 找不到用户名 @{target}\n请确保用户已使用过机器人")
            return
        
        target_user_id, target_username, target_first_name = user_info
    
    # 检查是否已经是管理员
    if self.db.is_admin(target_user_id):
        self.safe_send_message(update, f"⚠️ 用户 {target_user_id} 已经是管理员")
        return
    
    # 添加管理员
    if self.db.add_admin(target_user_id, target_username, target_first_name, user_id):
        self.safe_send_message(update, 
            f"✅ 成功添加管理员\n\n"
            f"👤 用户ID: {target_user_id}\n"
            f"📝 用户名: @{target_username}\n"
            f"🏷️ 昵称: {target_first_name}\n"
            f"⏰ 添加时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}"
        )
    else:
        self.safe_send_message(update, "❌ 添加管理员失败")


    def remove_admin_command(self, update: Update, context: CallbackContext):
    """移除管理员命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not context.args:
        self.safe_send_message(update, 
            "📝 使用方法:\n"
            "/removeadmin [用户ID]\n\n"
            "示例:\n"
            "/removeadmin 123456789"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        self.safe_send_message(update, "❌ 请提供有效的用户ID")
        return
    
    # 不能移除配置文件中的管理员
    if target_user_id in config.ADMIN_IDS:
        self.safe_send_message(update, "❌ 无法移除配置文件中的管理员")
        return
    
    # 不能移除自己
    if target_user_id == user_id:
        self.safe_send_message(update, "❌ 无法移除自己的管理员权限")
        return
    
    if not self.db.is_admin(target_user_id):
        self.safe_send_message(update, f"⚠️ 用户 {target_user_id} 不是管理员")
        return
    
    if self.db.remove_admin(target_user_id):
        self.safe_send_message(update, f"✅ 已移除管理员: {target_user_id}")
    else:
        self.safe_send_message(update, "❌ 移除管理员失败")


    def list_admins_command(self, update: Update, context: CallbackContext):
    """查看管理员列表命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    admins = self.db.get_all_admins()
    
    if not admins:
        self.safe_send_message(update, "📝 暂无管理员")
        return
    
    admin_text = "<b>👑 管理员列表</b>\n\n"
    
    for i, (admin_id, username, first_name, added_time) in enumerate(admins, 1):
        admin_text += f"<b>{i}.</b> "
        if admin_id in config.ADMIN_IDS:
            admin_text += f"👑 <code>{admin_id}</code> (超级管理员)\n"
        else:
            admin_text += f"🔧 <code>{admin_id}</code>\n"
        
        if username and username != "配置文件管理员":
            admin_text += f"   📝 @{username}\n"
        if first_name and first_name != "":
            admin_text += f"   🏷️ {first_name}\n"
        if added_time != "系统内置":
            admin_text += f"   ⏰ {added_time}\n"
        admin_text += "\n"
    
    admin_text += f"<b>📊 总计: {len(admins)} 个管理员</b>"
    
    self.safe_send_message(update, admin_text, 'HTML')


    def handle_admin_panel(self, query):
    """Admin Panel"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    # Get statistics
    stats = self.db.get_user_statistics()
    admin_count = len(self.db.get_all_admins()) if self.db.get_all_admins() else 0
    
    admin_permission = t(user_id, 'admin_super_admin') if user_id in config.ADMIN_IDS else t(user_id, 'admin_normal_admin')
    
    admin_text = f"""

    def handle_admin_users(self, query):
    """User Management Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get active user list
    active_users = self.db.get_active_users(days=7, limit=15)
    
    text = f"<b>{t(user_id, 'user_management_title')}</b>\n\n<b>{t(user_id, 'user_management_recent_active')}</b>\n\n"
    
    if active_users:
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(active_users[:10], 1):
            # Check membership status
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "💎" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"{t(user_id, 'user_management_user_prefix')}{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code> - {display_name}\n"
            if last_active:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
                    if time_diff.days == 0:
                        time_str = t(user_id, 'user_management_time_hours_ago').format(hours=time_diff.seconds//3600)
                    else:
                        time_str = t(user_id, 'user_management_time_days_ago').format(days=time_diff.days)
                    text += f"   🕒 {time_str}\n"
                except:
                    text += f"   🕒 {last_active}\n"
            text += "\n"
    else:
        text += t(user_id, 'user_management_no_active') + "\n"
    
    text += f"\n{t(user_id, 'user_management_legend')}\n{t(user_id, 'user_management_legend_admin')} | {t(user_id, 'user_management_legend_vip')} | {t(user_id, 'user_management_legend_normal')}"
    
    buttons = [
        [
            InlineKeyboardButton(t(user_id, 'user_management_btn_search'), callback_data="admin_search"),
            InlineKeyboardButton(t(user_id, 'user_management_btn_recent'), callback_data="admin_recent")
        ],
        [
            InlineKeyboardButton(t(user_id, 'user_management_btn_stats'), callback_data="admin_stats"),
            InlineKeyboardButton(t(user_id, 'user_management_btn_refresh'), callback_data="admin_users")
        ],
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_stats(self, query):
    """User Statistics Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    stats = self.db.get_user_statistics()
    
    # Calculate ratios
    total = stats.get('total_users', 0)
    active_rate = (stats.get('week_active', 0) / total * 100) if total > 0 else 0
    member_rate = (stats.get('active_members', 0) / total * 100) if total > 0 else 0
    
    text = f"""

    def handle_admin_manage(self, query):
    """Admin Management Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get admin list
    admins = self.db.get_all_admins()
    
    text = f"<b>{t(user_id, 'admin_manage_title')}</b>\n\n<b>{t(user_id, 'admin_manage_list')}</b>\n\n"
    
    if admins:
        for i, (admin_id, username, first_name, added_time) in enumerate(admins, 1):
            is_super = admin_id in config.ADMIN_IDS
            admin_type = t(user_id, 'admin_manage_super') if is_super else t(user_id, 'admin_manage_normal')
            
            display_name = first_name or username or f"{t(user_id, 'admin_manage_admin_prefix')}{admin_id}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_type}\n"
            text += f"   ID: <code>{admin_id}</code>\n"
            text += f"   {t(user_id, 'admin_manage_nickname')}: {display_name}\n"
            if username and username != t(user_id, 'admin_manage_config_admin'):
                text += f"   {t(user_id, 'admin_manage_username')}: @{username}\n"
            display_time = added_time if added_time != "系统内置" else t(user_id, 'admin_manage_system_builtin')
            text += f"   {t(user_id, 'admin_manage_added_time')}: {display_time}\n\n"
    else:
        text += t(user_id, 'admin_manage_no_admins') + "\n"
    
    text += f"\n<b>{t(user_id, 'admin_manage_description')}</b>\n• {t(user_id, 'admin_manage_desc_super')}\n• {t(user_id, 'admin_manage_desc_normal')}"
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_search(self, query):
    """Search User Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""

    def handle_admin_recent(self, query):
    """Recently Registered Users"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    recent_users = self.db.get_recent_users(limit=15)
    
    text = f"<b>{t(user_id, 'recent_users_title')}</b>\n\n"
    
    if recent_users:
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(recent_users, 1):
            # Check membership status
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "💎" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"{t(user_id, 'user_management_user_prefix')}{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code> - {display_name}\n"
            
            if register_time:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    reg_time = datetime.strptime(register_time, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - reg_time
                    if time_diff.days == 0:
                        time_str = t(user_id, 'user_management_time_hours_ago').format(hours=time_diff.seconds//3600)
                    else:
                        time_str = t(user_id, 'user_management_time_days_ago').format(days=time_diff.days)
                    text += f"   📅 {t(user_id, 'recent_users_registered').format(time=time_str)}\n"
                except:
                    text += f"   📅 {register_time}\n"
            text += "\n"
    else:
        text += t(user_id, 'recent_users_no_data') + "\n"
    
    text += f"\n{t(user_id, 'user_management_legend')}\n{t(user_id, 'user_management_legend_admin')} | {t(user_id, 'user_management_legend_vip')} | {t(user_id, 'user_management_legend_normal')}"
    
    buttons = [
        [
            InlineKeyboardButton(t(user_id, 'admin_btn_user_management'), callback_data="admin_users"),
            InlineKeyboardButton(t(user_id, 'recent_users_btn_refresh'), callback_data="admin_recent")
        ],
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_payment_stats(self, query):
    """管理员收款统计页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    try:
        from tron import PaymentDatabase
        payment_db = PaymentDatabase()
        
        # 获取统计数据
        today_stats = payment_db.get_today_stats()
        week_stats = payment_db.get_week_stats()
        month_stats = payment_db.get_month_stats()
        
        # 格式化今日统计
        today_date = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        
        text = f"""<b>{t(user_id, 'admin_payment_stats_title')}</b>


    def handle_admin_payment_orders(self, query, page: int = 1):
    """管理员订单列表页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 分页获取订单
        per_page = 5
        orders, total_pages = payment_db.get_orders_paginated(page=page, per_page=per_page)
        
        if not orders:
            text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n{t(user_id, 'admin_no_orders')}"
            buttons = [
                [InlineKeyboardButton(t(user_id, 'btn_admin_back_stats'), callback_data="admin_payment_stats")]
            ]
            keyboard = InlineKeyboardMarkup(buttons)
            self.safe_edit_message(query, text, 'HTML', keyboard)
            return
        
        text = f"""<b>{t(user_id, 'admin_orders_title')}</b>


    def handle_admin_payment_export(self, query):
    """管理员导出报表页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""<b>{t(user_id, 'admin_export_title')}</b>


    def handle_admin_export_generate(self, query, export_type: str):
    """生成并导出报表"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer(t(user_id, 'admin_export_generating'))
    
    try:
        from tron import PaymentDatabase
        payment_db = PaymentDatabase()
        
        # 根据类型确定日期范围
        start_date = None
        end_date = None
        filename_suffix = export_type
        
        if export_type == "today":
            now = datetime.now(BEIJING_TZ)
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            filename_suffix = now.strftime('%Y-%m-%d')
        elif export_type == "week":
            now = datetime.now(BEIJING_TZ)
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
            filename_suffix = f"week_{start_date.strftime('%Y-%m-%d')}"
        elif export_type == "month":
            now = datetime.now(BEIJING_TZ)
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end_date = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
            else:
                end_date = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
            filename_suffix = now.strftime('%Y-%m')
        
        # 生成CSV
        csv_content = payment_db.export_orders_csv(start_date, end_date)
        
        if not csv_content:
            query.answer(t(user_id, 'admin_export_empty'), show_alert=True)
            return
        
        # 发送文件
        filename = t(user_id, 'admin_export_file_name').format(date=filename_suffix)
        csv_bytes = BytesIO(csv_content.encode('utf-8'))
        csv_bytes.seek(0)
        
        query.message.reply_document(
            document=csv_bytes,
            filename=filename,
            caption=t(user_id, 'admin_export_success')
        )
        
        # 返回到导出菜单
        self.handle_admin_payment_export(query)
        
    except Exception as e:
        logger.error(f"导出报表失败: {e}")
        query.answer("❌ 导出失败", show_alert=True)


    def handle_admin_query_by_date(self, query):
    """按日期查询提示"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status in database
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_admin_query_date"
    )
    
    text = t(user_id, 'admin_query_date_prompt')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'btn_cancel'), callback_data="admin_payment_orders")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_query_by_user(self, query):
    """按用户查询提示"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status in database
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_admin_query_user"
    )
    
    text = t(user_id, 'admin_query_user_prompt')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'btn_cancel'), callback_data="admin_payment_orders")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_query_input(self, update: Update, user_id: int, text: str):
    """处理管理员查询输入"""
    user_state = self.get_user_state(user_id)
    action = user_state.get('action')
    
    if action == 'admin_query_date':
        # 处理日期查询
        self.handle_admin_date_query_result(update, user_id, text)
    elif action == 'admin_query_user':
        # 处理用户查询
        self.handle_admin_user_query_result(update, user_id, text)


    def handle_admin_date_query_result(self, update: Update, user_id: int, text: str):
    """处理日期查询结果"""
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 解析日期
        parts = text.strip().split()
        
        if len(parts) == 1:
            # 单日查询
            date_str = parts[0]
            start_date = datetime.strptime(date_str, '%Y-%m-%d')
            start_date = start_date.replace(tzinfo=BEIJING_TZ, hour=0, minute=0, second=0)
            end_date = start_date.replace(hour=23, minute=59, second=59)
        elif len(parts) == 2:
            # 日期范围查询
            start_str, end_str = parts
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
            start_date = start_date.replace(tzinfo=BEIJING_TZ, hour=0, minute=0, second=0)
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
            end_date = end_date.replace(tzinfo=BEIJING_TZ, hour=23, minute=59, second=59)
        else:
            update.message.reply_text(t(user_id, 'admin_invalid_date'))
            return
        
        # 查询订单
        orders = payment_db.get_orders_by_date_range(start_date, end_date)
        
        if not orders:
            update.message.reply_text(t(user_id, 'admin_query_no_results'))
            return
        
        # 显示结果
        text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n"
        text += f"📅 {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}\n"
        text += f"共找到 {len(orders)} 笔订单\n"
        
        # 状态映射
        status_map = {
            'pending': '⏳ 待支付',
            'paid': '💳 已支付',
            'completed': '✅ 已完成',
            'expired': '⏱️ 已过期',
            'cancelled': '❌ 已取消'
        }
        
        for i, order in enumerate(orders[:10], 1):  # 最多显示10个
            plan_info = PaymentConfig.PAYMENT_PLANS.get(order.plan_id, {})
            plan_name = plan_info.get('name', order.plan_id)
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"{i}️⃣ {order.order_id}\n"
            text += f"• {t(user_id, 'admin_orders_user_id')}: <code>{order.user_id}</code>\n"
            text += f"• {t(user_id, 'admin_orders_amount')}: {order.amount:.4f} USDT\n"
            text += f"• {t(user_id, 'admin_orders_plan')}: {plan_name}\n"
            text += f"• {t(user_id, 'admin_orders_status')}: {status_map.get(order.status.value, order.status.value)}\n"
            text += f"• {t(user_id, 'admin_orders_created')}: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if len(orders) > 10:
            text += f"\n... 还有 {len(orders) - 10} 笔订单"
        
        update.message.reply_text(text, parse_mode='HTML')
        
        # 清除状态 - reset user status
        self.db.save_user(
            user_id,
            update.message.from_user.username or "",
            update.message.from_user.first_name or "",
            "active"
        )
        
    except ValueError:
        update.message.reply_text(t(user_id, 'admin_invalid_date'))
    except Exception as e:
        logger.error(f"日期查询失败: {e}")
        update.message.reply_text("❌ 查询失败")


    def handle_admin_user_query_result(self, update: Update, user_id: int, text: str):
    """处理用户查询结果"""
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 解析用户ID
        target_user_id = int(text.strip())
        
        # 查询订单
        orders = payment_db.get_orders_by_user(target_user_id)
        
        if not orders:
            update.message.reply_text(t(user_id, 'admin_query_no_results'))
            return
        
        # 显示结果
        text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n"
        text += f"👤 用户ID: <code>{target_user_id}</code>\n"
        text += f"共找到 {len(orders)} 笔订单\n"
        
        # 状态映射
        status_map = {
            'pending': '⏳ 待支付',
            'paid': '💳 已支付',
            'completed': '✅ 已完成',
            'expired': '⏱️ 已过期',
            'cancelled': '❌ 已取消'
        }
        
        for i, order in enumerate(orders[:10], 1):  # 最多显示10个
            plan_info = PaymentConfig.PAYMENT_PLANS.get(order.plan_id, {})
            plan_name = plan_info.get('name', order.plan_id)
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"{i}️⃣ {order.order_id}\n"
            text += f"• {t(user_id, 'admin_orders_amount')}: {order.amount:.4f} USDT\n"
            text += f"• {t(user_id, 'admin_orders_plan')}: {plan_name}\n"
            text += f"• {t(user_id, 'admin_orders_status')}: {status_map.get(order.status.value, order.status.value)}\n"
            text += f"• {t(user_id, 'admin_orders_created')}: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if len(orders) > 10:
            text += f"\n... 还有 {len(orders) - 10} 笔订单"
        
        update.message.reply_text(text, parse_mode='HTML')
        
        # 清除状态 - reset user status
        self.db.save_user(
            user_id,
            update.message.from_user.username or "",
            update.message.from_user.first_name or "",
            "active"
        )
        
    except ValueError:
        update.message.reply_text(t(user_id, 'admin_invalid_user_id'))
    except Exception as e:
        logger.error(f"用户查询失败: {e}")
        update.message.reply_text("❌ 查询失败")


    def handle_make_admin(self, query, target_user_id: int):
    """设置用户为管理员"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查用户是否存在
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        query.answer("❌ 用户不存在")
        return
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    
    # 添加为管理员
    success = self.db.add_admin(target_user_id, username, first_name, user_id)
    
    if success:
        query.answer("✅ 管理员设置成功")
        # 刷新用户详情页面
        self.handle_user_detail(query, target_user_id)
    else:
        query.answer("❌ 设置失败")

    def handle_admin_card_menu(self, query):
    """Admin Card Activation Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""

    def handle_admin_card_generate(self, query, days: int):
    """Admin Generate Card"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Generate card
    success, code, message = self.db.create_redeem_code(t(user_id, 'member_level_member'), days, None, user_id)
    
    if success:
        text = f"""

    def handle_admin_manual_menu(self, query):
    """Admin Manual Activation Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_manual_user"
    )
    
    text = f"""

    def handle_admin_manual_grant(self, query, context, days: int):
    """管理员执行人工开通"""
    admin_id = query.from_user.id
    
    if not self.db.is_admin(admin_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查是否有待处理的用户
    if admin_id not in self.pending_manual_open:
        query.answer("❌ 没有待处理的用户")
        return
    
    target_user_id = self.pending_manual_open[admin_id]
    
    # 执行授予
    success = self.db.grant_membership_days(target_user_id, days, "会员")
    
    if success:
        # 获取新的会员状态
        is_member, level, expiry = self.db.check_membership(target_user_id)
        
        # 获取用户信息
        user_info = self.db.get_user_membership_info(target_user_id)
        username = user_info.get('username', '')
        first_name = user_info.get('first_name', '')
        display_name = first_name or username or f"用户{target_user_id}"
        
        text = f"""

    def handle_admin_revoke_menu(self, query):
    """Admin Revoke Membership Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_revoke_user"
    )
    
    text = f"""

    def handle_admin_revoke_confirm(self, query, context, target_user_id: int):
    """管理员确认撤销会员"""
    admin_id = query.from_user.id
    
    if not self.db.is_admin(admin_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    query.answer()
    
    # 获取用户信息（撤销前）
    user_info = self.db.get_user_membership_info(target_user_id)
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    # 执行撤销
    success = self.db.revoke_membership(target_user_id)
    
    if success:
        text = f"""

    def payment_stats_command(self, update: Update, context: CallbackContext):
    """管理员支付统计命令"""
    user_id = update.effective_user.id
    
    # 检查是否是管理员
    if not self.db.is_admin(user_id):
        update.message.reply_text("❌ 无权访问")
        return
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderStatus
        
        payment_db = PaymentDatabase()
        
        # 获取统计数据
        conn = sqlite3.connect(payment_db.db_path)
        c = conn.cursor()
        
        # 总订单数
        c.execute("SELECT COUNT(*) FROM orders")
        total_orders = c.fetchone()[0]
        
        # 已完成订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.COMPLETED.value,))
        completed_orders = c.fetchone()[0]
        
        # 总收入
        c.execute("SELECT SUM(amount) FROM orders WHERE status = ?", (OrderStatus.COMPLETED.value,))
        total_revenue = c.fetchone()[0] or 0
        
        # 今日订单
        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ? AND created_at LIKE ?", 
                  (OrderStatus.COMPLETED.value, f"{today}%"))
        today_orders = c.fetchone()[0]
        
        # 今日收入
        c.execute("SELECT SUM(amount) FROM orders WHERE status = ? AND created_at LIKE ?",
                  (OrderStatus.COMPLETED.value, f"{today}%"))
        today_revenue = c.fetchone()[0] or 0
        
        # 待支付订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.PENDING.value,))
        pending_orders = c.fetchone()[0]
        
        # 已取消订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.CANCELLED.value,))
        cancelled_orders = c.fetchone()[0]
        
        # 已过期订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.EXPIRED.value,))
        expired_orders = c.fetchone()[0]
        
        conn.close()
        
        # 计算转化率
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        stats_text = f"""

    def handle_admin_revoke_cancel(self, query):
    """取消撤销会员"""
    query.answer()
    
    text = "❌ <b>已取消撤销操作</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 返回管理面板", callback_data="admin_panel")]
    ])
    
    self.safe_edit_message(query, text, 'HTML', keyboard)

# ================================
# 广播消息功能
# ================================


    def handle_batch_create_admin_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理管理员用户名输入（支持多个管理员，每行一个）"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    text = text.strip()
    if text.lower() in ['跳过', '无', 'skip', 'none', '']:
        task['admin_usernames'] = []
        task['admin_username'] = ""  # 向后兼容
    else:
        # 解析多个管理员（每行一个）
        lines = text.split('\n')
        admin_usernames = []
        for line in lines:
            line = line.strip()
            if line and line.lower() not in ['跳过', '无', 'skip', 'none']:
                # 移除 @ 前缀
                admin_username = line.lstrip('@')
                if admin_username:
                    admin_usernames.append(admin_username)
        
        task['admin_usernames'] = admin_usernames
        # 向后兼容：保存第一个管理员
        task['admin_username'] = admin_usernames[0] if admin_usernames else ""
    
    self._ask_for_group_names(update, user_id)




# ===== Handler Methods =====

    def add_admin_command(self, update: Update, context: CallbackContext):
    """添加管理员命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not context.args:
        self.safe_send_message(update, 
            "📝 使用方法:\n"
            "/addadmin [用户ID]\n"
            "/addadmin [用户名]\n\n"
            "示例:\n"
            "/addadmin 123456789\n"
            "/addadmin @username"
        )
        return
    
    target = context.args[0].strip()
    
    # 尝试解析为用户ID
    try:
        target_user_id = int(target)
        target_username = "未知"
        target_first_name = "未知"
    except ValueError:
        # 尝试按用户名查找
        target = target.replace("@", "")
        user_info = self.db.get_user_by_username(target)
        if not user_info:
            self.safe_send_message(update, f"❌ 找不到用户名 @{target}\n请确保用户已使用过机器人")
            return
        
        target_user_id, target_username, target_first_name = user_info
    
    # 检查是否已经是管理员
    if self.db.is_admin(target_user_id):
        self.safe_send_message(update, f"⚠️ 用户 {target_user_id} 已经是管理员")
        return
    
    # 添加管理员
    if self.db.add_admin(target_user_id, target_username, target_first_name, user_id):
        self.safe_send_message(update, 
            f"✅ 成功添加管理员\n\n"
            f"👤 用户ID: {target_user_id}\n"
            f"📝 用户名: @{target_username}\n"
            f"🏷️ 昵称: {target_first_name}\n"
            f"⏰ 添加时间: {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}"
        )
    else:
        self.safe_send_message(update, "❌ 添加管理员失败")


    def remove_admin_command(self, update: Update, context: CallbackContext):
    """移除管理员命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    if not context.args:
        self.safe_send_message(update, 
            "📝 使用方法:\n"
            "/removeadmin [用户ID]\n\n"
            "示例:\n"
            "/removeadmin 123456789"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        self.safe_send_message(update, "❌ 请提供有效的用户ID")
        return
    
    # 不能移除配置文件中的管理员
    if target_user_id in config.ADMIN_IDS:
        self.safe_send_message(update, "❌ 无法移除配置文件中的管理员")
        return
    
    # 不能移除自己
    if target_user_id == user_id:
        self.safe_send_message(update, "❌ 无法移除自己的管理员权限")
        return
    
    if not self.db.is_admin(target_user_id):
        self.safe_send_message(update, f"⚠️ 用户 {target_user_id} 不是管理员")
        return
    
    if self.db.remove_admin(target_user_id):
        self.safe_send_message(update, f"✅ 已移除管理员: {target_user_id}")
    else:
        self.safe_send_message(update, "❌ 移除管理员失败")


    def list_admins_command(self, update: Update, context: CallbackContext):
    """查看管理员列表命令"""
    user_id = update.effective_user.id
    
    if not self.db.is_admin(user_id):
        self.safe_send_message(update, "❌ 仅管理员可以使用此命令")
        return
    
    admins = self.db.get_all_admins()
    
    if not admins:
        self.safe_send_message(update, "📝 暂无管理员")
        return
    
    admin_text = "<b>👑 管理员列表</b>\n\n"
    
    for i, (admin_id, username, first_name, added_time) in enumerate(admins, 1):
        admin_text += f"<b>{i}.</b> "
        if admin_id in config.ADMIN_IDS:
            admin_text += f"👑 <code>{admin_id}</code> (超级管理员)\n"
        else:
            admin_text += f"🔧 <code>{admin_id}</code>\n"
        
        if username and username != "配置文件管理员":
            admin_text += f"   📝 @{username}\n"
        if first_name and first_name != "":
            admin_text += f"   🏷️ {first_name}\n"
        if added_time != "系统内置":
            admin_text += f"   ⏰ {added_time}\n"
        admin_text += "\n"
    
    admin_text += f"<b>📊 总计: {len(admins)} 个管理员</b>"
    
    self.safe_send_message(update, admin_text, 'HTML')


    def handle_admin_panel(self, query):
    """Admin Panel"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    # Get statistics
    stats = self.db.get_user_statistics()
    admin_count = len(self.db.get_all_admins()) if self.db.get_all_admins() else 0
    
    admin_permission = t(user_id, 'admin_super_admin') if user_id in config.ADMIN_IDS else t(user_id, 'admin_normal_admin')
    
    admin_text = f"""

    def handle_admin_users(self, query):
    """User Management Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get active user list
    active_users = self.db.get_active_users(days=7, limit=15)
    
    text = f"<b>{t(user_id, 'user_management_title')}</b>\n\n<b>{t(user_id, 'user_management_recent_active')}</b>\n\n"
    
    if active_users:
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(active_users[:10], 1):
            # Check membership status
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "💎" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"{t(user_id, 'user_management_user_prefix')}{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code> - {display_name}\n"
            if last_active:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    last_time = datetime.strptime(last_active, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - last_time
                    if time_diff.days == 0:
                        time_str = t(user_id, 'user_management_time_hours_ago').format(hours=time_diff.seconds//3600)
                    else:
                        time_str = t(user_id, 'user_management_time_days_ago').format(days=time_diff.days)
                    text += f"   🕒 {time_str}\n"
                except:
                    text += f"   🕒 {last_active}\n"
            text += "\n"
    else:
        text += t(user_id, 'user_management_no_active') + "\n"
    
    text += f"\n{t(user_id, 'user_management_legend')}\n{t(user_id, 'user_management_legend_admin')} | {t(user_id, 'user_management_legend_vip')} | {t(user_id, 'user_management_legend_normal')}"
    
    buttons = [
        [
            InlineKeyboardButton(t(user_id, 'user_management_btn_search'), callback_data="admin_search"),
            InlineKeyboardButton(t(user_id, 'user_management_btn_recent'), callback_data="admin_recent")
        ],
        [
            InlineKeyboardButton(t(user_id, 'user_management_btn_stats'), callback_data="admin_stats"),
            InlineKeyboardButton(t(user_id, 'user_management_btn_refresh'), callback_data="admin_users")
        ],
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_stats(self, query):
    """User Statistics Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    stats = self.db.get_user_statistics()
    
    # Calculate ratios
    total = stats.get('total_users', 0)
    active_rate = (stats.get('week_active', 0) / total * 100) if total > 0 else 0
    member_rate = (stats.get('active_members', 0) / total * 100) if total > 0 else 0
    
    text = f"""

    def handle_admin_manage(self, query):
    """Admin Management Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Get admin list
    admins = self.db.get_all_admins()
    
    text = f"<b>{t(user_id, 'admin_manage_title')}</b>\n\n<b>{t(user_id, 'admin_manage_list')}</b>\n\n"
    
    if admins:
        for i, (admin_id, username, first_name, added_time) in enumerate(admins, 1):
            is_super = admin_id in config.ADMIN_IDS
            admin_type = t(user_id, 'admin_manage_super') if is_super else t(user_id, 'admin_manage_normal')
            
            display_name = first_name or username or f"{t(user_id, 'admin_manage_admin_prefix')}{admin_id}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_type}\n"
            text += f"   ID: <code>{admin_id}</code>\n"
            text += f"   {t(user_id, 'admin_manage_nickname')}: {display_name}\n"
            if username and username != t(user_id, 'admin_manage_config_admin'):
                text += f"   {t(user_id, 'admin_manage_username')}: @{username}\n"
            display_time = added_time if added_time != "系统内置" else t(user_id, 'admin_manage_system_builtin')
            text += f"   {t(user_id, 'admin_manage_added_time')}: {display_time}\n\n"
    else:
        text += t(user_id, 'admin_manage_no_admins') + "\n"
    
    text += f"\n<b>{t(user_id, 'admin_manage_description')}</b>\n• {t(user_id, 'admin_manage_desc_super')}\n• {t(user_id, 'admin_manage_desc_normal')}"
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_search(self, query):
    """Search User Interface"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""

    def handle_admin_recent(self, query):
    """Recently Registered Users"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    recent_users = self.db.get_recent_users(limit=15)
    
    text = f"<b>{t(user_id, 'recent_users_title')}</b>\n\n"
    
    if recent_users:
        for i, (uid, username, first_name, register_time, last_active, status) in enumerate(recent_users, 1):
            # Check membership status
            is_member, level, _ = self.db.check_membership(uid)
            member_icon = "💎" if is_member else "❌"
            admin_icon = "👑" if self.db.is_admin(uid) else ""
            
            display_name = first_name or username or f"{t(user_id, 'user_management_user_prefix')}{uid}"
            if len(display_name) > 15:
                display_name = display_name[:15] + "..."
            
            text += f"{i}. {admin_icon}{member_icon} <code>{uid}</code> - {display_name}\n"
            
            if register_time:
                try:
                    # Database stores naive datetime strings, compare with naive Beijing time
                    reg_time = datetime.strptime(register_time, '%Y-%m-%d %H:%M:%S')
                    time_diff = datetime.now(BEIJING_TZ).replace(tzinfo=None) - reg_time
                    if time_diff.days == 0:
                        time_str = t(user_id, 'user_management_time_hours_ago').format(hours=time_diff.seconds//3600)
                    else:
                        time_str = t(user_id, 'user_management_time_days_ago').format(days=time_diff.days)
                    text += f"   📅 {t(user_id, 'recent_users_registered').format(time=time_str)}\n"
                except:
                    text += f"   📅 {register_time}\n"
            text += "\n"
    else:
        text += t(user_id, 'recent_users_no_data') + "\n"
    
    text += f"\n{t(user_id, 'user_management_legend')}\n{t(user_id, 'user_management_legend_admin')} | {t(user_id, 'user_management_legend_vip')} | {t(user_id, 'user_management_legend_normal')}"
    
    buttons = [
        [
            InlineKeyboardButton(t(user_id, 'admin_btn_user_management'), callback_data="admin_users"),
            InlineKeyboardButton(t(user_id, 'recent_users_btn_refresh'), callback_data="admin_recent")
        ],
        [InlineKeyboardButton(t(user_id, 'admin_btn_back_panel'), callback_data="admin_panel")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_payment_stats(self, query):
    """管理员收款统计页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    try:
        from tron import PaymentDatabase
        payment_db = PaymentDatabase()
        
        # 获取统计数据
        today_stats = payment_db.get_today_stats()
        week_stats = payment_db.get_week_stats()
        month_stats = payment_db.get_month_stats()
        
        # 格式化今日统计
        today_date = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        
        text = f"""<b>{t(user_id, 'admin_payment_stats_title')}</b>


    def handle_admin_payment_orders(self, query, page: int = 1):
    """管理员订单列表页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 分页获取订单
        per_page = 5
        orders, total_pages = payment_db.get_orders_paginated(page=page, per_page=per_page)
        
        if not orders:
            text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n{t(user_id, 'admin_no_orders')}"
            buttons = [
                [InlineKeyboardButton(t(user_id, 'btn_admin_back_stats'), callback_data="admin_payment_stats")]
            ]
            keyboard = InlineKeyboardMarkup(buttons)
            self.safe_edit_message(query, text, 'HTML', keyboard)
            return
        
        text = f"""<b>{t(user_id, 'admin_orders_title')}</b>


    def handle_admin_payment_export(self, query):
    """管理员导出报表页面"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""<b>{t(user_id, 'admin_export_title')}</b>


    def handle_admin_export_generate(self, query, export_type: str):
    """生成并导出报表"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer(t(user_id, 'admin_export_generating'))
    
    try:
        from tron import PaymentDatabase
        payment_db = PaymentDatabase()
        
        # 根据类型确定日期范围
        start_date = None
        end_date = None
        filename_suffix = export_type
        
        if export_type == "today":
            now = datetime.now(BEIJING_TZ)
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            filename_suffix = now.strftime('%Y-%m-%d')
        elif export_type == "week":
            now = datetime.now(BEIJING_TZ)
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
            filename_suffix = f"week_{start_date.strftime('%Y-%m-%d')}"
        elif export_type == "month":
            now = datetime.now(BEIJING_TZ)
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end_date = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
            else:
                end_date = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
            filename_suffix = now.strftime('%Y-%m')
        
        # 生成CSV
        csv_content = payment_db.export_orders_csv(start_date, end_date)
        
        if not csv_content:
            query.answer(t(user_id, 'admin_export_empty'), show_alert=True)
            return
        
        # 发送文件
        filename = t(user_id, 'admin_export_file_name').format(date=filename_suffix)
        csv_bytes = BytesIO(csv_content.encode('utf-8'))
        csv_bytes.seek(0)
        
        query.message.reply_document(
            document=csv_bytes,
            filename=filename,
            caption=t(user_id, 'admin_export_success')
        )
        
        # 返回到导出菜单
        self.handle_admin_payment_export(query)
        
    except Exception as e:
        logger.error(f"导出报表失败: {e}")
        query.answer("❌ 导出失败", show_alert=True)


    def handle_admin_query_by_date(self, query):
    """按日期查询提示"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status in database
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_admin_query_date"
    )
    
    text = t(user_id, 'admin_query_date_prompt')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'btn_cancel'), callback_data="admin_payment_orders")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_query_by_user(self, query):
    """按用户查询提示"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status in database
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_admin_query_user"
    )
    
    text = t(user_id, 'admin_query_user_prompt')
    
    buttons = [
        [InlineKeyboardButton(t(user_id, 'btn_cancel'), callback_data="admin_payment_orders")]
    ]
    
    keyboard = InlineKeyboardMarkup(buttons)
    self.safe_edit_message(query, text, 'HTML', keyboard)


    def handle_admin_query_input(self, update: Update, user_id: int, text: str):
    """处理管理员查询输入"""
    user_state = self.get_user_state(user_id)
    action = user_state.get('action')
    
    if action == 'admin_query_date':
        # 处理日期查询
        self.handle_admin_date_query_result(update, user_id, text)
    elif action == 'admin_query_user':
        # 处理用户查询
        self.handle_admin_user_query_result(update, user_id, text)


    def handle_admin_date_query_result(self, update: Update, user_id: int, text: str):
    """处理日期查询结果"""
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 解析日期
        parts = text.strip().split()
        
        if len(parts) == 1:
            # 单日查询
            date_str = parts[0]
            start_date = datetime.strptime(date_str, '%Y-%m-%d')
            start_date = start_date.replace(tzinfo=BEIJING_TZ, hour=0, minute=0, second=0)
            end_date = start_date.replace(hour=23, minute=59, second=59)
        elif len(parts) == 2:
            # 日期范围查询
            start_str, end_str = parts
            start_date = datetime.strptime(start_str, '%Y-%m-%d')
            start_date = start_date.replace(tzinfo=BEIJING_TZ, hour=0, minute=0, second=0)
            end_date = datetime.strptime(end_str, '%Y-%m-%d')
            end_date = end_date.replace(tzinfo=BEIJING_TZ, hour=23, minute=59, second=59)
        else:
            update.message.reply_text(t(user_id, 'admin_invalid_date'))
            return
        
        # 查询订单
        orders = payment_db.get_orders_by_date_range(start_date, end_date)
        
        if not orders:
            update.message.reply_text(t(user_id, 'admin_query_no_results'))
            return
        
        # 显示结果
        text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n"
        text += f"📅 {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}\n"
        text += f"共找到 {len(orders)} 笔订单\n"
        
        # 状态映射
        status_map = {
            'pending': '⏳ 待支付',
            'paid': '💳 已支付',
            'completed': '✅ 已完成',
            'expired': '⏱️ 已过期',
            'cancelled': '❌ 已取消'
        }
        
        for i, order in enumerate(orders[:10], 1):  # 最多显示10个
            plan_info = PaymentConfig.PAYMENT_PLANS.get(order.plan_id, {})
            plan_name = plan_info.get('name', order.plan_id)
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"{i}️⃣ {order.order_id}\n"
            text += f"• {t(user_id, 'admin_orders_user_id')}: <code>{order.user_id}</code>\n"
            text += f"• {t(user_id, 'admin_orders_amount')}: {order.amount:.4f} USDT\n"
            text += f"• {t(user_id, 'admin_orders_plan')}: {plan_name}\n"
            text += f"• {t(user_id, 'admin_orders_status')}: {status_map.get(order.status.value, order.status.value)}\n"
            text += f"• {t(user_id, 'admin_orders_created')}: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if len(orders) > 10:
            text += f"\n... 还有 {len(orders) - 10} 笔订单"
        
        update.message.reply_text(text, parse_mode='HTML')
        
        # 清除状态 - reset user status
        self.db.save_user(
            user_id,
            update.message.from_user.username or "",
            update.message.from_user.first_name or "",
            "active"
        )
        
    except ValueError:
        update.message.reply_text(t(user_id, 'admin_invalid_date'))
    except Exception as e:
        logger.error(f"日期查询失败: {e}")
        update.message.reply_text("❌ 查询失败")


    def handle_admin_user_query_result(self, update: Update, user_id: int, text: str):
    """处理用户查询结果"""
    try:
        from tron import PaymentDatabase, PaymentConfig
        payment_db = PaymentDatabase()
        
        # 解析用户ID
        target_user_id = int(text.strip())
        
        # 查询订单
        orders = payment_db.get_orders_by_user(target_user_id)
        
        if not orders:
            update.message.reply_text(t(user_id, 'admin_query_no_results'))
            return
        
        # 显示结果
        text = f"<b>{t(user_id, 'admin_orders_title')}</b>\n\n"
        text += f"👤 用户ID: <code>{target_user_id}</code>\n"
        text += f"共找到 {len(orders)} 笔订单\n"
        
        # 状态映射
        status_map = {
            'pending': '⏳ 待支付',
            'paid': '💳 已支付',
            'completed': '✅ 已完成',
            'expired': '⏱️ 已过期',
            'cancelled': '❌ 已取消'
        }
        
        for i, order in enumerate(orders[:10], 1):  # 最多显示10个
            plan_info = PaymentConfig.PAYMENT_PLANS.get(order.plan_id, {})
            plan_name = plan_info.get('name', order.plan_id)
            
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"{i}️⃣ {order.order_id}\n"
            text += f"• {t(user_id, 'admin_orders_amount')}: {order.amount:.4f} USDT\n"
            text += f"• {t(user_id, 'admin_orders_plan')}: {plan_name}\n"
            text += f"• {t(user_id, 'admin_orders_status')}: {status_map.get(order.status.value, order.status.value)}\n"
            text += f"• {t(user_id, 'admin_orders_created')}: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if len(orders) > 10:
            text += f"\n... 还有 {len(orders) - 10} 笔订单"
        
        update.message.reply_text(text, parse_mode='HTML')
        
        # 清除状态 - reset user status
        self.db.save_user(
            user_id,
            update.message.from_user.username or "",
            update.message.from_user.first_name or "",
            "active"
        )
        
    except ValueError:
        update.message.reply_text(t(user_id, 'admin_invalid_user_id'))
    except Exception as e:
        logger.error(f"用户查询失败: {e}")
        update.message.reply_text("❌ 查询失败")


    def handle_make_admin(self, query, target_user_id: int):
    """设置用户为管理员"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查用户是否存在
    user_info = self.db.get_user_membership_info(target_user_id)
    if not user_info:
        query.answer("❌ 用户不存在")
        return
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    
    # 添加为管理员
    success = self.db.add_admin(target_user_id, username, first_name, user_id)
    
    if success:
        query.answer("✅ 管理员设置成功")
        # 刷新用户详情页面
        self.handle_user_detail(query, target_user_id)
    else:
        query.answer("❌ 设置失败")

    def handle_admin_card_menu(self, query):
    """Admin Card Activation Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    text = f"""

    def handle_admin_card_generate(self, query, days: int):
    """Admin Generate Card"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Generate card
    success, code, message = self.db.create_redeem_code(t(user_id, 'member_level_member'), days, None, user_id)
    
    if success:
        text = f"""

    def handle_admin_manual_menu(self, query):
    """Admin Manual Activation Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_manual_user"
    )
    
    text = f"""

    def handle_admin_manual_grant(self, query, context, days: int):
    """管理员执行人工开通"""
    admin_id = query.from_user.id
    
    if not self.db.is_admin(admin_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    # 检查是否有待处理的用户
    if admin_id not in self.pending_manual_open:
        query.answer("❌ 没有待处理的用户")
        return
    
    target_user_id = self.pending_manual_open[admin_id]
    
    # 执行授予
    success = self.db.grant_membership_days(target_user_id, days, "会员")
    
    if success:
        # 获取新的会员状态
        is_member, level, expiry = self.db.check_membership(target_user_id)
        
        # 获取用户信息
        user_info = self.db.get_user_membership_info(target_user_id)
        username = user_info.get('username', '')
        first_name = user_info.get('first_name', '')
        display_name = first_name or username or f"用户{target_user_id}"
        
        text = f"""

    def handle_admin_revoke_menu(self, query):
    """Admin Revoke Membership Menu"""
    user_id = query.from_user.id
    
    if not self.db.is_admin(user_id):
        query.answer(t(user_id, 'admin_panel_access_denied'))
        return
    
    query.answer()
    
    # Set user status
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_revoke_user"
    )
    
    text = f"""

    def handle_admin_revoke_confirm(self, query, context, target_user_id: int):
    """管理员确认撤销会员"""
    admin_id = query.from_user.id
    
    if not self.db.is_admin(admin_id):
        query.answer("❌ 仅管理员可访问")
        return
    
    query.answer()
    
    # 获取用户信息（撤销前）
    user_info = self.db.get_user_membership_info(target_user_id)
    is_member, level, expiry = self.db.check_membership(target_user_id)
    
    username = user_info.get('username', '')
    first_name = user_info.get('first_name', '')
    display_name = first_name or username or f"用户{target_user_id}"
    
    # 执行撤销
    success = self.db.revoke_membership(target_user_id)
    
    if success:
        text = f"""

    def payment_stats_command(self, update: Update, context: CallbackContext):
    """管理员支付统计命令"""
    user_id = update.effective_user.id
    
    # 检查是否是管理员
    if not self.db.is_admin(user_id):
        update.message.reply_text("❌ 无权访问")
        return
    
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderStatus
        
        payment_db = PaymentDatabase()
        
        # 获取统计数据
        conn = sqlite3.connect(payment_db.db_path)
        c = conn.cursor()
        
        # 总订单数
        c.execute("SELECT COUNT(*) FROM orders")
        total_orders = c.fetchone()[0]
        
        # 已完成订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.COMPLETED.value,))
        completed_orders = c.fetchone()[0]
        
        # 总收入
        c.execute("SELECT SUM(amount) FROM orders WHERE status = ?", (OrderStatus.COMPLETED.value,))
        total_revenue = c.fetchone()[0] or 0
        
        # 今日订单
        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ? AND created_at LIKE ?", 
                  (OrderStatus.COMPLETED.value, f"{today}%"))
        today_orders = c.fetchone()[0]
        
        # 今日收入
        c.execute("SELECT SUM(amount) FROM orders WHERE status = ? AND created_at LIKE ?",
                  (OrderStatus.COMPLETED.value, f"{today}%"))
        today_revenue = c.fetchone()[0] or 0
        
        # 待支付订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.PENDING.value,))
        pending_orders = c.fetchone()[0]
        
        # 已取消订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.CANCELLED.value,))
        cancelled_orders = c.fetchone()[0]
        
        # 已过期订单
        c.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (OrderStatus.EXPIRED.value,))
        expired_orders = c.fetchone()[0]
        
        conn.close()
        
        # 计算转化率
        completion_rate = (completed_orders / total_orders * 100) if total_orders > 0 else 0
        
        stats_text = f"""

    def handle_admin_revoke_cancel(self, query):
    """取消撤销会员"""
    query.answer()
    
    text = "❌ <b>已取消撤销操作</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 返回管理面板", callback_data="admin_panel")]
    ])
    
    self.safe_edit_message(query, text, 'HTML', keyboard)

# ================================
# 广播消息功能
# ================================


    def handle_batch_create_admin_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理管理员用户名输入（支持多个管理员，每行一个）"""
    if user_id not in self.pending_batch_create:
        self.safe_send_message(update, "❌ 会话已过期，请重新开始")
        return
    
    task = self.pending_batch_create[user_id]
    
    text = text.strip()
    if text.lower() in ['跳过', '无', 'skip', 'none', '']:
        task['admin_usernames'] = []
        task['admin_username'] = ""  # 向后兼容
    else:
        # 解析多个管理员（每行一个）
        lines = text.split('\n')
        admin_usernames = []
        for line in lines:
            line = line.strip()
            if line and line.lower() not in ['跳过', '无', 'skip', 'none']:
                # 移除 @ 前缀
                admin_username = line.lstrip('@')
                if admin_username:
                    admin_usernames.append(admin_username)
        
        task['admin_usernames'] = admin_usernames
        # 向后兼容：保存第一个管理员
        task['admin_username'] = admin_usernames[0] if admin_usernames else ""
    
    self._ask_for_group_names(update, user_id)


