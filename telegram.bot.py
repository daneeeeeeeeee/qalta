import os
import bcrypt
import telebot
import sqlite3
import datetime
import fitz  # PyMuPDF
import re
from openai import OpenAI
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler

import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))



bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)
DB_PATH = 'qaltauser.db'


def connect_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    name TEXT,
                    password BLOB)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount REAL,
                    category TEXT,
                    date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id))''')
    conn.commit()
    cur.close()
    conn.close()


init_db()


@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('📝 Зарегистрироваться'))
    markup.add(types.KeyboardButton('🔑 Войти'))
    bot.send_message(message.chat.id, 'Привет! Выберите действие:', reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '📝 Зарегистрироваться')
def register(message):
    bot.send_message(message.chat.id, 'Введите ваше имя:')
    bot.register_next_step_handler(message, process_register_name)


def process_register_name(message):
    name = message.text.strip()
    bot.send_message(message.chat.id, 'Введите пароль:')
    bot.register_next_step_handler(message, process_register_password, name)


def process_register_password(message, name):
    password = message.text.strip()
    conn = connect_db()
    cur = conn.cursor()

    # Хешируем пароль как байты (BLOB)
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    try:
        cur.execute("INSERT INTO users (telegram_id, name, password) VALUES (?, ?, ?)",
                    (message.from_user.id, name, hashed))
        conn.commit()
        bot.send_message(message.chat.id, '✅ Регистрация прошла успешно! Теперь вы можете войти в систему.')
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, '❌ Этот Telegram ID уже зарегистрирован! Попробуйте войти.')

    cur.close()
    conn.close()



@bot.message_handler(func=lambda message: message.text == '🔑 Войти')
def login(message):
    bot.send_message(message.chat.id, 'Введите ваше имя:')
    bot.register_next_step_handler(message, process_login)


def process_login(message):
    name = message.text.strip()
    bot.send_message(message.chat.id, 'Введите пароль:')
    bot.register_next_step_handler(message, lambda msg: check_login(msg, name))


def check_login(message, name):
    password = message.text.strip()
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT id, password FROM users WHERE name = ?", (name,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    # В базе пароль хранится как байты, без .encode()
    if user and bcrypt.checkpw(password.encode('utf-8'), user[1]):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton('💰 Добавить доход'))
        markup.add(types.KeyboardButton('📉 Добавить расход'))
        markup.add(types.KeyboardButton('📊 Посмотреть статистику'))
        bot.send_message(message.chat.id, '✅ Вход выполнен!', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, '❌ Неверные данные, попробуйте снова.')


@bot.message_handler(func=lambda message: message.text == '💰 Добавить доход')
def add_income(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    categories = ['Основные виды доходов', 'Дополнительные доходы', 'Разовые доходы', '⬅️ Назад']
    for category in categories:
        markup.add(types.KeyboardButton(category))
    bot.send_message(message.chat.id, 'Выберите категорию дохода:', reply_markup=markup)
    bot.register_next_step_handler(message, process_income_category)





def process_income_category(message):
    category = message.text.strip()

    if category == '⬅️ Назад':
        main_menu(message)  # Возвращаем в главное меню
        return

    subcategories = {
        'Основные виды доходов': ['Зарплата', 'Бонусы и премии', 'Пенсия', 'Стипендия'],
        'Дополнительные доходы': ['Фриланс', 'Продажа товаров/услуг', 'Аренда недвижимости', 'Инвестиции', 'Дивиденды', 'Проценты по вкладам'],
        'Разовые доходы': ['Возврат долгов', 'Наследство', 'Подарки и выигрыши', 'Кэшбэк и скидки']
    }

    if category in subcategories:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for subcategory in subcategories[category]:
            markup.add(types.KeyboardButton(subcategory))
        markup.add(types.KeyboardButton('⬅️ Назад'))
        bot.send_message(message.chat.id, 'Выберите подкатегорию дохода:', reply_markup=markup)
        bot.register_next_step_handler(message, process_income_subcategory, category)
    else:
        bot.send_message(message.chat.id, 'Введите сумму дохода:')
        bot.register_next_step_handler(message, save_income, category)


def process_income_subcategory(message, category):
    subcategory = message.text.strip()

    if subcategory == '⬅️ Назад':
        add_income(message)  # Возвращаем в выбор категории доходов
        return

    bot.send_message(message.chat.id, 'Введите сумму дохода:')
    bot.register_next_step_handler(message, save_income, subcategory)

def save_income(message, category):
    try:
        amount = float(message.text.strip())
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_income:{category}:{amount}"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        bot.send_message(message.chat.id, f"Вы уверены, что хотите добавить доход {amount} в категорию \"{category}\"?", reply_markup=markup)
    except ValueError:
        bot.send_message(message.chat.id, '❌ Введите корректную сумму!')
        bot.register_next_step_handler(message, save_income, category)

def main_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('💰 Добавить доход'))
    markup.add(types.KeyboardButton('📉 Добавить расход'))
    markup.add(types.KeyboardButton('📊 Посмотреть статистику'))
    bot.send_message(message.chat.id, 'Выберите действие:', reply_markup=markup)




@bot.message_handler(func=lambda message: message.text == '📉 Добавить расход')
def add_expense(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    categories = ['📌 Обязательные расходы', '📌 Переменные расходы', '📌 Разовые расходы', '📌 Финансовые обязательства', '⬅️ Назад']
    for category in categories:
        markup.add(types.KeyboardButton(category))
    bot.send_message(message.chat.id, 'Выберите категорию расхода:', reply_markup=markup)
    bot.register_next_step_handler(message, process_expense_category)

def process_expense_category(message):
    category = message.text.strip()

    if category == '⬅️ Назад':
        main_menu(message)  # Здесь вызывали несуществующую функцию
        return


    subcategories = {
        '📌 Обязательные расходы': ['🏠 Жилье', '🚗 Транспорт', '🍽️ Еда', '📱 Связь и интернет', '💊 Здоровье', '👨‍👩‍👧‍👦 Семья и дети'],
        '📌 Переменные расходы': ['🎉 Развлечения', '🛍️ Одежда и обувь', '✈️ Путешествия', '📚 Образование'],
        '📌 Разовые расходы': ['🎁 Подарки и праздники', '🏠 Покупки для дома', '🐶 Домашние животные'],
        '📌 Финансовые обязательства': ['💳 Кредиты и долги', '💰 Инвестиции и накопления']
    }

    if category in subcategories:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for subcategory in subcategories[category]:
            markup.add(types.KeyboardButton(subcategory))
        markup.add(types.KeyboardButton('⬅️ Назад'))
        bot.send_message(message.chat.id, 'Выберите подкатегорию расхода:', reply_markup=markup)
        bot.register_next_step_handler(message, process_expense_subcategory, category)
    else:
        bot.send_message(message.chat.id, 'Введите сумму расхода:')
        bot.register_next_step_handler(message, save_expense, category)

def process_expense_subcategory(message, category):
    subcategory = message.text.strip()
    if subcategory == '⬅️ Назад':
        add_expense(message)
    else:
        bot.send_message(message.chat.id, 'Введите сумму расхода:')
        bot.register_next_step_handler(message, save_expense, subcategory)

def save_expense(message, category):
    try:
        amount = float(message.text.strip())
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_expense:{category}:{amount}"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
        bot.send_message(message.chat.id, f"Вы уверены, что хотите добавить расход {amount} в категорию \"{category}\"?", reply_markup=markup)
    except ValueError:
        bot.send_message(message.chat.id, '❌ Введите корректную сумму!')
        bot.register_next_step_handler(message, save_expense, category)



@bot.message_handler(func=lambda message: message.text == '📊 Посмотреть статистику')
def show_statistics(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('🗓 Отчет за неделю'))
    markup.add(types.KeyboardButton('📅 Отчет за месяц'))
    markup.add(types.KeyboardButton('⬅️ Назад'))  # Кнопка "Назад"
    bot.send_message(message.chat.id, 'Выберите период для отчета:', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '⬅️ Назад')
def back_to_main_menu(message):
    main_menu(message)  # Возвращаем в главное меню


@bot.message_handler(func=lambda message: message.text == '🗓 Отчет за неделю')
def show_week_report(message):
    conn = connect_db()
    cur = conn.cursor()

    week_start = datetime.datetime.now() - datetime.timedelta(days=7)
    cur.execute("""
        SELECT SUM(amount) FROM transactions 
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) 
        AND date >= ?
    """, (message.from_user.id, week_start.strftime('%Y-%m-%d')))
    income = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT SUM(amount) FROM transactions 
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) 
        AND date >= ?
        AND type = 'расход'
    """, (message.from_user.id, week_start.strftime('%Y-%m-%d')))
    expense = cur.fetchone()[0] or 0

    balance = income - expense

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⬅️ Назад'))  # Кнопка "Назад"
    bot.send_message(message.chat.id, f"📅 Отчет за неделю:\n💰 Доход: {income} $\n📉 Расход: {expense} $\n💵 Баланс: {balance} $", reply_markup=markup)
    cur.close()
    conn.close()

@bot.message_handler(func=lambda message: message.text == '📅 Отчет за месяц')
def show_month_report(message):
    conn = connect_db()
    cur = conn.cursor()

    month_start = datetime.datetime.now().replace(day=1)
    cur.execute("""
        SELECT SUM(amount) FROM transactions 
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) 
        AND date >= ?
    """, (message.from_user.id, month_start.strftime('%Y-%m-%d')))
    income = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT SUM(amount) FROM transactions 
        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) 
        AND date >= ?
        AND type = 'расход'
    """, (message.from_user.id, month_start.strftime('%Y-%m-%d')))
    expense = cur.fetchone()[0] or 0

    balance = income - expense

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('⬅️ Назад'))  # Кнопка "Назад"
    bot.send_message(message.chat.id, f"📅 Отчет за месяц:\n💰 Доход: {income} $\n📉 Расход: {expense} $\n💵 Баланс: {balance} $", reply_markup=markup)
    cur.close()
    conn.close()


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_income") or call.data.startswith("confirm_expense") or call.data == "cancel")
def confirm_transaction(call):
    if call.data == "cancel":
        bot.send_message(call.message.chat.id, "❌ Операция отменена.")
        main_menu(call.message)
        return

    action, category, amount = call.data.split(":")
    amount = float(amount)
    user_id = call.from_user.id

    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
    user = cur.fetchone()

    if user:
        transaction_type = "доход" if action == "confirm_income" else "расход"
        cur.execute("INSERT INTO transactions (user_id, type, amount, category, date) VALUES (?, ?, ?, ?, DATE('now'))",
                    (user[0], transaction_type, amount, category))
        conn.commit()
        bot.send_message(call.message.chat.id, f"✅ {transaction_type.capitalize()} в категории \"{category}\" добавлен!")
    else:
        bot.send_message(call.message.chat.id, "❌ Ошибка: пользователь не найден!")

    cur.close()
    conn.close()
    main_menu(call.message)


@bot.message_handler(commands=['users'])
def show_users(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этой команде.")
        return

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT telegram_id, name, password FROM users")
    users = cur.fetchall()

    cur.close()
    conn.close()

    if not users:
        bot.send_message(message.chat.id, "📭 В базе данных нет пользователей.")
        return

    user_list = "👥 Список пользователей:\n" + "━━━━━━━━━━━━━━━━━━\n"
    for telegram_id, name, password in users:
        user_list += f"🆔 ID: {telegram_id}\n👤 Имя: {name}\n🔑 Пароль: {password}\n"
        user_list += "━━━━━━━━━━━━━━━━━━\n"

    bot.send_message(message.chat.id, user_list, parse_mode="Markdown")



@bot.message_handler(content_types=['document'])
def handle_pdf(message):
    if not message.document.mime_type == 'application/pdf':
        bot.reply_to(message, "Пожалуйста, отправьте PDF-файл.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{message.document.file_name}"
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)

    bot.send_message(message.chat.id, "📄 Обрабатываю чек...")

    try:
        text = extract_text_from_pdf(file_path)
        amount = extract_amount(text)

        if amount is None:
            bot.send_message(message.chat.id, "❗ Не удалось извлечь сумму из файла.")
            return

        user_id = message.from_user.id
        conn = connect_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
        user = cur.fetchone()

        if not user:
            bot.send_message(message.chat.id, "❌ Вы не зарегистрированы в системе.")
            return

        db_user_id = user[0]

        # Распознаём тип операции по ключевым словам
        if "зачисление" in text.lower() or "пополнение" in text.lower():
            transaction_type = "доход"
            category = "Платёж по выписке"
        elif "перевод" in text.lower() or "снятие" in text.lower():
            transaction_type = "расход"
            category = "Перевод по выписке"
        else:
            transaction_type = "доход"
            category = "Неопределено"

        cur.execute("""
            INSERT INTO transactions (user_id, type, amount, category, date)
            VALUES (?, ?, ?, ?, DATE('now'))
        """, (db_user_id, transaction_type, amount, category))

        conn.commit()
        cur.close()
        conn.close()

        bot.send_message(message.chat.id, f"✅ {transaction_type.capitalize()} {amount}₸ добавлен в категорию \"{category}\"")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при обработке: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# 🔍 Вспомогательные функции

def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def extract_amount(text):
    matches = re.findall(r'[+-]?\d+[.,]?\d*', text)
    if matches:
        return float(matches[0].replace(',', '.'))
    return None

def analyze_with_gpt(text):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты финансовый аналитик. У тебя есть банковская выписка пользователя. "
                    "Проанализируй её и представь отчёт в следующей структуре, БЕЗ использования символов форматирования вроде *, #, - и других. "
                    "Пиши чистый текст, понятный человеку. Вот структура:\n\n"

                    "Доходы:\n"
                    "Основные виды доходов:\n"
                    "1. Зарплата: ...\n"
                    "2. Бонусы и премии: ...\n"
                    "(если нет — просто не указывай)\n\n"

                    "Дополнительные доходы:\n"
                    "...\n\n"

                    "Разовые доходы:\n"
                    "...\n\n"

                    "Расходы:\n"
                    "Обязательные расходы:\n"
                    "1. Жилье: ...\n"
                    "2. Транспорт: ...\n"
                    "...\n\n"

                    "Переменные расходы:\n"
                    "...\n\n"

                    "Разовые расходы:\n"
                    "...\n\n"

                    "Финансовые обязательства:\n"
                    "...\n\n"

                    "Частые траты:\n"
                    "1. ...\n"
                    "2. ...\n\n"

                    "Финансовые рекомендации:\n"
                    "1. ...\n"
                    "2. ...\n"
                    "3. ...\n"
                    "4. ...\n"
                )
            },
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()



# Остальная логика бота (доходы, расходы, отчеты, напоминания) оставляется без изменений и добавляется ниже.
# Убедись, что ты не определяешь снова handle_pdf и не хранишь пароли в открытом виде.

if __name__ == "__main__":
    print("🤖 Бот запущен и ждёт PDF-файлы...")



















def send_reminders():
    conn = connect_db()
    cur = conn.cursor()

    # Получаем всех пользователей
    cur.execute("SELECT telegram_id FROM users")
    users = cur.fetchall()

    cur.close()
    conn.close()

    for user in users:
        bot.send_message(user[0], "💡 Не забудьте записать свои доходы и расходы за сегодня!")

scheduler = BackgroundScheduler()
scheduler.add_job(send_reminders, 'cron', hour=15, minute=10)
scheduler.start()

bot.polling(none_stop=True)