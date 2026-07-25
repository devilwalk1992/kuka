import os, base64, fitz
from openai import OpenAI

BASE_DIR = r'G:\Trae工作文件\顾家产品库'
OUTPUT_DIR = os.path.join(BASE_DIR, 'markdown_db')

client = OpenAI(
    api_key='sk-ws-H.EHLRIYY.lQ0t.MEUCIQDDAH_SsWSrRmqiMo2G8Ahp7wXYpoRc7Mj8Hw6Cj9FAdgIgMV-LYKqyrYAsGUfQqVIRHD6cXHqF0JTYMg50fD0cAkA',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
)

CATEGORIES = [
    ('sofa_products', '沙发'),
    ('bed_products', '床架'),
    ('mattress_products', '床垫'),
]

def ocr_image(img_path, prompt):
    with open(img_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    ext = os.path.splitext(img_path)[1].lower().replace('.', '')
    mime = 'png' if ext == 'png' else 'jpeg'
    try:
        resp = client.chat.completions.create(
            model='qwen-vl-max',
            messages=[{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/{mime};base64,{img_b64}'}},
                {'type': 'text', 'text': prompt},
            ]}],
            temperature=0.1, max_tokens=2000,
        )
        return resp.choices[0].message.content or ''
    except Exception as e:
        return f'[OCR失败] {e}'

def pdf_to_img(pdf_path):
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=200)
    img = pdf_path.replace('.pdf', '_p0.png')
    pix.save(img)
    doc.close()
    return img

def update_md(md_path, content):
    if not os.path.exists(md_path): return False
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    new, inside, ok = [], False, False
    for line in lines:
        if line.startswith('## 产品信息'):
            inside = True
            new.append(line); new.append('\\n'); new.append(content); new.append('\\n')
            ok = True
        elif inside and line.startswith('## '):
            inside = False; new.append(line)
        elif not inside:
            new.append(line)
    if ok:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.writelines(new)
    return ok

def needs_ocr(fp):
    ppt_dir = os.path.join(fp, 'PPT')
    if not os.path.isdir(ppt_dir): return None
    fs = os.listdir(ppt_dir)
    xlsx = [f for f in fs if f.endswith('.xlsx') and not f.startswith('~$')]
    pptx = [f for f in fs if f.endswith('.pptx')]
    pdf = [f for f in fs if f.endswith('.pdf')]
    png = [f for f in fs if f.lower().endswith('.png') and '\u8be6\u60c5' not in f]
    jpg = [f for f in fs if f.lower().endswith(('.jpg','.jpeg')) and '\u8be6\u60c5' not in f]
    if xlsx: return None
    if pptx: return None  # has text-extractable doc
    if png: return ('image', os.path.join(ppt_dir, png[0]))
    if jpg: return ('image', os.path.join(ppt_dir, jpg[0]))
    if pdf: return ('pdf', os.path.join(ppt_dir, pdf[0]))
    return None

print('>>> \u4e09\u54c1\u7c7b OCR \u8bc6\u522b')
for subdir, label in CATEGORIES:
    cat_dir = os.path.join(BASE_DIR, subdir)
    if not os.path.isdir(cat_dir): continue
    print(f'\\n--- {label} ---')
    for folder in sorted(os.listdir(cat_dir)):
        fp = os.path.join(cat_dir, folder)
        if not os.path.isdir(fp) or folder.startswith('~$'): continue
        doc = needs_ocr(fp)
        if not doc: continue
        typ, path = doc
        print(f'  {folder}...', end=' ')
        if typ == 'pdf':
            img = pdf_to_img(path)
            text = ocr_image(img, '\u8bf7\u63d0\u53d6\u8fd9\u5f20\u4ea7\u54c1\u8d44\u6599\u56fe\u4e2d\u7684\u6240\u6709\u6587\u5b57\u4fe1\u606f\uff0c\u5305\u62ec\u4ea7\u54c1\u540d\u79f0\u3001\u9002\u914d\u98ce\u683c\u3001\u5404\u89c4\u683c\u5c3a\u5bf8(CM)\u3001\u6750\u8d28\u3001\u989c\u8272\u3001\u529f\u80fd\u7b49\u3002\u6309\u539f\u6587\u8f93\u51fa\u3002')
            os.remove(img)
        else:
            text = ocr_image(path, '\u8bf7\u63d0\u53d6\u8fd9\u5f20\u4ea7\u54c1\u8d44\u6599\u56fe\u4e2d\u7684\u6240\u6709\u6587\u5b57\u4fe1\u606f\uff0c\u5305\u62ec\u4ea7\u54c1\u540d\u79f0\u3001\u9002\u914d\u98ce\u683c\u3001\u5404\u89c4\u683c\u5c3a\u5bf8(CM)\u3001\u6750\u8d28\u3001\u989c\u8272\u7b49\u3002\u6309\u539f\u6587\u8f93\u51fa\u3002')
        md_path = os.path.join(OUTPUT_DIR, folder.replace(' ', '_') + '.md')
        if update_md(md_path, f'### OCR\u8bc6\u522b\u7ed3\u679c\\n\\n{text}'):
            print(f'OK ({len(text)} chars)')
        else:
            print('MD\u6587\u4ef6\u66f4\u65b0\u5931\u8d25')
print('\\n\u5168\u90e8\u5b8c\u6210')
