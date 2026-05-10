import sqlite3
import bcrypt
conn = sqlite3.connect('var/data/shim_internal.db')
c = conn.cursor()
c.execute("SELECT user_id, password FROM users WHERE user_id='admin'")
res = c.fetchone()
print(bcrypt.checkpw(b'admin', res[1].encode('utf-8')))
print(bcrypt.checkpw(b'000', res[1].encode('utf-8')))
print(bcrypt.checkpw(b'0000', res[1].encode('utf-8')))
