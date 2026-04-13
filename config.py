import os

# Telegram Bot Token
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8664211264:AAEXdXJflIUv6WXYMpDsaUzu7QlcdSEUS8c')

# Admin Chat ID
ADMIN_ID = os.environ.get('ADMIN_ID', '1045855587')

# Webhook URL (Railway app URL)
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://karimovtextilbot-production.up.railway.app')

# Database connection details (Local OSPanel MySQL)
MYSQLHOST = os.environ.get('MYSQLHOST', 'localhost')
MYSQLUSER = os.environ.get('MYSQLUSER', 'root')
MYSQLPASSWORD = os.environ.get('MYSQLPASSWORD', '')
MYSQLDATABASE = os.environ.get('MYSQLDATABASE', 'trikotaj_bot')
MYSQLPORT = int(os.environ.get('MYSQLPORT', 3306))
