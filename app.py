import telebot
from telebot import types
from flask import Flask, request
import config
from database import Database
import json
import os
import logging

# Loglarni sozlash
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
def get_main_keyboard(role):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        markup.add("📦 Tovar Turlari", "⚙️ Rastenka/Detallar")
        markup.add("➕ Yangi Zakaz", "📊 Hisobotlar")
    else:
        markup.add("📥 Ish Topshirish")
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❌ Bekor qilish")
    return markup

# --- START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        first_name = message.from_user.first_name
        role = 'admin' if chat_id == config.ADMIN_ID else 'chevar'
        
        Database.execute("INSERT INTO users (chat_id, first_name, role) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE first_name = VALUES(first_name)", 
                   (chat_id, first_name, role))
        
        set_user_state(chat_id, 'main_menu')
        welcome = f"Xush kelibsiz, <b>{first_name}</b>! \nLoyiha: <b>Karimov Textile</b>."
        send_msg(chat_id, welcome, get_main_keyboard(role))
    except Exception as e:
        logging.error(f"Startda xato: {e}")

# --- ADMIN HANDLERS ---
@bot.message_handler(func=lambda m: m.chat.id == config.ADMIN_ID)
def admin_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        state_info = get_user_state(chat_id)
        state = state_info['state'] if state_info else 'main_menu'

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard('admin'))

        # TOVAR TURLARI
        if text == "📦 Tovar Turlari":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            resp = "📂 <b>Mavjud tovar turlari:</b>\n\n"
            for t in types_list: resp += f"• {t['name']}\n"
            resp += "\n<i>Yangi tur qo'shish uchun nomini yuboring.</i>"
            set_user_state(chat_id, 'add_product_type')
            send_msg(chat_id, resp, get_cancel_keyboard())
        elif state == 'add_product_type':
            Database.execute("INSERT IGNORE INTO product_types (name) VALUES (%s)", (text,))
            set_user_state(chat_id, 'main_menu')
            send_msg(chat_id, f"✅ Tur '{text}' qo'shildi.", get_main_keyboard('admin'))

        # RASTENKA
        elif text == "⚙️ Rastenka/Detallar":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            markup = types.InlineKeyboardMarkup()
            for t in types_list: markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"rastenka_type:{t['id']}"))
            send_msg(chat_id, "Qaysi tur uchun detal qo'shamiz?", markup)
        elif state == 'enter_operation_name':
            set_user_state(chat_id, 'enter_operation_price', {**state_info['data'], 'name': text})
            send_msg(chat_id, f"'{text}' uchun narxni kiriting (so'mda):", get_cancel_keyboard())
        elif state == 'enter_operation_price':
            try:
                price = float(text)
                data = state_info['data']
                Database.execute("INSERT INTO operations (product_type_id, name, price) VALUES (%s, %s, %s)", (data['type_id'], data['name'], price))
                set_user_state(chat_id, 'main_menu')
                send_msg(chat_id, f"✅ Detal qo'shildi: {data['name']} - {price} so'm", get_main_keyboard('admin'))
            except: send_msg(chat_id, "Faqat son kiriting!")

        # YANGI ZAKAZ
        elif text == "➕ Yangi Zakaz":
            types_list = Database.fetch_all("SELECT * FROM product_types")
            markup = types.InlineKeyboardMarkup()
            for t in types_list: markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"batch_type:{t['id']}"))
            send_msg(chat_id, "Zakaz turini tanlang:", markup)
        elif state == 'enter_batch_name':
            set_user_state(chat_id, 'enter_batch_items', {**state_info['data'], 'batch_name': text})
            send_msg(chat_id, f"'{text}' zakaz uchun razmer va sonini quyidagi formatda yuboring:\n<code>Razmer | Pachka soni | Dona (pachkada)</code>\n\nMisol: <code>XL | 10 | 5</code>", get_cancel_keyboard())
        elif state == 'enter_batch_items':
            try:
                parts = [p.strip() for p in text.split('|')]
                size, packs, per_pack = parts[0], int(parts[1]), int(parts[2])
                data = state_info['data']
                batch_id = Database.execute("INSERT INTO batches (product_type_id, name) VALUES (%s, %s)", (data['type_id'], data['batch_name']))
                Database.execute("INSERT INTO batch_items (batch_id, size, pack_count, items_per_pack, total_qty, remaining_qty) VALUES (%s, %s, %s, %s, %s, %s)", 
                           (batch_id, size, packs, per_pack, packs * per_pack, packs * per_pack))
                set_user_state(chat_id, 'main_menu')
                send_msg(chat_id, f"✅ Zakaz saqlandi! ID: {batch_id}", get_main_keyboard('admin'))
            except: send_msg(chat_id, "Format xato! Misol: XL | 10 | 5")

        # HISOBOTLAR
        elif text == "📊 Hisobotlar":
            logs = Database.fetch_all("SELECT chat_id, SUM(qty) as total_qty FROM work_logs GROUP BY chat_id")
            resp = "📊 <b>Umumiy ish hisoboti:</b>\n\n"
            for l in logs:
                user = Database.fetch_one("SELECT first_name FROM users WHERE chat_id = %s", (l['chat_id'],))
                resp += f"👤 {user['first_name']}: {l['total_qty']} dona\n"
            send_msg(chat_id, resp, get_main_keyboard('admin'))

    except Exception as e:
        logging.error(f"Admin handlerda xato: {e}")

