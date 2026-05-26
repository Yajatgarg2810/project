# view_users.py
import sqlite3

def view_all_users():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row  # This enables column access by name
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    
    print("\n=== ALL REGISTERED USERS ===")
    print(f"{'ID':<4} {'Email':<25} {'Username':<15} {'Is Admin':<8}")
    print("-" * 60)
    
    for user in users:
        print(f"{user['id']:<4} {user['email']:<25} {user['username']:<15} {bool(user['is_admin']):<8}")
    
    conn.close()

if __name__ == '__main__':
    view_all_users()