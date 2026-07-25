"""餐桌品类专用 - 读取 table_products 的 JPG 生成 MD 文档"""
import os, base64, re, json
from openai import OpenAI

BASE_DIR = r'G:\Trae工作文件\顾家产品库'
TABLE_DIR = os.path.join(BASE_DIR, 'table_products')
OUTPUT_DIR = os.path.join(BASE_DIR, 'markdown_db')
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = OpenAI(
    api_key='sk-ws-H.EHLRIYY.lQ0t.MEUCIQDDAH_SsWSrRmqiMo2G8Ahp7wXYpoRc7Mj8Hw6Cj9FAdgIgMV-LYKqyrYAsGUfQqVIRHD6cXHqF0JTYMg50fD0cAkA',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
)

def ocr_image(img_path):
    """使用千问VL识别图片文字"""
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    ext = os.path.splitext(img_path)[1].lower().replace('.', '')
    mime = 'png' if ext == 'png' else 'jpeg'
    
    prompt = "请提取这张餐桌产品资料图中的所有文字信息，包括：产品型号、是圆桌还是方桌、尺寸大小(CM)、有哪些尺寸可选、材质、设计风格、配色等。按要点简洁输出。"
    
    try:
        response = client.chat.completions.create(
            model='qwen-vl-max',
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image_url', 'image_url': {'url': f'data:image/{mime};base64,{img_b64}'}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
            temperature=0.1,
            max_tokens=2000,
        )
        return response.choices[0].message.content or ''
    except Exception as e:
        return f'[OCR失败] {e}'

def list_images(d):
    if not os.path.isdir(d): return []
    exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    return sorted([f for f in os.listdir(d) if f.lower().endswith(exts)])

def safe_name(f):
    return f.replace(' ', '_').replace('/', '_')

print(">>> 餐桌品类 MD 生成")
count = 0

for folder in sorted(os.listdir(TABLE_DIR)):
    fp = os.path.join(TABLE_DIR, folder)
    if not os.path.isdir(fp) or folder.startswith('~$'): continue
    
    # 查找产品信息图（优先 *产品信息* 命名的文件）
    info_img = None
    all_imgs = list_images(fp)
    for img in all_imgs:
        if '产品信息' in img:
            info_img = img
            break
    if not info_img and all_imgs:
        # 如果没有产品信息图，取第一张
        info_img = all_imgs[0]
    
    lines = [f"# {folder}\n", "## 产品信息\n"]
    
    if info_img:
        img_path = os.path.join(fp, info_img)
        print(f"  OCR识别: {folder}/{info_img}...")
        ocr_text = ocr_image(img_path)
        print(f"    → {ocr_text[:150]}...")
        
        # 将OCR结果写入产品信息
        for line in ocr_text.strip().split('\n'):
            line = line.strip()
            if line:
                if re.match(r'^[*-]', line):
                    lines.append(line)
                elif re.match(r'^###?\s', line):
                    lines.append(f"\n{line}")
                elif '：' in line or ':' in line:
                    lines.append(f"- {line}")
                else:
                    lines.append(line)
        lines.append("")
    
    # 记录产品图
    product_imgs = [img for img in all_imgs if img != info_img]
    
    if product_imgs:
        lines.append("## 图片素材\n")
        lines.append(f"\n### 产品图 ({len(product_imgs)}张)")
        for img in product_imgs:
            rel = os.path.relpath(os.path.join(fp, img), BASE_DIR).replace('\\', '/')
            lines.append(f"![{folder}]({rel})")
    
    # 写入MD
    md_path = os.path.join(OUTPUT_DIR, f"{safe_name(folder)}.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    count += 1
    print(f"  ✓ 已生成: {safe_name(folder)}.md")

print(f"\n餐桌品类完成: {count} 个文件")
