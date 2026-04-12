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
        logging.error(f"Xabar: {e}")

def get_user_state(chat_id):
    state = Database.fetch_one("SELECT * FROM user_states WHERE chat_id = %s", (chat_id,))
    return state if state else {'state': 'main_menu', 'data': '{}'}

def parse_data(data):
    return json.loads(data) if isinstance(data, str) else (data or {})

def set_user_state(chat_id, state_name, data=None):
    data_json = json.dumps(data) if data else '{}'
    Database.execute("INSERT INTO user_states (chat_id, state, data) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE state=VALUES(state), data=VALUES(data)", (chat_id, state_name, data_json))

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

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    try:
        chat_id = message.chat.id
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        if str(chat_id) == str(config.ADMIN_ID):
            Database.execute("INSERT INTO users (chat_id, first_name, role, status) VALUES (%s, %s, 'admin', 'active') ON DUPLICATE KEY UPDATE role='admin', status='active'", (chat_id, message.from_user.first_name))
            set_user_state(chat_id, 'main_menu')
            return send_msg(chat_id, "Salom, Admin! Bot 100% sozlandi.", get_main_keyboard('admin'))
        
        if user and user['status'] == 'active':
            set_user_state(chat_id, 'main_menu')
            send_msg(chat_id, f"Xush kelibsiz, {user['first_name']}!", get_main_keyboard('chevar', 'active', True))
        elif user and user.get('phone'):
            send_msg(chat_id, "Arizangiz ko'rib chiqilmoqda...")
        else:
            send_msg(chat_id, "Botdan foydalanish uchun ro'yxatdan o'ting.", get_main_keyboard('chevar', 'pending', False))
    except Exception as e: logging.error(f"Start: {e}")

