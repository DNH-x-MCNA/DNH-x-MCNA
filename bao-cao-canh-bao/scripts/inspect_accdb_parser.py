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
    print(strip_accents(msg))

def run_inspect():
    accdb_path = r"D:\DNH\DataTestMCNA.accdb"
    
    if not os.path.exists(accdb_path):
        safe_print(f"Loi: File {accdb_path} khong ton tai!")
        return

    safe_print(f"\n==================================================")
    safe_print(f"INSPECTING ACCESS DB WITH PURE PYTHON PARSER")
    safe_print(f"==================================================")
    
    try:
        from access_parser import AccessParser
    except ImportError:
        safe_print("access-parser is not installed. Installing access-parser...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "access-parser"])
        from access_parser import AccessParser

    try:
        db = AccessParser(accdb_path)
        tables = db.catalog
        safe_print(f"Tables in Access Database: {list(tables)}")
        
        # Show first 5 tables column details and sample data
        for table in list(tables)[:8]:
            safe_print(f"\n--- Table: {table} ---")
            try:
                # parse_table returns a dict where key = col_name, value = list of row values
                table_data = db.parse_table(table)
                columns = list(table_data.keys())
                safe_print(f"Columns: {', '.join(columns)}")
                
                # Check row count
                row_count = 0
                if columns:
                    row_count = len(table_data[columns[0]])
                safe_print(f"Row count: {row_count}")
                
                # Print a sample row if rows exist
                if row_count > 0:
                    safe_print("Sample Row data:")
                    sample_row = {}
                    for col in columns:
                        # get the first row value
                        sample_row[col] = str(table_data[col][0])[:100]
                    safe_print(str(sample_row))
                else:
                    safe_print("Table is empty.")
            except Exception as ex:
                safe_print(f"Could not parse table {table}: {ex}")
                
    except Exception as e:
        safe_print(f"Error parsing Access DB: {e}")

if __name__ == "__main__":
    run_inspect()
