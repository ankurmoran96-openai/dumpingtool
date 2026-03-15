import sqlite3
import time
from datetime import datetime, timedelta
from config import DATABASE_PATH

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # User Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            expiry INTEGER
        )
    ''')
    
    # Keys Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            duration_days INTEGER,
            is_used INTEGER DEFAULT 0,
            used_by INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

def add_key(key, duration_days):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO keys (key, duration_days) VALUES (?, ?)', (key, duration_days))
    conn.commit()
    conn.close()

def redeem_key(user_id, username, key):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT duration_days FROM keys WHERE key = ? AND is_used = 0', (key,))
    result = cursor.fetchone()
    
    if result:
        duration_days = result[0]
        # Calculate new expiry
        cursor.execute('SELECT expiry FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        now = int(time.time())
        if user and user[0] > now:
            new_expiry = user[0] + (duration_days * 86400)
        else:
            new_expiry = now + (duration_days * 86400)
            
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, expiry) VALUES (?, ?, ?)', (user_id, username, new_expiry))
        cursor.execute('UPDATE keys SET is_used = 1, used_by = ? WHERE key = ?', (user_id, key))
        conn.commit()
        conn.close()
        return True, new_expiry
    
    conn.close()
    return False, None

def is_subscribed(user_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT expiry FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        expiry = result[0]
        if expiry > int(time.time()):
            return True, expiry
    return False, None

def get_all_keys():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT key, duration_days, is_used FROM keys')
    result = cursor.fetchall()
    conn.close()
    return result
