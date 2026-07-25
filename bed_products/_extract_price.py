import win32com.client as win32
import pythoncom
import os, json, re

EXCEL_PATH = r'G:\Trae工作文件\顾家产品库\bed_products\顾家经典系列批发价格表-07版本(1).xlsx'
BED_DIR = r'G:\Trae工作文件\顾家产品库\bed_products'
MATTRESS_DIR = r'G:\Trae工作文件\顾家产品库\mattress_products'
OUTPUT_DIR = r'G:\Trae工作文件\顾家产品库\markdown_db'

os.makedirs(OUTPUT_DIR, exist_ok=True)

pythoncom.CoInitialize()
excel = win32.Dispatch('Excel.Application')
excel.Visible = False
excel.DisplayAlerts = False

try:
    wb = excel.Workbooks.Open(EXCEL_PATH, 0, False, 5, '202607')

    # ========== Sheet 01-床架 ==========
    ws = wb.Sheets('01-床架')
    max_r = ws.UsedRange.Rows.Count
    max_c = ws.UsedRange.Columns.Count
    data = ws.Range(ws.Cells(1, 1), ws.Cells(max_r, max_c)).Value
    
    bed_frame_data = []
    current_product = {}
    
    for i, row in enumerate(data):
        r = i + 1
        if r <= 3:
            continue
        
        c1 = str(row[0]).strip() if row[0] is not None else ''
        c2 = str(row[1]).strip() if row[1] is not None else ''
        c4 = str(row[3]).strip() if row[3] is not None else ''
        c5 = str(row[4]).strip() if row[4] is not None else ''
        c9 = row[8]
        c14 = str(row[13]).strip() if row[13] is not None else ''
        
        if c1 and not c1.startswith('=') and c1 != 'None':
            current_product['系列'] = c1
        if c2 and not c2.startswith('='):
            current_product['货号'] = c2.split('\n')[0].strip()
        if c4 and not c4.startswith('='):
            current_product['配色型号'] = c4
        if c14 and c14 != 'None':
            current_product['可搭配床垫厚度'] = c14
        
        if not c5:
            continue
        
        product_series = current_product.get('系列', '').replace('\n', '')
        product_code = current_product.get('货号', '').replace('\n', '')
        color_model = current_product.get('配色型号', '').replace('\n', '')
        
        if not product_code:
            continue
        
        wholesale = 0
        try:
            wholesale = float(c9) if c9 else 0
        except (ValueError, TypeError):
            wholesale = 0
        actual_price = round(wholesale * 1.7) if wholesale > 0 else 0
        
        bed_frame_data.append({
            '产品系列': product_series,
            '货号': product_code,
            '配色型号': color_model,
            '规格': c5,
            '实际成交价': actual_price,
            '可搭配床垫厚度': current_product.get('可搭配床垫厚度', '')
        })
    
    print(f"01-床架: 提取 {len(bed_frame_data)} 条记录")

    # ========== Sheet 02-床垫 ==========
    ws2 = wb.Sheets('02-床垫')
    max_r2 = ws2.UsedRange.Rows.Count
    max_c2 = ws2.UsedRange.Columns.Count
    data2 = ws2.Range(ws2.Cells(1, 1), ws2.Cells(max_r2, max_c2)).Value
    
    mattress_data = []
    current_mattress = {}
    
    for i, row in enumerate(data2):
        r = i + 1
        if r <= 2:
            continue
        
        c2 = str(row[1]).strip() if row[1] is not None else ''
        c5 = str(row[4]).strip() if row[4] is not None else ''
        c7 = str(row[6]).strip() if row[6] is not None else ''
        c8 = row[7]
        c10 = str(row[9]).strip() if row[9] is not None else ''
        
        if c2 and not c2.startswith('='):
            current_mattress['系列'] = c2.replace('\n', '')
        if c5 and not c5.startswith('='):
            current_mattress['货号'] = c5.split('\n')[0].strip()
        if c10 and not c10.startswith('='):
            current_mattress['材质'] = c10.replace('\n', '')
        
        if not c7:
            continue
        
        product_series = current_mattress.get('系列', '')
        product_code = current_mattress.get('货号', '')
        material = current_mattress.get('材质', '')
        
        if not product_code:
            continue
        
        wholesale = 0
        try:
            wholesale = float(c8) if c8 else 0
        except (ValueError, TypeError):
            wholesale = 0
        actual_price = round(wholesale * 1.7) if wholesale > 0 else 0
        
        mattress_data.append({
            '产品系列': product_series,
            '货号': product_code,
            '规格': c7,
            '实际成交价': actual_price,
            '材质': material
        })
    
    print(f"02-床垫: 提取 {len(mattress_data)} 条记录")
    
    wb.Close()
    
    # ========== Group data by 货号 ==========
    frame_by_code = {}
    for item in bed_frame_data:
        code = item['货号']
        if code not in frame_by_code:
            frame_by_code[code] = []
        frame_by_code[code].append(item)
    
    mattress_by_code = {}
    for item in mattress_data:
        code = item['货号']
        if code not in mattress_by_code:
            mattress_by_code[code] = []
        mattress_by_code[code].append(item)
    
    # Save extracted data as JSON
    output = {
        'bed_frames': bed_frame_data,
        'mattresses': mattress_data
    }
    with open(os.path.join(OUTPUT_DIR, '_price_data.json'), 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # ========== Utility functions ==========
    def normalize(s):
        return re.sub(r'[\s.\n]', '', s.upper())

    def match_code(folder, code_dict):
        folder_norm = normalize(folder)
        
        for code, items in code_dict.items():
            code_norm = normalize(code)
            if folder_norm == code_norm:
                return items
        
        folder_stripped = re.sub(r'^(JD|HS|BY)', '', folder_norm)
        for code, items in code_dict.items():
            code_stripped = re.sub(r'^(JD|B|90|HS|BY)', '', normalize(code))
            if folder_stripped and folder_stripped == code_stripped:
                return items
            nums = re.findall(r'\d+[A-Z0-9]*', folder_stripped)
            for n in nums:
                if len(n) >= 4 and n in code_stripped:
                    return items
        return []

    def price_str(val):
        """格式化价格，去掉批发价字段后的实际成交价"""
        if val == 0:
            return ''
        return f"¥{val:,}" if isinstance(val, int) else f"¥{val:,.0f}"

    # ========== Generate MD for bed_products ==========
    bed_folders = [d for d in os.listdir(BED_DIR) 
                   if os.path.isdir(os.path.join(BED_DIR, d)) and not d.startswith('~$')]
    
    md_count = 0
    bed_no_match = []
    
    for folder in bed_folders:
        matched_frames = match_code(folder, frame_by_code)
        matched_mattresses = match_code(folder, mattress_by_code)
        
        if not matched_frames and not matched_mattresses:
            bed_no_match.append(folder)
            continue
        
        md_lines = []
        md_lines.append(f"# {folder}\n")
        
        if matched_frames:
            by_color = {}
            for item in matched_frames:
                color = item['配色型号']
                if color not in by_color:
                    by_color[color] = []
                by_color[color].append(item)
            
            md_lines.append("## 床架\n")
            for color, items in by_color.items():
                md_lines.append(f"### 配色型号: {color}\n")
                md_lines.append("| 规格 | 实际成交价 | 可搭配床垫厚度 |")
                md_lines.append("|------|-----------|--------------|")
                for item in items:
                    md_lines.append(f"| {item['规格']} | {price_str(item['实际成交价'])} | {item['可搭配床垫厚度']} |")
                md_lines.append("")
        
        if matched_mattresses:
            md_lines.append("## 床垫\n")
            series = matched_mattresses[0]['产品系列']
            md_lines.append(f"**产品系列**: {series}\n")
            
            material = matched_mattresses[0]['材质']
            if material:
                md_lines.append(f"**材质**: {material}\n")
            
            md_lines.append("| 货号 | 规格 | 实际成交价 |")
            md_lines.append("|------|------|-----------|")
            for item in matched_mattresses:
                md_lines.append(f"| {item['货号']} | {item['规格']} | {price_str(item['实际成交价'])} |")
            md_lines.append("")
        
        safe_name = folder.replace(' ', '_').replace('/', '_')
        md_path = os.path.join(OUTPUT_DIR, f"{safe_name}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        
        md_count += 1
        print(f"已生成: {safe_name}.md ({len(matched_frames)} 床架, {len(matched_mattresses)} 床垫)")

    # ========== Generate MD for mattress_products ==========
    mattress_folders = [d for d in os.listdir(MATTRESS_DIR) 
                        if os.path.isdir(os.path.join(MATTRESS_DIR, d)) and not d.startswith('~$')]
    
    mattress_md_count = 0
    mattress_no_match = []
    
    for folder in mattress_folders:
        matched = match_code(folder, mattress_by_code)
        
        if not matched:
            mattress_no_match.append(folder)
            continue
        
        # Group by product series
        series = matched[0]['产品系列']
        material = matched[0]['材质']
        
        md_lines = []
        md_lines.append(f"# {folder}\n")
        md_lines.append("## 床垫\n")
        if series:
            md_lines.append(f"**产品系列**: {series}\n")
        if material:
            md_lines.append(f"**材质**: {material}\n")
        
        md_lines.append("| 货号 | 规格 | 实际成交价 |")
        md_lines.append("|------|------|-----------|")
        for item in matched:
            md_lines.append(f"| {item['货号']} | {item['规格']} | {price_str(item['实际成交价'])} |")
        md_lines.append("")
        
        safe_name = folder.replace(' ', '_').replace('/', '_')
        md_path = os.path.join(OUTPUT_DIR, f"{safe_name}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))
        
        mattress_md_count += 1
        print(f"已生成: {safe_name}.md ({len(matched)} 床垫)")
    
    # ========== Summary ==========
    print(f"\n床架产品: 共生成 {md_count} 个 MD 文件")
    if bed_no_match:
        print(f"  未匹配: {bed_no_match}")
    
    print(f"\n床垫产品: 共生成 {mattress_md_count} 个 MD 文件")
    if mattress_no_match:
        print(f"  未匹配: {mattress_no_match}")
    
    print(f"\n总计: {md_count + mattress_md_count} 个 MD 文件")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    excel.Quit()
    pythoncom.CoUninitialize()
