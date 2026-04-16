import psycopg2, os

DB = os.environ.get("DATABASE_URL", "postgresql://postgres:gJMkVUuFkYlIfqGHJZxbrfDOmQdTVOaC@trolley.proxy.rlwy.net:41753/railway")
conn = psycopg2.connect(DB)
cur = conn.cursor()

print("=== TUM SATIN ALMALAR ===")
cur.execute("""
    SELECT id, LOWER(TRIM(email)) as email, content_id, amount, currency,
           device_fp, shopier_order_id, status, created_at
    FROM shopier_purchases
    WHERE status = 'completed'
    ORDER BY created_at DESC
""")
rows = cur.fetchall()
for r in rows:
    print(f"  id={r[0]} email={r[1]} content={r[2]} amount={r[3]} {r[4]} device_fp={r[5][:20] if r[5] else 'NULL'}... order={r[6]} status={r[7]} at={r[8]}")

print(f"\nToplam: {len(rows)} satin alma")

emails = set(r[1] for r in rows if r[1])
print(f"\nBenzersiz email: {len(emails)}")

print("\n=== KULLANICI HESAP ESLESMESI ===")
for em in sorted(emails):
    cur.execute("SELECT id, email, name FROM users WHERE LOWER(TRIM(email)) = %s", (em,))
    user = cur.fetchone()
    purchases = [r for r in rows if r[1] == em]
    contents = [r[2] for r in purchases]
    has_account = "HESAP VAR" if user else "HESAP YOK"
    print(f"  {em} -> {has_account} | Satin almalar: {contents}")

cur.close()
conn.close()
