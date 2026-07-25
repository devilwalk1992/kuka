with open('build_full_database.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Fix the duplicate function definition
c = c.replace('def scan_images_in_folderdef scan_images_in_folder', 'def scan_images_in_folder')

with open('build_full_database.py', 'w', encoding='utf-8') as f:
    f.write(c)

# Verify
with open('build_full_database.py', 'r', encoding='utf-8') as f:
    c = f.read()

import ast
try:
    ast.parse(c)
    print('语法检查通过')
except SyntaxError as e:
    print(f'语法错误: {e}')
    # Show context around the error
    lines = c.split('\n')
    lineno = e.lineno - 1
    for i in range(max(0, lineno-2), min(len(lines), lineno+3)):
        print(f'  L{i+1}: {lines[i]}')
