import os, re

md_dir = 'markdown_db'
report = []

for f in sorted(os.listdir(md_dir)):
    if not f.endswith('.md') or f == 'product_images.json':
        continue
    
    path = os.path.join(md_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    
    lines = content.split('\n')
    
    # === 检查规格尺寸 ===
    # 找到 "规格参数" 或 "尺寸" 章节
    has_spec_section = False
    spec_table_rows = 0
    spec_table_cm = 0
    for i, line in enumerate(lines):
        if re.match(r'^##\s+2\.', line):
            has_spec_section = True
            # 往后找表格行
            for j in range(i+1, min(i+50, len(lines))):
                if lines[j].startswith('|') and 'cm' in lines[j].lower():
                    spec_table_cm += 1
                if lines[j].startswith('|') and not lines[j].strip().startswith('|---'):
                    # 非表头/分隔行的表格行
                    if '---' not in lines[j]:
                        spec_table_rows += 1
    
    has_size_in_table = spec_table_cm > 0
    has_spec_rows = spec_table_rows > 2  # 至少有几个规格行
    
    # === 检查价格 ===
    has_price_section = False
    price_rows = 0
    for i, line in enumerate(lines):
        if re.match(r'^##\s+4\.', line):
            has_price_section = True
            for j in range(i+1, min(i+50, len(lines))):
                l = lines[j].strip()
                if '¥' in l:
                    price_rows += 1
    
    # === 收集问题 ===
    issues = []
    if not has_spec_section:
        issues.append('无规格参数章节(## 2.)')
    elif not has_spec_rows:
        issues.append(f'规格表格行数过少({spec_table_rows}行)')
    elif not has_size_in_table:
        issues.append('规格表格中无尺寸信息(cm)')
    
    if not has_price_section:
        issues.append('无价格章节(## 4.)')
    elif price_rows == 0:
        issues.append('价格表中无实际报价(¥)')
    
    summary = {
        'file': f,
        'spec_rows': spec_table_rows,
        'spec_cm': spec_table_cm,
        'price_rows': price_rows,
        'issues': issues,
        'ok': len(issues) == 0,
    }
    report.append(summary)

# 输出
print(f"{'文件':22s} | 规格行 | 含尺寸 | 价格行 | 状态")
print('-' * 65)
for r in report:
    status = 'OK' if r['ok'] else '!!'
    print(f"{r['file']:22s} | {r['spec_rows']:5d} | {str(r['spec_cm']>0):>4s} | {r['price_rows']:5d} | {status}")
    if not r['ok']:
        for iss in r['issues']:
            print(f"  {'':22s} |      |        |       | -> {iss}")

print()
ok_count = sum(1 for r in report if r['ok'])
print(f'通过: {ok_count}/{len(report)}')
print()
print('有问题的文件:')
for r in report:
    if not r['ok']:
        print(f'  {r["file"]}: {"; ".join(r["issues"])}')
