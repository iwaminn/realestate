#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('data/realestate.db')
cursor = conn.cursor()

# SUUMOの物件を確認
cursor.execute("""
    SELECT id, title, price, layout, area, address, url, source_site
    FROM properties 
    WHERE source_site = 'Suumo'
    ORDER BY id DESC
    LIMIT 10
""")

print("=== SUUMOの最新物件 ===")
for row in cursor.fetchall():
    id, title, price, layout, area, address, url, source_site = row
    print(f"ID: {id}, {title}, {price}万円, {layout}, {area}㎡")
    print(f"  住所: {address}")
    print(f"  URL: {url}")
    print(f"  Source: {source_site}")
    print()

# すべてのソースサイトを確認
cursor.execute("SELECT DISTINCT source_site, COUNT(*) FROM properties GROUP BY source_site")
print("=== ソースサイト別件数 ===")
for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]}件")

conn.close()