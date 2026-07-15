import os
import pandas as pd

def strip_accents(s):
    accents_map = {
        'a': 'áàảãạăắằẳẵặâấầẩẫậ',
        'A': 'ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬ',
        'd': 'đ',
        'D': 'Đ',
        'e': 'éèẻẽẹêếềểễệ',
        'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
        'i': 'íìỉĩị',
        'I': 'ÍÌỈĨỊ',
        'o': 'óòỏõọôốồổỗộơớờởỡợ',
        'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
        'u': 'úùủũụưứừửữự',
        'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
        'y': 'ýỳỷỹỵ',
        'Y': 'ÝỲỶỸỴ'
    }
    res = str(s)
    for r, chars in accents_map.items():
        for c in chars:
            res = res.replace(c, r)
    return res

def safe_print(msg):
    print(strip_accents(msg))

def check_all_files():
    base_dir = r"D:\DNH"
    files = [
        "1. Báo cáo tồn kho thành phẩm 16.01.2026.xlsx",
        "2. Data Phai thu tổng hợp SX&TM 16.01.26.xlsx",
        "3. Báo cáo công nợ phải thu Nam Hà TM_16.01.2026.xlsx",
        "Báo cáo KPI lương kinh doanh_MN.xlsx"
    ]
    
    for f in files:
        path = os.path.join(base_dir, f)
        if not os.path.exists(path):
            safe_print(f"File {f} does not exist.")
            continue
            
        safe_print(f"\n=========================================")
        safe_print(f"FILE: {f}")
        safe_print(f"=========================================")
        xl = pd.ExcelFile(path)
        for sheet in xl.sheet_names:
            try:
                df = pd.read_excel(path, sheet_name=sheet, nrows=2)
                cols = [str(c) for c in df.columns]
                safe_print(f"Sheet: '{sheet}' -> Columns: {cols}")
            except Exception as e:
                safe_print(f"Sheet: '{sheet}' -> Error: {e}")

if __name__ == "__main__":
    check_all_files()
