"""沙发图片重命名：统一为 货号-配色代码-颜色名称.jpg 格式"""
import os, re

SOFA_DIR = r'G:\Trae工作文件\顾家产品库\sofa_products'

# 常见颜色中文名映射（从配色代码文件/PPT中提取）
# key = 颜色代号段, value = (完整代码, 中文名)
# 更完整的映射放在下面，运行时还会从文件名自动提取

def get_color_name(code):
    """根据配色代码提取颜色中文名"""
    name_map = {
        'T250010': '黑骑士', 'T250061': '菊蕊白', 'T250083': '暖沙', 'T250122': '暖栗色',
        'T250133': '烟灰色', 'T250163': '奶咖', 'T342182': '栗子棕', 'T326030': '魅影黑',
        'U665010': '星爵黑', 'U665021': '岩灰', 'U665033': '星云灰', 'U665042': '琥珀橙',
        'U665051': '燕麦拿铁', 'U665073': '砂岩棕', 'U665082': '熔岩褐', 'U665115': '烟墨棕',
        'U665123': '沙滩白', 'U665162': '暗夜棕', 'U670021': '芝士米', 'U670082': '熔岩褐',
        'U775012': '暮云灰', 'U775030': '米白',
        'W767010': '暖灰', 'W767072': '奶棕色', 'W767083': '月光灰', 'W767161': '奶油米',
        'W767172': '烟灰紫', 'W767192': '浆果红棕', 'W767221': '乳酪白',
        'W799012': '浆果红棕', 'W758022': '晨雾绿', 'W758011': '烟粉',
        'F250010': '黑骑士', 'F250061': '菊蕊白', 'F250083': '暖沙', 'F250122': '暖栗色',
        'F250133': '烟灰色', 'F670021': '芝士米', 'F670021-X': '芝士米', 'F799012': '浆果红棕',
        'F767072-X': '奶棕色', 'F767083-X': '月光灰', 'F767192': '浆果红棕',
        'T502111': '云石白', 'T502192': '暮山褐',
        'U544023': '雾霾蓝', 'U544052': '抹茶绿',
        'T511210': '宁和蓝', 'T511231': '雾蓝',
        'T250163': '奶咖色',
    }
    # 先精确匹配
    if code in name_map:
        return name_map[code]
    # 尝试部分匹配（取前7位）
    prefix = code[:7] if len(code) >= 7 else code
    for k, v in name_map.items():
        if k.startswith(prefix) or prefix.startswith(k):
            return v
    return ''

def extract_code_from_filename(fname):
    """从文件名提取配色代码"""
    # Pattern like "U665010", "T250010", "W767072" etc.
    m = re.search(r'([A-Z]\d{5,}[\w\-]*)', fname)
    if m:
        code = m.group(1)
        # Clean trailing separators
        code = re.sub(r'[\-_\.\s]+$', '', code)
        return code
    return ''

def extract_color_from_filename(fname):
    """从文件名提取颜色中文名"""
    # Remove extension
    base = os.path.splitext(fname)[0]
    # Common separators and known color names
    color_names = ['黑骑士', '菊蕊白', '暖栗色', '暖沙', '烟灰色', '奶咖', '栗子棕', '魅影黑',
                   '星爵黑', '岩灰', '星云灰', '琥珀橙', '燕麦拿铁', '砂岩棕', '熔岩褐', '烟墨棕',
                   '沙滩白', '暗夜棕', '芝士米', '暮云灰', '米白', '暖灰', '奶棕色', '月光灰',
                   '奶油米', '烟灰紫', '浆果红棕', '乳酪白', '晨雾绿', '烟粉', '云石白', '暮山褐',
                   '雾霾蓝', '抹茶绿', '宁和蓝', '雾蓝', '奶咖色', '暖沙色']
    for name in color_names:
        if name in base:
            return name
    return ''

def rename_images():
    total = 0
    renamed = 0
    errors = 0
    
    for folder in sorted(os.listdir(SOFA_DIR)):
        fp = os.path.join(SOFA_DIR, folder)
        if not os.path.isdir(fp) or folder.startswith('~$'): continue
        
        product_code = folder  # 货号
        
        for subdir_name in ['场景图', '浏览图', '入户实景图', '白底图']:
            subdir = os.path.join(fp, subdir_name)
            if not os.path.isdir(subdir): continue
            
            for fname in sorted(os.listdir(subdir)):
                fpath = os.path.join(subdir, fname)
                if not os.path.isfile(fpath): continue
                
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'): continue
                
                total += 1
                
                # 提取配色代码和颜色名
                code = extract_code_from_filename(fname)
                color_name = extract_color_from_filename(fname)
                
                # 如果从文件名没找到，从代码反查
                if not color_name and code:
                    color_name = get_color_name(code)
                
                # 构建新文件名
                parts = [product_code]
                if code:
                    parts.append(code)
                if color_name:
                    parts.append(color_name)
                
                new_name = '-'.join(parts) + ext
                new_path = os.path.join(subdir, new_name)
                
                if fname != new_name and not os.path.exists(new_path):
                    try:
                        os.rename(fpath, new_path)
                        print(f'  [{folder}/{subdir_name}] {fname} → {new_name}')
                        renamed += 1
                    except Exception as e:
                        print(f'  [ERROR] {fname}: {e}')
                        errors += 1
    
    print(f'\n总计: {total} 张图片, 重命名 {renamed} 张, 失败 {errors}')

if __name__ == '__main__':
    print(">>> 沙发图片重命名\n")
    rename_images()
