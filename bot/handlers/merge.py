

# ===== Handler Methods from EnhancedBot =====

    def handle_merge_start(self, query):
    """开始账户合并流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="temp_merge_")
    
    # 初始化任务
    self.pending_merge[user_id] = {
        'temp_dir': temp_dir,
        'files': []
    }
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_merge_files"
    )
    
    user_id = query.from_user.id
    text = f"""

    def handle_merge_file_upload(self, update: Update, context: CallbackContext, document):
    """处理合并文件上传 - 仅接受ZIP文件"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_merge:
        self.safe_send_message(update, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    filename = document.file_name
    
    # 检查文件类型 - 仅接受ZIP文件
    if not filename.lower().endswith('.zip'):
        self.safe_send_message(update, t(user_id, 'merge_zip_only_error'))
        return
    
    # 下载文件
    file_path = os.path.join(task['temp_dir'], filename)
    try:
        document.get_file().download(file_path)
        task['files'].append(filename)
        
        total_files = len(task['files'])
        
        # 创建即时操作按钮
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(user_id, 'merge_btn_continue'), callback_data="merge_continue")],
            [InlineKeyboardButton(t(user_id, 'merge_btn_complete'), callback_data="merge_finish")],
            [InlineKeyboardButton(t(user_id, 'merge_btn_cancel'), callback_data="merge_cancel")]
        ])
        
        self.safe_send_message(
            update,
            f"{t(user_id, 'merge_received_zip').format(count=total_files)}\n\n"
            f"{t(user_id, 'merge_filename').format(filename=filename)}\n\n"
            f"<b>{t(user_id, 'merge_select_action')}</b>\n"
            f"{t(user_id, 'merge_action_continue')}\n"
            f"{t(user_id, 'merge_action_complete')}",
            'HTML',
            reply_markup=keyboard
        )
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'merge_download_failed').format(error=str(e)))



    def handle_merge_continue(self, query):
    """处理继续上传文件"""
    user_id = query.from_user.id
    query.answer(t(user_id, 'merge_continue_upload_hint'))
    
    if user_id not in self.pending_merge:
        self.safe_edit_message(query, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    total_files = len(task['files'])
    
    text = f"""

    def handle_merge_cancel(self, query):
    """处理取消合并"""
    query.answer()
    user_id = query.from_user.id
    
    if user_id in self.pending_merge:
        self.cleanup_merge_task(user_id)
    
    self.safe_edit_message(query, t(user_id, 'merge_cancelled'))
    
    # 返回主菜单
    time.sleep(1)
    fake_update = type('obj', (object,), {
        'effective_user': type('obj', (object,), {'id': user_id})()
    })()
    self.show_main_menu(fake_update, user_id)


    def handle_merge_finish(self, update: Update, context: CallbackContext, query):
    """完成合并，开始处理"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_merge:
        self.safe_edit_message(query, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    
    if not task['files']:
        self.safe_edit_message(query, t(user_id, 'merge_no_files'))
        return
    
    self.safe_edit_message(query, f"<b>{t(user_id, 'merge_processing')}</b>", 'HTML')
    
    # 在后台线程中处理
    def process_merge():
        asyncio.run(self.process_merge_files(update, context, user_id))
    
    thread = threading.Thread(target=process_merge, daemon=True)
    thread.start()




# ===== Handler Methods =====

    def handle_merge_start(self, query):
    """开始账户合并流程"""
    user_id = query.from_user.id
    query.answer()
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="temp_merge_")
    
    # 初始化任务
    self.pending_merge[user_id] = {
        'temp_dir': temp_dir,
        'files': []
    }
    
    # 设置用户状态
    self.db.save_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or "",
        "waiting_merge_files"
    )
    
    user_id = query.from_user.id
    text = f"""

    def handle_merge_file_upload(self, update: Update, context: CallbackContext, document):
    """处理合并文件上传 - 仅接受ZIP文件"""
    user_id = update.effective_user.id
    
    if user_id not in self.pending_merge:
        self.safe_send_message(update, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    filename = document.file_name
    
    # 检查文件类型 - 仅接受ZIP文件
    if not filename.lower().endswith('.zip'):
        self.safe_send_message(update, t(user_id, 'merge_zip_only_error'))
        return
    
    # 下载文件
    file_path = os.path.join(task['temp_dir'], filename)
    try:
        document.get_file().download(file_path)
        task['files'].append(filename)
        
        total_files = len(task['files'])
        
        # 创建即时操作按钮
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(user_id, 'merge_btn_continue'), callback_data="merge_continue")],
            [InlineKeyboardButton(t(user_id, 'merge_btn_complete'), callback_data="merge_finish")],
            [InlineKeyboardButton(t(user_id, 'merge_btn_cancel'), callback_data="merge_cancel")]
        ])
        
        self.safe_send_message(
            update,
            f"{t(user_id, 'merge_received_zip').format(count=total_files)}\n\n"
            f"{t(user_id, 'merge_filename').format(filename=filename)}\n\n"
            f"<b>{t(user_id, 'merge_select_action')}</b>\n"
            f"{t(user_id, 'merge_action_continue')}\n"
            f"{t(user_id, 'merge_action_complete')}",
            'HTML',
            reply_markup=keyboard
        )
    except Exception as e:
        self.safe_send_message(update, t(user_id, 'merge_download_failed').format(error=str(e)))



    def handle_merge_continue(self, query):
    """处理继续上传文件"""
    user_id = query.from_user.id
    query.answer(t(user_id, 'merge_continue_upload_hint'))
    
    if user_id not in self.pending_merge:
        self.safe_edit_message(query, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    total_files = len(task['files'])
    
    text = f"""

    def handle_merge_cancel(self, query):
    """处理取消合并"""
    query.answer()
    user_id = query.from_user.id
    
    if user_id in self.pending_merge:
        self.cleanup_merge_task(user_id)
    
    self.safe_edit_message(query, t(user_id, 'merge_cancelled'))
    
    # 返回主菜单
    time.sleep(1)
    fake_update = type('obj', (object,), {
        'effective_user': type('obj', (object,), {'id': user_id})()
    })()
    self.show_main_menu(fake_update, user_id)


    def handle_merge_finish(self, update: Update, context: CallbackContext, query):
    """完成合并，开始处理"""
    user_id = query.from_user.id
    query.answer()
    
    if user_id not in self.pending_merge:
        self.safe_edit_message(query, t(user_id, 'merge_no_task'))
        return
    
    task = self.pending_merge[user_id]
    
    if not task['files']:
        self.safe_edit_message(query, t(user_id, 'merge_no_files'))
        return
    
    self.safe_edit_message(query, f"<b>{t(user_id, 'merge_processing')}</b>", 'HTML')
    
    # 在后台线程中处理
    def process_merge():
        asyncio.run(self.process_merge_files(update, context, user_id))
    
    thread = threading.Thread(target=process_merge, daemon=True)
    thread.start()


