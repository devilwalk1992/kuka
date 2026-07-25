import os, base64, json, fitz  # PyMuPDF
from openai import OpenAI

BASE_DIR = r'G:\Trae工作文件\顾家产品库'
OUTPUT_DIR = os.path.join(BASE_DIR, 'markdown_db')

client = OpenAI(
    api_key='sk-ws-H.EHLRIYY.lQ0t.MEUCIQDDAH_SsWSrRmqiMo2G8Ahp7wXYpoRc7Mj8Hw6Cj9FAdgIgMV-LYKqyrYAsGUfQqVIRHD6cXHqF0JTYMg50fD0cAkA',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
)

def ocr_image(img_path, prompt="请提取这张产品页中的关键信息：产品名称、适配风格、各规格尺寸(CM)、材质。按要点简洁输出。"):
    """使用千问VL识别图片文字"""
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    ext = os.path.splitext(img_path)[1].lower().replace('.', '')
    mime = 'png' if ext == 'png' else 'jpeg'
    
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

def pdf_page_to_image(pdf_path, page_num=0):
    """将PDF指定页转为图片（临时保存）"""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(dpi=200)
    img_path = pdf_path.replace('.pdf', f'_page{page_num}.png')
    pix.save(img_path)
    doc.close()
    return img_path


# ========== 1. JD.6012 - 处理PNG文档 ==========
print("=== JD.6012: OCR图片文档 ===")
ppt_dir = os.path.join(BASE_DIR, 'sofa_products', 'JD.6012', 'PPT')
results_6012 = []

for fname in sorted(os.listdir(ppt_dir)):
    if not fname.lower().endswith(('.png', '.jpg', '.jpeg')) or '详情' in fname:
        continue
    fp = os.path.join(ppt_dir, fname)
    print(f'  识别: {fname}...')
    text = ocr_image(fp, "请完整提取这张产品资料图中的所有文字信息，包括产品名称、适配风格、各规格尺寸(CM)、材质、颜色等。按原文输出。")
    results_6012.append(f'### {fname}\n\n{text}')
    print(f'    → {text[:100]}...')

# ========== 2. JD.6015 - PDF转图片后OCR ==========
print("\n=== JD.6015: OCR PDF文档 ===")
pdf_path = os.path.join(BASE_DIR, 'sofa_products', 'JD.6015', 'PPT', 'JD.6015.pdf')
results_6015 = []

img_path = pdf_page_to_image(pdf_path)
print(f'  转图: {os.path.basename(img_path)}')
text = ocr_image(img_path, "请完整提取这张产品资料图中的所有文字信息，包括产品名称、适配风格、各规格尺寸(CM)、材质、颜色、功能等。按原文输出。")
results_6015.append(f'### 产品资料页\n\n{text}')
print(f'    → {text[:100]}...')

# 清理临时图片
if os.path.exists(img_path):
    os.remove(img_path)

# Also process 详情页.jpg if exists (JD.6015's shared folder has it but it's for JD.6012)
# Skip for JD.6015 - 详情页.jpg is actually for JD.6012

# ========== 3. 更新MD文件 ==========
def update_md(md_path, ocr_section):
    """替换MD文件中 ## 产品信息 和 ## 图片素材 之间的内容为OCR提取结果"""
    if not os.path.exists(md_path):
        print(f'  MD文件不存在: {md_path}')
        return
    
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    in_product_info = False
    replaced = False
    
    for line in lines:
        if line.startswith('## 产品信息'):
            in_product_info = True
            new_lines.append(line)
            new_lines.append('\n')
            new_lines.append(ocr_section)
            new_lines.append('\n')
            replaced = True
        elif in_product_info and line.startswith('## '):
            in_product_info = False
            new_lines.append(line)
        elif not in_product_info:
            new_lines.append(line)
    
    if replaced:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f'  已更新: {os.path.basename(md_path)}')
    else:
        print(f'  未找到产品信息标记: {os.path.basename(md_path)}')

# Update JD.6012
ocr_6012 = '\n\n'.join(results_6012)
update_md(os.path.join(OUTPUT_DIR, 'JD.6012.md'), ocr_6012)

# Update JD.6015
ocr_6015 = '\n\n'.join(results_6015)
update_md(os.path.join(OUTPUT_DIR, 'JD.6015.md'), ocr_6015)

print("\n=== 完成 ===")
