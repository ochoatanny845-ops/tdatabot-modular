# TData Bot - 模块化版本（基于原版）

**100%保留原版tdata.py功能，模块化组织结构**

---

## 📁 项目结构

```
tdatabot-modular/
├── main.py                        # 新入口（调用原版）
├── original/                      # 原版代码目录
│   ├── tdata.py                  # 原版主文件（1.3MB，完整功能）
│   ├── account_classifier.py
│   ├── login_api.py
│   ├── tron.py
│   ├── i18n/
│   └── device_params/
├── bot/                           # 模块化扩展（未来）
│   ├── handlers/
│   └── services/
├── core/                          # 核心模块（未来）
├── .env                           # 配置文件
└── requirements.txt
```

---

## 🚀 使用方法

### 方式1：直接运行原版（推荐）

```bash
cd original
python tdata.py
```

### 方式2：通过新入口运行

```bash
python main.py
```

两种方式功能完全一致！

---

## ✨ 所有功能（100%原版）

✅ 账号检测（SpamBot）  
✅ 格式转换（TData⇄Session）  
✅ 2FA管理  
✅ 一键清理  
✅ 资料修改  
✅ 批量操作  
✅ VIP系统  
✅ 管理面板  
✅ 群发通知  

---

##配置

复制 `.env.example` 到 `.env`：

```env
TOKEN=your_bot_token
API_ID=12345678
API_HASH=your_api_hash
ADMIN_IDS=your_telegram_id
```

---

## 📝 说明

- `original/` - 原版完整代码，零修改
- `main.py` - 新入口，导入并运行原版
- `bot/`, `core/` - 预留模块化扩展目录

**当前版本：直接使用original/tdata.py，功能100%保证**

---

**推荐：直接运行 `python original/tdata.py` 开始使用！** ✅
