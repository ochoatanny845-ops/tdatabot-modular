"""
修复 proxy_manager.py 的导入错误
PBKDF2 -> PBKDF2HMAC
"""

import os
import re

# 读取文件
file_path = 'core/proxy_manager.py'

if not os.path.exists(file_path):
    print(f"ERROR: {file_path} not found")
    exit(1)

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换导入
content = content.replace(
    'from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2',
    'from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC'
)

# 替换所有使用的地方
content = content.replace('PBKDF2(', 'PBKDF2HMAC(')

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"[OK] Fixed {file_path}")
print("PBKDF2 -> PBKDF2HMAC")
print("\nNow you can run: python run.py")
