

# ===== Handler Methods from EnhancedBot =====

    def handle_vip_menu(self, query):
    """显示VIP会员菜单"""
    user_id = query.from_user.id
    query.answer()
    
    # 获取会员状态
    is_member, level, expiry = self.db.check_membership(user_id)
    
    if self.db.is_admin(user_id):
        member_status = t(user_id, 'member_status_admin')
    elif is_member:
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        
        member_status = f"{t(user_id, 'member_status_member')} {translated_level}\n{t(user_id, 'member_status_expire').format(time=expiry)}"
    else:
        member_status = t(user_id, 'member_status_none')
    
    text = f"""

    def handle_usdt_payment(self, query):
    """显示USDT支付菜单"""
    user_id = query.from_user.id
    query.answer()
    
    # 如果当前消息是图片消息（来自取消订单），先删除再发送新消息
    message_was_photo = query.message and query.message.photo
    if message_was_photo:
        try:
            query.message.delete()
        except Exception as e:
            logger.warning(f"删除图片消息失败: {e}")
    
    # 检查是否有待支付订单
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderStatus
        
        payment_db = PaymentDatabase()
        existing_order = payment_db.get_user_pending_order(user_id)
        
        if existing_order:
            # 检查是否过期
            from datetime import datetime, timezone, timedelta
            BEIJING_TZ = timezone(timedelta(hours=8))
            now = datetime.now(BEIJING_TZ)
            expires_at = existing_order.expires_at.replace(tzinfo=BEIJING_TZ)
            
            if now < expires_at:
                # 有未过期订单，提示用户 - 使用 i18n
                remaining_minutes = int((expires_at - now).total_seconds() / 60)
                
                error_existing = t(user_id, 'payment_error_existing_order')
                order_id_label = t(user_id, 'payment_order_id')
                amount_label = t(user_id, 'payment_amount')
                minutes_label = t(user_id, 'payment_minutes')
                
                text = f"""

    def handle_vip_redeem(self, query):
    """处理兑换卡密"""
    user_id = query.from_user.id
    query.answer()
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_redeem_code"
    )
    
    text = f"""



# ===== Handler Methods =====

    def handle_vip_menu(self, query):
    """显示VIP会员菜单"""
    user_id = query.from_user.id
    query.answer()
    
    # 获取会员状态
    is_member, level, expiry = self.db.check_membership(user_id)
    
    if self.db.is_admin(user_id):
        member_status = t(user_id, 'member_status_admin')
    elif is_member:
        # 翻译会员等级
        if level == "会员":
            translated_level = t(user_id, 'member_level_member')
        elif level == "管理员":
            translated_level = t(user_id, 'member_level_admin')
        else:
            translated_level = level  # 保留其他未知等级
        
        member_status = f"{t(user_id, 'member_status_member')} {translated_level}\n{t(user_id, 'member_status_expire').format(time=expiry)}"
    else:
        member_status = t(user_id, 'member_status_none')
    
    text = f"""

    def handle_usdt_payment(self, query):
    """显示USDT支付菜单"""
    user_id = query.from_user.id
    query.answer()
    
    # 如果当前消息是图片消息（来自取消订单），先删除再发送新消息
    message_was_photo = query.message and query.message.photo
    if message_was_photo:
        try:
            query.message.delete()
        except Exception as e:
            logger.warning(f"删除图片消息失败: {e}")
    
    # 检查是否有待支付订单
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tron import PaymentDatabase, OrderStatus
        
        payment_db = PaymentDatabase()
        existing_order = payment_db.get_user_pending_order(user_id)
        
        if existing_order:
            # 检查是否过期
            from datetime import datetime, timezone, timedelta
            BEIJING_TZ = timezone(timedelta(hours=8))
            now = datetime.now(BEIJING_TZ)
            expires_at = existing_order.expires_at.replace(tzinfo=BEIJING_TZ)
            
            if now < expires_at:
                # 有未过期订单，提示用户 - 使用 i18n
                remaining_minutes = int((expires_at - now).total_seconds() / 60)
                
                error_existing = t(user_id, 'payment_error_existing_order')
                order_id_label = t(user_id, 'payment_order_id')
                amount_label = t(user_id, 'payment_amount')
                minutes_label = t(user_id, 'payment_minutes')
                
                text = f"""

    def handle_vip_redeem(self, query):
    """处理兑换卡密"""
    user_id = query.from_user.id
    query.answer()
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_redeem_code"
    )
    
    text = f"""

