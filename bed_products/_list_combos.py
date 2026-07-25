"""分析价格表中的组合规格"""
import os, re
import win32com.client as win32, pythoncom

pythoncom.CoInitialize()
excel = win32.Dispatch('Excel.Application')
excel.Visible = False
wb = excel.Workbooks.Open(r'G:\Trae工作文件\顾家产品库\sofa_products\沙发经典产品价格表.xlsx')

# Target products (our sofa_products folders)
target_codes = ['9659','HS.8002','JD.0006','JD.0006B','JD.0020','JD.0021','JD.0036',
                'JD.0061','JD.0062','JD.0069','JD.0072','JD.0077',
                'JD.6012','JD.6013','JD.6015','JD.6016','JD.6025','JD.6172','JD.6188']

for sheet_name in ['顾家经典固定', '顾家经典功能']:
    ws = wb.Sheets(sheet_name)
    data = ws.Range(ws.Cells(1,1), ws.Cells(ws.UsedRange.Rows.Count, ws.UsedRange.Columns.Count)).Value
    current_code = ''
    for i, row in enumerate(data):
        if i < 3: continue
        c2 = str(row[1]).strip() if row[1] is not None else ''
        c4 = str(row[3]).strip() if row[3] is not None else ''
        c6 = str(row[5]).strip() if row[5] is not None else ''
        c7 = row[6] if row[6] is not None else 0
        if c2 and c2 != '货号' and re.match(r'^[\w\.]+$', c2):
            current_code = c2
        if current_code and current_code in target_codes and c6 and c7:
            try: price = float(c7)
            except: price = 0
            actual = round(price * 1.7)
            if '+' in c6:
                print(f"{current_code}|{c6.strip()}|{actual}")

wb.Close(); excel.Quit(); pythoncom.CoUninitialize()
