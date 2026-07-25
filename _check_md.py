import os
md_dir = 'markdown_db'
for f in sorted(os.listdir(md_dir)):
    if not f.endswith('.md') or f == 'product_images.json':
        continue
    path = os.path.join(md_dir, f)
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    has_fabric = any(k in content for k in ['面料','材质','填充','海绵'])
    prices = [l for l in content.split('\n') if '¥' in l or '成交价' in l]
    has_wholesale = '批发' in content or '1.7' in content
    fabric_icon = 'OK' if has_fabric else '--'
    price_icon = 'OK' if prices else '--'
    safe_icon = 'OK' if not has_wholesale else 'WARN'
    print(f'{f:20s} | 面料/填充: {fabric_icon} | 价格表: {price_icon} ({len(prices)}行) | 无批发泄露: {safe_icon}')
