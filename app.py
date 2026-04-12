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
        markup.add("📦 Ombor", "⚙️ Rastenka")
        markup.add("➕ Yangi Zakaz", "📤 Ish Tarqatish")
        markup.add("📊 Hisobotlar")
    elif status == 'active':
        markup.add("📥 Yangi Ishlar", "📥 Ish Topshirish")
        markup.add("📊 Mening Hisobim")
    elif not has_phone:
        markup.add("📝 Ro'yxatdan o'tish")
    return markup

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("❌ Bekor qilish")
    return markup

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        # Admin ID tekshiruvi (str/int xatosini oldini olish)
        if str(chat_id) == str(config.ADMIN_ID):
            Database.execute("INSERT INTO users (chat_id, first_name, role, status) VALUES (%s, %s, 'admin', 'active') ON DUPLICATE KEY UPDATE role='admin', status='active'", (chat_id, message.from_user.first_name))
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Xush kelibsiz, Admin!", get_main_keyboard('admin'))
        
        if user and user['status'] == 'active':
            set_user_state(chat_id, 'main_menu')
            send_msg(chat_id, f"Salom, {user['first_name']}!", get_main_keyboard('chevar', 'active', True))
        elif user and user.get('phone'):
            send_msg(chat_id, "Arizangiz ko'rib chiqilmoqda... ⏳")
        else:
            send_msg(chat_id, "Botdan foydalanish uchun ro'yxatdan o'ting.", get_main_keyboard('chevar', 'pending', False))
    except Exception as e: logging.error(f"Start Error: {e}")

