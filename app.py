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
    return {'state': 'main_menu', 'data': {}}

def set_user_state(chat_id, state_name, data=None):
    data_json = json.dumps(data) if data else None
    Database.execute("""
        INSERT INTO user_states (chat_id, state, data) 
        VALUES (%s, %s, %s) 
        ON DUPLICATE KEY UPDATE state = VALUES(state), data = VALUES(data)
    """, (chat_id, state_name, data_json))

# --- KEYBOARDS ---
def get_main_keyboard(role, status='pending', has_phone=False):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        markup.add("📦 Tovar Turlari", "⚙️ Rastenka/Detallar")
        markup.add("➕ Yangi Zakaz", "📊 Hisobotlar")
    elif status == 'active':
        markup.add("📥 Ish Topshirish")
    elif not has_phone:
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
            if not user.get('phone'):
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, "Botdan foydalanish uchun ro'yxatdan o'tishingiz kerak.", get_main_keyboard('chevar', 'pending', False))
            
            if user['status'] == 'active':
                set_user_state(chat_id, 'main_menu')
                send_msg(chat_id, f"Xush kelibsiz, {user['first_name']}!", get_main_keyboard('chevar', 'active', True))
            elif user['status'] == 'pending':
                send_msg(chat_id, "Sizning arizangiz ko'rib chiqilmoqda... ⏳", get_main_keyboard('chevar', 'pending', True))
        else:
            Database.execute("INSERT INTO users (chat_id, first_name) VALUES (%s, %s)", (chat_id, message.from_user.first_name))
            send_msg(chat_id, "Assalomu alaykum! Botdan foydalanish uchun ro'yxatdan o'tishingiz kerak.", get_main_keyboard('chevar', 'pending', False))

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
        state = state_info['state']
        data = state_info['data']

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            role = 'admin' if chat_id == config.ADMIN_ID else 'chevar'
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard(role, user['status'] if user else 'pending', bool(user and user.get('phone'))))

        # --- REGISTRATION ---
        if text == "📝 Ro'yxatdan o'tish":
            set_user_state(chat_id, 'reg_name')
            return send_msg(chat_id, "Ism va familiyangizni kiriting:", get_cancel_keyboard())
        elif state == 'reg_name':
            set_user_state(chat_id, 'reg_phone', {'full_name': text})
            return send_msg(chat_id, "Telefon raqamingizni yuboring:", get_reg_keyboards('phone'))
        elif state == 'reg_phone' and message.contact:
            data['phone'] = message.contact.phone_number
            set_user_state(chat_id, 'reg_location', data)
            return send_msg(chat_id, "Manzilingizni yuboring:", get_reg_keyboards('location'))
        elif state == 'reg_location' and message.location:
            data['lat'], data['lon'] = message.location.latitude, message.location.longitude
            set_user_state(chat_id, 'reg_machines', data)
            return send_msg(chat_id, "Mashinalar sonini kiriting:", get_cancel_keyboard())
        elif state == 'reg_machines':
            data['machines'] = text
            set_user_state(chat_id, 'reg_tailors', data)
            return send_msg(chat_id, "Chevarlar sonini kiriting:", get_cancel_keyboard())
        elif state == 'reg_tailors':
            Database.execute("UPDATE users SET first_name=%s, phone=%s, location=%s, machine_count=%s, tailor_count=%s, status='pending' WHERE chat_id=%s",
                       (data['full_name'], data['phone'], f"{data['lat']},{data['lon']}", data['machines'], text, chat_id))
            set_user_state(chat_id, 'pending_approval')
            send_msg(chat_id, "Arizangiz qabul qilindi. ✅", get_main_keyboard('chevar', 'pending', True))
            markup = types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{chat_id}"), types.InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{chat_id}"))
            send_msg(config.ADMIN_ID, f"🆕 <b>Ariza:</b>\n👤 {data['full_name']}\n📞 {data['phone']}\n⚙️ Mashina: {data['machines']}\n🧵 Chevarlar: {text}", markup)
            return bot.send_location(config.ADMIN_ID, data['lat'], data['lon'])

        # --- ADMIN ---
        if chat_id == config.ADMIN_ID:
            if text == "📦 Tovar Turlari":
                types_list = Database.fetch_all("SELECT * FROM product_types")
                resp = "📂 <b>Mavjud tovar turlari:</b>\n\n" + "\n".join([f"• {t['name']}" for t in types_list])
                set_user_state(chat_id, 'add_type')
                return send_msg(chat_id, resp + "\n\n<i>Yangi tur nomini yuboring:</i>", get_cancel_keyboard())
            elif state == 'add_type':
                Database.execute("INSERT IGNORE INTO product_types (name) VALUES (%s)", (text,))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, f"✅ Tur '{text}' qo'shildi.", get_main_keyboard('admin'))
            elif text == "⚙️ Rastenka/Detallar":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"rastenka:{t['id']}"))
                return send_msg(chat_id, "Turini tanlang:", markup)
            elif state == 'ent_op_name':
                set_user_state(chat_id, 'ent_op_price', {**data, 'name': text})
                return send_msg(chat_id, f"'{text}' narxi:", get_cancel_keyboard())
            elif state == 'ent_op_price':
                Database.execute("INSERT INTO operations (product_type_id, name, price) VALUES (%s, %s, %s)", (data['type_id'], data['name'], float(text)))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, "✅ Saqlandi.", get_main_keyboard('admin'))
            elif text == "➕ Yangi Zakaz":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"batch:{t['id']}"))
                return send_msg(chat_id, "Turini tanlang:", markup)
            elif state == 'ent_batch_name':
                set_user_state(chat_id, 'ent_batch_items', {**data, 'name': text})
                return send_msg(chat_id, "Format: <code>Razmer | Pachka | Dona</code>", get_cancel_keyboard())
            elif state == 'ent_batch_items':
                p = text.split('|')
                b_id = Database.execute("INSERT INTO batches (product_type_id, name) VALUES (%s, %s)", (data['type_id'], data['name']))
                Database.execute("INSERT INTO batch_items (batch_id, size, pack_count, items_per_pack, total_qty, remaining_qty) VALUES (%s, %s, %s, %s, %s, %s)", (b_id, p[0].strip(), int(p[1]), int(p[2]), int(p[1])*int(p[2]), int(p[1])*int(p[2])))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, f"✅ Zakaz ID: {b_id}", get_main_keyboard('admin'))
            elif text == "📊 Hisobotlar":
                logs = Database.fetch_all("SELECT chat_id, SUM(qty) as q FROM work_logs GROUP BY chat_id")
                resp = "📊 <b>Hisobot:</b>\n" + "\n".join([f"👤 {l['chat_id']}: {l['q']} dona" for l in logs])
                return send_msg(chat_id, resp, get_main_keyboard('admin'))

        # --- CHEVAR ---
        if user and user['status'] == 'active':
            if text == "📥 Ish Topshirish":
                set_user_state(chat_id, 'ch_ent_id')
                return send_msg(chat_id, "Zakaz ID kiriting:", get_cancel_keyboard())
            elif state == 'ch_ent_id':
                items = Database.fetch_all("SELECT * FROM batch_items WHERE batch_id=%s", (int(text),))
                markup = types.InlineKeyboardMarkup()
                for i in items: markup.add(types.InlineKeyboardButton(f"{i['size']} ({i['remaining_qty']})", callback_data=f"ch_sz:{i['id']}"))
                return send_msg(chat_id, "Razmer:", markup)
            elif state == 'ch_ent_qty':
                item = Database.fetch_one("SELECT * FROM batch_items WHERE id=%s", (data['sz_id'],))
                qty = int(text) * item['items_per_pack']
                Database.execute("INSERT INTO work_logs (chat_id, batch_id, size_id, qty) VALUES (%s, %s, %s, %s)", (chat_id, item['batch_id'], item['id'], qty))
                Database.execute("UPDATE batch_items SET remaining_qty = remaining_qty - %s WHERE id=%s", (qty, item['id']))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, f"✅ Qabul qilindi: {qty} dona", get_main_keyboard('chevar', 'active', True))

    except Exception as e: logging.error(f"Error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id, data = call.message.chat.id, call.data
    if data.startswith("approve:"):
        u_id = int(data.split(":")[1])
        Database.execute("UPDATE users SET status='active' WHERE chat_id=%s", (u_id,))
        send_msg(u_id, "✅ Tasdiqlandi!", get_main_keyboard('chevar', 'active', True))
        bot.edit_message_text("✅ Tasdiqlandi", chat_id, call.message.message_id)
    elif data.startswith("reject:"):
        u_id = int(data.split(":")[1])
        Database.execute("UPDATE users SET status='rejected' WHERE chat_id=%s", (u_id,))
        send_msg(u_id, "❌ Rad etildi", get_main_keyboard('chevar', 'pending', False))
    elif data.startswith("rastenka:"):
        set_user_state(chat_id, 'ent_op_name', {'type_id': data.split(":")[1]})
        send_msg(chat_id, "Detal nomi:", get_cancel_keyboard())
    elif data.startswith("batch:"):
        set_user_state(chat_id, 'ent_batch_name', {'type_id': data.split(":")[1]})
        send_msg(chat_id, "Zakaz nomi:", get_cancel_keyboard())
    elif data.startswith("ch_sz:"):
        set_user_state(chat_id, 'ch_ent_qty', {'sz_id': data.split(":")[1]})
        send_msg(chat_id, "Pachka soni:", get_cancel_keyboard())
    bot.answer_callback_query(call.id)

@app.route('/reset_users')
def reset():
    Database.execute("UPDATE users SET status='pending', phone=NULL WHERE chat_id != %s", (config.ADMIN_ID,))
    return "Ok", 200

@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/init")
def init(): return Database.init_db() and "Ok" or "Error"

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
