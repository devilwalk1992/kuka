with open('build_full_database.py', 'r', encoding='utf-8') as f:
    content = f.read()

# === 操作A: 在 extract_text_from_xlsx 之后添加 image OCR 函数 ===
old_anchor = '''def extract_text_from_xlsx(xlsx_path: str) -> str:
    """从 Excel 文件中提取所有文本内容"""
    try:
        import pandas as pd
        xls = pd.ExcelFile(xlsx_path)
        all_text = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            texts = []
            for col in df.columns:
                for val in df[col].dropna():
                    s = str(val).strip()
                    if s and s != 'nan':
                        texts.append(s)
            if texts:
                all_text.append(f"[Sheet: {sheet}]\\n" + "\\n".join(texts[:200]))
        return "\\n\\n".join(all_text)
    except Exception as e:
        print(f"  \\u26a0\\ufe0f 读取 Excel 失败 ({os.path.basename(xlsx_path)}): {e}")
        return ""


def scan_images_in_folder'''

new_anchor = '''def extract_text_from_xlsx(xlsx_path: str) -> str:
    """从 Excel 文件中提取所有文本内容"""
    try:
        import pandas as pd
        xls = pd.ExcelFile(xlsx_path)
        all_text = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            texts = []
            for col in df.columns:
                for val in df[col].dropna():
                    s = str(val).strip()
                    if s and s != 'nan':
                        texts.append(s)
            if texts:
                all_text.append(f"[Sheet: {sheet}]\\n" + "\\n".join(texts[:200]))
        return "\\n\\n".join(all_text)
    except Exception as e:
        print(f"  \\u26a0\\ufe0f 读取 Excel 失败 ({os.path.basename(xlsx_path)}): {e}")
        return ""


def extract_text_from_image(image_path: str) -> str:
    """从图片文件中通过 OCR 提取文本"""
    try:
        import easyocr
        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        results = reader.readtext(image_path)
        texts = [r[1] for r in results]
        return "\\n".join(texts) if texts else ""
    except ImportError:
        print(f"  \\u26a0\\ufe0f 未安装 easyocr，无法 OCR 图片 ({os.path.basename(image_path)})")
        return ""
    except Exception as e:
        print(f"  \\u26a0\\ufe0f 读取图片失败 ({os.path.basename(image_path)}): {e}")
        return ""


def scan_images_in_folder'''

count = content.count(old_anchor)
print(f'锚点A出现: {count} 次')
if count == 1:
    content = content.replace(old_anchor, new_anchor, 1)
    print('操作A: 添加 image OCR 函数成功')

# === 操作B: 更新文档文件搜索（在 PPT/ 目录下也搜索图片）===
old_search = '''            doc_files = (
                glob.glob(os.path.join(ppt_dir, "*.pptx"))
                + glob.glob(os.path.join(ppt_dir, "*.ppt"))
                + glob.glob(os.path.join(ppt_dir, "*.pdf"))
                + glob.glob(os.path.join(ppt_dir, "*.docx"))
                + glob.glob(os.path.join(ppt_dir, "*.xlsx"))
            )'''

new_search = '''            doc_files = (
                glob.glob(os.path.join(ppt_dir, "*.pptx"))
                + glob.glob(os.path.join(ppt_dir, "*.ppt"))
                + glob.glob(os.path.join(ppt_dir, "*.pdf"))
                + glob.glob(os.path.join(ppt_dir, "*.docx"))
                + glob.glob(os.path.join(ppt_dir, "*.xlsx"))
                + glob.glob(os.path.join(ppt_dir, "*.[jJ][pP][gG]"))
                + glob.glob(os.path.join(ppt_dir, "*.[jJ][pP][eE][gG]"))
                + glob.glob(os.path.join(ppt_dir, "*.[pP][nN][gG]"))
            )'''

count = content.count(old_search)
print(f'锚点B出现: {count} 次')
if count == 1:
    content = content.replace(old_search, new_search, 1)
    print('操作B: 更新搜索词成功')

# === 操作C: 更新提取逻辑，添加 image 分支 ===
old_extract = '''        for doc in doc_files:
            ext = os.path.splitext(doc)[1].lower()
            if ext == ".pdf":
                doc_text += extract_text_from_pdf(doc) + "\\n"
            elif ext == ".docx":
                doc_text += extract_text_from_docx(doc) + "\\n"
            elif ext == ".xlsx":
                doc_text += extract_text_from_xlsx(doc) + "\\n"
            else:
                doc_text += extract_text_from_ppt(doc) + "\\n"'''

new_extract = '''        for doc in doc_files:
            ext = os.path.splitext(doc)[1].lower()
            if ext == ".pdf":
                doc_text += extract_text_from_pdf(doc) + "\\n"
            elif ext == ".docx":
                doc_text += extract_text_from_docx(doc) + "\\n"
            elif ext == ".xlsx":
                doc_text += extract_text_from_xlsx(doc) + "\\n"
            elif ext in (".jpg", ".jpeg", ".png"):
                doc_text += extract_text_from_image(doc) + "\\n"
            else:
                doc_text += extract_text_from_ppt(doc) + "\\n"'''

count = content.count(old_extract)
print(f'锚点C出现: {count} 次')
if count == 1:
    content = content.replace(old_extract, new_extract, 1)
    print('操作C: 更新提取逻辑成功')

# 保存
with open('build_full_database.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 验证
with open('build_full_database.py', 'r', encoding='utf-8') as f:
    c = f.read()
print()
print('=== 验证 ===')
print('extract_text_from_image:', 'extract_text_from_image' in c)
print('*.jpg in search:', '*.jpg' in c or '*.[jJ][pP][gG]' in c)
print('*.png in search:', '*.[pP][nN][gG]' in c)
print('image OCR in extract:', 'extract_text_from_image(doc)' in c)