# --- GLOBAL HANDLER ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'contact', 'location'])
def global_handler(message):
    try:
        chat_id, text = message.chat.id, message.text
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        state_info = get_user_state(chat_id)
        state, data = state_info['state'], state_info['data']

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            role = 'admin' if str(chat_id) == str(config.ADMIN_ID) else 'chevar'
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard(role, user['status'] if user else 'pending', bool(user and user.get('phone'))))

        # REGISTRATION
        if text == "📝 Ro'yxatdan o'tish":
            set_user_state(chat_id, 'reg_name')
            return send_msg(chat_id, "Ism-familiyangizni kiriting:", get_cancel_keyboard())
        
        elif state == 'reg_name':
            set_user_state(chat_id, 'reg_phone', {'name': text})
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📞 Telefon yuborish", request_contact=True))
            return send_msg(chat_id, "Telefon raqamingizni yuboring:", markup)
        
        elif state == 'reg_phone' and message.contact:
            data['phone'] = message.contact.phone_number
            Database.execute("INSERT INTO users (chat_id, first_name, phone, status) VALUES (%s, %s, %s, 'pending') ON DUPLICATE KEY UPDATE first_name=%s, phone=%s, status='pending'", (chat_id, data['name'], data['phone'], data['name'], data['phone']))
            set_user_state(chat_id, 'pending')
            send_msg(chat_id, "Arizangiz Adminga yuborildi. ✅", get_main_keyboard('chevar', 'pending', True))
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appr:{chat_id}"))
            return send_msg(config.ADMIN_ID, f"🆕 Yangi chevar arizasi:\n👤 {data['name']}\n📞 {data['phone']}", markup)

        # ADMIN LOGIC
        if str(chat_id) == str(config.ADMIN_ID):
            if text == "📦 Ombor":
                batches = Database.fetch_all("SELECT b.*, pt.name as type_name FROM batches b JOIN product_types pt ON b.product_type_id = pt.id WHERE b.status='active'")
                resp = "📦 <b>Ombordagi bichilgan ishlar:</b>\n\n"
                for b in batches: resp += f"🔹 {b['name']} ({b['type_name']})\n   Qoldi: {b['remaining_in_warehouse']} dona\n\n"
                return send_msg(chat_id, resp or "Ombor bo'sh.")
            
            elif text == "⚙️ Rastenka":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"rastenka:{t['id']}"))
                return send_msg(chat_id, "Turi bo'yicha narxlarni tanlang:", markup)
            
            elif state == 'ent_op_name':
                set_user_state(chat_id, 'ent_op_price', {**data, 'name': text})
                return send_msg(chat_id, f"'{text}' narxi (so'mda):", get_cancel_keyboard())
            
            elif state == 'ent_op_price':
                Database.execute("INSERT INTO operations (product_type_id, name, price) VALUES (%s, %s, %s)", (data['type_id'], data['name'], float(text)))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, "✅ Operatsiya va narx saqlandi.", get_main_keyboard('admin'))

            elif text == "➕ Yangi Zakaz":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"b_type:{t['id']}"))
                return send_msg(chat_id, "Zakaz turini tanlang:", markup)
            
            elif state == 'b_name':
                set_user_state(chat_id, 'b_qty', {**data, 'name': text})
                return send_msg(chat_id, f"'{text}' dan necha dona bichildi?", get_cancel_keyboard())
            
            elif state == 'b_qty':
                qty = int(text)
                b_id = Database.execute("INSERT INTO batches (product_type_id, name, total_qty, remaining_in_warehouse) VALUES (%s, %s, %s, %s)", (data['t_id'], data['name'], qty, qty))
                set_user_state(chat_id, 'b_items', {'b_id': b_id, 'name': data['name']})
                return send_msg(chat_id, "Razmerlarni kiriting (Masalan: `XL | 10 | 5`):", get_cancel_keyboard())
            
            elif state == 'b_items':
                p = [x.strip() for x in text.split('|')]
                qty = int(p[1]) * int(p[2])
                Database.execute("INSERT INTO batch_items (batch_id, size, pack_count, items_per_pack, total_qty, remaining_unassigned) VALUES (%s, %s, %s, %s, %s, %s)", (data['b_id'], p[0], int(p[1]), int(p[2]), qty, qty))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, "✅ Omborga qo'shildi.", get_main_keyboard('admin'))

            elif text == "📤 Ish Tarqatish":
                markup = types.InlineKeyboardMarkup()
                for b in Database.fetch_all("SELECT * FROM batches WHERE remaining_in_warehouse > 0"): markup.add(types.InlineKeyboardButton(b['name'], callback_data=f"dist_b:{b['id']}"))
                return send_msg(chat_id, "Qaysi ishni tarqatamiz?", markup)
            
            elif state == 'dist_qty':
                qty_to_give = int(text)
                Database.execute("INSERT INTO assignments (chevar_id, batch_item_id, qty_assigned, status) VALUES (%s, %s, %s, 'pending')", (data['u_id'], data['i_id'], qty_to_give))
                Database.execute("UPDATE batch_items SET remaining_unassigned = remaining_unassigned - %s WHERE id = %s", (qty_to_give, data['i_id']))
                Database.execute("UPDATE batches SET remaining_in_warehouse = remaining_in_warehouse - %s WHERE id = (SELECT batch_id FROM batch_items WHERE id = %s)", (qty_to_give, data['i_id']))
                set_user_state(chat_id, 'main_menu')
                send_msg(data['u_id'], "📥 Sizga yangi ish topshirildi! 'Yangi Ishlar' bo'limini tekshiring.")
                return send_msg(chat_id, "✅ Ish tarqatildi.", get_main_keyboard('admin'))

        # CHEVAR LOGIC
        if user and user['status'] == 'active':
            if text == "📥 Yangi Ishlar":
                assigns = Database.fetch_all("SELECT a.*, b.name as b_name, bi.size FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.chevar_id = %s AND a.status = 'pending'", (chat_id,))
                if not assigns: return send_msg(chat_id, "Yangi topshiriqlar yo'q.")
                for a in assigns:
                    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"acc_job:{a['id']}"))
                    send_msg(chat_id, f"📥 <b>Yangi ish:</b>\nZakaz: {a['b_name']}\nRazmer: {a['size']}\nSoni: {a['qty_assigned']} dona", markup)
            
            elif text == "📥 Ish Topshirish":
                assigns = Database.fetch_all("SELECT a.*, b.name as b_name, bi.size FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.chevar_id = %s AND a.status = 'accepted'", (chat_id,))
                if not assigns: return send_msg(chat_id, "Qabul qilingan ishlar yo'q.")
                markup = types.InlineKeyboardMarkup()
                for a in assigns: markup.add(types.InlineKeyboardButton(f"{a['b_name']} ({a['size']})", callback_data=f"report_a:{a['id']}"))
                return send_msg(chat_id, "Qaysi ish bo'yicha report berasiz?", markup)

    except Exception as e: logging.error(f"Global Error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        chat_id, data = call.message.chat.id, call.data
        if data.startswith("appr:"):
            u_id = data.split(":")[1]
            Database.execute("UPDATE users SET status='active' WHERE chat_id=%s", (u_id,))
            send_msg(u_id, "✅ Tasdiqlandi!", get_main_keyboard('chevar', 'active', True))
            bot.edit_message_text("✅ Tasdiqlandi", chat_id, call.message.message_id)
        
        elif data.startswith("rastenka:"):
            set_user_state(chat_id, 'ent_op_name', {'type_id': data.split(":")[1]})
            send_msg(chat_id, "Operatsiya (detal) nomini kiriting:", get_cancel_keyboard())
        
        elif data.startswith("b_type:"):
            set_user_state(chat_id, 'b_name', {'t_id': data.split(":")[1]})
            send_msg(chat_id, "Zakaz (partiya) nomini kiriting:", get_cancel_keyboard())
        
        elif data.startswith("dist_b:"):
            b_id = data.split(":")[1]
            markup = types.InlineKeyboardMarkup()
            for i in Database.fetch_all("SELECT * FROM batch_items WHERE batch_id=%s AND remaining_unassigned > 0", (b_id,)): markup.add(types.InlineKeyboardButton(f"{i['size']} ({i['remaining_unassigned']})", callback_data=f"dist_i:{i['id']}"))
            bot.edit_message_text("Razmerni tanlang:", chat_id, call.message.message_id, reply_markup=markup)
        
        elif data.startswith("dist_i:"):
            i_id = data.split(":")[1]
            markup = types.InlineKeyboardMarkup()
            for u in Database.fetch_all("SELECT * FROM users WHERE role='chevar' AND status='active'"): markup.add(types.InlineKeyboardButton(u['first_name'], callback_data=f"dist_u:{i_id}:{u['chat_id']}"))
            bot.edit_message_text("Chevarni tanlang:", chat_id, call.message.message_id, reply_markup=markup)
        
        elif data.startswith("dist_u:"):
            p = data.split(":")
            set_user_state(chat_id, 'dist_qty', {'i_id': p[1], 'u_id': p[2]})
            send_msg(chat_id, "Beriladigan dona sonini kiriting:", get_cancel_keyboard())

        elif data.startswith("acc_job:"):
            a_id = data.split(":")[1]
            Database.execute("UPDATE assignments SET status='accepted' WHERE id=%s", (a_id,))
            bot.edit_message_text("✅ Ish qabul qilindi. Boshladik!", chat_id, call.message.message_id)

        bot.answer_callback_query(call.id)
    except Exception as e: logging.error(f"Callback: {e}")

@app.route('/' + config.BOT_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=config.WEBHOOK_URL + '/' + config.BOT_TOKEN)
    return "Webhook set", 200

@app.route("/init")
def init(): return Database.init_db() and "Ok" or "Error"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