# --- GLOBAL HANDLER ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'contact'])
def global_handler(message):
    try:
        chat_id, text = message.chat.id, message.text
        user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        state_info = get_user_state(chat_id)
        state, data = state_info['state'], parse_data(state_info['data'])

        if text == "❌ Bekor qilish":
            set_user_state(chat_id, 'main_menu')
            role = 'admin' if str(chat_id) == str(config.ADMIN_ID) else 'chevar'
            return send_msg(chat_id, "Bekor qilindi.", get_main_keyboard(role, user['status'] if user else 'pending', bool(user and user.get('phone'))))

        # REGISTRATION
        if text == "📝 Ro'yxatdan o'tish":
            set_user_state(chat_id, 'reg_name')
            return send_msg(chat_id, "Ism-familiyangizni yuboring:", types.ReplyKeyboardRemove())
        elif state == 'reg_name':
            set_user_state(chat_id, 'reg_phone', {'name': text})
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("📞 Telefon", request_contact=True))
            return send_msg(chat_id, "Raqamingizni yuboring:", markup)
        elif state == 'reg_phone' and message.contact:
            Database.execute("INSERT INTO users (chat_id, first_name, phone, status) VALUES (%s, %s, %s, 'pending') ON DUPLICATE KEY UPDATE phone=VALUES(phone), status='pending'", (chat_id, data['name'], message.contact.phone_number))
            set_user_state(chat_id, 'pending')
            send_msg(chat_id, "✅ Ariza yuborildi.", get_main_keyboard('chevar', 'pending', True))
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appr:{chat_id}"))
            return send_msg(config.ADMIN_ID, f"🆕 Ariza: {data['name']} ({message.contact.phone_number})", markup)

        # ADMIN
        if str(chat_id) == str(config.ADMIN_ID):
            if text == "📦 Ombor":
                batches = Database.fetch_all("SELECT b.*, pt.name as t_name FROM batches b JOIN product_types pt ON b.product_type_id = pt.id")
                resp = "📦 <b>Ombor holati:</b>\n" + "\n".join([f"• {b['name']} ({b['t_name']}): {b['remaining_in_warehouse']} dona" for b in batches])
                return send_msg(chat_id, resp or "Ombor bo'sh.")
            
            elif text == "⚙️ Rastenka":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"rast:{t['id']}"))
                return send_msg(chat_id, "Tini tanlang:", markup)
            elif state == 'ras_n':
                set_user_state(chat_id, 'ras_p', {**data, 'n': text})
                return send_msg(chat_id, "Narxi (so'm):")
            elif state == 'ras_p':
                Database.execute("INSERT INTO operations (product_type_id, name, price) VALUES (%s, %s, %s)", (data['t_id'], data['n'], float(text)))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, "✅ Saqlandi.", get_main_keyboard('admin'))

            elif text == "➕ Yangi Zakaz":
                markup = types.InlineKeyboardMarkup()
                for t in Database.fetch_all("SELECT * FROM product_types"): markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"ord_t:{t['id']}"))
                return send_msg(chat_id, "Turini tanlang:", markup)
            elif state == 'ord_n':
                set_user_state(chat_id, 'ord_q', {**data, 'n': text})
                return send_msg(chat_id, "Bichilgan umumiy soni:")
            elif state == 'ord_q':
                b_id = Database.execute("INSERT INTO batches (product_type_id, name, total_qty, remaining_in_warehouse) VALUES (%s, %s, %s, %s)", (data['t_id'], data['n'], int(text), int(text)))
                set_user_state(chat_id, 'ord_i', {'b_id': b_id})
                return send_msg(chat_id, "Razmerlarni kiritishda davom eting (XL | 10 | 5):")
            elif state == 'ord_i':
                if text == "✅ Tamomlash":
                    set_user_state(chat_id, 'main_menu')
                    return send_msg(chat_id, "✅ Zakaz yakunlandi.", get_main_keyboard('admin'))
                p = text.split('|')
                qty = int(p[1]) * int(p[2])
                Database.execute("INSERT INTO batch_items (batch_id, size, pack_count, items_per_pack, total_qty, remaining_unassigned) VALUES (%s, %s, %s, %s, %s, %s)", (data['b_id'], p[0].strip(), int(p[1]), int(p[2]), qty, qty))
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Tamomlash")
                return send_msg(chat_id, "Keyingi razmer (format: L | 5 | 5) yoki tugatish:", markup)

            elif text == "📤 Ish Tarqatish":
                markup = types.InlineKeyboardMarkup()
                for b in Database.fetch_all("SELECT * FROM batches WHERE remaining_in_warehouse > 0"): markup.add(types.InlineKeyboardButton(b['name'], callback_data=f"gv_b:{b['id']}"))
                return send_msg(chat_id, "Ishni tanlang:", markup)
            elif state == 'gv_q':
                qty = int(text)
                Database.execute("INSERT INTO assignments (chevar_id, batch_item_id, qty_assigned) VALUES (%s, %s, %s)", (data['u_id'], data['i_id'], qty))
                Database.execute("UPDATE batch_items SET remaining_unassigned = remaining_unassigned - %s WHERE id = %s", (qty, data['i_id']))
                Database.execute("UPDATE batches SET remaining_in_warehouse = remaining_in_warehouse - %s WHERE id = (SELECT batch_id FROM batch_items WHERE id = %s)", (qty, data['i_id']))
                set_user_state(chat_id, 'main_menu')
                send_msg(data['u_id'], "📥 Sizga yangi ish berildi!")
                return send_msg(chat_id, "✅ Ish topshirildi.", get_main_keyboard('admin'))

            elif text == "📊 Hisobotlar":
                stats = Database.fetch_all("SELECT u.first_name, SUM(wl.total_price) as sum FROM users u JOIN work_logs wl ON u.chat_id = wl.chat_id GROUP BY u.chat_id")
                resp = "📊 <b>Hisobot:</b>\n" + "\n".join([f"👤 {s['first_name']}: {s['sum']} so'm" for s in stats])
                return send_msg(chat_id, resp or "Hali hisobotlar yo'q.")

        # CHEVAR
        if user and user['status'] == 'active':
            if text == "📥 Yangi Ishlar":
                assigns = Database.fetch_all("SELECT a.id, b.name, bi.size, a.qty_assigned FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.chevar_id = %s AND a.status = 'pending'", (chat_id,))
                if not assigns: return send_msg(chat_id, "Yangi ishlar yo'q.")
                for a in assigns:
                    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"acc:{a['id']}"))
                    send_msg(chat_id, f"📦 {a['name']} ({a['size']}) - {a['qty_assigned']} dona", markup)
            
            elif text == "📥 Ish Topshirish":
                active_assigns = Database.fetch_all("SELECT a.id, b.name, bi.size FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.chevar_id = %s AND a.status = 'accepted'", (chat_id,))
                if not active_assigns: return send_msg(chat_id, "Qabul qilingan ishlar yo'q.")
                markup = types.InlineKeyboardMarkup()
                for a in active_assigns: markup.add(types.InlineKeyboardButton(f"{a['name']} ({a['size']})", callback_data=f"rpt_a:{a['id']}"))
                return send_msg(chat_id, "Ishni tanlang:", markup)
            
            elif state == 'rpt_q':
                data['p_qty'] = int(text)
                op = Database.fetch_one("SELECT * FROM operations WHERE id = %s", (data['o_id'],))
                item = Database.fetch_one("SELECT * FROM batch_items WHERE id = (SELECT batch_item_id FROM assignments WHERE id = %s)", (data['a_id'],))
                total_qty = data['p_qty'] * item['items_per_pack']
                total_sum = total_qty * float(op['price'])
                Database.execute("INSERT INTO work_logs (chat_id, assignment_id, operation_id, qty, total_price) VALUES (%s, %s, %s, %s, %s)", (chat_id, data['a_id'], data['o_id'], total_qty, total_sum))
                set_user_state(chat_id, 'main_menu')
                return send_msg(chat_id, f"✅ Hisoblandi: {total_qty} dona = {total_sum} so'm", get_main_keyboard('chevar', 'active', True))

            elif text == "📊 Mening Hisobim":
                total = Database.fetch_one("SELECT SUM(total_price) as sum FROM work_logs WHERE chat_id = %s", (chat_id,))
                send_msg(chat_id, f"💳 <b>Sizning balansingiz:</b>\n\nJami ishlangan: {total['sum'] or 0} so'm", get_main_keyboard('chevar', 'active', True))

    except Exception as e: logging.error(f"Global: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id, data = call.message.chat.id, call.data
    if data.startswith("appr:"):
        u_id = data.split(":")[1]
        Database.execute("UPDATE users SET status='active' WHERE chat_id=%s", (u_id,))
        send_msg(u_id, "✅ Tasdiqlandi!", get_main_keyboard('chevar', 'active', True))
        bot.edit_message_text("✅ Tasdiqlandi", chat_id, call.message.message_id)
    elif data.startswith("rast:"):
        set_user_state(chat_id, 'ras_n', {'t_id': data.split(":")[1]})
        send_msg(chat_id, "Operatsiya nomi (misol: Yoqa tikish):")
    elif data.startswith("ord_t:"):
        set_user_state(chat_id, 'ord_n', {'t_id': data.split(":")[1]})
        send_msg(chat_id, "Zakaz (bichim) nomi:")
    elif data.startswith("gv_b:"):
        b_id = data.split(":")[1]
        markup = types.InlineKeyboardMarkup()
        for i in Database.fetch_all("SELECT * FROM batch_items WHERE batch_id=%s AND remaining_unassigned > 0", (b_id,)): markup.add(types.InlineKeyboardButton(f"{i['size']} ({i['remaining_unassigned']})", callback_data=f"gv_i:{i['id']}"))
        bot.edit_message_text("Razmerni tanlang:", chat_id, call.message.message_id, reply_markup=markup)
    elif data.startswith("gv_i:"):
        i_id = data.split(":")[1]
        markup = types.InlineKeyboardMarkup()
        for u in Database.fetch_all("SELECT * FROM users WHERE role='chevar' AND status='active'"): markup.add(types.InlineKeyboardButton(u['first_name'], callback_data=f"gv_u:{i_id}:{u['chat_id']}"))
        bot.edit_message_text("Chevarni tanlang:", chat_id, call.message.message_id, reply_markup=markup)
    elif data.startswith("gv_u:"):
        p = data.split(":")
        set_user_state(chat_id, 'gv_q', {'i_id': p[1], 'u_id': p[2]})
        send_msg(chat_id, "Necha dona berasiz?")
    elif data.startswith("acc:"):
        a_id = data.split(":")[1]
        Database.execute("UPDATE assignments SET status='accepted' WHERE id=%s", (a_id,))
        bot.edit_message_text("✅ Qabul qilindi!", chat_id, call.message.message_id)
    elif data.startswith("rpt_a:"):
        a_id = data.split(":")[1]
        assign = Database.fetch_one("SELECT bi.batch_id, b.product_type_id FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.id = %s", (a_id,))
        markup = types.InlineKeyboardMarkup()
        for o in Database.fetch_all("SELECT * FROM operations WHERE product_type_id = %s", (assign['product_type_id'],)): markup.add(types.InlineKeyboardButton(f"{o['name']} ({o['price']})", callback_data=f"rpt_o:{a_id}:{o['id']}"))
        bot.edit_message_text("Bajargan operatsiyangizni tanlang:", chat_id, call.message.message_id, reply_markup=markup)
    elif data.startswith("rpt_o:"):
        p = data.split(":")
        set_user_state(chat_id, 'rpt_q', {'a_id': p[1], 'o_id': p[2]})
        send_msg(chat_id, "Necha pachka (bog'lam) tikdingiz?")
    bot.answer_callback_query(call.id)

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
