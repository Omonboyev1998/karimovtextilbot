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

# --- STANDART RAZMERLAR ---
SIZES = ["46", "48", "50", "52", "54", "56", "58", "60", "62", "64", "66", "68"]

# --- UTILS ---
def send_msg(chat_id, text, markup=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML')
    except Exception as e: logging.error(f"Send Error: {e}")

def get_user_state(chat_id):
    state = Database.fetch_one("SELECT * FROM user_states WHERE chat_id = %s", (chat_id,))
    return state if state else {'state': 'main_menu', 'data': '{}'}

def parse_data(data):
    if not data: return {}
    return json.loads(data) if isinstance(data, str) else data

def set_user_state(chat_id, state_name, data=None):
    data_json = json.dumps(data) if data else '{}'
    Database.execute("INSERT INTO user_states (chat_id, state, data) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE state=VALUES(state), data=VALUES(data)", (chat_id, state_name, data_json))

# --- KEYBOARDS ---
def get_main_keyboard(role, status='active'):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    if role == 'admin':
        markup.add("📦 Ombor", "📤 Ish Tarqatuvchi")
        markup.add("➕ Yangi Ish Qo'shish", "⚙️ Rastenka Sozlash")
        markup.add("👥 Chevarlar", "📊 Hisobotlar")
    elif status == 'active':
        markup.add("📤 Ishni Topshirish", "📊 Mening Hisobim")
        markup.add("📥 Mening Ishlarim")
    else:
        markup.add("📝 Ro'yxatdan o'tish")
    return markup

def get_cancel_keyboard():
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Bekor qilish")

def get_size_keyboard(added_sizes=[]):
    markup = types.InlineKeyboardMarkup(row_width=4)
    btns = []
    for s in SIZES:
        label = f"✅ {s}" if s in added_sizes else s
        btns.append(types.InlineKeyboardButton(label, callback_data=f"sel_s:{s}"))
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("✅ TAMOMLASH", callback_data="finish_batch"))
    return markup

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
    if str(chat_id) == str(config.ADMIN_ID):
        Database.execute("INSERT INTO users (chat_id, first_name, role, status) VALUES (%s, %s, 'admin', 'active') ON DUPLICATE KEY UPDATE role='admin', status='active'", (chat_id, message.from_user.first_name))
        set_user_state(chat_id, 'main_menu')
        return send_msg(chat_id, "🤝 <b>Xush kelibsiz, Admin!</b>\nTizim tayyor.", get_main_keyboard('admin'))
    
    if user and user['status'] == 'active':
        set_user_state(chat_id, 'main_menu')
        send_msg(chat_id, f"Assalomu alaykum, {user['first_name']}!", get_main_keyboard('chevar', 'active'))
    else:
        send_msg(chat_id, "Botdan foydalanish uchun ro'yxatdan o'ting.", get_main_keyboard('chevar', 'pending'))

