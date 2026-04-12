import telebot
from telebot import types
from flask import Flask, request
import config
from database import Database
import json
import os
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
bot = telebot.TeleBot(config.BOT_TOKEN, threaded=False)

# --- UTILS ---
def send_msg(chat_id, text, markup=None):
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        logging.error(f"Xabar yuborishda xato: {e}")

def get_user_state(chat_id):
    state = Database.fetch_one("SELECT * FROM user_states WHERE chat_id = %s", (chat_id,))
    if state:
        state['data'] = json.loads(state['data']) if state['data'] else {}
        return state
    return None

def set_user_state(chat_id, state_name, data=None):
    data_json = json.dumps(data) if data else None
    Database.execute("""
        INSERT INTO user_states (chat_id, state, data) 
        VALUES (%s, %s, %s) 
        ON DUPLICATE KEY UPDATE state = VALUES(state), data = VALUES(data)
    """, (chat_id, state_name, data_json))

# --- KEYBOARDS ---
def get_main_keyboard(role, status='pending'):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        markup.add("📦 Tovar Turlari", "⚙️ Rastenka/Detallar")
        markup.add("➕ Yangi Zakaz", "📊 Hisobotlar")
    elif status == 'active':
        markup.add("📥 Ish Topshirish")
    elif status == 'pending':
        markup.add("📝 Ro'yxatdan o'tish")
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❌ Bekor qilish")
    return markup

def get_reg_keyboards(step):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if step == 'phone':
        markup.add(types.KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True))
    elif step == 'location':
        markup.add(types.KeyboardButton("📍 Manzilni yuborish", request_location=True))
    markup.add("❌ Bekor qilish")
    return markup

# --- START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        
        if chat_id == config.ADMIN_ID:
            Database.execute("INSERT INTO users (chat_id, first_name, role, status) VALUES (%s, %s, 'admin', 'active') ON DUPLICATE KEY UPDATE role='admin', status='active'", 
                       (chat_id, message.from_user.first_name))
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Xush kelibsiz, Admin!", get_main_keyboard('admin'))

        if user:
            if user['status'] == 'active':
                set_user_state(chat_id, 'main_menu')
                send_msg(chat_id, f"Xush kelibsiz, {user['first_name']}!", get_main_keyboard('chevar', 'active'))
            elif user['status'] == 'pending':
                send_msg(chat_id, "Sizning arizangiz ko'rib chiqilmoqda...")
            elif user['status'] == 'rejected':
                send_msg(chat_id, "Arizangiz rad etilgan. Qayta ro'yxatdan o'tishingiz mumkin.", get_main_keyboard('chevar', 'pending'))
        else:
            send_msg(chat_id, "Assalomu alaykum! Botdan foydalanish uchun ro'yxatdan o'tishingiz kerak.", get_main_keyboard('chevar', 'pending'))

    except Exception as e:
        logging.error(f"Startda xato: {e}")

# --- GLOBAL HANDLERS ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'contact', 'location'])
def global_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        state_info = get_user_state(chat_id)
        state = state_info['state'] if state_info else 'main_menu'

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard('admin' if chat_id == config.ADMIN_ID else 'chevar', user['status'] if user else 'pending'))

        # --- REGISTRATION FLOW ---
        if text == "📝 Ro'yxatdan o'tish":
            set_user_state(chat_id, 'reg_name')
            send_msg(chat_id, "Ism va familiyangizni kiriting:", get_cancel_keyboard())
        
        elif state == 'reg_name':
            set_user_state(chat_id, 'reg_phone', {'full_name': text})
            send_msg(chat_id, "Telefon raqamingizni yuboring (tugmani bosing):", get_reg_keyboards('phone'))
        
        elif state == 'reg_phone' and message.contact:
            data = state_info['data']
            data['phone'] = message.contact.phone_number
            set_user_state(chat_id, 'reg_location', data)
            send_msg(chat_id, "Manzilingizni yuboring (tugmani bosing):", get_reg_keyboards('location'))
        
        elif state == 'reg_location' and message.location:
            data = state_info['data']
            data['lat'] = message.location.latitude
            data['lon'] = message.location.longitude
            set_user_state(chat_id, 'reg_machines', data)
            send_msg(chat_id, "Mashinalar sonini kiriting:", get_cancel_keyboard())
        
        elif state == 'reg_machines':
            data = state_info['data']
            data['machines'] = text
            set_user_state(chat_id, 'reg_tailors', data)
            send_msg(chat_id, "Chevarlar sonini kiriting:", get_cancel_keyboard())
        
        elif state == 'reg_tailors':
            data = state_info['data']
            # Ma'lumotlarni bazaga pending holatida saqlaymiz
            Database.execute("""
                INSERT INTO users (chat_id, first_name, last_name, phone, location, machine_count, tailor_count, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                ON DUPLICATE KEY UPDATE first_name=%s, last_name=%s, phone=%s, location=%s, machine_count=%s, tailor_count=%s, status='pending'
            """, (chat_id, data['full_name'], '', data['phone'], f"{data['lat']},{data['lon']}", data['machines'], text, 
                  data['full_name'], '', data['phone'], f"{data['lat']},{data['lon']}", data['machines'], text))
            
            set_user_state(chat_id, 'pending_approval')
            send_msg(chat_id, "Arizangiz qabul qilindi. Admin tasdiqlashini kuting. ✅", get_main_keyboard('chevar', 'pending'))
            
            # Adminga xabar yuboramiz
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_user:{chat_id}"),
                       types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_user:{chat_id}"))
            
            admin_msg = f"🆕 <b>Yangi chevar arizasi:</b>\n\n👤 {data['full_name']}\n📞 {data['phone']}\n⚙️ Mashinalar: {data['machines']}\n🧵 Chevarlar: {text}"
            send_msg(config.ADMIN_ID, admin_msg, markup)
            if 'lat' in data:
                bot.send_location(config.ADMIN_ID, data['lat'], data['lon'])

        # --- ADMIN HANDLERS (EXCEPT REG) ---
        elif chat_id == config.ADMIN_ID:
            # (Oldingi admin funksiyalari: Tovar, Rastenka, Zakaz - qisqacha saqlandi)
            if text == "📦 Tovar Turlari":
                # ... (oldingi kod)
                pass
            # ... qolgan admin logikasi

    except Exception as e:
        logging.error(f"Global handlerda xato: {e}")

# --- CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data = call.data
        if data.startswith("approve_user:"):
            u_id = int(data.split(":")[1])
            Database.execute("UPDATE users SET status='active' WHERE chat_id=%s", (u_id,))
            bot.edit_message_text("✅ Chevar tasdiqlandi!", call.message.chat.id, call.message.message_id)
            send_msg(u_id, "Tabriklaymiz! Arizangiz tasdiqlandi. Endi botdan to'liq foydalanishingiz mumkin. ✅", get_main_keyboard('chevar', 'active'))
            set_user_state(u_id, 'main_menu')
        
        elif data.startswith("reject_user:"):
            u_id = int(data.split(":")[1])
            Database.execute("UPDATE users SET status='rejected' WHERE chat_id=%s", (u_id,))
            bot.edit_message_text("❌ Ariza rad etildi.", call.message.chat.id, call.message.message_id)
            send_msg(u_id, "Arizangiz rad etildi. ❌", get_main_keyboard('chevar', 'pending'))
        
        # ... qolgan callbacklar (rastenka_type va h.k.)

    except Exception as e: logging.error(f"Callbackda xato: {e}")

@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/init")
def init():
    return Database.init_db() and "Ok" or "Error"

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
