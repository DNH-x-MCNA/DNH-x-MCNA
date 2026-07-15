import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), "dnh_sources.db")

def create_mock_sources():
    print(f"Khoi tao database nguon mo phang tai: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Danh muc Nhan vien Bravo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_employees (
        emp_id VARCHAR(20) PRIMARY KEY,
        name NVARCHAR(100) NOT NULL,
        email VARCHAR(100),
        phone VARCHAR(20),
        region_id VARCHAR(10)
    );
    """)

    # 2. Danh muc Khach hang Bravo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_customers (
        cust_id VARCHAR(20) PRIMARY KEY,
        name NVARCHAR(200) NOT NULL,
        segment VARCHAR(10) CHECK(segment IN ('OTC', 'ETC')),
        region_id VARCHAR(10),
        daily_debt_limit REAL DEFAULT 0,
        allowed_debt_days INT DEFAULT 30
    );
    """)

    # 3. Hop dong ETC Bravo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_contracts (
        contract_id VARCHAR(20) PRIMARY KEY,
        contract_number VARCHAR(50) UNIQUE NOT NULL,
        cust_id VARCHAR(20),
        sign_date DATE NOT NULL,
        total_budget REAL NOT NULL,
        status NVARCHAR(50) DEFAULT 'Hieu luc',
        FOREIGN KEY (cust_id) REFERENCES bravo_customers(cust_id)
    );
    """)

    # 4. Phu luc Hop dong ETC Bravo
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_appendices (
        appendix_id VARCHAR(20) PRIMARY KEY,
        contract_id VARCHAR(20),
        appendix_number VARCHAR(50) NOT NULL,
        sign_date DATE NOT NULL,
        amount REAL NOT NULL,
        status NVARCHAR(50) DEFAULT 'Chua thuc hien',
        FOREIGN KEY (contract_id) REFERENCES bravo_contracts(contract_id)
    );
    """)

    # 5. Bravo B8R2 - San xuat - Chia theo 3 khay/mien (Bac, Trung, Nam)
    # B8R2 Bac
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_b8r2_bac_production (
        order_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) UNIQUE NOT NULL,
        order_date DATE NOT NULL,
        cust_id VARCHAR(20),
        emp_id VARCHAR(20),
        contract_id VARCHAR(20) NULL,
        total_amount REAL NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (cust_id) REFERENCES bravo_customers(cust_id),
        FOREIGN KEY (emp_id) REFERENCES bravo_employees(emp_id),
        FOREIGN KEY (contract_id) REFERENCES bravo_contracts(contract_id)
    );
    """)

    # B8R2 Trung
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_b8r2_trung_production (
        order_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) UNIQUE NOT NULL,
        order_date DATE NOT NULL,
        cust_id VARCHAR(20),
        emp_id VARCHAR(20),
        contract_id VARCHAR(20) NULL,
        total_amount REAL NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (cust_id) REFERENCES bravo_customers(cust_id),
        FOREIGN KEY (emp_id) REFERENCES bravo_employees(emp_id),
        FOREIGN KEY (contract_id) REFERENCES bravo_contracts(contract_id)
    );
    """)

    # B8R2 Nam
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_b8r2_nam_production (
        order_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) UNIQUE NOT NULL,
        order_date DATE NOT NULL,
        cust_id VARCHAR(20),
        emp_id VARCHAR(20),
        contract_id VARCHAR(20) NULL,
        total_amount REAL NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (cust_id) REFERENCES bravo_customers(cust_id),
        FOREIGN KEY (emp_id) REFERENCES bravo_employees(emp_id),
        FOREIGN KEY (contract_id) REFERENCES bravo_contracts(contract_id)
    );
    """)

    # 6. Bravo B8R3 - Thuong mai (Don hang & Hoa don)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_b8r3_orders (
        order_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) UNIQUE NOT NULL,
        order_date DATE NOT NULL,
        cust_id VARCHAR(20),
        emp_id VARCHAR(20),
        total_amount REAL NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (cust_id) REFERENCES bravo_customers(cust_id),
        FOREIGN KEY (emp_id) REFERENCES bravo_employees(emp_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bravo_b8r3_invoices (
        invoice_id VARCHAR(20) PRIMARY KEY,
        invoice_number VARCHAR(50) UNIQUE NOT NULL,
        invoice_date DATE NOT NULL,
        order_id VARCHAR(20),
        appendix_id VARCHAR(20) NULL,
        amount REAL NOT NULL,
        tax_amount REAL NOT NULL,
        status NVARCHAR(50) -- 'Da phat hanh', 'Da thanh toan'
    );
    """)

    # 7. Database DMS (San xuat & Thuong mai)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dms_orders (
        dms_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) NOT NULL,
        order_date DATE NOT NULL,
        cust_id VARCHAR(20),
        emp_id VARCHAR(20),
        total_amount REAL NOT NULL,
        segment VARCHAR(10),
        status NVARCHAR(50)
    );
    """)

    # --- CHEN DU LIEU MAU ---
    # Nhan vien
    employees_data = [
        ("EMP001", "Nguyen Van A", "a.nv@namhapharma.com", "0912345678", "BAC"),
        ("EMP002", "Tran Thi B", "b.tt@namhapharma.com", "0987654321", "BAC"),
        ("EMP003", "Le Van C", "c.lv@namhapharma.com", "0905123456", "TRUNG"),
        ("EMP004", "Pham Minh D", "d.pm@namhapharma.com", "0934567890", "NAM"),
        ("EMP005", "Hoang Ngoc E", "e.hn@namhapharma.com", "0977889900", "NAM")
    ]
    cursor.executemany("INSERT OR REPLACE INTO bravo_employees VALUES (?,?,?,?,?)", employees_data)

    # Khach hang (OTC & ETC)
    customers_data = [
        ("CUST001", "Nha Thuoc Long Chau 1", "OTC", "BAC", 50000000.0, 15), # Hạn mức công nợ 50tr, nợ 15 ngày
        ("CUST002", "Nha Thuoc An Khang 2", "OTC", "NAM", 70000000.0, 20),
        ("CUST003", "Benh Vien Bach Mai", "ETC", "BAC", 500000000.0, 60), # ETC - BV Bạch Mai
        ("CUST004", "Benh Vien Cho Ray", "ETC", "NAM", 800000000.0, 60),  # ETC - BV Chợ Rẫy
        ("CUST005", "Nha Thuoc Tay Trung Bo", "OTC", "TRUNG", 30000000.0, 10),
        ("CUST006", "Benh Vien Trung Uong Hue", "ETC", "TRUNG", 400000000.0, 45)
    ]
    cursor.executemany("INSERT OR REPLACE INTO bravo_customers VALUES (?,?,?,?,?,?)", customers_data)

    # Hop dong ETC
    contracts_data = [
        ("CTR001", "HD-BM-2024-01", "CUST003", "2024-01-10", 2000000000.0, "Hieu luc"),
        ("CTR002", "HD-CR-2024-02", "CUST004", "2024-02-15", 3000000000.0, "Hieu luc"),
        ("CTR003", "HD-TWH-2025-01", "CUST006", "2025-01-05", 1500000000.0, "Hieu luc")
    ]
    cursor.executemany("INSERT OR REPLACE INTO bravo_contracts VALUES (?,?,?,?,?,?)", contracts_data)

    # Phu luc Hop dong ETC
    appendices_data = [
        ("APX001", "CTR001", "PL-BM-01", "2024-02-01", 500000000.0, "Da hoan thanh"),
        ("APX002", "CTR001", "PL-BM-02", "2024-08-01", 500000000.0, "Da hoan thanh"),
        ("APX003", "CTR001", "PL-BM-03", "2025-03-01", 1000000000.0, "Dang thuc hien"),
        ("APX004", "CTR002", "PL-CR-01", "2024-03-15", 1000000000.0, "Da hoan thanh"),
        ("APX005", "CTR002", "PL-CR-02", "2025-05-15", 2000000000.0, "Dang thuc hien"),
        ("APX006", "CTR003", "PL-TWH-01", "2025-02-01", 1500000000.0, "Dang thuc hien")
    ]
    cursor.executemany("INSERT OR REPLACE INTO bravo_appendices VALUES (?,?,?,?,?,?)", appendices_data)

    # Tao du lieu don hang lich su trong vong hon 2 nam (tu dau 2024 den nay - giua 2026)
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2026, 6, 28)
    delta_days = (end_date - start_date).days

    orders_b8r2_bac = []
    orders_b8r2_trung = []
    orders_b8r2_nam = []
    orders_b8r3 = []
    invoices_b8r3 = []
    dms_orders_data = []

    # Map details to make it easy to generate
    etc_contracts = {
        "CUST003": ("CTR001", ["APX001", "APX002", "APX003"]),
        "CUST004": ("CTR002", ["APX004", "APX005"]),
        "CUST006": ("CTR003", ["APX006"])
    }

    # Sinh don hang ngau nhien
    order_idx = 1
    invoice_idx = 1
    
    for i in range(250): # 250 don hang
        days_offset = random.randint(0, delta_days)
        order_date = start_date + timedelta(days=days_offset)
        order_date_str = order_date.strftime("%Y-%m-%d")
        
        cust = random.choice(customers_data)
        cust_id, cust_name, segment, region, limit, days = cust
        
        # Chon nhan vien thuoc mien do
        miennv = [e for e in employees_data if e[4] == region]
        emp = random.choice(miennv)
        emp_id = emp[0]
        
        amount = round(random.uniform(5000000, 150000000), 2)
        status = random.choice(["Da giao", "Da duyet"])
        
        # Chon contract neu la ETC
        contract_id = None
        appendix_id = None
        if segment == 'ETC' and cust_id in etc_contracts:
            contract_id, app_ids = etc_contracts[cust_id]
            appendix_id = random.choice(app_ids)
            amount = round(random.uniform(100000000, 400000000), 2) # don ETC thuong to hon

        order_id = f"ORD{order_idx:04d}"
        order_code = f"DH-{region}-{order_date.strftime('%y%m%d')}-{order_idx}"
        
        # Chia vao cac bang nguon
        # Bravo B8R2 - San xuat (San pham tu san xuat thau hoac ban thuong mai san xuat)
        is_production = random.choice([True, False])
        
        if is_production:
            if region == "BAC":
                orders_b8r2_bac.append((order_id, order_code, order_date_str, cust_id, emp_id, contract_id, amount, status))
            elif region == "TRUNG":
                orders_b8r2_trung.append((order_id, order_code, order_date_str, cust_id, emp_id, contract_id, amount, status))
            else:
                orders_b8r2_nam.append((order_id, order_code, order_date_str, cust_id, emp_id, contract_id, amount, status))
        else:
            # Bravo B8R3 - Thuong mai
            orders_b8r3.append((order_id, order_code, order_date_str, cust_id, emp_id, amount, status))
            
            # Xuat hoa don cho don hang thuong mai
            if status == "Da giao":
                inv_id = f"INV{invoice_idx:04d}"
                inv_code = f"HD-TM-{order_date.strftime('%y%m%d')}-{invoice_idx}"
                tax = round(amount * 0.1, 2)
                inv_status = random.choice(["Da phat hanh", "Da thanh toan"])
                # Gia lap hoa don bi qua han neu date cach day xa ma trang thai van Da phat hanh (chua thanh toan)
                invoices_b8r3.append((inv_id, inv_code, order_date_str, order_id, appendix_id, amount, tax, inv_status))
                invoice_idx += 1
                
        # DMS luu ca san xuat va thuong mai (dong bo tu he thong handheld)
        dms_orders_data.append((f"DMS{order_idx:04d}", order_code, order_date_str, cust_id, emp_id, amount, segment, status))
        order_idx += 1

    # Chen du lieu vao cac bang nguon
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r2_bac_production VALUES (?,?,?,?,?,?,?,?)", orders_b8r2_bac)
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r2_trung_production VALUES (?,?,?,?,?,?,?,?)", orders_b8r2_trung)
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r2_nam_production VALUES (?,?,?,?,?,?,?,?)", orders_b8r2_nam)
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r3_orders VALUES (?,?,?,?,?,?,?)", orders_b8r3)
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r3_invoices VALUES (?,?,?,?,?,?,?,?)", invoices_b8r3)
    cursor.executemany("INSERT OR REPLACE INTO dms_orders VALUES (?,?,?,?,?,?,?,?)", dms_orders_data)

    # Gia lap them hoa don cho san xuat (trong Bravo B8R3 cung co ghi nhan hoa don SX thau)
    # Lay cac don hang ETC tu B8R2 da giao de tao hoa don trong B8R3
    etc_invoices = []
    cursor.execute("""
    SELECT order_id, order_code, order_date, cust_id, contract_id, total_amount FROM bravo_b8r2_bac_production WHERE contract_id IS NOT NULL
    UNION ALL
    SELECT order_id, order_code, order_date, cust_id, contract_id, total_amount FROM bravo_b8r2_trung_production WHERE contract_id IS NOT NULL
    UNION ALL
    SELECT order_id, order_code, order_date, cust_id, contract_id, total_amount FROM bravo_b8r2_nam_production WHERE contract_id IS NOT NULL
    """)
    prod_etc_orders = cursor.fetchall()
    
    for o_id, o_code, o_date, c_id, ctr_id, amt in prod_etc_orders:
        app_ids = etc_contracts[c_id][1]
        app_id = random.choice(app_ids)
        inv_id = f"INV{invoice_idx:04d}"
        inv_code = f"HD-SX-{o_id[3:]}"
        tax = round(amt * 0.05, 2) # Thuoc thau thue 5%
        # Gia lap trang thai thanh toan: nhung hoa don qua han (>45 hoac >60 ngay) co the chua thanh toan
        inv_date = datetime.strptime(o_date, "%Y-%m-%d")
        today = datetime.now()
        days_diff = (today - inv_date).days
        
        if days_diff > 90:
            inv_status = random.choice(["Da thanh toan", "Da thanh toan", "Da phat hanh"]) # Phan lon da thanh toan
        else:
            inv_status = random.choice(["Da phat hanh", "Da thanh toan"])
            
        etc_invoices.append((inv_id, inv_code, o_date, o_id, app_id, amt, tax, inv_status))
        invoice_idx += 1
        
    cursor.executemany("INSERT OR REPLACE INTO bravo_b8r3_invoices VALUES (?,?,?,?,?,?,?,?)", etc_invoices)

    # Rieng khach hang CUST001 va CUST005 gia lap vuot han muc cong no ngay tai thoi diem hien tai
    # Tao 1 hoa don to chua thanh toan ngay hom nay/hom qua
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # CUST001: Hạn mức 50tr, tao hoa don 65tr chưa thanh toán hôm nay
    cursor.execute("INSERT OR REPLACE INTO bravo_b8r3_orders VALUES ('ORD9999', 'DH-BAC-SPECIAL-1', ?, 'CUST001', 'EMP001', 65000000.0, 'Da giao')", (today_str,))
    cursor.execute("INSERT OR REPLACE INTO bravo_b8r3_invoices VALUES ('INV9999', 'HD-SPECIAL-CUST001', ?, 'ORD9999', NULL, 65000000.0, 6500000.0, 'Da phat hanh')", (today_str,))

    # CUST005: Hạn mức 30tr, tạo hóa đơn quá hạn 40 ngày (allowed_debt_days=10)
    past_date_str = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
    cursor.execute("INSERT OR REPLACE INTO bravo_b8r3_orders VALUES ('ORD9998', 'DH-TRUNG-SPECIAL-2', ?, 'CUST005', 'EMP003', 35000000.0, 'Da giao')", (past_date_str,))
    cursor.execute("INSERT OR REPLACE INTO bravo_b8r3_invoices VALUES ('INV9998', 'HD-SPECIAL-CUST005', ?, 'ORD9998', NULL, 35000000.0, 3500000.0, 'Da phat hanh')", (past_date_str,))

    conn.commit()
    conn.close()
    print("Tao du lieu nguon mo phang thanh cong!")

if __name__ == "__main__":
    create_mock_sources()
