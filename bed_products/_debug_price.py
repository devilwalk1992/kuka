"""Debug: check price_map for JD.0061"""
import os, re
import win32com.client as win32, pythoncom

pythoncom.CoInitialize()
excel = win32.Dispatch('Excel.Application')
excel.Visible = False
wb = excel.Workbooks.Open(r'G:\Trae工作文件\顾家产品库\sofa_products\沙发经典产品价格表.xlsx')
price_map = {}

def normalize_spec(s):
    s = s.strip()
    s = re.sub(r'\s+', '', s)
    s = s.replace('\uff5c', '|').replace('\u4e28', '|')
    return s

for sheet_name in ['\u987e\u5bb6\u7ecf\u5178\u56fa\u5b9a', '\u987e\u5bb6\u7ecf\u5178\u529f\u80fd']:
    ws = wb.Sheets(sheet_name)
    data = ws.Range(ws.Cells(1,1), ws.Cells(ws.UsedRange.Rows.Count, ws.UsedRange.Columns.Count)).Value
    current_code = ''
    for i, row in enumerate(data):
        if i < 3: continue
        c2 = str(row[1]).strip() if row[1] is not None else ''
        c6 = str(row[5]).strip() if row[5] is not None else ''
        c7 = row[6] if row[6] is not None else 0
        if c2 and c2 != '\u8d27\u53f7' and re.match(r'^[\w\.]+$', c2):
            current_code = c2
        if current_code and c6 and c7:
            try: price = float(c7)
            except: price = 0
            if current_code not in price_map:
                price_map[current_code] = {'name': '', 'specs': {}}
            sk = normalize_spec(c6)
            if sk not in price_map[current_code]['specs']:
                price_map[current_code]['specs'][sk] = price

wb.Close()
excel.Quit()
pythoncom.CoUninitialize()

if 'JD.0061' in price_map:
    print('JD.0061 found, specs:', len(price_map['JD.0061']['specs']))
    target = '2.5\u5de6|\u6276\u624b\u7ffb\u6298+1\u53f3'
    if target in price_map['JD.0061']['specs']:
        print(f'EXACT match: {target} = {price_map["JD.0061"]["specs"][target]}')
    else:
        print(f'NOT found: {repr(target)}')
        for k in sorted(price_map['JD.0061']['specs'].keys()):
            if '2.5' in k:
                print(f'  {repr(k)} = {price_map["JD.0061"]["specs"][k]}')
else:
    print('JD.0061 NOT found')
    # Check what codes exist
    codes = [k for k in price_map if 'JD' in k or '0061' in k]
    print(f'Similar codes: {codes[:10]}')
