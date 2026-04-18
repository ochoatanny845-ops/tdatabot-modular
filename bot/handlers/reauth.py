

# ===== Handler Methods from EnhancedBot =====

    def refresh_proxy_panel(self, query):
    """刷新代理面板"""
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # 统计住宅代理数量
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    proxy_text = f"""

    def handle_reauthorize_start(self, query):
    """处理重新授权开始"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查会员权限
    is_member, level, expiry = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(
            query,
            t(user_id, 'reauth_need_member'),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t(user_id, 'btn_vip_menu'), callback_data="vip_menu"),
                InlineKeyboardButton(t(user_id, 'btn_back'), callback_data="back_to_main")
            ]])
        )
        return
    
    text = f"""

    def handle_reauthorize_callbacks(self, update: Update, context: CallbackContext, query, data: str):
    """处理重新授权回调"""
    user_id = query.from_user.id
    
    if data == "reauthorize_cancel":
        query.answer()
        if user_id in self.pending_reauthorize:
            self.cleanup_reauthorize_task(user_id)
        self.show_main_menu(update, user_id)
    elif data == "reauthorize_confirm":
        self.handle_reauthorize_execute(update, context, query, user_id)
    elif data == "reauth_auto_detect":
        self.handle_reauthorize_auto_detect(update, context, query, user_id)
    elif data == "reauth_manual_input":
        self.handle_reauthorize_manual_input(update, context, query, user_id)


    def handle_reauthorize_auto_detect(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理自动识别2FA"""
    query.answer()
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    files = task['files']
    file_type = task['file_type']
    
    # 自动检测每个文件的密码
    progress_text = f"🔍 <b>{t(user_id, 'reauth_processing_file')}...</b>\n\n{t(user_id, 'status_processing')}"
    self.safe_edit_message(query, progress_text, parse_mode='HTML')
    
    detected_count = 0
    password_map = {}  # {file_path: password}
    
    for file_path, file_name in files:
        try:
            detected_password = self.two_factor_manager.password_detector.detect_password(file_path, file_type)
            if detected_password:
                password_map[file_path] = detected_password
                detected_count += 1
        except Exception as e:
            logger.warning(f"Failed to detect password for {file_name}: {e}")
    
    # 保存检测结果
    task['password_map'] = password_map
    task['password_mode'] = 'auto'
    
    # 显示检测结果
    result_text = f"""{t(user_id, 'reauth_pwd_detect_complete')}


    def handle_reauthorize_manual_input(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理手动输入2FA"""
    query.answer()
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    task['password_mode'] = 'manual'
    
    text = f"""<b>{t(user_id, 'reauth_manual_old_pwd_title')}</b>


    def handle_reauthorize_old_password_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理旧密码输入（手动模式）"""
    if user_id not in self.pending_reauthorize:
        self.safe_send_message(update, t(user_id, 'reauth_session_expired_restart'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 保存旧密码
    text = text.strip()
    if text.lower() in ['无', 'skip', 'none', '']:
        task['old_password'] = ""
    else:
        task['old_password'] = text
    
    # 询问新密码
    msg = self.safe_send_message(
        update,
        f"{t(user_id, 'reauth_old_pwd_saved')}\n\n{t(user_id, 'reauth_new_pwd_prompt')}\n\n{t(user_id, 'reauth_new_pwd_tip')}",
        parse_mode='HTML'
    )
    
    # 设置用户状态为等待输入新密码
    self.db.save_user(user_id, "", "", "reauthorize_new_password")


    def handle_reauthorize_new_password_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理新密码输入"""
    if user_id not in self.pending_reauthorize:
        self.safe_send_message(update, t(user_id, 'reauth_session_expired_restart'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 保存新密码
    text = text.strip()
    if text.lower() in ['无', 'skip', 'none', '']:
        task['new_password'] = ""
    else:
        task['new_password'] = text
    
    # 显示确认信息
    old_pwd_display = t(user_id, 'reauth_pwd_none') if not task.get('old_password') else t(user_id, 'reauth_pwd_masked')
    new_pwd_display = t(user_id, 'reauth_pwd_none') if not task.get('new_password') else t(user_id, 'reauth_pwd_masked')
    
    text = f"""

    def handle_reauthorize_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """执行重新授权"""
    query.answer(t(user_id, 'reauth_starting'))
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 在新线程中执行
    def execute():
        try:
            self._execute_reauthorize(update, context, user_id, task)
        except Exception as e:
            logger.error(f"Reauthorize execution failed: {e}")
            import traceback
            traceback.print_exc()
            context.bot.send_message(
                chat_id=user_id,
                text=f"❌ <b>{t(user_id, 'reauth_failed')}</b>\n\n{t(user_id, 'reauth_error').format(error=str(e))}",
                parse_mode='HTML'
            )
        finally:
            if user_id in self.pending_reauthorize:
                self.cleanup_reauthorize_task(user_id)
    
    thread = threading.Thread(target=execute, daemon=True)
    thread.start()
    
    self.safe_edit_message(
        query,
        f"<b>{t(user_id, 'reauth_in_progress')}</b>\n\n{t(user_id, 'reauth_please_wait')}",
        parse_mode='HTML'
    )


    def _create_reauth_progress_keyboard(self, user_id: int, total: int, success: int, frozen: int, wrong_pwd: int, banned: int, network_error: int) -> InlineKeyboardMarkup:
    """创建重新授权进度按钮 - 6行2列布局"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_account_count'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{total}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_success'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{success}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_frozen'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{frozen}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_banned'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{banned}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_2fa_error'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{wrong_pwd}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_network_error'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{network_error}", callback_data="reauthorize_noop")
        ]
    ])


    def _execute_reauthorize(self, update: Update, context: CallbackContext, user_id: int, task: Dict):
    """实际执行重新授权"""
    import asyncio
    
    files = task['files']
    file_type = task['file_type']
    password_mode = task.get('password_mode', 'manual')
    password_map = task.get('password_map', {})  # For auto mode
    old_password = task.get('old_password', '')  # For manual mode
    new_password = task.get('new_password', '')
    
    # 创建进度消息
    total_files = len(files)
    
    # 创建初始按钮布局
    keyboard = self._create_reauth_progress_keyboard(user_id, total_files, 0, 0, 0, 0, 0)
    
    progress_msg = context.bot.send_message(
        chat_id=user_id,
        text=f"🚀 <b>{t(user_id, 'reauth_start')}</b>\n\n{t(user_id, 'reauth_progress').format(current=0, total=total_files, percent=0)}",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    
    # 执行重新授权
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 结果分类
    results = {
        'success': [],
        'frozen': [],
        'banned': [],
        'wrong_password': [],
        'network_error': [],
        'other_error': []
    }
    
    last_update_count = 0
    
    def progress_callback(current, total, message):
        nonlocal last_update_count
        # 每10个更新一次，或者是最后一个
        if current - last_update_count >= 10 or current == total:
            try:
                progress = int(current / total * 100)
                
                # 统计当前结果
                success_count = len(results['success'])
                frozen_count = len(results['frozen'])
                banned_count = len(results['banned'])
                wrong_pwd_count = len(results['wrong_password'])
                network_error_count = len(results['network_error'])
                other_error_count = len(results['other_error'])
                
                # 创建实时统计按钮
                keyboard = self._create_reauth_progress_keyboard(
                    user_id, total, success_count, frozen_count, wrong_pwd_count, banned_count, network_error_count
                )
                
                logger.info(f"📊 重新授权进度: {current}/{total} ({progress}%) - 成功:{success_count} 冻结:{frozen_count} 封禁:{banned_count} 密码错误:{wrong_pwd_count} 网络:{network_error_count}")
                print(f"📊 重新授权进度: {current}/{total} ({progress}%) - 成功:{success_count} 冻结:{frozen_count} 封禁:{banned_count} 密码错误:{wrong_pwd_count} 网络:{network_error_count}", flush=True)
                
                context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=progress_msg.message_id,
                    text=f"🚀 <b>{t(user_id, 'reauth_start')}</b>\n\n{t(user_id, 'reauth_progress').format(current=current, total=total, percent=progress)}",
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                last_update_count = current
            except Exception as e:
                logger.warning(f"⚠️ 更新进度消息失败: {e}")
    
    try:
        logger.info(f"📊 开始重新授权 - 用户ID: {user_id}, 账号数: {total_files}")
        print(f"📊 开始重新授权 - 用户ID: {user_id}, 账号数: {total_files}, 并发数: {config.REAUTH_CONCURRENT}", flush=True)
        
        # 使用并发处理账号
        completed_count = 0
        
        async def process_account_wrapper(idx, file_path, file_name):
            """处理单个账号的包装器 - 确保永不卡死"""
            nonlocal completed_count
            try:
                # 根据模式决定使用哪个密码
                if password_mode == 'auto':
                    account_old_password = password_map.get(file_path, '')
                else:
                    account_old_password = old_password
                
                result = await self._reauthorize_single_account(
                    file_path, file_name, account_old_password, new_password, user_id, file_type
                )
                
                # 根据结果分类
                if result['status'] == 'success':
                    results['success'].append((file_path, file_name, result))
                elif result['status'] == 'frozen':
                    results['frozen'].append((file_path, file_name, result))
                elif result['status'] == 'banned':
                    results['banned'].append((file_path, file_name, result))
                elif result['status'] == 'wrong_password':
                    results['wrong_password'].append((file_path, file_name, result))
                elif result['status'] == 'network_error':
                    results['network_error'].append((file_path, file_name, result))
                else:
                    results['other_error'].append((file_path, file_name, result))
                
                completed_count += 1
                progress_callback(completed_count, total_files, f"已完成 {completed_count}/{total_files}")
                
            except Exception as e:
                # 确保任何异常都不会阻止进度
                logger.error(f"❌ 处理账号失败 {file_name}: {e}")
                print(f"❌ 处理账号失败 {file_name}: {e}", flush=True)
                results['other_error'].append((file_path, file_name, {'status': 'error', 'error': str(e)}))
                completed_count += 1
                progress_callback(completed_count, total_files, f"已完成 {completed_count}/{total_files}")
        
        async def process_batch():
            """批量并发处理账号 - 确保永不卡死"""
            # 创建信号量控制并发数
            semaphore = asyncio.Semaphore(config.REAUTH_CONCURRENT)
            
            async def process_with_semaphore(idx, file_path, file_name):
                async with semaphore:
                    await process_account_wrapper(idx, file_path, file_name)
            
            # 创建所有任务
            tasks = [
                process_with_semaphore(idx, file_path, file_name)
                for idx, (file_path, file_name) in enumerate(files)
            ]
            
            # 并发执行所有任务 - 添加总超时保护（每个账号最多3分钟，总共不超过账号数*3分钟）
            # 但至少30分钟
            MINIMUM_TOTAL_TIMEOUT = 1800  # 30分钟最小超时
            PER_ACCOUNT_TIMEOUT = 180  # 每个账号3分钟
            total_timeout = max(total_files * PER_ACCOUNT_TIMEOUT, MINIMUM_TOTAL_TIMEOUT)
            logger.info(f"⏰ 设置总超时: {total_timeout}秒 ({total_timeout/60:.1f}分钟)")
            print(f"⏰ 设置总超时: {total_timeout}秒 ({total_timeout/60:.1f}分钟)", flush=True)
            
            try:
                # 使用return_exceptions=True允许部分失败不影响其他任务
                # 异常已在process_account_wrapper中处理
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=total_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"⏰ 批量处理超时（{total_timeout}秒），强制结束")
                print(f"⏰ 批量处理超时（{total_timeout}秒），强制结束", flush=True)
        
        # 执行批量处理
        loop.run_until_complete(process_batch())
        
        # 生成报告和打包结果 - 确保总是执行
        logger.info("📊 开始生成报告...")
        print("📊 开始生成报告...", flush=True)
        try:
            self._generate_reauthorize_report(context, user_id, results, progress_msg)
        except Exception as e:
            logger.error(f"❌ 生成报告失败，但继续尝试发送已有数据: {e}")
            print(f"❌ 生成报告失败，但继续尝试发送已有数据: {e}", flush=True)
            # 即使报告生成失败，也要尝试发送基本统计信息
            try:
                total = sum(len(v) for v in results.values())
                success_count = len(results['success'])
                context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ 报告生成出现问题，但处理完成\n\n总数: {total}\n成功: {success_count}",
                    parse_mode='HTML'
                )
            except:
                pass
        
    except Exception as e:
        logger.error(f"❌ 重新授权执行失败: {e}")
        print(f"❌ 重新授权执行失败: {e}", flush=True)
        # 即使整体失败，也尝试发送错误消息
        try:
            context.bot.send_message(
                chat_id=user_id,
                text=f"❌ 重新授权出现严重错误: {str(e)}\n\n已处理账号可能未完全保存",
                parse_mode='HTML'
            )
        except:
            pass
        
    finally:
        loop.close()
        # 清理临时文件
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)

async def _reauthorize_single_account(self, file_path: str, file_name: str, old_password: str, new_password: str, user_id: int, file_type: str = 'session') -> Dict:
    """重新授权单个账号（支持Session和TData格式）- 带超时保护"""
    logger.info(f"🔄 开始处理账号: {file_name} (格式: {file_type.upper()})")
    print(f"🔄 开始处理账号: {file_name} (格式: {file_type.upper()})", flush=True)
    
    # 为每个账号设置最大处理时间（180秒 = 3分钟）
    # 这确保即使账号出现问题也不会永久卡住
    timeout_seconds = 180
    
    try:
        return await asyncio.wait_for(
            self._reauthorize_single_account_impl(file_path, file_name, old_password, new_password, user_id, file_type),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error(f"⏰ [{file_name}] 处理超时（{timeout_seconds}秒），自动跳过")
        print(f"⏰ [{file_name}] 处理超时（{timeout_seconds}秒），自动跳过", flush=True)
        return {'status': 'other_error', 'error': f'处理超时（{timeout_seconds}秒）'}
    except Exception as e:
        logger.error(f"❌ [{file_name}] 处理时发生未预期错误: {e}")
        print(f"❌ [{file_name}] 处理时发生未预期错误: {e}", flush=True)
        return {'status': 'other_error', 'error': f'未预期错误: {str(e)}'}

async def _reauthorize_single_account_impl(self, file_path: str, file_name: str, old_password: str, new_password: str, user_id: int, file_type: str = 'session') -> Dict:
    """重新授权单个账号的实际实现"""
    client = None
    new_client = None
    temp_session_path = None
    original_tdata_path = None
    
    try:
        # 如果是TData格式，先转换为Session
        if file_type == 'tdata':
            if not OPENTELE_AVAILABLE:
                return {'status': 'other_error', 'error': 'opentele库未安装，无法处理TData格式'}
            
            logger.info(f"📂 [{file_name}] TData格式 - 转换为Session进行处理...")
            print(f"📂 [{file_name}] TData格式 - 转换为Session进行处理...", flush=True)
            
            try:
                # 保存原始TData路径
                original_tdata_path = file_path
                
                # 加载TData - 添加超时保护（30秒）
                try:
                    tdesk = await asyncio.wait_for(
                        asyncio.to_thread(TDesktop, file_path),
                        timeout=30
                    )
                    if not tdesk.isLoaded():
                        return {'status': 'frozen', 'error': 'TData未授权或无效'}
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData加载超时（30秒）")
                    print(f"⏰ [{file_name}] TData加载超时（30秒）", flush=True)
                    return {'status': 'other_error', 'error': 'TData加载超时'}
                
                # 创建临时Session文件
                os.makedirs(config.SESSIONS_BAK_DIR, exist_ok=True)
                temp_session_name = f"reauth_tdata_{time.time_ns()}"
                temp_session_path = os.path.join(config.SESSIONS_BAK_DIR, temp_session_name)
                
                # 转换TData为Session - 添加超时保护（60秒）
                try:
                    temp_client = await asyncio.wait_for(
                        tdesk.ToTelethon(
                            session=temp_session_path,
                            flag=UseCurrentSession,
                            api=API.TelegramDesktop
                        ),
                        timeout=60
                    )
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData转Session超时（60秒）")
                    print(f"⏰ [{file_name}] TData转Session超时（60秒）", flush=True)
                    return {'status': 'other_error', 'error': 'TData转Session超时'}
                
                # 断开临时客户端
                if temp_client:
                    try:
                        await asyncio.wait_for(temp_client.disconnect(), timeout=10)
                    except Exception:
                        pass
                
                # 使用转换后的Session路径
                file_path = temp_session_path
                
                logger.info(f"✅ [{file_name}] TData转Session完成")
                print(f"✅ [{file_name}] TData转Session完成", flush=True)
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ [{file_name}] TData转换操作超时")
                print(f"⏰ [{file_name}] TData转换操作超时", flush=True)
                return {'status': 'other_error', 'error': 'TData转换操作超时'}
            except Exception as e:
                logger.error(f"❌ [{file_name}] TData转换失败: {e}")
                print(f"❌ [{file_name}] TData转换失败: {e}", flush=True)
                return {'status': 'other_error', 'error': f'TData转换失败: {str(e)}'}
        
        # 使用配置中的API凭据（不能使用随机设备的API凭据，因为现有session是用特定API凭据创建的）
        # Telegram会验证API凭据与手机号的匹配关系
        old_api_id = config.API_ID
        old_api_hash = config.API_HASH
        
        # 获取随机设备参数（用于新会话）
        # 注意：API凭据必须使用配置的有效凭据，不能随机化
        # 只随机化设备指纹参数（device_model, system_version等）
        random_device_params = None
        new_api_id = old_api_id  # 使用相同的API凭据
        new_api_hash = old_api_hash  # 使用相同的API凭据
        
        if config.REAUTH_USE_RANDOM_DEVICE:
            try:
                random_device_params = self.device_params_manager.get_random_device_params()
                logger.info(f"📱 [{file_name}] 新会话将使用随机设备指纹")
                print(f"📱 [{file_name}] 新会话将使用随机设备指纹", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 获取随机设备参数失败: {e}")
                print(f"⚠️ [{file_name}] 获取随机设备参数失败: {e}", flush=True)
        
        logger.info(f"📱 [{file_name}] 旧会话使用配置的API凭据: API_ID={old_api_id}")
        print(f"📱 [{file_name}] 旧会话使用配置的API凭据: API_ID={old_api_id}", flush=True)
        
        # 获取代理（强制使用代理优先）
        proxy_dict = None
        proxy_info = None
        use_proxy = config.REAUTH_FORCE_PROXY or self.proxy_manager.is_proxy_mode_active(self.db)
        
        if use_proxy and self.proxy_manager.proxies:
            proxy_info = self.proxy_manager.get_next_proxy()
            if proxy_info:
                proxy_dict = self.checker.create_proxy_dict(proxy_info)
                proxy_type = "住宅代理" if proxy_info.get('is_residential', False) else "代理"
                logger.info(f"🌐 [{file_name}] 强制使用{proxy_type}（配置: REAUTH_FORCE_PROXY={config.REAUTH_FORCE_PROXY}）")
                print(f"🌐 [{file_name}] 强制使用{proxy_type}（配置: REAUTH_FORCE_PROXY={config.REAUTH_FORCE_PROXY}）", flush=True)
            else:
                logger.warning(f"⚠️ [{file_name}] 代理模式启用但无可用代理")
                print(f"⚠️ [{file_name}] 代理模式启用但无可用代理", flush=True)
        else:
            logger.info(f"ℹ️ [{file_name}] 代理模式未启用，使用本地连接")
            print(f"ℹ️ [{file_name}] 代理模式未启用，使用本地连接", flush=True)
        
        # 步骤1: 创建旧客户端连接
        session_base = file_path.replace('.session', '') if file_path.endswith('.session') else file_path
        
        client = TelegramClient(
            session_base,
            int(old_api_id),
            str(old_api_hash),
            timeout=config.CONNECTION_TIMEOUT,
            connection_retries=3,
            retry_delay=1,
            proxy=proxy_dict
        )
        
        logger.info(f"⏳ [{file_name}] 连接到Telegram服务器（旧会话）...")
        print(f"⏳ [{file_name}] 连接到Telegram服务器（旧会话）...", flush=True)
        
        # 强制代理优先逻辑：只有代理超时才回退到本地
        connect_success = False
        try:
            await asyncio.wait_for(client.connect(), timeout=config.CONNECTION_TIMEOUT)
            logger.info(f"✅ [{file_name}] 旧会话连接成功（使用{'代理' if proxy_dict else '本地'}）")
            print(f"✅ [{file_name}] 旧会话连接成功（使用{'代理' if proxy_dict else '本地'}）", flush=True)
            connect_success = True
        except asyncio.TimeoutError:
            if proxy_dict and config.REAUTH_FORCE_PROXY:
                # 只有在使用代理且超时的情况下才回退
                logger.warning(f"⚠️ [{file_name}] 代理连接超时，回退到本地连接")
                print(f"⚠️ [{file_name}] 代理连接超时，回退到本地连接", flush=True)
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"⚠️ [{file_name}] 断开旧客户端失败: {e}")
                # 重新创建不带代理的客户端
                client = TelegramClient(
                    session_base,
                    int(old_api_id),
                    str(old_api_hash),
                    timeout=30
                )
                await client.connect()
                logger.info(f"✅ [{file_name}] 本地连接成功")
                print(f"✅ [{file_name}] 本地连接成功", flush=True)
                connect_success = True
            else:
                # 如果不是代理超时，或者没有配置强制代理，则抛出异常
                logger.error(f"❌ [{file_name}] 连接超时且无法回退")
                print(f"❌ [{file_name}] 连接超时且无法回退", flush=True)
                return {'status': 'network_error', 'error': '连接超时'}
        
        # 检查授权状态
        if not await client.is_user_authorized():
            return {'status': 'frozen', 'error': '账号未授权或已失效'}
        
        # 获取账号信息
        me = await client.get_me()
        phone = me.phone if me.phone else "unknown"
        logger.info(f"📱 [{file_name}] 账号手机号: {phone}")
        print(f"📱 [{file_name}] 账号手机号: {phone}", flush=True)
        
        # 步骤2: 重置所有会话（踢掉其他设备）
        logger.info(f"🔄 [{file_name}] 步骤1: 重置所有会话...")
        print(f"🔄 [{file_name}] 步骤1: 重置所有会话...", flush=True)
        
        try:
            sessions = await client(GetAuthorizationsRequest())
            if len(sessions.authorizations) > 1:
                await client(ResetAuthorizationsRequest())
                logger.info(f"✅ [{file_name}] 已踢掉其他设备登录")
                print(f"✅ [{file_name}] 已踢掉其他设备登录", flush=True)
            else:
                logger.info(f"ℹ️ [{file_name}] 只有一个会话，无需重置")
                print(f"ℹ️ [{file_name}] 只有一个会话，无需重置", flush=True)
        except Exception as e:
            logger.warning(f"⚠️ [{file_name}] 重置会话失败: {e}")
            print(f"⚠️ [{file_name}] 重置会话失败: {e}", flush=True)
        
        # 步骤3: 检查密码状态（如果提供了旧密码）
        # TODO: 实际的密码验证需要在登录时进行
        # Telethon不提供独立的密码验证API，只能在sign_in时验证
        if old_password:
            logger.info(f"🔐 [{file_name}] 步骤2: 检查2FA状态...")
            print(f"🔐 [{file_name}] 步骤2: 检查2FA状态...", flush=True)
            
            try:
                password_data = await client(GetPasswordRequest())
                if password_data.has_password:
                    logger.info(f"ℹ️ [{file_name}] 账号有2FA，将在重新登录时验证密码")
                    print(f"ℹ️ [{file_name}] 账号有2FA，将在重新登录时验证密码", flush=True)
                else:
                    logger.info(f"ℹ️ [{file_name}] 账号没有2FA")
                    print(f"ℹ️ [{file_name}] 账号没有2FA", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 检查2FA状态失败: {e}")
                print(f"⚠️ [{file_name}] 检查2FA状态失败: {e}", flush=True)
        
        # 步骤4: 创建新会话（使用随机设备参数）
        logger.info(f"🔑 [{file_name}] 步骤3: 创建新会话（使用随机设备参数）...")
        print(f"🔑 [{file_name}] 步骤3: 创建新会话（使用随机设备参数）...", flush=True)
        
        # 为新会话创建新路径
        new_session_path = f"{session_base}_new"
        
        # 创建新客户端（使用随机设备参数的API凭据）
        new_client = TelegramClient(
            new_session_path,
            int(new_api_id),
            str(new_api_hash),
            timeout=config.CONNECTION_TIMEOUT,
            proxy=proxy_dict,
            # 添加随机设备参数（如果有）
            device_model=random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop',
            system_version=random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10',
            app_version=random_device_params.get('app_version', '3.2.8 x64') if random_device_params else '3.2.8 x64',
            lang_code=random_device_params.get('lang_code', 'en') if random_device_params else 'en',
            system_lang_code=random_device_params.get('system_lang_code', 'en-US') if random_device_params else 'en-US'
        )
        
        logger.info(f"📱 [{file_name}] 新会话设备信息: {random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop'}, {random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10'}")
        print(f"📱 [{file_name}] 新会话设备信息: {random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop'}, {random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10'}", flush=True)
        
        # 连接新客户端（强制代理优先）
        try:
            await asyncio.wait_for(new_client.connect(), timeout=config.CONNECTION_TIMEOUT)
            logger.info(f"✅ [{file_name}] 新会话连接成功（使用{'代理' if proxy_dict else '本地'}）")
            print(f"✅ [{file_name}] 新会话连接成功（使用{'代理' if proxy_dict else '本地'}）", flush=True)
        except asyncio.TimeoutError:
            if proxy_dict and config.REAUTH_FORCE_PROXY:
                logger.warning(f"⚠️ [{file_name}] 新会话代理连接超时，回退到本地连接")
                print(f"⚠️ [{file_name}] 新会话代理连接超时，回退到本地连接", flush=True)
                try:
                    await new_client.disconnect()
                except Exception as e:
                    logger.warning(f"⚠️ [{file_name}] 断开新客户端失败: {e}")
                # 重新创建不带代理的客户端
                new_client = TelegramClient(
                    new_session_path,
                    int(new_api_id),
                    str(new_api_hash),
                    timeout=config.CONNECTION_TIMEOUT,
                    device_model=random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop',
                    system_version=random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10',
                    app_version=random_device_params.get('app_version', '3.2.8 x64') if random_device_params else '3.2.8 x64',
                    lang_code=random_device_params.get('lang_code', 'en') if random_device_params else 'en',
                    system_lang_code=random_device_params.get('system_lang_code', 'en-US') if random_device_params else 'en-US'
                )
                await new_client.connect()
                logger.info(f"✅ [{file_name}] 新会话本地连接成功")
                print(f"✅ [{file_name}] 新会话本地连接成功", flush=True)
            else:
                raise
        
        # 步骤5: 请求验证码
        logger.info(f"📲 [{file_name}] 步骤4: 请求验证码...")
        print(f"📲 [{file_name}] 步骤4: 请求验证码...", flush=True)
        
        sent_code = await new_client(SendCodeRequest(
            phone,
            int(new_api_id),
            str(new_api_hash),
            CodeSettings()
        ))
        
        logger.info(f"✅ [{file_name}] 验证码已发送")
        print(f"✅ [{file_name}] 验证码已发送", flush=True)
        
        # 步骤6: 从旧会话获取验证码
        logger.info(f"📥 [{file_name}] 步骤5: 获取验证码...")
        print(f"📥 [{file_name}] 步骤5: 获取验证码...", flush=True)
        
        await asyncio.sleep(3)  # 等待验证码到达
        
        entity = await client.get_entity(777000)
        messages = await client.get_messages(entity, limit=1)
        
        if not messages:
            return {'status': 'other_error', 'error': '未收到验证码'}
        
        # Support both 5 and 6 digit verification codes
        # Use a pattern that works for digit-only codes without word boundaries
        code_match = re.search(r"(\d{5,6})", messages[0].message)
        if not code_match:
            return {'status': 'other_error', 'error': '验证码格式不正确'}
        
        code = code_match.group(1)
        logger.info(f"✅ [{file_name}] 获取到验证码: {code}")
        print(f"✅ [{file_name}] 获取到验证码: {code}", flush=True)
        
        # 步骤7: 新客户端登录
        logger.info(f"🔐 [{file_name}] 步骤6: 新会话登录...")
        print(f"🔐 [{file_name}] 步骤6: 新会话登录...", flush=True)
        
        try:
            await new_client.sign_in(
                phone=phone,
                phone_code_hash=sent_code.phone_code_hash,
                code=code
            )
            logger.info(f"✅ [{file_name}] 新会话登录成功")
            print(f"✅ [{file_name}] 新会话登录成功", flush=True)
        except SessionPasswordNeededError:
            # 需要2FA密码 - 优先使用旧密码，如果没有则使用新密码
            password_to_use = old_password if old_password else new_password
            if not password_to_use:
                return {'status': 'wrong_password', 'error': '需要2FA密码但未提供'}
            
            try:
                await new_client.sign_in(phone=phone, password=password_to_use)
                logger.info(f"✅ [{file_name}] 使用2FA密码登录成功")
                print(f"✅ [{file_name}] 使用2FA密码登录成功", flush=True)
            except PasswordHashInvalidError:
                return {'status': 'wrong_password', 'error': '2FA密码错误'}
        
        # 初始化密码设置状态标志
        password_set_success = False
        
        # 步骤8: 设置新密码（如果提供）
        if new_password and new_password != old_password:
            logger.info(f"🔑 [{file_name}] 步骤7: 设置新密码...")
            print(f"🔑 [{file_name}] 步骤7: 设置新密码...", flush=True)
            
            try:
                # 使用edit_2fa方法来设置新密码
                # 这是Telethon推荐的方式
                await new_client.edit_2fa(
                    current_password=old_password if old_password else None,
                    new_password=new_password,
                    hint=f"Modified {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",  # 使用UTC时间
                    email=None  # 可选的恢复邮箱
                )
                
                password_set_success = True
                logger.info(f"✅ [{file_name}] 新密码设置成功")
                print(f"✅ [{file_name}] 新密码设置成功", flush=True)
                
            except PasswordHashInvalidError:
                # 专门处理密码错误异常
                logger.warning(f"⚠️ [{file_name}] 旧密码不正确，无法设置新密码")
                print(f"⚠️ [{file_name}] 旧密码不正确，无法设置新密码", flush=True)
                # 不阻止整个流程，继续执行
                
            except (RPCError, FloodWaitError, NetworkError) as e:
                # 处理Telegram API相关错误
                error_type = type(e).__name__
                logger.warning(f"⚠️ [{file_name}] 设置新密码失败（Telegram错误）: {error_type}")
                print(f"⚠️ [{file_name}] 设置新密码失败（Telegram错误）: {error_type}", flush=True)
                # 不阻止整个流程，继续执行
                
            except Exception as e:
                # 捕获其他未预期的错误
                error_type = type(e).__name__
                logger.warning(f"⚠️ [{file_name}] 设置新密码时出现未预期错误: {error_type}")
                print(f"⚠️ [{file_name}] 设置新密码时出现未预期错误: {error_type}", flush=True)
                # 不阻止整个流程，继续执行
            
            # 如果密码设置失败，记录到结果中
            if not password_set_success:
                logger.info(f"ℹ️ [{file_name}] 注意: 新密码未成功设置，账号当前密码保持不变")
                print(f"ℹ️ [{file_name}] 注意: 新密码未成功设置，账号当前密码保持不变", flush=True)
                
        elif new_password and new_password == old_password:
            logger.info(f"ℹ️ [{file_name}] 新密码与旧密码相同，跳过密码设置")
            print(f"ℹ️ [{file_name}] 新密码与旧密码相同，跳过密码设置", flush=True)
        else:
            logger.info(f"ℹ️ [{file_name}] 未提供新密码，跳过密码设置")
            print(f"ℹ️ [{file_name}] 未提供新密码，跳过密码设置", flush=True)
        
        # 步骤9: 登出旧会话
        logger.info(f"🚪 [{file_name}] 步骤8: 登出旧会话...")
        print(f"🚪 [{file_name}] 步骤8: 登出旧会话...", flush=True)
        
        try:
            await client.log_out()
            logger.info(f"✅ [{file_name}] 旧会话已登出")
            print(f"✅ [{file_name}] 旧会话已登出", flush=True)
        except Exception as e:
            logger.warning(f"⚠️ [{file_name}] 登出旧会话失败: {e}")
            print(f"⚠️ [{file_name}] 登出旧会话失败: {e}", flush=True)
        
        # 步骤10: 验证旧会话失效
        logger.info(f"✔️ [{file_name}] 步骤9: 验证旧会话失效...")
        print(f"✔️ [{file_name}] 步骤9: 验证旧会话失效...", flush=True)
        
        # 断开新客户端
        await new_client.disconnect()
        
        # 替换旧会话文件
        old_session_file = f"{session_base}.session"
        new_session_file = f"{new_session_path}.session"
        
        if os.path.exists(new_session_file):
            if os.path.exists(old_session_file):
                os.remove(old_session_file)
            shutil.move(new_session_file, old_session_file)
            
            # 处理journal文件
            new_journal = f"{new_session_path}.session-journal"
            old_journal = f"{session_base}.session-journal"
            if os.path.exists(new_journal):
                if os.path.exists(old_journal):
                    os.remove(old_journal)
                shutil.move(new_journal, old_journal)
            
            logger.info(f"✅ [{file_name}] 新会话文件已替换旧会话")
            print(f"✅ [{file_name}] 新会话文件已替换旧会话", flush=True)
        
        # 步骤10: 如果原始格式是TData，转换回TData
        if file_type == 'tdata' and original_tdata_path:
            logger.info(f"📂 [{file_name}] 步骤10: 转换Session回TData格式...")
            print(f"📂 [{file_name}] 步骤10: 转换Session回TData格式...", flush=True)
            
            convert_client = None
            try:
                # 使用新Session创建TData - 添加总超时保护（90秒）
                try:
                    new_tdata_path = f"{original_tdata_path}_new"
                    os.makedirs(new_tdata_path, exist_ok=True)
                    
                    # 连接新Session - 使用OpenTele的TelegramClient
                    from opentele.tl import TelegramClient as OpenTeleClient
                    convert_client = OpenTeleClient(
                        session_base,
                        int(new_api_id),
                        str(new_api_hash)
                    )
                    
                    # 连接超时保护（15秒）
                    await asyncio.wait_for(convert_client.connect(), timeout=15)
                    
                    if not await convert_client.is_user_authorized():
                        logger.error(f"❌ [{file_name}] 新Session未授权，无法转换回TData")
                        print(f"❌ [{file_name}] 新Session未授权，无法转换回TData", flush=True)
                        # 清理临时目录
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': '新Session未授权，无法转换回TData'}
                    
                    # 转换Session为TData
                    logger.info(f"🔄 [{file_name}] 开始转换Session为TData...")
                    print(f"🔄 [{file_name}] 开始转换Session为TData...", flush=True)
                    
                    # 转换Session为TData - 添加超时保护（60秒）
                    try:
                        tdesk_new = await asyncio.wait_for(
                            convert_client.ToTDesktop(flag=UseCurrentSession),
                            timeout=60
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ [{file_name}] Session转TData超时（60秒）")
                        print(f"⏰ [{file_name}] Session转TData超时（60秒）", flush=True)
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': 'Session转TData超时'}
                    
                    # 保存TData - 添加超时保护（使用线程，15秒）
                    logger.info(f"💾 [{file_name}] 保存TData到: {new_tdata_path}")
                    print(f"💾 [{file_name}] 保存TData到: {new_tdata_path}", flush=True)
                    
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(tdesk_new.SaveTData, new_tdata_path),
                            timeout=15
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ [{file_name}] 保存TData超时（15秒）")
                        print(f"⏰ [{file_name}] 保存TData超时（15秒）", flush=True)
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': '保存TData超时'}
                    
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData转换整体超时")
                    print(f"⏰ [{file_name}] TData转换整体超时", flush=True)
                    if os.path.exists(new_tdata_path):
                        shutil.rmtree(new_tdata_path, ignore_errors=True)
                    return {'status': 'other_error', 'error': 'TData转换整体超时'}
                
                # 验证TData目录是否创建成功
                if not os.path.exists(new_tdata_path):
                    logger.error(f"❌ [{file_name}] TData转换失败：目录不存在")
                    print(f"❌ [{file_name}] TData转换失败：目录不存在", flush=True)
                    return {'status': 'other_error', 'error': 'TData转换失败：目录不存在'}
                
                tdata_dirs = [d for d in os.listdir(new_tdata_path) if os.path.isdir(os.path.join(new_tdata_path, d))]
                if not tdata_dirs:
                    logger.error(f"❌ [{file_name}] TData转换失败：未生成TData目录")
                    print(f"❌ [{file_name}] TData转换失败：未生成TData目录", flush=True)
                    if os.path.exists(new_tdata_path):
                        shutil.rmtree(new_tdata_path, ignore_errors=True)
                    return {'status': 'other_error', 'error': 'TData转换失败：未生成TData目录'}
                
                logger.info(f"✅ [{file_name}] TData目录已生成: {tdata_dirs}")
                print(f"✅ [{file_name}] TData目录已生成: {tdata_dirs}", flush=True)
                
                # 创建2fa.txt文件（只在密码设置成功时）
                if new_password and password_set_success:
                    password_file = os.path.join(new_tdata_path, "2fa.txt")
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(new_password)
                    logger.info(f"✅ [{file_name}] 已创建2fa.txt密码文件")
                    print(f"✅ [{file_name}] 已创建2fa.txt密码文件", flush=True)
                
                # 删除旧TData，替换为新TData
                logger.info(f"🔄 [{file_name}] 替换旧TData...")
                print(f"🔄 [{file_name}] 替换旧TData...", flush=True)
                if os.path.exists(original_tdata_path):
                    shutil.rmtree(original_tdata_path, ignore_errors=True)
                shutil.move(new_tdata_path, original_tdata_path)
                
                logger.info(f"✅ [{file_name}] Session已成功转换回TData格式")
                print(f"✅ [{file_name}] Session已成功转换回TData格式", flush=True)
                
                # 断开客户端
                if convert_client:
                    await convert_client.disconnect()
                
            except Exception as e:
                logger.error(f"❌ [{file_name}] 转换回TData失败: {e}")
                print(f"❌ [{file_name}] 转换回TData失败: {e}", flush=True)
                import traceback
                traceback.print_exc()
                
                # 清理临时目录
                if os.path.exists(f"{original_tdata_path}_new"):
                    shutil.rmtree(f"{original_tdata_path}_new", ignore_errors=True)
                
                # 断开客户端
                if convert_client:
                    try:
                        await convert_client.disconnect()
                    except Exception as e:
                        logger.warning(f"⚠️ [{file_name}] 断开客户端失败: {e}")
                
                # TData转换失败应该返回错误，不应该标记为成功
                return {'status': 'other_error', 'error': f'TData转换失败: {str(e)}'}
        
        logger.info(f"🎉 [{file_name}] 重新授权完成！")
        print(f"🎉 [{file_name}] 重新授权完成！", flush=True)
        
        # 准备返回数据
        result = {
            'status': 'success',
            'phone': phone,
            'message': '重新授权成功',
            'file_type': file_type,
            'new_password': new_password if new_password else '无',  # 新密码
            'password_set_success': password_set_success,  # 密码设置状态：True=成功，False=失败/未尝试
            'device_model': random_device_params.get('device_model', '默认设备') if random_device_params else '默认设备',
            'system_version': random_device_params.get('system_version', '默认系统') if random_device_params else '默认系统',
            'app_version': random_device_params.get('app_version', '默认版本') if random_device_params else '默认版本',
            'proxy_used': '使用代理' if proxy_dict else '本地连接',
            'proxy_type': proxy_info.get('type', 'N/A') if proxy_info else 'N/A'
        }
        
        # 更新JSON文件（包括新设备参数和twoFA）
        if file_type == 'session':
            json_path = os.path.splitext(f"{session_base}.session")[0] + '.json'
            try:
                current_time = datetime.now(BEIJING_TZ)
                
                # 读取或创建JSON数据
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    logger.info(f"📄 [{file_name}] 读取现有JSON文件")
                    print(f"📄 [{file_name}] 读取现有JSON文件", flush=True)
                else:
                    # 创建新的JSON文件结构
                    json_data = {
                        "phone": phone,
                        "session_file": os.path.splitext(file_name)[0],
                        "last_connect_date": current_time.strftime('%Y-%m-%dT%H:%M:%S+0000'),
                        "session_created_date": current_time.strftime('%Y-%m-%dT%H:%M:%S+0000'),
                        "last_check_time": int(current_time.timestamp())
                    }
                    logger.info(f"📄 [{file_name}] 创建新JSON文件")
                    print(f"📄 [{file_name}] 创建新JSON文件", flush=True)
                
                # 更新设备参数（如果使用了随机设备）
                if random_device_params:
                    json_data['app_id'] = new_api_id
                    json_data['app_hash'] = new_api_hash
                    json_data['device_model'] = random_device_params.get('device_model', 'Desktop')
                    json_data['system_version'] = random_device_params.get('system_version', 'Windows 10')
                    json_data['app_version'] = random_device_params.get('app_version', '3.2.8 x64')
                    json_data['lang_pack'] = random_device_params.get('lang_code', 'en')
                    json_data['system_lang_pack'] = random_device_params.get('system_lang_code', 'en-US')
                    
                    # 兼容旧字段名
                    json_data['device'] = random_device_params.get('device', 'Desktop')
                    json_data['sdk'] = random_device_params.get('sdk', 'Windows 10 x64')
                    
                    logger.info(f"✅ [{file_name}] 已更新JSON文件中的设备参数")
                    print(f"✅ [{file_name}] 已更新JSON文件中的设备参数", flush=True)
                
                # 更新2FA密码（只在密码设置成功时更新）
                if new_password and password_set_success:
                    # 删除所有旧的密码字段
                    old_fields_to_remove = ['twoFA', '2fa', 'password', 'two_fa']
                    for field in old_fields_to_remove:
                        if field in json_data:
                            del json_data[field]
                    
                    # 设置标准的 twofa 字段
                    json_data['twoFA'] = new_password
                    json_data['has_password'] = True
                    logger.info(f"✅ [{file_name}] 已更新JSON文件中的twofa字段")
                    print(f"✅ [{file_name}] 已更新JSON文件中的twofa字段", flush=True)
                elif new_password and not password_set_success:
                    logger.info(f"ℹ️ [{file_name}] 密码设置失败，保持JSON文件中的旧密码")
                    print(f"ℹ️ [{file_name}] 密码设置失败，保持JSON文件中的旧密码", flush=True)
                
                # 保存JSON文件
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"💾 [{file_name}] JSON文件已保存")
                print(f"💾 [{file_name}] JSON文件已保存", flush=True)
                
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 更新JSON文件失败: {e}")
                print(f"⚠️ [{file_name}] 更新JSON文件失败: {e}", flush=True)
        
        # 更新TData格式的密码文件（只在密码设置成功时更新）
        if new_password and password_set_success and file_type == 'tdata' and original_tdata_path:
            try:
                # 尝试常见的密码文件名
                password_files = ['2fa.txt', 'twofa.txt', 'password.txt']
                password_file_path = None
                
                # 检查是否已存在密码文件
                for pf in password_files:
                    test_path = os.path.join(original_tdata_path, pf)
                    if os.path.exists(test_path):
                        password_file_path = test_path
                        break
                
                # 如果不存在，创建2fa.txt
                if not password_file_path:
                    password_file_path = os.path.join(original_tdata_path, '2fa.txt')
                
                # 写入新密码
                with open(password_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_password)
                
                logger.info(f"✅ [{file_name}] 已更新TData密码文件: {os.path.basename(password_file_path)}")
                print(f"✅ [{file_name}] 已更新TData密码文件: {os.path.basename(password_file_path)}", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 更新TData密码文件失败: {e}")
                print(f"⚠️ [{file_name}] 更新TData密码文件失败: {e}", flush=True)
        elif new_password and not password_set_success and file_type == 'tdata' and original_tdata_path:
            logger.info(f"ℹ️ [{file_name}] 密码设置失败，保持TData原始密码文件")
            print(f"ℹ️ [{file_name}] 密码设置失败，保持TData原始密码文件", flush=True)
        
        # 添加文件路径信息
        if file_type == 'session':
            # Session格式：返回session文件路径
            result['session_path'] = f"{session_base}.session"
            result['tdata_path'] = None
        else:
            # TData格式：返回TData目录路径和session文件路径
            result['session_path'] = f"{session_base}.session" if os.path.exists(f"{session_base}.session") else None
            result['tdata_path'] = original_tdata_path
        
        return result
        
    except UserDeactivatedError:
        return {'status': 'frozen', 'error': '账号已被冻结'}
    except PhoneNumberBannedError:
        return {'status': 'banned', 'error': '账号已被封禁'}
    except PasswordHashInvalidError:
        return {'status': 'wrong_password', 'error': '密码错误'}
    except asyncio.TimeoutError:
        return {'status': 'network_error', 'error': '连接超时'}
    except Exception as e:
        logger.error(f"❌ [{file_name}] 重新授权失败: {e}")
        print(f"❌ [{file_name}] 重新授权失败: {e}", flush=True)
        return {'status': 'other_error', 'error': str(e)}
    
    finally:
        # 清理客户端
        if client:
            try:
                await client.disconnect()
            except:
                pass
        if new_client:
            try:
                await new_client.disconnect()
            except:
                pass
        
        # 清理临时Session文件（如果是从TData转换的）
        if temp_session_path and os.path.exists(f"{temp_session_path}.session"):
            try:
                os.remove(f"{temp_session_path}.session")
                journal_file = f"{temp_session_path}.session-journal"
                if os.path.exists(journal_file):
                    os.remove(journal_file)
                logger.info(f"🧹 [{file_name}] 已清理临时Session文件")
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 清理临时Session失败: {e}")


    def _generate_reauthorize_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成重新授权报告和打包结果 - 确保永不卡死"""
    logger.info("📊 开始生成报告和打包结果...")
    print("📊 开始生成报告和打包结果...", flush=True)
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    
    # 统计
    total = sum(len(v) for v in results.values())
    success_count = len(results['success'])
    frozen_count = len(results['frozen'])
    banned_count = len(results['banned'])
    wrong_pwd_count = len(results['wrong_password'])
    network_error_count = len(results['network_error'])
    other_error_count = len(results['other_error'])
    
    # 生成文本报告 - 添加异常保护
    report_filename = f"reauthorize_report_{timestamp}.txt"
    report_path = os.path.join(config.RESULTS_DIR, report_filename)
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'reauth_report_title')}\n")
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'reauth_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
            f.write(f"{t(user_id, 'reauth_report_total')} {total}\n")
            f.write(f"{t(user_id, 'reauth_report_success')} {success_count}\n")
            f.write(f"{t(user_id, 'reauth_report_frozen')} {frozen_count}\n")
            f.write(f"{t(user_id, 'reauth_report_banned')} {banned_count}\n")
            f.write(f"{t(user_id, 'reauth_report_pwd_error')} {wrong_pwd_count}\n")
            f.write(f"{t(user_id, 'reauth_report_network')} {network_error_count}\n")
            f.write(f"{t(user_id, 'reauth_report_other')} {other_error_count}\n")
            f.write("=" * 80 + "\n\n")
            
            # 详细结果
            for category, items in results.items():
                if items:
                    # 翻译分类标题
                    category_key = f'reauth_report_category_{category}'
                    category_title = t(user_id, category_key)
                    f.write(f"\n{category_title} ({len(items)})\n")
                    f.write("-" * 80 + "\n")
                    for file_path, file_name, result in items:
                        f.write(f"{t(user_id, 'reauth_report_file')} {file_name}\n")
                        if 'phone' in result:
                            f.write(f"{t(user_id, 'reauth_report_phone')} {result['phone']}\n")
                        
                        # 成功的账户显示详细信息
                        if category == 'success':
                            if 'device_model' in result:
                                f.write(f"{t(user_id, 'reauth_report_device_model')} {result['device_model']}\n")
                            if 'system_version' in result:
                                f.write(f"{t(user_id, 'reauth_report_system_version')} {result['system_version']}\n")
                            if 'app_version' in result:
                                f.write(f"{t(user_id, 'reauth_report_app_version')} {result['app_version']}\n")
                            if 'proxy_used' in result:
                                # 翻译连接方式
                                proxy_value = result['proxy_used']
                                if '使用代理' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_proxy')
                                elif '本地连接 (代理失败后回退)' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_local_fallback')
                                elif '本地连接' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_local')
                                else:
                                    proxy_value_translated = proxy_value
                                
                                f.write(f"{t(user_id, 'reauth_report_connection')} {proxy_value_translated}")
                                if result.get('proxy_type') and result['proxy_type'] != 'N/A':
                                    f.write(f" ({result['proxy_type'].upper()})")
                                f.write("\n")
                            if 'new_password' in result:
                                f.write(f"{t(user_id, 'reauth_report_new_password')} {result['new_password']}\n")
                        
                        if 'error' in result:
                            f.write(f"{t(user_id, 'reauth_report_error')} {result['error']}\n")
                        f.write("\n")
        logger.info(f"✅ 报告文件已生成: {report_path}")
        print(f"✅ 报告文件已生成: {report_path}", flush=True)
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
        print(f"❌ 生成报告文件失败: {e}", flush=True)
        # 创建一个简化的报告
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(f"{t(user_id, 'reauth_report_gen_failed')} {e}\n\n")
                f.write(f"{t(user_id, 'reauth_report_total_success').format(total=total, success=success_count)}\n")
        except:
            pass
    
    # 打包成功的账号（支持TData和Session格式）- 添加异常保护
    zip_files = []
    
    # 打包成功的账号
    if results['success']:
        logger.info("📦 开始打包成功的账号...")
        print("📦 开始打包成功的账号...", flush=True)
        try:
            success_zip = os.path.join(config.RESULTS_DIR, f"reauthorize_success_{timestamp}.zip")
            with zipfile.ZipFile(success_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path, file_name, result in results['success']:
                    result_file_type = result.get('file_type', 'session')
                    phone = result.get('phone', 'unknown')
                    
                    if result_file_type == 'tdata':
                        # TData格式：创建 手机号/tdata/D877... 结构
                        tdata_path = result.get('tdata_path')
                        if tdata_path and os.path.exists(tdata_path):
                            # SaveTData会在指定路径下创建tdata子目录
                            # 需要找到包含D877...目录的实际tdata目录
                            actual_tdata_dir = os.path.join(tdata_path, 'tdata')
                            
                            if os.path.exists(actual_tdata_dir) and os.path.isdir(actual_tdata_dir):
                                # 有tdata子目录，使用它
                                source_dir = actual_tdata_dir
                            else:
                                # 没有tdata子目录，tdata_path本身就是tdata目录
                                source_dir = tdata_path
                            
                            # 添加source_dir下的所有文件，路径为：手机号/tdata/D877.../
                            for root, dirs, files in os.walk(source_dir):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对于source_dir的相对路径
                                    rel_path = os.path.relpath(file_full_path, source_dir)
                                    # 构建完整的归档路径：手机号/tdata/D877.../file
                                    arc_path = os.path.join(phone, 'tdata', rel_path)
                                    zipf.write(file_full_path, arc_path)
                            
                            # 如果密码设置成功，创建2fa.txt文件
                            password_set_success = result.get('password_set_success', False)
                            new_password = result.get('new_password', '')
                            if password_set_success and new_password and new_password != '无':
                                # 在zip中创建 手机号/2fa.txt 文件（与tdata同级）
                                password_content = new_password.encode('utf-8')
                                password_arcname = os.path.join(phone, '2fa.txt')
                                zipf.writestr(password_arcname, password_content)
                            
                            # 添加Session文件（如果有）到手机号根目录
                            session_path = result.get('session_path')
                            if session_path and os.path.exists(session_path):
                                session_base = os.path.splitext(session_path)[0]
                                # Session文件
                                zipf.write(session_path, f"{phone}/{phone}.session")
                                # Journal文件
                                journal_path = f"{session_base}.session-journal"
                                if os.path.exists(journal_path):
                                    zipf.write(journal_path, f"{phone}/{phone}.session-journal")
                                # JSON文件
                                json_path = f"{session_base}.json"
                                if os.path.exists(json_path):
                                    zipf.write(json_path, f"{phone}/{phone}.json")
                    else:
                        # Session格式：直接打包
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 添加journal文件
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 添加JSON文件
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            zip_files.append(('success', success_zip, success_count))
            logger.info(f"✅ 成功账号已打包: {success_zip}")
            print(f"✅ 成功账号已打包: {success_zip}", flush=True)
        except Exception as e:
            logger.error(f"❌ 打包成功账号失败: {e}")
            print(f"❌ 打包成功账号失败: {e}", flush=True)
    
    # 打包失败的账号（分类）- 添加异常保护
    failed_categories = {
        'frozen': ('冻结', results['frozen']),
        'banned': ('封禁', results['banned']),
        'wrong_password': ('密码错误', results['wrong_password']),
        'network_error': ('网络错误', results['network_error']),
        'other_error': ('其他错误', results['other_error'])
    }
    
    for category_key, (category_name, items) in failed_categories.items():
        if items:
            logger.info(f"📦 开始打包{category_name}账号...")
            print(f"📦 开始打包{category_name}账号...", flush=True)
            try:
                failed_zip = os.path.join(config.RESULTS_DIR, f"reauthorize_{category_key}_{timestamp}.zip")
                with zipfile.ZipFile(failed_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path, file_name, result in items:
                        # 失败的账号直接返回原始上传的完整文件结构
                        # 不做任何修改，保持原样
                        if os.path.isdir(file_path):
                            # TData目录 - 找到并打包包含手机号的完整文件夹
                            # file_path通常指向D877...或tdata目录
                            # 需要找到最顶层的手机号文件夹并完整打包
                            
                            # 向上查找，找到手机号文件夹（通常是数字命名的文件夹）
                            current_path = file_path
                            phone_folder = None
                            
                            # 最多向上查找3层
                            for _ in range(3):
                                parent = os.path.dirname(current_path)
                                folder_name = os.path.basename(current_path)
                                
                                # 如果文件夹名是数字（手机号），就是我们要找的
                                if folder_name.isdigit() and len(folder_name) > 10:
                                    phone_folder = current_path
                                    break
                                current_path = parent
                            
                            # 如果没找到手机号文件夹，就用file_path的父目录
                            if not phone_folder:
                                phone_folder = os.path.dirname(file_path)
                            
                            # 打包整个手机号文件夹及其所有内容
                            base_dir = os.path.dirname(phone_folder)
                            for root, dirs, files in os.walk(phone_folder):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    # 保持从base_dir开始的相对路径
                                    rel_path = os.path.relpath(file_full_path, base_dir)
                                    zipf.write(file_full_path, rel_path)
                        else:
                            # Session文件 - 直接使用原始文件名
                            if os.path.exists(file_path):
                                zipf.write(file_path, file_name)
                            # 添加journal文件（如果存在）
                            journal_path = file_path + '-journal'
                            if os.path.exists(journal_path):
                                zipf.write(journal_path, file_name + '-journal')
                            # 添加json文件（如果存在）
                            json_path = os.path.splitext(file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
                zip_files.append((category_key, failed_zip, len(items)))
                logger.info(f"✅ {category_name}账号已打包: {failed_zip}")
                print(f"✅ {category_name}账号已打包: {failed_zip}", flush=True)
            except Exception as e:
                logger.error(f"❌ 打包{category_name}账号失败: {e}")
                print(f"❌ 打包{category_name}账号失败: {e}", flush=True)
    
    # 发送统计信息 - 添加异常保护
    summary = f"""



# ===== Handler Methods =====

    def refresh_proxy_panel(self, query):
    """刷新代理面板"""
    proxy_enabled_db = self.db.get_proxy_enabled()
    proxy_mode_active = self.proxy_manager.is_proxy_mode_active(self.db)
    
    # 统计住宅代理数量
    residential_count = sum(1 for p in self.proxy_manager.proxies if p.get('is_residential', False))
    
    proxy_text = f"""

    def handle_reauthorize_start(self, query):
    """处理重新授权开始"""
    query.answer()
    user_id = query.from_user.id
    
    # 检查会员权限
    is_member, level, expiry = self.db.check_membership(user_id)
    if not is_member and not self.db.is_admin(user_id):
        self.safe_edit_message(
            query,
            t(user_id, 'reauth_need_member'),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t(user_id, 'btn_vip_menu'), callback_data="vip_menu"),
                InlineKeyboardButton(t(user_id, 'btn_back'), callback_data="back_to_main")
            ]])
        )
        return
    
    text = f"""

    def handle_reauthorize_callbacks(self, update: Update, context: CallbackContext, query, data: str):
    """处理重新授权回调"""
    user_id = query.from_user.id
    
    if data == "reauthorize_cancel":
        query.answer()
        if user_id in self.pending_reauthorize:
            self.cleanup_reauthorize_task(user_id)
        self.show_main_menu(update, user_id)
    elif data == "reauthorize_confirm":
        self.handle_reauthorize_execute(update, context, query, user_id)
    elif data == "reauth_auto_detect":
        self.handle_reauthorize_auto_detect(update, context, query, user_id)
    elif data == "reauth_manual_input":
        self.handle_reauthorize_manual_input(update, context, query, user_id)


    def handle_reauthorize_auto_detect(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理自动识别2FA"""
    query.answer()
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    files = task['files']
    file_type = task['file_type']
    
    # 自动检测每个文件的密码
    progress_text = f"🔍 <b>{t(user_id, 'reauth_processing_file')}...</b>\n\n{t(user_id, 'status_processing')}"
    self.safe_edit_message(query, progress_text, parse_mode='HTML')
    
    detected_count = 0
    password_map = {}  # {file_path: password}
    
    for file_path, file_name in files:
        try:
            detected_password = self.two_factor_manager.password_detector.detect_password(file_path, file_type)
            if detected_password:
                password_map[file_path] = detected_password
                detected_count += 1
        except Exception as e:
            logger.warning(f"Failed to detect password for {file_name}: {e}")
    
    # 保存检测结果
    task['password_map'] = password_map
    task['password_mode'] = 'auto'
    
    # 显示检测结果
    result_text = f"""{t(user_id, 'reauth_pwd_detect_complete')}


    def handle_reauthorize_manual_input(self, update: Update, context: CallbackContext, query, user_id: int):
    """处理手动输入2FA"""
    query.answer()
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    task['password_mode'] = 'manual'
    
    text = f"""<b>{t(user_id, 'reauth_manual_old_pwd_title')}</b>


    def handle_reauthorize_old_password_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理旧密码输入（手动模式）"""
    if user_id not in self.pending_reauthorize:
        self.safe_send_message(update, t(user_id, 'reauth_session_expired_restart'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 保存旧密码
    text = text.strip()
    if text.lower() in ['无', 'skip', 'none', '']:
        task['old_password'] = ""
    else:
        task['old_password'] = text
    
    # 询问新密码
    msg = self.safe_send_message(
        update,
        f"{t(user_id, 'reauth_old_pwd_saved')}\n\n{t(user_id, 'reauth_new_pwd_prompt')}\n\n{t(user_id, 'reauth_new_pwd_tip')}",
        parse_mode='HTML'
    )
    
    # 设置用户状态为等待输入新密码
    self.db.save_user(user_id, "", "", "reauthorize_new_password")


    def handle_reauthorize_new_password_input(self, update: Update, context: CallbackContext, user_id: int, text: str):
    """处理新密码输入"""
    if user_id not in self.pending_reauthorize:
        self.safe_send_message(update, t(user_id, 'reauth_session_expired_restart'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 保存新密码
    text = text.strip()
    if text.lower() in ['无', 'skip', 'none', '']:
        task['new_password'] = ""
    else:
        task['new_password'] = text
    
    # 显示确认信息
    old_pwd_display = t(user_id, 'reauth_pwd_none') if not task.get('old_password') else t(user_id, 'reauth_pwd_masked')
    new_pwd_display = t(user_id, 'reauth_pwd_none') if not task.get('new_password') else t(user_id, 'reauth_pwd_masked')
    
    text = f"""

    def handle_reauthorize_execute(self, update: Update, context: CallbackContext, query, user_id: int):
    """执行重新授权"""
    query.answer(t(user_id, 'reauth_starting'))
    
    if user_id not in self.pending_reauthorize:
        self.safe_edit_message(query, t(user_id, 'reauth_session_expired'))
        return
    
    task = self.pending_reauthorize[user_id]
    
    # 在新线程中执行
    def execute():
        try:
            self._execute_reauthorize(update, context, user_id, task)
        except Exception as e:
            logger.error(f"Reauthorize execution failed: {e}")
            import traceback
            traceback.print_exc()
            context.bot.send_message(
                chat_id=user_id,
                text=f"❌ <b>{t(user_id, 'reauth_failed')}</b>\n\n{t(user_id, 'reauth_error').format(error=str(e))}",
                parse_mode='HTML'
            )
        finally:
            if user_id in self.pending_reauthorize:
                self.cleanup_reauthorize_task(user_id)
    
    thread = threading.Thread(target=execute, daemon=True)
    thread.start()
    
    self.safe_edit_message(
        query,
        f"<b>{t(user_id, 'reauth_in_progress')}</b>\n\n{t(user_id, 'reauth_please_wait')}",
        parse_mode='HTML'
    )


    def _create_reauth_progress_keyboard(self, user_id: int, total: int, success: int, frozen: int, wrong_pwd: int, banned: int, network_error: int) -> InlineKeyboardMarkup:
    """创建重新授权进度按钮 - 6行2列布局"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_account_count'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{total}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_success'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{success}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_frozen'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{frozen}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_banned'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{banned}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_2fa_error'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{wrong_pwd}", callback_data="reauthorize_noop")
        ],
        [
            InlineKeyboardButton(t(user_id, 'reauth_stat_network_error'), callback_data="reauthorize_noop"),
            InlineKeyboardButton(f"{network_error}", callback_data="reauthorize_noop")
        ]
    ])


    def _execute_reauthorize(self, update: Update, context: CallbackContext, user_id: int, task: Dict):
    """实际执行重新授权"""
    import asyncio
    
    files = task['files']
    file_type = task['file_type']
    password_mode = task.get('password_mode', 'manual')
    password_map = task.get('password_map', {})  # For auto mode
    old_password = task.get('old_password', '')  # For manual mode
    new_password = task.get('new_password', '')
    
    # 创建进度消息
    total_files = len(files)
    
    # 创建初始按钮布局
    keyboard = self._create_reauth_progress_keyboard(user_id, total_files, 0, 0, 0, 0, 0)
    
    progress_msg = context.bot.send_message(
        chat_id=user_id,
        text=f"🚀 <b>{t(user_id, 'reauth_start')}</b>\n\n{t(user_id, 'reauth_progress').format(current=0, total=total_files, percent=0)}",
        parse_mode='HTML',
        reply_markup=keyboard
    )
    
    # 执行重新授权
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 结果分类
    results = {
        'success': [],
        'frozen': [],
        'banned': [],
        'wrong_password': [],
        'network_error': [],
        'other_error': []
    }
    
    last_update_count = 0
    
    def progress_callback(current, total, message):
        nonlocal last_update_count
        # 每10个更新一次，或者是最后一个
        if current - last_update_count >= 10 or current == total:
            try:
                progress = int(current / total * 100)
                
                # 统计当前结果
                success_count = len(results['success'])
                frozen_count = len(results['frozen'])
                banned_count = len(results['banned'])
                wrong_pwd_count = len(results['wrong_password'])
                network_error_count = len(results['network_error'])
                other_error_count = len(results['other_error'])
                
                # 创建实时统计按钮
                keyboard = self._create_reauth_progress_keyboard(
                    user_id, total, success_count, frozen_count, wrong_pwd_count, banned_count, network_error_count
                )
                
                logger.info(f"📊 重新授权进度: {current}/{total} ({progress}%) - 成功:{success_count} 冻结:{frozen_count} 封禁:{banned_count} 密码错误:{wrong_pwd_count} 网络:{network_error_count}")
                print(f"📊 重新授权进度: {current}/{total} ({progress}%) - 成功:{success_count} 冻结:{frozen_count} 封禁:{banned_count} 密码错误:{wrong_pwd_count} 网络:{network_error_count}", flush=True)
                
                context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=progress_msg.message_id,
                    text=f"🚀 <b>{t(user_id, 'reauth_start')}</b>\n\n{t(user_id, 'reauth_progress').format(current=current, total=total, percent=progress)}",
                    parse_mode='HTML',
                    reply_markup=keyboard
                )
                last_update_count = current
            except Exception as e:
                logger.warning(f"⚠️ 更新进度消息失败: {e}")
    
    try:
        logger.info(f"📊 开始重新授权 - 用户ID: {user_id}, 账号数: {total_files}")
        print(f"📊 开始重新授权 - 用户ID: {user_id}, 账号数: {total_files}, 并发数: {config.REAUTH_CONCURRENT}", flush=True)
        
        # 使用并发处理账号
        completed_count = 0
        
        async def process_account_wrapper(idx, file_path, file_name):
            """处理单个账号的包装器 - 确保永不卡死"""
            nonlocal completed_count
            try:
                # 根据模式决定使用哪个密码
                if password_mode == 'auto':
                    account_old_password = password_map.get(file_path, '')
                else:
                    account_old_password = old_password
                
                result = await self._reauthorize_single_account(
                    file_path, file_name, account_old_password, new_password, user_id, file_type
                )
                
                # 根据结果分类
                if result['status'] == 'success':
                    results['success'].append((file_path, file_name, result))
                elif result['status'] == 'frozen':
                    results['frozen'].append((file_path, file_name, result))
                elif result['status'] == 'banned':
                    results['banned'].append((file_path, file_name, result))
                elif result['status'] == 'wrong_password':
                    results['wrong_password'].append((file_path, file_name, result))
                elif result['status'] == 'network_error':
                    results['network_error'].append((file_path, file_name, result))
                else:
                    results['other_error'].append((file_path, file_name, result))
                
                completed_count += 1
                progress_callback(completed_count, total_files, f"已完成 {completed_count}/{total_files}")
                
            except Exception as e:
                # 确保任何异常都不会阻止进度
                logger.error(f"❌ 处理账号失败 {file_name}: {e}")
                print(f"❌ 处理账号失败 {file_name}: {e}", flush=True)
                results['other_error'].append((file_path, file_name, {'status': 'error', 'error': str(e)}))
                completed_count += 1
                progress_callback(completed_count, total_files, f"已完成 {completed_count}/{total_files}")
        
        async def process_batch():
            """批量并发处理账号 - 确保永不卡死"""
            # 创建信号量控制并发数
            semaphore = asyncio.Semaphore(config.REAUTH_CONCURRENT)
            
            async def process_with_semaphore(idx, file_path, file_name):
                async with semaphore:
                    await process_account_wrapper(idx, file_path, file_name)
            
            # 创建所有任务
            tasks = [
                process_with_semaphore(idx, file_path, file_name)
                for idx, (file_path, file_name) in enumerate(files)
            ]
            
            # 并发执行所有任务 - 添加总超时保护（每个账号最多3分钟，总共不超过账号数*3分钟）
            # 但至少30分钟
            MINIMUM_TOTAL_TIMEOUT = 1800  # 30分钟最小超时
            PER_ACCOUNT_TIMEOUT = 180  # 每个账号3分钟
            total_timeout = max(total_files * PER_ACCOUNT_TIMEOUT, MINIMUM_TOTAL_TIMEOUT)
            logger.info(f"⏰ 设置总超时: {total_timeout}秒 ({total_timeout/60:.1f}分钟)")
            print(f"⏰ 设置总超时: {total_timeout}秒 ({total_timeout/60:.1f}分钟)", flush=True)
            
            try:
                # 使用return_exceptions=True允许部分失败不影响其他任务
                # 异常已在process_account_wrapper中处理
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=total_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"⏰ 批量处理超时（{total_timeout}秒），强制结束")
                print(f"⏰ 批量处理超时（{total_timeout}秒），强制结束", flush=True)
        
        # 执行批量处理
        loop.run_until_complete(process_batch())
        
        # 生成报告和打包结果 - 确保总是执行
        logger.info("📊 开始生成报告...")
        print("📊 开始生成报告...", flush=True)
        try:
            self._generate_reauthorize_report(context, user_id, results, progress_msg)
        except Exception as e:
            logger.error(f"❌ 生成报告失败，但继续尝试发送已有数据: {e}")
            print(f"❌ 生成报告失败，但继续尝试发送已有数据: {e}", flush=True)
            # 即使报告生成失败，也要尝试发送基本统计信息
            try:
                total = sum(len(v) for v in results.values())
                success_count = len(results['success'])
                context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ 报告生成出现问题，但处理完成\n\n总数: {total}\n成功: {success_count}",
                    parse_mode='HTML'
                )
            except:
                pass
        
    except Exception as e:
        logger.error(f"❌ 重新授权执行失败: {e}")
        print(f"❌ 重新授权执行失败: {e}", flush=True)
        # 即使整体失败，也尝试发送错误消息
        try:
            context.bot.send_message(
                chat_id=user_id,
                text=f"❌ 重新授权出现严重错误: {str(e)}\n\n已处理账号可能未完全保存",
                parse_mode='HTML'
            )
        except:
            pass
        
    finally:
        loop.close()
        # 清理临时文件
        if task.get('temp_dir') and os.path.exists(task['temp_dir']):
            shutil.rmtree(task['temp_dir'], ignore_errors=True)

async def _reauthorize_single_account(self, file_path: str, file_name: str, old_password: str, new_password: str, user_id: int, file_type: str = 'session') -> Dict:
    """重新授权单个账号（支持Session和TData格式）- 带超时保护"""
    logger.info(f"🔄 开始处理账号: {file_name} (格式: {file_type.upper()})")
    print(f"🔄 开始处理账号: {file_name} (格式: {file_type.upper()})", flush=True)
    
    # 为每个账号设置最大处理时间（180秒 = 3分钟）
    # 这确保即使账号出现问题也不会永久卡住
    timeout_seconds = 180
    
    try:
        return await asyncio.wait_for(
            self._reauthorize_single_account_impl(file_path, file_name, old_password, new_password, user_id, file_type),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error(f"⏰ [{file_name}] 处理超时（{timeout_seconds}秒），自动跳过")
        print(f"⏰ [{file_name}] 处理超时（{timeout_seconds}秒），自动跳过", flush=True)
        return {'status': 'other_error', 'error': f'处理超时（{timeout_seconds}秒）'}
    except Exception as e:
        logger.error(f"❌ [{file_name}] 处理时发生未预期错误: {e}")
        print(f"❌ [{file_name}] 处理时发生未预期错误: {e}", flush=True)
        return {'status': 'other_error', 'error': f'未预期错误: {str(e)}'}

async def _reauthorize_single_account_impl(self, file_path: str, file_name: str, old_password: str, new_password: str, user_id: int, file_type: str = 'session') -> Dict:
    """重新授权单个账号的实际实现"""
    client = None
    new_client = None
    temp_session_path = None
    original_tdata_path = None
    
    try:
        # 如果是TData格式，先转换为Session
        if file_type == 'tdata':
            if not OPENTELE_AVAILABLE:
                return {'status': 'other_error', 'error': 'opentele库未安装，无法处理TData格式'}
            
            logger.info(f"📂 [{file_name}] TData格式 - 转换为Session进行处理...")
            print(f"📂 [{file_name}] TData格式 - 转换为Session进行处理...", flush=True)
            
            try:
                # 保存原始TData路径
                original_tdata_path = file_path
                
                # 加载TData - 添加超时保护（30秒）
                try:
                    tdesk = await asyncio.wait_for(
                        asyncio.to_thread(TDesktop, file_path),
                        timeout=30
                    )
                    if not tdesk.isLoaded():
                        return {'status': 'frozen', 'error': 'TData未授权或无效'}
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData加载超时（30秒）")
                    print(f"⏰ [{file_name}] TData加载超时（30秒）", flush=True)
                    return {'status': 'other_error', 'error': 'TData加载超时'}
                
                # 创建临时Session文件
                os.makedirs(config.SESSIONS_BAK_DIR, exist_ok=True)
                temp_session_name = f"reauth_tdata_{time.time_ns()}"
                temp_session_path = os.path.join(config.SESSIONS_BAK_DIR, temp_session_name)
                
                # 转换TData为Session - 添加超时保护（60秒）
                try:
                    temp_client = await asyncio.wait_for(
                        tdesk.ToTelethon(
                            session=temp_session_path,
                            flag=UseCurrentSession,
                            api=API.TelegramDesktop
                        ),
                        timeout=60
                    )
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData转Session超时（60秒）")
                    print(f"⏰ [{file_name}] TData转Session超时（60秒）", flush=True)
                    return {'status': 'other_error', 'error': 'TData转Session超时'}
                
                # 断开临时客户端
                if temp_client:
                    try:
                        await asyncio.wait_for(temp_client.disconnect(), timeout=10)
                    except Exception:
                        pass
                
                # 使用转换后的Session路径
                file_path = temp_session_path
                
                logger.info(f"✅ [{file_name}] TData转Session完成")
                print(f"✅ [{file_name}] TData转Session完成", flush=True)
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ [{file_name}] TData转换操作超时")
                print(f"⏰ [{file_name}] TData转换操作超时", flush=True)
                return {'status': 'other_error', 'error': 'TData转换操作超时'}
            except Exception as e:
                logger.error(f"❌ [{file_name}] TData转换失败: {e}")
                print(f"❌ [{file_name}] TData转换失败: {e}", flush=True)
                return {'status': 'other_error', 'error': f'TData转换失败: {str(e)}'}
        
        # 使用配置中的API凭据（不能使用随机设备的API凭据，因为现有session是用特定API凭据创建的）
        # Telegram会验证API凭据与手机号的匹配关系
        old_api_id = config.API_ID
        old_api_hash = config.API_HASH
        
        # 获取随机设备参数（用于新会话）
        # 注意：API凭据必须使用配置的有效凭据，不能随机化
        # 只随机化设备指纹参数（device_model, system_version等）
        random_device_params = None
        new_api_id = old_api_id  # 使用相同的API凭据
        new_api_hash = old_api_hash  # 使用相同的API凭据
        
        if config.REAUTH_USE_RANDOM_DEVICE:
            try:
                random_device_params = self.device_params_manager.get_random_device_params()
                logger.info(f"📱 [{file_name}] 新会话将使用随机设备指纹")
                print(f"📱 [{file_name}] 新会话将使用随机设备指纹", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 获取随机设备参数失败: {e}")
                print(f"⚠️ [{file_name}] 获取随机设备参数失败: {e}", flush=True)
        
        logger.info(f"📱 [{file_name}] 旧会话使用配置的API凭据: API_ID={old_api_id}")
        print(f"📱 [{file_name}] 旧会话使用配置的API凭据: API_ID={old_api_id}", flush=True)
        
        # 获取代理（强制使用代理优先）
        proxy_dict = None
        proxy_info = None
        use_proxy = config.REAUTH_FORCE_PROXY or self.proxy_manager.is_proxy_mode_active(self.db)
        
        if use_proxy and self.proxy_manager.proxies:
            proxy_info = self.proxy_manager.get_next_proxy()
            if proxy_info:
                proxy_dict = self.checker.create_proxy_dict(proxy_info)
                proxy_type = "住宅代理" if proxy_info.get('is_residential', False) else "代理"
                logger.info(f"🌐 [{file_name}] 强制使用{proxy_type}（配置: REAUTH_FORCE_PROXY={config.REAUTH_FORCE_PROXY}）")
                print(f"🌐 [{file_name}] 强制使用{proxy_type}（配置: REAUTH_FORCE_PROXY={config.REAUTH_FORCE_PROXY}）", flush=True)
            else:
                logger.warning(f"⚠️ [{file_name}] 代理模式启用但无可用代理")
                print(f"⚠️ [{file_name}] 代理模式启用但无可用代理", flush=True)
        else:
            logger.info(f"ℹ️ [{file_name}] 代理模式未启用，使用本地连接")
            print(f"ℹ️ [{file_name}] 代理模式未启用，使用本地连接", flush=True)
        
        # 步骤1: 创建旧客户端连接
        session_base = file_path.replace('.session', '') if file_path.endswith('.session') else file_path
        
        client = TelegramClient(
            session_base,
            int(old_api_id),
            str(old_api_hash),
            timeout=config.CONNECTION_TIMEOUT,
            connection_retries=3,
            retry_delay=1,
            proxy=proxy_dict
        )
        
        logger.info(f"⏳ [{file_name}] 连接到Telegram服务器（旧会话）...")
        print(f"⏳ [{file_name}] 连接到Telegram服务器（旧会话）...", flush=True)
        
        # 强制代理优先逻辑：只有代理超时才回退到本地
        connect_success = False
        try:
            await asyncio.wait_for(client.connect(), timeout=config.CONNECTION_TIMEOUT)
            logger.info(f"✅ [{file_name}] 旧会话连接成功（使用{'代理' if proxy_dict else '本地'}）")
            print(f"✅ [{file_name}] 旧会话连接成功（使用{'代理' if proxy_dict else '本地'}）", flush=True)
            connect_success = True
        except asyncio.TimeoutError:
            if proxy_dict and config.REAUTH_FORCE_PROXY:
                # 只有在使用代理且超时的情况下才回退
                logger.warning(f"⚠️ [{file_name}] 代理连接超时，回退到本地连接")
                print(f"⚠️ [{file_name}] 代理连接超时，回退到本地连接", flush=True)
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"⚠️ [{file_name}] 断开旧客户端失败: {e}")
                # 重新创建不带代理的客户端
                client = TelegramClient(
                    session_base,
                    int(old_api_id),
                    str(old_api_hash),
                    timeout=30
                )
                await client.connect()
                logger.info(f"✅ [{file_name}] 本地连接成功")
                print(f"✅ [{file_name}] 本地连接成功", flush=True)
                connect_success = True
            else:
                # 如果不是代理超时，或者没有配置强制代理，则抛出异常
                logger.error(f"❌ [{file_name}] 连接超时且无法回退")
                print(f"❌ [{file_name}] 连接超时且无法回退", flush=True)
                return {'status': 'network_error', 'error': '连接超时'}
        
        # 检查授权状态
        if not await client.is_user_authorized():
            return {'status': 'frozen', 'error': '账号未授权或已失效'}
        
        # 获取账号信息
        me = await client.get_me()
        phone = me.phone if me.phone else "unknown"
        logger.info(f"📱 [{file_name}] 账号手机号: {phone}")
        print(f"📱 [{file_name}] 账号手机号: {phone}", flush=True)
        
        # 步骤2: 重置所有会话（踢掉其他设备）
        logger.info(f"🔄 [{file_name}] 步骤1: 重置所有会话...")
        print(f"🔄 [{file_name}] 步骤1: 重置所有会话...", flush=True)
        
        try:
            sessions = await client(GetAuthorizationsRequest())
            if len(sessions.authorizations) > 1:
                await client(ResetAuthorizationsRequest())
                logger.info(f"✅ [{file_name}] 已踢掉其他设备登录")
                print(f"✅ [{file_name}] 已踢掉其他设备登录", flush=True)
            else:
                logger.info(f"ℹ️ [{file_name}] 只有一个会话，无需重置")
                print(f"ℹ️ [{file_name}] 只有一个会话，无需重置", flush=True)
        except Exception as e:
            logger.warning(f"⚠️ [{file_name}] 重置会话失败: {e}")
            print(f"⚠️ [{file_name}] 重置会话失败: {e}", flush=True)
        
        # 步骤3: 检查密码状态（如果提供了旧密码）
        # TODO: 实际的密码验证需要在登录时进行
        # Telethon不提供独立的密码验证API，只能在sign_in时验证
        if old_password:
            logger.info(f"🔐 [{file_name}] 步骤2: 检查2FA状态...")
            print(f"🔐 [{file_name}] 步骤2: 检查2FA状态...", flush=True)
            
            try:
                password_data = await client(GetPasswordRequest())
                if password_data.has_password:
                    logger.info(f"ℹ️ [{file_name}] 账号有2FA，将在重新登录时验证密码")
                    print(f"ℹ️ [{file_name}] 账号有2FA，将在重新登录时验证密码", flush=True)
                else:
                    logger.info(f"ℹ️ [{file_name}] 账号没有2FA")
                    print(f"ℹ️ [{file_name}] 账号没有2FA", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 检查2FA状态失败: {e}")
                print(f"⚠️ [{file_name}] 检查2FA状态失败: {e}", flush=True)
        
        # 步骤4: 创建新会话（使用随机设备参数）
        logger.info(f"🔑 [{file_name}] 步骤3: 创建新会话（使用随机设备参数）...")
        print(f"🔑 [{file_name}] 步骤3: 创建新会话（使用随机设备参数）...", flush=True)
        
        # 为新会话创建新路径
        new_session_path = f"{session_base}_new"
        
        # 创建新客户端（使用随机设备参数的API凭据）
        new_client = TelegramClient(
            new_session_path,
            int(new_api_id),
            str(new_api_hash),
            timeout=config.CONNECTION_TIMEOUT,
            proxy=proxy_dict,
            # 添加随机设备参数（如果有）
            device_model=random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop',
            system_version=random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10',
            app_version=random_device_params.get('app_version', '3.2.8 x64') if random_device_params else '3.2.8 x64',
            lang_code=random_device_params.get('lang_code', 'en') if random_device_params else 'en',
            system_lang_code=random_device_params.get('system_lang_code', 'en-US') if random_device_params else 'en-US'
        )
        
        logger.info(f"📱 [{file_name}] 新会话设备信息: {random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop'}, {random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10'}")
        print(f"📱 [{file_name}] 新会话设备信息: {random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop'}, {random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10'}", flush=True)
        
        # 连接新客户端（强制代理优先）
        try:
            await asyncio.wait_for(new_client.connect(), timeout=config.CONNECTION_TIMEOUT)
            logger.info(f"✅ [{file_name}] 新会话连接成功（使用{'代理' if proxy_dict else '本地'}）")
            print(f"✅ [{file_name}] 新会话连接成功（使用{'代理' if proxy_dict else '本地'}）", flush=True)
        except asyncio.TimeoutError:
            if proxy_dict and config.REAUTH_FORCE_PROXY:
                logger.warning(f"⚠️ [{file_name}] 新会话代理连接超时，回退到本地连接")
                print(f"⚠️ [{file_name}] 新会话代理连接超时，回退到本地连接", flush=True)
                try:
                    await new_client.disconnect()
                except Exception as e:
                    logger.warning(f"⚠️ [{file_name}] 断开新客户端失败: {e}")
                # 重新创建不带代理的客户端
                new_client = TelegramClient(
                    new_session_path,
                    int(new_api_id),
                    str(new_api_hash),
                    timeout=config.CONNECTION_TIMEOUT,
                    device_model=random_device_params.get('device_model', 'Desktop') if random_device_params else 'Desktop',
                    system_version=random_device_params.get('system_version', 'Windows 10') if random_device_params else 'Windows 10',
                    app_version=random_device_params.get('app_version', '3.2.8 x64') if random_device_params else '3.2.8 x64',
                    lang_code=random_device_params.get('lang_code', 'en') if random_device_params else 'en',
                    system_lang_code=random_device_params.get('system_lang_code', 'en-US') if random_device_params else 'en-US'
                )
                await new_client.connect()
                logger.info(f"✅ [{file_name}] 新会话本地连接成功")
                print(f"✅ [{file_name}] 新会话本地连接成功", flush=True)
            else:
                raise
        
        # 步骤5: 请求验证码
        logger.info(f"📲 [{file_name}] 步骤4: 请求验证码...")
        print(f"📲 [{file_name}] 步骤4: 请求验证码...", flush=True)
        
        sent_code = await new_client(SendCodeRequest(
            phone,
            int(new_api_id),
            str(new_api_hash),
            CodeSettings()
        ))
        
        logger.info(f"✅ [{file_name}] 验证码已发送")
        print(f"✅ [{file_name}] 验证码已发送", flush=True)
        
        # 步骤6: 从旧会话获取验证码
        logger.info(f"📥 [{file_name}] 步骤5: 获取验证码...")
        print(f"📥 [{file_name}] 步骤5: 获取验证码...", flush=True)
        
        await asyncio.sleep(3)  # 等待验证码到达
        
        entity = await client.get_entity(777000)
        messages = await client.get_messages(entity, limit=1)
        
        if not messages:
            return {'status': 'other_error', 'error': '未收到验证码'}
        
        # Support both 5 and 6 digit verification codes
        # Use a pattern that works for digit-only codes without word boundaries
        code_match = re.search(r"(\d{5,6})", messages[0].message)
        if not code_match:
            return {'status': 'other_error', 'error': '验证码格式不正确'}
        
        code = code_match.group(1)
        logger.info(f"✅ [{file_name}] 获取到验证码: {code}")
        print(f"✅ [{file_name}] 获取到验证码: {code}", flush=True)
        
        # 步骤7: 新客户端登录
        logger.info(f"🔐 [{file_name}] 步骤6: 新会话登录...")
        print(f"🔐 [{file_name}] 步骤6: 新会话登录...", flush=True)
        
        try:
            await new_client.sign_in(
                phone=phone,
                phone_code_hash=sent_code.phone_code_hash,
                code=code
            )
            logger.info(f"✅ [{file_name}] 新会话登录成功")
            print(f"✅ [{file_name}] 新会话登录成功", flush=True)
        except SessionPasswordNeededError:
            # 需要2FA密码 - 优先使用旧密码，如果没有则使用新密码
            password_to_use = old_password if old_password else new_password
            if not password_to_use:
                return {'status': 'wrong_password', 'error': '需要2FA密码但未提供'}
            
            try:
                await new_client.sign_in(phone=phone, password=password_to_use)
                logger.info(f"✅ [{file_name}] 使用2FA密码登录成功")
                print(f"✅ [{file_name}] 使用2FA密码登录成功", flush=True)
            except PasswordHashInvalidError:
                return {'status': 'wrong_password', 'error': '2FA密码错误'}
        
        # 初始化密码设置状态标志
        password_set_success = False
        
        # 步骤8: 设置新密码（如果提供）
        if new_password and new_password != old_password:
            logger.info(f"🔑 [{file_name}] 步骤7: 设置新密码...")
            print(f"🔑 [{file_name}] 步骤7: 设置新密码...", flush=True)
            
            try:
                # 使用edit_2fa方法来设置新密码
                # 这是Telethon推荐的方式
                await new_client.edit_2fa(
                    current_password=old_password if old_password else None,
                    new_password=new_password,
                    hint=f"Modified {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",  # 使用UTC时间
                    email=None  # 可选的恢复邮箱
                )
                
                password_set_success = True
                logger.info(f"✅ [{file_name}] 新密码设置成功")
                print(f"✅ [{file_name}] 新密码设置成功", flush=True)
                
            except PasswordHashInvalidError:
                # 专门处理密码错误异常
                logger.warning(f"⚠️ [{file_name}] 旧密码不正确，无法设置新密码")
                print(f"⚠️ [{file_name}] 旧密码不正确，无法设置新密码", flush=True)
                # 不阻止整个流程，继续执行
                
            except (RPCError, FloodWaitError, NetworkError) as e:
                # 处理Telegram API相关错误
                error_type = type(e).__name__
                logger.warning(f"⚠️ [{file_name}] 设置新密码失败（Telegram错误）: {error_type}")
                print(f"⚠️ [{file_name}] 设置新密码失败（Telegram错误）: {error_type}", flush=True)
                # 不阻止整个流程，继续执行
                
            except Exception as e:
                # 捕获其他未预期的错误
                error_type = type(e).__name__
                logger.warning(f"⚠️ [{file_name}] 设置新密码时出现未预期错误: {error_type}")
                print(f"⚠️ [{file_name}] 设置新密码时出现未预期错误: {error_type}", flush=True)
                # 不阻止整个流程，继续执行
            
            # 如果密码设置失败，记录到结果中
            if not password_set_success:
                logger.info(f"ℹ️ [{file_name}] 注意: 新密码未成功设置，账号当前密码保持不变")
                print(f"ℹ️ [{file_name}] 注意: 新密码未成功设置，账号当前密码保持不变", flush=True)
                
        elif new_password and new_password == old_password:
            logger.info(f"ℹ️ [{file_name}] 新密码与旧密码相同，跳过密码设置")
            print(f"ℹ️ [{file_name}] 新密码与旧密码相同，跳过密码设置", flush=True)
        else:
            logger.info(f"ℹ️ [{file_name}] 未提供新密码，跳过密码设置")
            print(f"ℹ️ [{file_name}] 未提供新密码，跳过密码设置", flush=True)
        
        # 步骤9: 登出旧会话
        logger.info(f"🚪 [{file_name}] 步骤8: 登出旧会话...")
        print(f"🚪 [{file_name}] 步骤8: 登出旧会话...", flush=True)
        
        try:
            await client.log_out()
            logger.info(f"✅ [{file_name}] 旧会话已登出")
            print(f"✅ [{file_name}] 旧会话已登出", flush=True)
        except Exception as e:
            logger.warning(f"⚠️ [{file_name}] 登出旧会话失败: {e}")
            print(f"⚠️ [{file_name}] 登出旧会话失败: {e}", flush=True)
        
        # 步骤10: 验证旧会话失效
        logger.info(f"✔️ [{file_name}] 步骤9: 验证旧会话失效...")
        print(f"✔️ [{file_name}] 步骤9: 验证旧会话失效...", flush=True)
        
        # 断开新客户端
        await new_client.disconnect()
        
        # 替换旧会话文件
        old_session_file = f"{session_base}.session"
        new_session_file = f"{new_session_path}.session"
        
        if os.path.exists(new_session_file):
            if os.path.exists(old_session_file):
                os.remove(old_session_file)
            shutil.move(new_session_file, old_session_file)
            
            # 处理journal文件
            new_journal = f"{new_session_path}.session-journal"
            old_journal = f"{session_base}.session-journal"
            if os.path.exists(new_journal):
                if os.path.exists(old_journal):
                    os.remove(old_journal)
                shutil.move(new_journal, old_journal)
            
            logger.info(f"✅ [{file_name}] 新会话文件已替换旧会话")
            print(f"✅ [{file_name}] 新会话文件已替换旧会话", flush=True)
        
        # 步骤10: 如果原始格式是TData，转换回TData
        if file_type == 'tdata' and original_tdata_path:
            logger.info(f"📂 [{file_name}] 步骤10: 转换Session回TData格式...")
            print(f"📂 [{file_name}] 步骤10: 转换Session回TData格式...", flush=True)
            
            convert_client = None
            try:
                # 使用新Session创建TData - 添加总超时保护（90秒）
                try:
                    new_tdata_path = f"{original_tdata_path}_new"
                    os.makedirs(new_tdata_path, exist_ok=True)
                    
                    # 连接新Session - 使用OpenTele的TelegramClient
                    from opentele.tl import TelegramClient as OpenTeleClient
                    convert_client = OpenTeleClient(
                        session_base,
                        int(new_api_id),
                        str(new_api_hash)
                    )
                    
                    # 连接超时保护（15秒）
                    await asyncio.wait_for(convert_client.connect(), timeout=15)
                    
                    if not await convert_client.is_user_authorized():
                        logger.error(f"❌ [{file_name}] 新Session未授权，无法转换回TData")
                        print(f"❌ [{file_name}] 新Session未授权，无法转换回TData", flush=True)
                        # 清理临时目录
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': '新Session未授权，无法转换回TData'}
                    
                    # 转换Session为TData
                    logger.info(f"🔄 [{file_name}] 开始转换Session为TData...")
                    print(f"🔄 [{file_name}] 开始转换Session为TData...", flush=True)
                    
                    # 转换Session为TData - 添加超时保护（60秒）
                    try:
                        tdesk_new = await asyncio.wait_for(
                            convert_client.ToTDesktop(flag=UseCurrentSession),
                            timeout=60
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ [{file_name}] Session转TData超时（60秒）")
                        print(f"⏰ [{file_name}] Session转TData超时（60秒）", flush=True)
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': 'Session转TData超时'}
                    
                    # 保存TData - 添加超时保护（使用线程，15秒）
                    logger.info(f"💾 [{file_name}] 保存TData到: {new_tdata_path}")
                    print(f"💾 [{file_name}] 保存TData到: {new_tdata_path}", flush=True)
                    
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(tdesk_new.SaveTData, new_tdata_path),
                            timeout=15
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ [{file_name}] 保存TData超时（15秒）")
                        print(f"⏰ [{file_name}] 保存TData超时（15秒）", flush=True)
                        if os.path.exists(new_tdata_path):
                            shutil.rmtree(new_tdata_path, ignore_errors=True)
                        return {'status': 'other_error', 'error': '保存TData超时'}
                    
                except asyncio.TimeoutError:
                    logger.error(f"⏰ [{file_name}] TData转换整体超时")
                    print(f"⏰ [{file_name}] TData转换整体超时", flush=True)
                    if os.path.exists(new_tdata_path):
                        shutil.rmtree(new_tdata_path, ignore_errors=True)
                    return {'status': 'other_error', 'error': 'TData转换整体超时'}
                
                # 验证TData目录是否创建成功
                if not os.path.exists(new_tdata_path):
                    logger.error(f"❌ [{file_name}] TData转换失败：目录不存在")
                    print(f"❌ [{file_name}] TData转换失败：目录不存在", flush=True)
                    return {'status': 'other_error', 'error': 'TData转换失败：目录不存在'}
                
                tdata_dirs = [d for d in os.listdir(new_tdata_path) if os.path.isdir(os.path.join(new_tdata_path, d))]
                if not tdata_dirs:
                    logger.error(f"❌ [{file_name}] TData转换失败：未生成TData目录")
                    print(f"❌ [{file_name}] TData转换失败：未生成TData目录", flush=True)
                    if os.path.exists(new_tdata_path):
                        shutil.rmtree(new_tdata_path, ignore_errors=True)
                    return {'status': 'other_error', 'error': 'TData转换失败：未生成TData目录'}
                
                logger.info(f"✅ [{file_name}] TData目录已生成: {tdata_dirs}")
                print(f"✅ [{file_name}] TData目录已生成: {tdata_dirs}", flush=True)
                
                # 创建2fa.txt文件（只在密码设置成功时）
                if new_password and password_set_success:
                    password_file = os.path.join(new_tdata_path, "2fa.txt")
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(new_password)
                    logger.info(f"✅ [{file_name}] 已创建2fa.txt密码文件")
                    print(f"✅ [{file_name}] 已创建2fa.txt密码文件", flush=True)
                
                # 删除旧TData，替换为新TData
                logger.info(f"🔄 [{file_name}] 替换旧TData...")
                print(f"🔄 [{file_name}] 替换旧TData...", flush=True)
                if os.path.exists(original_tdata_path):
                    shutil.rmtree(original_tdata_path, ignore_errors=True)
                shutil.move(new_tdata_path, original_tdata_path)
                
                logger.info(f"✅ [{file_name}] Session已成功转换回TData格式")
                print(f"✅ [{file_name}] Session已成功转换回TData格式", flush=True)
                
                # 断开客户端
                if convert_client:
                    await convert_client.disconnect()
                
            except Exception as e:
                logger.error(f"❌ [{file_name}] 转换回TData失败: {e}")
                print(f"❌ [{file_name}] 转换回TData失败: {e}", flush=True)
                import traceback
                traceback.print_exc()
                
                # 清理临时目录
                if os.path.exists(f"{original_tdata_path}_new"):
                    shutil.rmtree(f"{original_tdata_path}_new", ignore_errors=True)
                
                # 断开客户端
                if convert_client:
                    try:
                        await convert_client.disconnect()
                    except Exception as e:
                        logger.warning(f"⚠️ [{file_name}] 断开客户端失败: {e}")
                
                # TData转换失败应该返回错误，不应该标记为成功
                return {'status': 'other_error', 'error': f'TData转换失败: {str(e)}'}
        
        logger.info(f"🎉 [{file_name}] 重新授权完成！")
        print(f"🎉 [{file_name}] 重新授权完成！", flush=True)
        
        # 准备返回数据
        result = {
            'status': 'success',
            'phone': phone,
            'message': '重新授权成功',
            'file_type': file_type,
            'new_password': new_password if new_password else '无',  # 新密码
            'password_set_success': password_set_success,  # 密码设置状态：True=成功，False=失败/未尝试
            'device_model': random_device_params.get('device_model', '默认设备') if random_device_params else '默认设备',
            'system_version': random_device_params.get('system_version', '默认系统') if random_device_params else '默认系统',
            'app_version': random_device_params.get('app_version', '默认版本') if random_device_params else '默认版本',
            'proxy_used': '使用代理' if proxy_dict else '本地连接',
            'proxy_type': proxy_info.get('type', 'N/A') if proxy_info else 'N/A'
        }
        
        # 更新JSON文件（包括新设备参数和twoFA）
        if file_type == 'session':
            json_path = os.path.splitext(f"{session_base}.session")[0] + '.json'
            try:
                current_time = datetime.now(BEIJING_TZ)
                
                # 读取或创建JSON数据
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    logger.info(f"📄 [{file_name}] 读取现有JSON文件")
                    print(f"📄 [{file_name}] 读取现有JSON文件", flush=True)
                else:
                    # 创建新的JSON文件结构
                    json_data = {
                        "phone": phone,
                        "session_file": os.path.splitext(file_name)[0],
                        "last_connect_date": current_time.strftime('%Y-%m-%dT%H:%M:%S+0000'),
                        "session_created_date": current_time.strftime('%Y-%m-%dT%H:%M:%S+0000'),
                        "last_check_time": int(current_time.timestamp())
                    }
                    logger.info(f"📄 [{file_name}] 创建新JSON文件")
                    print(f"📄 [{file_name}] 创建新JSON文件", flush=True)
                
                # 更新设备参数（如果使用了随机设备）
                if random_device_params:
                    json_data['app_id'] = new_api_id
                    json_data['app_hash'] = new_api_hash
                    json_data['device_model'] = random_device_params.get('device_model', 'Desktop')
                    json_data['system_version'] = random_device_params.get('system_version', 'Windows 10')
                    json_data['app_version'] = random_device_params.get('app_version', '3.2.8 x64')
                    json_data['lang_pack'] = random_device_params.get('lang_code', 'en')
                    json_data['system_lang_pack'] = random_device_params.get('system_lang_code', 'en-US')
                    
                    # 兼容旧字段名
                    json_data['device'] = random_device_params.get('device', 'Desktop')
                    json_data['sdk'] = random_device_params.get('sdk', 'Windows 10 x64')
                    
                    logger.info(f"✅ [{file_name}] 已更新JSON文件中的设备参数")
                    print(f"✅ [{file_name}] 已更新JSON文件中的设备参数", flush=True)
                
                # 更新2FA密码（只在密码设置成功时更新）
                if new_password and password_set_success:
                    # 删除所有旧的密码字段
                    old_fields_to_remove = ['twoFA', '2fa', 'password', 'two_fa']
                    for field in old_fields_to_remove:
                        if field in json_data:
                            del json_data[field]
                    
                    # 设置标准的 twofa 字段
                    json_data['twoFA'] = new_password
                    json_data['has_password'] = True
                    logger.info(f"✅ [{file_name}] 已更新JSON文件中的twofa字段")
                    print(f"✅ [{file_name}] 已更新JSON文件中的twofa字段", flush=True)
                elif new_password and not password_set_success:
                    logger.info(f"ℹ️ [{file_name}] 密码设置失败，保持JSON文件中的旧密码")
                    print(f"ℹ️ [{file_name}] 密码设置失败，保持JSON文件中的旧密码", flush=True)
                
                # 保存JSON文件
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"💾 [{file_name}] JSON文件已保存")
                print(f"💾 [{file_name}] JSON文件已保存", flush=True)
                
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 更新JSON文件失败: {e}")
                print(f"⚠️ [{file_name}] 更新JSON文件失败: {e}", flush=True)
        
        # 更新TData格式的密码文件（只在密码设置成功时更新）
        if new_password and password_set_success and file_type == 'tdata' and original_tdata_path:
            try:
                # 尝试常见的密码文件名
                password_files = ['2fa.txt', 'twofa.txt', 'password.txt']
                password_file_path = None
                
                # 检查是否已存在密码文件
                for pf in password_files:
                    test_path = os.path.join(original_tdata_path, pf)
                    if os.path.exists(test_path):
                        password_file_path = test_path
                        break
                
                # 如果不存在，创建2fa.txt
                if not password_file_path:
                    password_file_path = os.path.join(original_tdata_path, '2fa.txt')
                
                # 写入新密码
                with open(password_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_password)
                
                logger.info(f"✅ [{file_name}] 已更新TData密码文件: {os.path.basename(password_file_path)}")
                print(f"✅ [{file_name}] 已更新TData密码文件: {os.path.basename(password_file_path)}", flush=True)
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 更新TData密码文件失败: {e}")
                print(f"⚠️ [{file_name}] 更新TData密码文件失败: {e}", flush=True)
        elif new_password and not password_set_success and file_type == 'tdata' and original_tdata_path:
            logger.info(f"ℹ️ [{file_name}] 密码设置失败，保持TData原始密码文件")
            print(f"ℹ️ [{file_name}] 密码设置失败，保持TData原始密码文件", flush=True)
        
        # 添加文件路径信息
        if file_type == 'session':
            # Session格式：返回session文件路径
            result['session_path'] = f"{session_base}.session"
            result['tdata_path'] = None
        else:
            # TData格式：返回TData目录路径和session文件路径
            result['session_path'] = f"{session_base}.session" if os.path.exists(f"{session_base}.session") else None
            result['tdata_path'] = original_tdata_path
        
        return result
        
    except UserDeactivatedError:
        return {'status': 'frozen', 'error': '账号已被冻结'}
    except PhoneNumberBannedError:
        return {'status': 'banned', 'error': '账号已被封禁'}
    except PasswordHashInvalidError:
        return {'status': 'wrong_password', 'error': '密码错误'}
    except asyncio.TimeoutError:
        return {'status': 'network_error', 'error': '连接超时'}
    except Exception as e:
        logger.error(f"❌ [{file_name}] 重新授权失败: {e}")
        print(f"❌ [{file_name}] 重新授权失败: {e}", flush=True)
        return {'status': 'other_error', 'error': str(e)}
    
    finally:
        # 清理客户端
        if client:
            try:
                await client.disconnect()
            except:
                pass
        if new_client:
            try:
                await new_client.disconnect()
            except:
                pass
        
        # 清理临时Session文件（如果是从TData转换的）
        if temp_session_path and os.path.exists(f"{temp_session_path}.session"):
            try:
                os.remove(f"{temp_session_path}.session")
                journal_file = f"{temp_session_path}.session-journal"
                if os.path.exists(journal_file):
                    os.remove(journal_file)
                logger.info(f"🧹 [{file_name}] 已清理临时Session文件")
            except Exception as e:
                logger.warning(f"⚠️ [{file_name}] 清理临时Session失败: {e}")


    def _generate_reauthorize_report(self, context: CallbackContext, user_id: int, results: Dict, progress_msg):
    """生成重新授权报告和打包结果 - 确保永不卡死"""
    logger.info("📊 开始生成报告和打包结果...")
    print("📊 开始生成报告和打包结果...", flush=True)
    
    timestamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    
    # 统计
    total = sum(len(v) for v in results.values())
    success_count = len(results['success'])
    frozen_count = len(results['frozen'])
    banned_count = len(results['banned'])
    wrong_pwd_count = len(results['wrong_password'])
    network_error_count = len(results['network_error'])
    other_error_count = len(results['other_error'])
    
    # 生成文本报告 - 添加异常保护
    report_filename = f"reauthorize_report_{timestamp}.txt"
    report_path = os.path.join(config.RESULTS_DIR, report_filename)
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'reauth_report_title')}\n")
            f.write("=" * 80 + "\n")
            f.write(f"{t(user_id, 'reauth_report_time')} {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}\n")
            f.write(f"{t(user_id, 'reauth_report_total')} {total}\n")
            f.write(f"{t(user_id, 'reauth_report_success')} {success_count}\n")
            f.write(f"{t(user_id, 'reauth_report_frozen')} {frozen_count}\n")
            f.write(f"{t(user_id, 'reauth_report_banned')} {banned_count}\n")
            f.write(f"{t(user_id, 'reauth_report_pwd_error')} {wrong_pwd_count}\n")
            f.write(f"{t(user_id, 'reauth_report_network')} {network_error_count}\n")
            f.write(f"{t(user_id, 'reauth_report_other')} {other_error_count}\n")
            f.write("=" * 80 + "\n\n")
            
            # 详细结果
            for category, items in results.items():
                if items:
                    # 翻译分类标题
                    category_key = f'reauth_report_category_{category}'
                    category_title = t(user_id, category_key)
                    f.write(f"\n{category_title} ({len(items)})\n")
                    f.write("-" * 80 + "\n")
                    for file_path, file_name, result in items:
                        f.write(f"{t(user_id, 'reauth_report_file')} {file_name}\n")
                        if 'phone' in result:
                            f.write(f"{t(user_id, 'reauth_report_phone')} {result['phone']}\n")
                        
                        # 成功的账户显示详细信息
                        if category == 'success':
                            if 'device_model' in result:
                                f.write(f"{t(user_id, 'reauth_report_device_model')} {result['device_model']}\n")
                            if 'system_version' in result:
                                f.write(f"{t(user_id, 'reauth_report_system_version')} {result['system_version']}\n")
                            if 'app_version' in result:
                                f.write(f"{t(user_id, 'reauth_report_app_version')} {result['app_version']}\n")
                            if 'proxy_used' in result:
                                # 翻译连接方式
                                proxy_value = result['proxy_used']
                                if '使用代理' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_proxy')
                                elif '本地连接 (代理失败后回退)' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_local_fallback')
                                elif '本地连接' in proxy_value:
                                    proxy_value_translated = t(user_id, 'reauth_connection_local')
                                else:
                                    proxy_value_translated = proxy_value
                                
                                f.write(f"{t(user_id, 'reauth_report_connection')} {proxy_value_translated}")
                                if result.get('proxy_type') and result['proxy_type'] != 'N/A':
                                    f.write(f" ({result['proxy_type'].upper()})")
                                f.write("\n")
                            if 'new_password' in result:
                                f.write(f"{t(user_id, 'reauth_report_new_password')} {result['new_password']}\n")
                        
                        if 'error' in result:
                            f.write(f"{t(user_id, 'reauth_report_error')} {result['error']}\n")
                        f.write("\n")
        logger.info(f"✅ 报告文件已生成: {report_path}")
        print(f"✅ 报告文件已生成: {report_path}", flush=True)
    except Exception as e:
        logger.error(f"❌ 生成报告文件失败: {e}")
        print(f"❌ 生成报告文件失败: {e}", flush=True)
        # 创建一个简化的报告
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(f"{t(user_id, 'reauth_report_gen_failed')} {e}\n\n")
                f.write(f"{t(user_id, 'reauth_report_total_success').format(total=total, success=success_count)}\n")
        except:
            pass
    
    # 打包成功的账号（支持TData和Session格式）- 添加异常保护
    zip_files = []
    
    # 打包成功的账号
    if results['success']:
        logger.info("📦 开始打包成功的账号...")
        print("📦 开始打包成功的账号...", flush=True)
        try:
            success_zip = os.path.join(config.RESULTS_DIR, f"reauthorize_success_{timestamp}.zip")
            with zipfile.ZipFile(success_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path, file_name, result in results['success']:
                    result_file_type = result.get('file_type', 'session')
                    phone = result.get('phone', 'unknown')
                    
                    if result_file_type == 'tdata':
                        # TData格式：创建 手机号/tdata/D877... 结构
                        tdata_path = result.get('tdata_path')
                        if tdata_path and os.path.exists(tdata_path):
                            # SaveTData会在指定路径下创建tdata子目录
                            # 需要找到包含D877...目录的实际tdata目录
                            actual_tdata_dir = os.path.join(tdata_path, 'tdata')
                            
                            if os.path.exists(actual_tdata_dir) and os.path.isdir(actual_tdata_dir):
                                # 有tdata子目录，使用它
                                source_dir = actual_tdata_dir
                            else:
                                # 没有tdata子目录，tdata_path本身就是tdata目录
                                source_dir = tdata_path
                            
                            # 添加source_dir下的所有文件，路径为：手机号/tdata/D877.../
                            for root, dirs, files in os.walk(source_dir):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    # 计算相对于source_dir的相对路径
                                    rel_path = os.path.relpath(file_full_path, source_dir)
                                    # 构建完整的归档路径：手机号/tdata/D877.../file
                                    arc_path = os.path.join(phone, 'tdata', rel_path)
                                    zipf.write(file_full_path, arc_path)
                            
                            # 如果密码设置成功，创建2fa.txt文件
                            password_set_success = result.get('password_set_success', False)
                            new_password = result.get('new_password', '')
                            if password_set_success and new_password and new_password != '无':
                                # 在zip中创建 手机号/2fa.txt 文件（与tdata同级）
                                password_content = new_password.encode('utf-8')
                                password_arcname = os.path.join(phone, '2fa.txt')
                                zipf.writestr(password_arcname, password_content)
                            
                            # 添加Session文件（如果有）到手机号根目录
                            session_path = result.get('session_path')
                            if session_path and os.path.exists(session_path):
                                session_base = os.path.splitext(session_path)[0]
                                # Session文件
                                zipf.write(session_path, f"{phone}/{phone}.session")
                                # Journal文件
                                journal_path = f"{session_base}.session-journal"
                                if os.path.exists(journal_path):
                                    zipf.write(journal_path, f"{phone}/{phone}.session-journal")
                                # JSON文件
                                json_path = f"{session_base}.json"
                                if os.path.exists(json_path):
                                    zipf.write(json_path, f"{phone}/{phone}.json")
                    else:
                        # Session格式：直接打包
                        if os.path.exists(file_path):
                            zipf.write(file_path, file_name)
                        # 添加journal文件
                        journal_path = file_path + '-journal'
                        if os.path.exists(journal_path):
                            zipf.write(journal_path, file_name + '-journal')
                        # 添加JSON文件
                        json_path = os.path.splitext(file_path)[0] + '.json'
                        if os.path.exists(json_path):
                            zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
            zip_files.append(('success', success_zip, success_count))
            logger.info(f"✅ 成功账号已打包: {success_zip}")
            print(f"✅ 成功账号已打包: {success_zip}", flush=True)
        except Exception as e:
            logger.error(f"❌ 打包成功账号失败: {e}")
            print(f"❌ 打包成功账号失败: {e}", flush=True)
    
    # 打包失败的账号（分类）- 添加异常保护
    failed_categories = {
        'frozen': ('冻结', results['frozen']),
        'banned': ('封禁', results['banned']),
        'wrong_password': ('密码错误', results['wrong_password']),
        'network_error': ('网络错误', results['network_error']),
        'other_error': ('其他错误', results['other_error'])
    }
    
    for category_key, (category_name, items) in failed_categories.items():
        if items:
            logger.info(f"📦 开始打包{category_name}账号...")
            print(f"📦 开始打包{category_name}账号...", flush=True)
            try:
                failed_zip = os.path.join(config.RESULTS_DIR, f"reauthorize_{category_key}_{timestamp}.zip")
                with zipfile.ZipFile(failed_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path, file_name, result in items:
                        # 失败的账号直接返回原始上传的完整文件结构
                        # 不做任何修改，保持原样
                        if os.path.isdir(file_path):
                            # TData目录 - 找到并打包包含手机号的完整文件夹
                            # file_path通常指向D877...或tdata目录
                            # 需要找到最顶层的手机号文件夹并完整打包
                            
                            # 向上查找，找到手机号文件夹（通常是数字命名的文件夹）
                            current_path = file_path
                            phone_folder = None
                            
                            # 最多向上查找3层
                            for _ in range(3):
                                parent = os.path.dirname(current_path)
                                folder_name = os.path.basename(current_path)
                                
                                # 如果文件夹名是数字（手机号），就是我们要找的
                                if folder_name.isdigit() and len(folder_name) > 10:
                                    phone_folder = current_path
                                    break
                                current_path = parent
                            
                            # 如果没找到手机号文件夹，就用file_path的父目录
                            if not phone_folder:
                                phone_folder = os.path.dirname(file_path)
                            
                            # 打包整个手机号文件夹及其所有内容
                            base_dir = os.path.dirname(phone_folder)
                            for root, dirs, files in os.walk(phone_folder):
                                for file in files:
                                    file_full_path = os.path.join(root, file)
                                    # 保持从base_dir开始的相对路径
                                    rel_path = os.path.relpath(file_full_path, base_dir)
                                    zipf.write(file_full_path, rel_path)
                        else:
                            # Session文件 - 直接使用原始文件名
                            if os.path.exists(file_path):
                                zipf.write(file_path, file_name)
                            # 添加journal文件（如果存在）
                            journal_path = file_path + '-journal'
                            if os.path.exists(journal_path):
                                zipf.write(journal_path, file_name + '-journal')
                            # 添加json文件（如果存在）
                            json_path = os.path.splitext(file_path)[0] + '.json'
                            if os.path.exists(json_path):
                                zipf.write(json_path, os.path.splitext(file_name)[0] + '.json')
                zip_files.append((category_key, failed_zip, len(items)))
                logger.info(f"✅ {category_name}账号已打包: {failed_zip}")
                print(f"✅ {category_name}账号已打包: {failed_zip}", flush=True)
            except Exception as e:
                logger.error(f"❌ 打包{category_name}账号失败: {e}")
                print(f"❌ 打包{category_name}账号失败: {e}", flush=True)
    
    # 发送统计信息 - 添加异常保护
    summary = f"""

