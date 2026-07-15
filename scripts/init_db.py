import sqlite3
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "dnh_intermediate.db")

def init_intermediate_db():
    print(f"Khoi tao Database trung gian tai: {DB_FILE}")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print("Da xoa Database trung gian cu.")
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Bieu vung mien
    cursor.execute("""
    CREATE TABLE regions (
        region_id VARCHAR(10) PRIMARY KEY,
        region_name NVARCHAR(50) NOT NULL
    );
    """)
    
    # 2. Bieu Nhan vien
    cursor.execute("""
    CREATE TABLE employees (
        employee_id VARCHAR(20) PRIMARY KEY,
        full_name NVARCHAR(100) NOT NULL,
        email VARCHAR(100),
        phone VARCHAR(20),
        region_id VARCHAR(10),
        FOREIGN KEY (region_id) REFERENCES regions(region_id)
    );
    """)
    
    # 3. Bieu Khach hang
    cursor.execute("""
    CREATE TABLE customers (
        customer_id VARCHAR(20) PRIMARY KEY,
        customer_name NVARCHAR(200) NOT NULL,
        segment VARCHAR(10) CHECK (segment IN ('OTC', 'ETC')),
        region_id VARCHAR(10),
        daily_debt_limit DECIMAL(18, 2) DEFAULT 0,
        allowed_debt_days INT DEFAULT 30,
        FOREIGN KEY (region_id) REFERENCES regions(region_id)
    );
    """)
    
    # 4. Bieu Hop dong ETC
    cursor.execute("""
    CREATE TABLE contracts (
        contract_id VARCHAR(20) PRIMARY KEY,
        contract_number VARCHAR(50) UNIQUE NOT NULL,
        customer_id VARCHAR(20),
        sign_date DATE NOT NULL,
        total_budget DECIMAL(18, 2) NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );
    """)
    
    # 5. Bieu Phu luc hop dong ETC
    cursor.execute("""
    CREATE TABLE appendices (
        appendix_id VARCHAR(20) PRIMARY KEY,
        contract_id VARCHAR(20),
        appendix_number VARCHAR(50) NOT NULL,
        sign_date DATE NOT NULL,
        amount DECIMAL(18, 2) NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
    );
    """)
    
    # 6. Bieu Don hang
    cursor.execute("""
    CREATE TABLE orders (
        order_id VARCHAR(20) PRIMARY KEY,
        order_code VARCHAR(50) UNIQUE NOT NULL,
        order_date DATE NOT NULL,
        customer_id VARCHAR(20),
        employee_id VARCHAR(20),
        contract_id VARCHAR(20) NULL,
        total_amount DECIMAL(18, 2) NOT NULL,
        segment VARCHAR(10) CHECK (segment IN ('OTC', 'ETC')),
        status NVARCHAR(50),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
        FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
    );
    """)
    
    # 7. Bieu Hoa don
    cursor.execute("""
    CREATE TABLE invoices (
        invoice_id VARCHAR(20) PRIMARY KEY,
        invoice_number VARCHAR(50) UNIQUE NOT NULL,
        invoice_date DATE NOT NULL,
        order_id VARCHAR(20),
        appendix_id VARCHAR(20) NULL,
        amount DECIMAL(18, 2) NOT NULL,
        tax_amount DECIMAL(18, 2) NOT NULL,
        status NVARCHAR(50),
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
        FOREIGN KEY (appendix_id) REFERENCES appendices(appendix_id)
    );
    """)
    
    # Chen danh muc vung mien co dinh
    regions_data = [
        ("BAC", "Mien Bac"),
        ("TRUNG", "Mien Trung"),
        ("NAM", "Mien Nam")
    ]
    cursor.executemany("INSERT INTO regions VALUES (?, ?)", regions_data)
    
    conn.commit()
    conn.close()
    print("Khoi tao Database trung gian hoan tat!")

if __name__ == "__main__":
    init_intermediate_db()