# --- CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        chat_id = call.message.chat.id
        data = call.data
        if data.startswith("rastenka_type:"):
            set_user_state(chat_id, 'enter_operation_name', {'type_id': data.split(":")[1]})
            send_msg(chat_id, "Detal nomini yuboring:", get_cancel_keyboard())
        elif data.startswith("batch_type:"):
            set_user_state(chat_id, 'enter_batch_name', {'type_id': data.split(":")[1]})
            send_msg(chat_id, "Zakaz nomini yuboring:", get_cancel_keyboard())
        elif data.startswith("chevar_size:"):
            size_id = data.split(":")[1]
            set_user_state(chat_id, 'chevar_enter_qty', {'size_id': size_id})
            send_msg(chat_id, "Bajarilgan pachka sonini yuboring:", get_cancel_keyboard())
        bot.answer_callback_query(call.id)
    except Exception as e: logging.error(f"Callbackda xato: {e}")

# --- CHEVAR HANDLERS ---
@bot.message_handler(func=lambda m: True)
def chevar_handler(message):
    try:
        chat_id = message.chat.id
        text = message.text
        state_info = get_user_state(chat_id)
        state = state_info['state'] if state_info else 'main_menu'

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Menyuga qaytildi.", get_main_keyboard('chevar'))

        if text == "📥 Ish Topshirish":
            set_user_state(chat_id, 'chevar_enter_batch_id')
            send_msg(chat_id, "Zakaz ID raqamini kiriting:", get_cancel_keyboard())
        elif state == 'chevar_enter_batch_id':
            try:
                batch_id = int(text)
                items = Database.fetch_all("SELECT * FROM batch_items WHERE batch_id = %s", (batch_id,))
                if not items: return send_msg(chat_id, "Bunday ID topilmadi!")
                markup = types.InlineKeyboardMarkup()
                for i in items: markup.add(types.InlineKeyboardButton(f"{i['size']} ({i['remaining_qty']} dona qoldi)", callback_data=f"chevar_size:{i['id']}"))
                send_msg(chat_id, "Razmerni tanlang:", markup)
            except: send_msg(chat_id, "Faqat ID raqamini kiriting!")
        elif state == 'chevar_enter_qty':
            try:
                packs = int(text)
                data = state_info['data']
                item = Database.fetch_one("SELECT * FROM batch_items WHERE id = %s", (data['size_id'],))
                qty = packs * item['items_per_pack']
                Database.execute("INSERT INTO work_logs (chat_id, batch_id, size_id, qty) VALUES (%s, %s, %s, %s)", (chat_id, item['batch_id'], item['id'], qty))
                Database.execute("UPDATE batch_items SET remaining_qty = remaining_qty - %s WHERE id = %s", (qty, item['id']))
                set_user_state(chat_id, 'main_menu')
                send_msg(chat_id, f"✅ Ish qabul qilindi: {qty} dona.", get_main_keyboard('chevar'))
            except: send_msg(chat_id, "Faqat son kiriting!")
    except Exception as e: logging.error(f"Chevar xato: {e}")

@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
