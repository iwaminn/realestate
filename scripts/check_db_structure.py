#!/usr/bin/env python3
"""データベース構造確認"""

import sqlite3

conn = sqlite3.connect('realestate.db')
cursor = conn.cursor()

print("=== Properties table structure ===")
cursor.execute('PRAGMA table_info(properties)')
columns = cursor.fetchall()
for i, col in enumerate(columns):
    print(f"{i}: {col[1]} ({col[2]})")

print("\n=== Sample query result ===")
cursor.execute('''
    SELECT p.*, a.prefecture_name, a.ward_name
    FROM properties p
    JOIN areas a ON p.area_id = a.id
    LIMIT 1
''')

result = cursor.fetchone()
if result:
    print(f"Number of columns: {len(result)}")
    for i, val in enumerate(result):
        print(f"{i}: {val}")
else:
    print("No data found")

conn.close()