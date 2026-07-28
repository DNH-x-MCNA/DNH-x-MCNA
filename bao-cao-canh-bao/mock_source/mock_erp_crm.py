import sqlite3
import os
import random
from datetime import datetime, timedelta

MOCK_DIR = os.path.dirname(os.path.abspath(__file__))
ERP_DB = os.path.join(MOCK_DIR, 'erp.db')
CRM_DB = os.path.join(MOCK_DIR, 'crm.db')

def init_databases():
    os.makedirs(MOCK_DIR, exist_ok=True)
    
    # Initialize ERP Database
    conn_erp = sqlite3.connect(ERP_DB)
    cursor_erp = conn_erp.cursor()
    
    cursor_erp.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            sku TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor_erp.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            amount REAL NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    
    # Seed ERP Inventory
    items = [
        ("Laptop Dell XPS", "LAP-DELL-XPS", 100),
        ("iPhone 15 Pro", "MOB-IPHONE-15", 80),
        ("Samsung Monitor 27", "MON-SAMP-27", 15), # Trigger alert on start? Let's seed normal
        ("Logitech MX Master 3", "ACC-LOGI-MX3", 120),
        ("Mechanical Keyboard", "ACC-MECH-KB", 10) # Starts low to test trigger
    ]
    
    for name, sku, qty in items:
        cursor_erp.execute('''
            INSERT INTO inventory (item_name, sku, quantity, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET quantity=excluded.quantity, updated_at=excluded.updated_at
        ''', (name, sku, qty, datetime.now()))
        
    # Seed ERP Orders (mostly completed)
    now = datetime.now()
    for i in range(20):
        order_date = now - timedelta(hours=random.randint(1, 24))
        status = 'Completed' if random.random() > 0.1 else 'Failed'
        cursor_erp.execute('''
            INSERT INTO orders (customer_id, order_date, amount, status)
            VALUES (?, ?, ?, ?)
        ''', (random.randint(1000, 9999), order_date, round(random.uniform(10, 1000), 2), status))
        
    conn_erp.commit()
    conn_erp.close()
    
    # Initialize CRM Database
    conn_crm = sqlite3.connect(CRM_DB)
    cursor_crm = conn_crm.cursor()
    
    cursor_crm.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Seed CRM Support Tickets (mostly resolved/low priority)
    for i in range(10):
        created_at = now - timedelta(hours=random.randint(1, 48))
        status = 'Resolved' if random.random() > 0.4 else 'Open'
        priority = random.choice(['Low', 'Medium', 'High'])
        cursor_crm.execute('''
            INSERT INTO support_tickets (customer_id, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (random.randint(1000, 9999), priority, status, created_at, created_at + timedelta(hours=1)))
        
    conn_crm.commit()
    conn_crm.close()
    print("Mock databases initialized successfully.")

def trigger_low_inventory():
    conn = sqlite3.connect(ERP_DB)
    cursor = conn.cursor()
    # Update Laptop Dell XPS to quantity 12 (below threshold 20)
    cursor.execute('''
        UPDATE inventory 
        SET quantity = 12, updated_at = ? 
        WHERE sku = 'LAP-DELL-XPS'
    ''', (datetime.now(),))
    conn.commit()
    conn.close()
    print("[MOCK] Triggered: Laptop Dell XPS inventory is now 12 (Low Inventory Alert).")

def trigger_failed_orders():
    conn = sqlite3.connect(ERP_DB)
    cursor = conn.cursor()
    # Insert 6 failed orders in the last hour
    now = datetime.now()
    for _ in range(6):
        cursor.execute('''
            INSERT INTO orders (customer_id, order_date, amount, status)
            VALUES (?, ?, ?, ?)
        ''', (random.randint(1000, 9999), now - timedelta(minutes=random.randint(1, 45)), round(random.uniform(50, 500), 2), 'Failed'))
    conn.commit()
    conn.close()
    print("[MOCK] Triggered: 6 new Failed orders added in the last hour (Failed Orders Alert).")

def trigger_crm_overload():
    conn = sqlite3.connect(CRM_DB)
    cursor = conn.cursor()
    # Insert 4 urgent/high priority open support tickets
    now = datetime.now()
    for _ in range(4):
        cursor.execute('''
            INSERT INTO support_tickets (customer_id, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (random.randint(1000, 9999), 'Urgent', 'Open', now, now))
    conn.commit()
    conn.close()
    print("[MOCK] Triggered: 4 open Urgent tickets added (CRM SLA Overload Alert).")

def add_normal_order():
    conn = sqlite3.connect(ERP_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (customer_id, order_date, amount, status)
        VALUES (?, ?, ?, ?)
    ''', (random.randint(1000, 9999), datetime.now(), round(random.uniform(50, 500), 2), 'Completed'))
    conn.commit()
    conn.close()
    print("[MOCK] Added 1 Completed Order.")

if __name__ == '__main__':
    init_databases()
    # If run with arguments, we can trigger events
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'low_inventory':
            trigger_low_inventory()
        elif cmd == 'failed_orders':
            trigger_failed_orders()
        elif cmd == 'crm_overload':
            trigger_crm_overload()
        elif cmd == 'normal_order':
            add_normal_order()
