"""List all sofa combos missing sizes"""
import os, re

d = r'G:\Trae工作文件\顾家产品库\markdown_db'
sofa = [f for f in sorted(os.listdir(d)) if f.endswith('.md') and not f.startswith('_') and not f.startswith(('JD.B','JD.M','PT'))]

for f in sofa:
    content = open(os.path.join(d, f), encoding='utf-8').read()
    if '## 规格与价格' not in content:
        continue
    
    section = content.split('## 规格与价格')[1].split('## ')[0] if '## ' in content.split('## 规格与价格')[1] else content.split('## 规格与价格')[1]
    
    total = 0
    no_size = []
    with_size = []
    for line in section.split('\n'):
        if line.startswith('| ') and not line.startswith('| 规格') and not line.startswith('|---'):
            parts = line.split('|')
            if len(parts) >= 4:
                total += 1
                spec = parts[1].strip()[:50]
                size = parts[2].strip()
                price = parts[3].strip()
                if size == '-':
                    no_size.append((spec, price))
                else:
                    with_size.append(spec)
    
    if no_size:
        code = f.replace('.md', '')
        print(f"{code} ({total}个组合, {len(no_size)}个缺尺寸):")
        for spec, price in no_size:
            print(f"  ✗ {spec}  {price}")
    elif total > 0 and not no_size:
        print(f"{f.replace('.md','')} ({total}个组合, 全部有尺寸)")
