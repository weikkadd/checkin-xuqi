import ast
import sys

try:
    with open(r'C:\Users\ASUS\Documents\AgnesCode\checkin-xuqi\gaming4free-renew\renew.py', 'r', encoding='utf-8') as f:
        content = f.read()
    ast.parse(content)
    print("✅ Syntax OK")
except SyntaxError as e:
    print(f"❌ SyntaxError at line {e.lineno}: {e.msg}")
    print(f"   Text: {e.text}")
