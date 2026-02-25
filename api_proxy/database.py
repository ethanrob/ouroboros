"""
SQLite database for tracking API usage per key.
Simple: api_key -> cumulative_cost, requests_count, last_used_at.
"""

import sqlite3
from datetime import datetime
from typing import Optional, Tuple
import os


class UsageDB:
    """Simple usage tracking database."""
    
    def __init__(self, db_path: str = "api_usage.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cumulative_cost REAL DEFAULT 0.0,
                requests_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                daily_limit_usd REAL DEFAULT 100.0,
                notes TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                cost_usd REAL,
                FOREIGN KEY (api_key) REFERENCES api_keys(api_key)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_or_create_key(self, api_key: str) -> bool:
        """Create API key if it doesn't exist. Return True if created, False if exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT api_key FROM api_keys WHERE api_key = ?", (api_key,))
        exists = cursor.fetchone() is not None
        
        if not exists:
            cursor.execute("""
                INSERT INTO api_keys (api_key, cumulative_cost, requests_count)
                VALUES (?, 0.0, 0)
            """, (api_key,))
            conn.commit()
        
        conn.close()
        return not exists
    
    def is_key_valid(self, api_key: str) -> bool:
        """Check if API key is valid and active."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT is_active FROM api_keys WHERE api_key = ? AND is_active = 1",
            (api_key,)
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def log_usage(
        self,
        api_key: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float
    ) -> None:
        """Log a request and update cumulative cost."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Add to log
        cursor.execute("""
            INSERT INTO usage_log (api_key, model, prompt_tokens, completion_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?)
        """, (api_key, model, prompt_tokens, completion_tokens, cost_usd))
        
        # Update cumulative
        cursor.execute("""
            UPDATE api_keys
            SET cumulative_cost = cumulative_cost + ?,
                requests_count = requests_count + 1,
                last_used_at = CURRENT_TIMESTAMP
            WHERE api_key = ?
        """, (cost_usd, api_key))
        
        conn.commit()
        conn.close()
    
    def get_usage(self, api_key: str) -> Optional[dict]:
        """Get usage stats for an API key."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT cumulative_cost, requests_count, last_used_at, daily_limit_usd
            FROM api_keys
            WHERE api_key = ?
        """, (api_key,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "cumulative_cost": row[0],
            "requests_count": row[1],
            "last_used_at": row[2],
            "daily_limit_usd": row[3]
        }
    
    def check_daily_limit(self, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Check if key has exceeded daily limit.
        Returns (is_allowed, error_message)
        """
        # For MVP: simple check on cumulative cost
        # TODO: Implement daily rolling window
        usage = self.get_usage(api_key)
        if not usage:
            return False, "Key not found"
        
        if usage["cumulative_cost"] > usage["daily_limit_usd"]:
            return False, f"Daily limit exceeded: ${usage['cumulative_cost']:.2f} / ${usage['daily_limit_usd']:.2f}"
        
        return True, None


# Global instance
db = UsageDB()