# --- GLOBAL HANDLER ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'contact'])
def global_handler(message):
    chat_id, text = message.chat.id, message.text
    user = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
    state_info = get_user_state(chat_id)
    state, data = state_info['state'], parse_data(state_info['data'])
    role = 'admin' if str(chat_id) == str(config.ADMIN_ID) else 'chevar'

    if text == "❌ Bekor qilish":
        set_user_state(chat_id, 'main_menu')
        return send_msg(chat_id, "Amal bekor qilindi.", get_main_keyboard(role))

    # ADMIN: NEW BATCH
    if role == 'admin' and text == "➕ Yangi Ish Qo'shish":
        markup = types.InlineKeyboardMarkup()
        for t in Database.fetch_all("SELECT * FROM product_types"):
            markup.add(types.InlineKeyboardButton(t['name'], callback_data=f"init_b:{t['id']}"))
        return send_msg(chat_id, "Mahsulot turini tanlang:", markup)

    if state == 'wait_batch_name':
        set_user_state(chat_id, 'select_sizes', {**data, 'name': text, 'added': {}})
        return send_msg(chat_id, f"📦 <b>{text}</b> uchun razmerlarni tanlang:", get_size_keyboard())

    if state == 'wait_size_qty':
        qty = int(text)
        data['added'][data['active_size']] = qty
        set_user_state(chat_id, 'select_sizes', data)
        return send_msg(chat_id, f"✅ {data['active_size']} razmerdan {qty} dona qo'shildi. Yana tanlaysizmi?", get_size_keyboard(list(data['added'].keys())))

    # ADMIN: USERS & ASSIGNMENT
    if role == 'admin' and text == "👥 Chevarlar":
        chevars = Database.fetch_all("SELECT * FROM users WHERE role='chevar' AND status='active'")
        markup = types.InlineKeyboardMarkup()
        for c in chevars: markup.add(types.InlineKeyboardButton(f"👤 {c['first_name']}", callback_data=f"view_c:{c['chat_id']}"))
        return send_msg(chat_id, "Chevar tanlang:", markup)

    if state == 'give_qty':
        try:
            qty = int(text)
            Database.execute("INSERT INTO assignments (chevar_id, batch_item_id, qty_assigned) VALUES (%s, %s, %s)", (data['u_id'], data['i_id'], qty))
            Database.execute("UPDATE batch_items SET remaining_unassigned = remaining_unassigned - %s WHERE id = %s", (qty, data['i_id']))
            Database.execute("UPDATE batches SET remaining_in_warehouse = remaining_in_warehouse - %s WHERE id = (SELECT batch_id FROM batch_items WHERE id = %s)", (qty, data['i_id']))
            set_user_state(chat_id, 'main_menu')
            send_msg(data['u_id'], f"📥 Sizga yangi ish berildi ({qty} dona).")
            return send_msg(chat_id, "✅ Ish muvaffaqiyatli topshirildi.", get_main_keyboard('admin'))
        except: return send_msg(chat_id, "Faqat son kiriting:")

    # OTHER ADMIN/CHEVAR CMDS (Previously implemented)
    if text == "📦 Ombor":
        items = Database.fetch_all("SELECT bi.id, b.name, bi.size, bi.remaining_unassigned FROM batch_items bi JOIN batches b ON bi.batch_id = b.id WHERE bi.remaining_unassigned > 0")
        resp = "🏚 <b>Ombor holati:</b>\n\n"
        for i in items: resp += f"• {i['name']} ({i['size']}): {i['remaining_unassigned']} dona\n"
        return send_msg(chat_id, resp or "Ombor bo'sh.")

    if role == 'chevar' and text == "📤 Ishni Topshirish":
        assigns = Database.fetch_all("SELECT a.id, b.name, bi.size FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.chevar_id = %s AND a.status = 'accepted'", (chat_id,))
        if not assigns: return send_msg(chat_id, "Topshiriladigan ish yo'q.")
        markup = types.InlineKeyboardMarkup()
        for a in assigns: markup.add(types.InlineKeyboardButton(f"{a['name']} ({a['size']})", callback_data=f"rep_i:{a['id']}"))
        return send_msg(chat_id, "Ishni tanlang:", markup)

    if state == 'rep_q':
        qty = int(text)
        set_user_state(chat_id, 'rep_o', {**data, 'qty': qty})
        # Operations (Rastenka)
        assign = Database.fetch_one("SELECT bi.batch_id, b.product_type_id FROM assignments a JOIN batch_items bi ON a.batch_item_id = bi.id JOIN batches b ON bi.batch_id = b.id WHERE a.id = %s", (data['a_id'],))
        ops = Database.fetch_all("SELECT * FROM operations WHERE product_type_id = %s", (assign['product_type_id'],))
        markup = types.InlineKeyboardMarkup()
        for o in ops: markup.add(types.InlineKeyboardButton(f"{o['name']} ({o['price']} so'm)", callback_data=f"rep_o:{o['id']}"))
        return send_msg(chat_id, "Bajarilgan detalni tanlang:", markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id, data = call.message.chat.id, call.data
    state_data = parse_data(get_user_state(chat_id)['data'])

    if data.startswith("init_b:"):
        t_id = data.split(":")[1]
        set_user_state(chat_id, 'wait_batch_name', {'t_id': t_id})
        bot.delete_message(chat_id, call.message.message_id)
        send_msg(chat_id, "Yangi ish (partiya) nomini kiriting:\n(Masalan: <b>Erkaklar kostyumi</b>)", get_cancel_keyboard())

    elif data.startswith("sel_s:"):
        size = data.split(":")[1]
        state_data['active_size'] = size
        set_user_state(chat_id, 'wait_size_qty', state_data)
        bot.edit_message_text(f"🔢 <b>{size}</b> razmerdan necha dona qo'shiladi?", chat_id, call.message.message_id)

    elif data == "finish_batch":
        if not state_data.get('added'): return bot.answer_callback_query(call.id, "Hech bo'lmasa bitta razmer qo'shing!")
        
        total_qty = sum(state_data['added'].values())
        b_id = Database.execute("INSERT INTO batches (product_type_id, name, total_qty, remaining_in_warehouse) VALUES (%s, %s, %s, %s)", (state_data['t_id'], state_data['name'], total_qty, total_qty))
        for sz, q in state_data['added'].items():
            Database.execute("INSERT INTO batch_items (batch_id, size, total_qty, remaining_unassigned) VALUES (%s, %s, %s, %s)", (b_id, sz, q, q))
        
        set_user_state(chat_id, 'main_menu')
        bot.delete_message(chat_id, call.message.message_id)
        send_msg(chat_id, f"✅ <b>{state_data['name']}</b> muvaffaqiyatli saqlandi!\nJami: {total_qty} dona.", get_main_keyboard('admin'))

    elif data.startswith("view_c:"):
        u_id = data.split(":")[1]
        u = Database.fetch_one("SELECT * FROM users WHERE chat_id = %s", (u_id,))
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📤 Ish berish", callback_data=f"give_ch:{u_id}"))
        bot.edit_message_text(f"👤 <b>Chevar:</b> {u['first_name']}\n📞 <b>Tel:</b> {u['phone']}", chat_id, call.message.message_id, reply_markup=markup, parse_mode='HTML')

    elif data.startswith("give_ch:"):
        u_id = data.split(":")[1]
        items = Database.fetch_all("SELECT bi.id, b.name, bi.size, bi.remaining_unassigned FROM batch_items bi JOIN batches b ON bi.batch_id = b.id WHERE bi.remaining_unassigned > 0")
        markup = types.InlineKeyboardMarkup()
        for i in items: markup.add(types.InlineKeyboardButton(f"{i['name']} ({i['size']})", callback_data=f"give_i:{i['id']}:{u_id}"))
        bot.edit_message_text("Ombordagi ishlardan birini tanlang:", chat_id, call.message.message_id, reply_markup=markup)

    elif data.startswith("give_i:"):
        p = data.split(":")
        set_user_state(chat_id, 'give_qty', {'i_id': p[1], 'u_id': p[2]})
        bot.delete_message(chat_id, call.message.message_id)
        send_msg(chat_id, "Beriladigan dona miqdorini kiriting:", get_cancel_keyboard())

    elif data.startswith("rep_i:"):
        a_id = data.split(":")[1]
        set_user_state(chat_id, 'rep_q', {'a_id': a_id})
        bot.edit_message_text("Necha dona (yoki pachka) topshirmoqchisiz?", chat_id, call.message.message_id)

    elif data.startswith("rep_o:"):
        o_id = data.split(":")[1]
        op = Database.fetch_one("SELECT * FROM operations WHERE id = %s", (o_id,))
        total_sum = state_data['qty'] * float(op['price'])
        Database.execute("INSERT INTO work_logs (chat_id, assignment_id, operation_id, qty, total_price) VALUES (%s, %s, %s, %s, %s)", (chat_id, state_data['a_id'], o_id, state_data['qty'], total_sum))
        set_user_state(chat_id, 'main_menu')
        bot.delete_message(chat_id, call.message.message_id)
        send_msg(chat_id, f"✅ Topshirildi! {total_sum} so'm hisobingizga qo'shildi.", get_main_keyboard('chevar', 'active'))

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
