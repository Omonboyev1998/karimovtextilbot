import mysql.connector
from mysql.connector import Error, pooling
import config
import logging
import time

class Database:
    db_config = {
        "host": config.MYSQLHOST,
        "user": config.MYSQLUSER,
        "password": config.MYSQLPASSWORD,
        "port": config.MYSQLPORT,
        "database": config.MYSQLDATABASE,
        "charset": 'utf8mb4',
        "collation": 'utf8mb4_unicode_ci'
    }
    
    _pool = None

    @classmethod
    def get_pool(cls):
        if cls._pool is None:
            try:
                cls._pool = pooling.MySQLConnectionPool(
                    pool_name="mypool",
                    pool_size=5,
                    pool_reset_session=True,
                    **cls.db_config
                )
            except Error as e:
                logging.error(f"Pool yaratishda xato: {e}")
        return cls._pool

    @staticmethod
    def get_connection():
        pool = Database.get_pool()
        if pool:
            return pool.get_connection()
        return None

    @staticmethod
    def init_db():
        conn = Database.get_connection()
        if not conn: return False
        cursor = conn.cursor()
        try:
            # 1. USERS
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT PRIMARY KEY,
                    first_name VARCHAR(255),
                    phone VARCHAR(50),
                    location VARCHAR(500),
                    role ENUM('admin', 'chevar') DEFAULT 'chevar',
                    status ENUM('pending', 'active', 'rejected') DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 2. PRODUCT TYPES
            cursor.execute("CREATE TABLE IF NOT EXISTS product_types (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")

            # 3. OPERATIONS (Rastenka)
            cursor.execute("CREATE TABLE IF NOT EXISTS operations (id INT AUTO_INCREMENT PRIMARY KEY, product_type_id INT, name VARCHAR(255), price DECIMAL(10, 2), FOREIGN KEY (product_type_id) REFERENCES product_types(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")

            # 4. BATCHES (Ombor - Bichilgan ishlar)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    product_type_id INT,
                    name VARCHAR(255),
                    total_qty INT DEFAULT 0,
                    remaining_in_warehouse INT DEFAULT 0,
                    status ENUM('active', 'completed') DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 5. BATCH ITEMS (Pachkalar/Razmerlar)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS batch_items (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    batch_id INT,
                    size VARCHAR(50),
                    pack_count INT,
                    items_per_pack INT,
                    total_qty INT,
                    remaining_unassigned INT,
                    FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 6. ASSIGNMENTS (Ish tarqatish) [NEW]
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assignments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    chevar_id BIGINT,
                    batch_item_id INT,
                    qty_assigned INT,
                    qty_completed INT DEFAULT 0,
                    status ENUM('pending', 'accepted', 'completed') DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chevar_id) REFERENCES users(chat_id),
                    FOREIGN KEY (batch_item_id) REFERENCES batch_items(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 7. WORK LOGS (Hisobotlar)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS work_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    chat_id BIGINT,
                    assignment_id INT,
                    operation_id INT,
                    qty INT,
                    total_price DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES users(chat_id),
                    FOREIGN KEY (assignment_id) REFERENCES assignments(id),
                    FOREIGN KEY (operation_id) REFERENCES operations(id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # 8. States
            cursor.execute("CREATE TABLE IF NOT EXISTS user_states (chat_id BIGINT PRIMARY KEY, state VARCHAR(255), data JSON, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")

            # Ustunlar mavjudligini tekshirish va ALTER qilish (Mustahkamlik uchun)
            try: cursor.execute("ALTER TABLE batches ADD COLUMN product_type_id INT AFTER id")
            except: pass
            try: cursor.execute("ALTER TABLE batches ADD COLUMN total_qty INT DEFAULT 0")
            except: pass
            try: cursor.execute("ALTER TABLE batches ADD COLUMN remaining_in_warehouse INT DEFAULT 0")
            except: pass

            conn.commit()
            return True
        except Error as e:
            logging.error(f"Db Error: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def execute(query, params=()):
        conn = Database.get_connection()
        if not conn: return None
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logging.error(f"Execute Error: {e} | Query: {query}")
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def fetch_one(query, params=()):
        conn = Database.get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def fetch_all(query, params=()):
        conn = Database.get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
