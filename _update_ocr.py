with open('build_full_database.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 extract_text_from_image 函数并替换
start = None
end = None
for i, line in enumerate(lines):
    if 'def extract_text_from_image(image_path: str) -> str:' in line:
        start = i
    if start is not None and i > start:
        if line.strip().startswith('def ') or line.strip().startswith('# ==='):
            end = i
            break

if start is None:
    print('❌ 未找到 extract_text_from_image 函数')
    exit(1)
if end is None:
    end = len(lines)

print(f'找到 extract_text_from_image: L{start+1}-L{end}')

# 构建新的函数
new_func = '''def extract_text_from_image(image_path: str) -> str:
    """从图片文件中通过千问多模态 API 提取文本（识别详情页的面料、填充等信息）"""
    import base64
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(image_path)[1].lower().replace(".", "")
        mime = "png" if ext == "png" else "jpeg"

        response = client.chat.completions.create(
            model="qwen-vl-max-2025-01-25",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img_b64}"}},
                        {"type": "text", "text": "请完整提取这张产品详情页中的所有文字信息，特别是：产品名称、面料材质、填充物类型、海绵密度、尺寸规格、颜色等参数。按原文输出，不要遗漏。"},
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"  \\u26a0\\ufe0f OCR 识别图片失败 ({os.path.basename(image_path)}): {e}")
        return ""


def scan_images_in_folder'''

# 替换
old_text = ''.join(lines[start:end])
lines = lines[:start] + [new_func] + lines[end:]

with open('build_full_database.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('extract_text_from_image 已更新为千问 API 版本')
print('验证:', 'qwen-vl-max' in new_func)
