import os
import sqlite3
import time
from pathlib import Path

def seed():
    path = Path(os.getenv('SQLITE_PATH', 'data/warehouse.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers(customer_id INTEGER PRIMARY KEY, name TEXT, region TEXT, signup_date TEXT);
        CREATE TABLE IF NOT EXISTS orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, order_date TEXT, status TEXT);
        INSERT OR IGNORE INTO customers VALUES (1,'Acme','North','2025-01-10'),(2,'Birch','South','2025-02-12'),(3,'Cedar','North','2025-03-20');
        INSERT OR IGNORE INTO orders VALUES (1,1,125.0,'2025-04-01','completed'),(2,2,240.0,'2025-04-03','completed'),(3,1,80.0,'2025-05-01','completed'),(4,3,70.0,'2025-05-04','pending');
        """)

def execute(sql):
    if os.getenv('WAREHOUSE', 'sqlite') == 'snowflake':
        import snowflake.connector
        # The configured role MUST have SELECT only on approved tables, no UDF execution or write grants.
        kwargs = {key.lower():os.environ['SNOWFLAKE_' + key] for key in
                  ['ACCOUNT','USER','PASSWORD','ROLE','WAREHOUSE','DATABASE','SCHEMA']}
        with snowflake.connector.connect(**kwargs, login_timeout=15,
                session_parameters={'STATEMENT_TIMEOUT_IN_SECONDS':15, 'STATEMENT_QUEUED_TIMEOUT_IN_SECONDS':10}) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, timeout=15)
                return {'columns':[c[0] for c in cursor.description], 'rows':cursor.fetchmany(200)}
    path = Path(os.getenv('SQLITE_PATH', 'data/warehouse.db')).resolve()
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        conn.execute('PRAGMA query_only=ON')
        deadline = time.monotonic() + 3
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        cursor = conn.execute(sql)
        return {'columns':[c[0] for c in cursor.description], 'rows':cursor.fetchmany(200)}
    finally:
        conn.close()

if __name__ == '__main__':
    seed()
    print('Seeded synthetic warehouse')
