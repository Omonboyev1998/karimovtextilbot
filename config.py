import os

# Telegram Bot Configuration
# MUHIM: Bu qiymatlar Railway Environment Variables bo'limida kiritilishi shart!
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

# Railway Webhook URL (Railway bergan manzil)
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# Database Config (Railway MySQL o'zgaruvchilari avtomatik ishlaydi)
MYSQLHOST = os.environ.get('MYSQLHOST')
MYSQLUSER = os.environ.get('MYSQLUSER')
MYSQLPASSWORD = os.environ.get('MYSQLPASSWORD')
MYSQLPORT = os.environ.get('MYSQLPORT', 3306)
MYSQLDATABASE = os.environ.get('MYSQLDATABASE')
