"""Check which sofa MD files still lack sizes"""
import os, re

d = r'G:\Trae工作文件\顾家产品库\markdown_db'
for f in sorted(os.listdir(d)):
    if not f.endswith('.md') or f.startswith(('JD.B', 'JD.M', '_')):
        continue
    if f[0].isdigit() or f[:3].isalpha():
        pass  # sofa file
    else:
        continue
    
    content = open(os.path.join(d, f), encoding='utf-8').read()
    if '## 规格与价格' not in content:
        continue
    
    section = content.split('## 规格与价格')[1].split('## ')[0]
    missing = []
    for line in section.split('\n'):
        if line.startswith('| ') and not line.startswith('| 规格') and not line.startswith('|---'):
            parts = line.split('|')
            if len(parts) >= 4 and parts[2].strip() == '-':
                missing.append(parts[1].strip()[:50])
    
    if missing:
        print(f'{f}: {len(missing)}个缺尺寸')
        for m in missing[:3]:
            print(f'    {m}')
