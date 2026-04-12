import mysql.connector
from mysql.connector import Error
import config
import logging

class Database:
    @staticmethod
    def get_connection():
        try:
            conn = mysql.connector.connect(
                host=config.MYSQLHOST,
                user=config.MYSQLUSER,
                password=config.MYSQLPASSWORD,
                port=config.MYSQLPORT,
                database=config.MYSQLDATABASE,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            return conn
        except Error as e:
            logging.error(f"Ma'lumotlar bazasiga ulanishda xato: {e}")
            return None

    @staticmethod
    def init_db():
        conn = Database.get_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        
        # Foydalanuvchilar
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                first_name VARCHAR(255),
                username VARCHAR(255),
                role ENUM('admin', 'chevar') DEFAULT 'chevar',
                state VARCHAR(255) DEFAULT 'main_menu',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Tovar turlari
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Partiyalar (Batches)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                batch_id VARCHAR(50) UNIQUE NOT NULL,
                type_id INT,
                total_count INT,
                price_per_item DECIMAL(10, 2),
                status ENUM('active', 'completed') DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (type_id) REFERENCES product_types(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Ish natijalari (Work Logs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id BIGINT,
                batch_id VARCHAR(50),
                count INT,
                total_price DECIMAL(10, 2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id),
                FOREIGN KEY (batch_id) REFERENCES batches(batch_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        conn.commit()
        cursor.close()
        conn.close()
        logging.info("Ma'lumotlar bazasi muvaffaqiyatli initsializatsiya qilindi.")

    # ... boshqa execute/fetch funksiyalari (Mysql sintaksisida) ...
    @staticmethod
    def execute(query, params=()):
        conn = Database.get_connection()
        if not conn: return
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        cursor.close()
        conn.close()

    @staticmethod
    def fetch_one(query, params=()):
        conn = Database.get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row
