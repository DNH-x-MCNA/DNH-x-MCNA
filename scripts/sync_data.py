import sqlite3
import os

SRC_DB = os.path.join(os.path.dirname(__file__), "dnh_sources.db")
DEST_DB = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")

def run_sync():
    print("Bat dau qua trinh ETL dong bo du lieu...")
    
    if not os.path.exists(SRC_DB):
        print(f"Loi: Database nguon {SRC_DB} khong ton tai. Vui long chay mock_sources.py truoc!")
        return
        
    if not os.path.exists(DEST_DB):
        print(f"Loi: Database trung gian {DEST_DB} khong ton tai. Vui long chay init_db.py truoc!")
        return
        
    src_conn = sqlite3.connect(SRC_DB)
    dest_conn = sqlite3.connect(DEST_DB)
    
    src_cursor = src_conn.cursor()
    dest_cursor = dest_conn.cursor()
    
    # 1. Dong bo Nhan vien
    print("Dong bo Danh muc Nhan vien...")
    src_cursor.execute("SELECT emp_id, name, email, phone, region_id FROM bravo_employees")
    emps = src_cursor.fetchall()
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO employees (employee_id, full_name, email, phone, region_id)
    VALUES (?, ?, ?, ?, ?)
    """, emps)
    
    # 2. Dong bo Khach hang
    print("Dong bo Danh muc Khach hang...")
    src_cursor.execute("SELECT cust_id, name, segment, region_id, daily_debt_limit, allowed_debt_days FROM bravo_customers")
    custs = src_cursor.fetchall()
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO customers (customer_id, customer_name, segment, region_id, daily_debt_limit, allowed_debt_days)
    VALUES (?, ?, ?, ?, ?, ?)
    """, custs)
    
    # 3. Dong bo Hop dong ETC
    print("Dong bo Hop dong ETC...")
    src_cursor.execute("SELECT contract_id, contract_number, cust_id, sign_date, total_budget, status FROM bravo_contracts")
    contracts = src_cursor.fetchall()
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO contracts (contract_id, contract_number, customer_id, sign_date, total_budget, status)
    VALUES (?, ?, ?, ?, ?, ?)
    """, contracts)
    
    # 4. Dong bo Phu luc
    print("Dong bo Phu luc Hop dong ETC...")
    src_cursor.execute("SELECT appendix_id, contract_id, appendix_number, sign_date, amount, status FROM bravo_appendices")
    apps = src_cursor.fetchall()
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO appendices (appendix_id, contract_id, appendix_number, sign_date, amount, status)
    VALUES (?, ?, ?, ?, ?, ?)
    """, apps)
    
    # 5. Dong bo Don hang tu B8R2 (Bac, Trung, Nam) va B8R3
    print("Dong bo Don hang tu 3 khay B8R2 (San xuat) va B8R3 (Thuong mai)...")
    
    # Lay tat ca don hang tu Bravo B8R2
    all_orders = []
    
    # Bac
    src_cursor.execute("SELECT order_id, order_code, order_date, cust_id, emp_id, contract_id, total_amount, 'ETC', status FROM bravo_b8r2_bac_production")
    all_orders.extend(src_cursor.fetchall())
    
    # Trung
    src_cursor.execute("SELECT order_id, order_code, order_date, cust_id, emp_id, contract_id, total_amount, 'ETC', status FROM bravo_b8r2_trung_production")
    all_orders.extend(src_cursor.fetchall())
    
    # Nam
    src_cursor.execute("SELECT order_id, order_code, order_date, cust_id, emp_id, contract_id, total_amount, 'ETC', status FROM bravo_b8r2_nam_production")
    all_orders.extend(src_cursor.fetchall())
    
    # B8R3 (Thuong mai)
    src_cursor.execute("""
        SELECT o.order_id, o.order_code, o.order_date, o.cust_id, o.emp_id, NULL, o.total_amount, c.segment, o.status 
        FROM bravo_b8r3_orders o
        LEFT JOIN bravo_customers c ON o.cust_id = c.cust_id
    """)
    all_orders.extend(src_cursor.fetchall())
    
    # Duyet qua don hang, insert vao database trung gian
    # Su dung INSERT OR REPLACE de tranh trung lap ma don hang
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO orders (order_id, order_code, order_date, customer_id, employee_id, contract_id, total_amount, segment, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, all_orders)
    
    # 6. Dong bo Hoa don tu B8R3
    print("Dong bo Hoa don...")
    src_cursor.execute("SELECT invoice_id, invoice_number, invoice_date, order_id, appendix_id, amount, tax_amount, status FROM bravo_b8r3_invoices")
    invs = src_cursor.fetchall()
    dest_cursor.executemany("""
    INSERT OR REPLACE INTO invoices (invoice_id, invoice_number, invoice_date, order_id, appendix_id, amount, tax_amount, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, invs)
    
    # Commit changes
    dest_conn.commit()
    
    # Validate sync result
    dest_cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = dest_cursor.fetchone()[0]
    dest_cursor.execute("SELECT COUNT(*) FROM invoices")
    invoice_count = dest_cursor.fetchone()[0]
    dest_cursor.execute("SELECT COUNT(*) FROM customers")
    cust_count = dest_cursor.fetchone()[0]
    
    print("Dong bo thanh cong!")
    print(f"Thong ke du lieu trung gian:")
    print(f"- Khach hang: {cust_count}")
    print(f"- Don hang dong bo: {order_count} (Gom lich su tren 2 nam)")
    print(f"- Hoa don: {invoice_count}")
    
    src_conn.close()
    dest_conn.close()

if __name__ == "__main__":
    run_sync()
