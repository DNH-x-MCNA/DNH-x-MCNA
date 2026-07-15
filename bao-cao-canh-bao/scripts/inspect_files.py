import os
import sys

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
    # Strip accents for Windows console printing
    print(strip_accents(msg))

def inspect_excel(file_path):
    safe_print(f"\n==================================================")
    safe_print(f"INSPECTING EXCEL FILE: {os.path.basename(file_path)}")
    safe_print(f"==================================================")
    try:
        import pandas as pd
    except ImportError:
        safe_print("Pandas is not installed. Installing pandas and openpyxl...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas", "openpyxl"])
        import pandas as pd

    try:
        # Load excel file metadata
        xl = pd.ExcelFile(file_path)
        safe_print(f"Sheet names in file: {xl.sheet_names}")
        
        for sheet in xl.sheet_names[:3]: # inspect first 3 sheets max to prevent too long output
            safe_print(f"\n--- Sheet: {sheet} ---")
            # Read header and first few rows
            df = pd.read_excel(file_path, sheet_name=sheet, nrows=5)
            safe_print(f"Dimensions (estimated rows, columns): ({df.shape[0]} loaded rows, {df.shape[1]} columns)")
            safe_print("Columns and Types:")
            for col in df.columns:
                safe_print(f"  - {col}: (Type: {df[col].dtype})")
            safe_print("Sample data (first 2 rows):")
            sample_str = df.head(2).to_string()
            safe_print(sample_str)
    except Exception as e:
        safe_print(f"Error inspecting {file_path}: {e}")

def inspect_accdb(file_path):
    safe_print(f"\n==================================================")
    safe_print(f"INSPECTING ACCESS DB: {os.path.basename(file_path)}")
    safe_print(f"==================================================")
    
    try:
        import pyodbc
    except ImportError:
        safe_print("pyodbc is not installed. Installing pyodbc...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyodbc"])
        try:
            import pyodbc
        except ImportError:
            safe_print("Could not import pyodbc after installation.")
            return

    # Connection string for Access DB
    conn_str = (
        r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
        f'DBQ={file_path};'
    )
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Get list of tables
        tables = []
        for row in cursor.tables():
            if row.table_type == "TABLE":
                tables.append(row.table_name)
                
        safe_print(f"User tables in Access Database: {tables}")
        
        for table in tables[:8]: # inspect first 8 tables
            safe_print(f"\n--- Table: {table} ---")
            try:
                cursor.execute(f"SELECT TOP 1 * FROM [{table}]")
                columns = [column[0] for column in cursor.description]
                safe_print(f"Columns: {', '.join(columns)}")
                
                # Fetch a sample row
                row = cursor.fetchone()
                if row:
                    safe_print("Sample Row data:")
                    # Convert row to dict-like
                    row_dict = {}
                    for col, val in zip(columns, row):
                        row_dict[col] = str(val)[:100] # truncate long strings
                    safe_print(str(row_dict))
                else:
                    safe_print("Table is empty.")
            except Exception as ex:
                safe_print(f"Could not inspect table {table}: {ex}")
                
        conn.close()
    except Exception as e:
        safe_print(f"Error connecting to Access Database: {e}")
        safe_print("\nNote: Neu pyodbc error 'Driver not found', can tai va cai dat 'Microsoft Access Database Engine' tu Microsoft.")

if __name__ == "__main__":
    base_dir = r"D:\DNH"
    excel_files = [
        "1. Báo cáo tồn kho thành phẩm 16.01.2026.xlsx",
        "2. Data Phai thu tổng hợp SX&TM 16.01.26.xlsx",
        "3. Báo cáo công nợ phải thu Nam Hà TM_16.01.2026.xlsx",
        "Báo cáo KPI lương kinh doanh_MN.xlsx"
    ]
    accdb_file = "DataTestMCNA.accdb"
    
    for f in excel_files:
        path = os.path.join(base_dir, f)
        if os.path.exists(path):
            inspect_excel(path)
            
    accdb_path = os.path.join(base_dir, accdb_file)
    if os.path.exists(accdb_path):
        inspect_accdb(accdb_path)
