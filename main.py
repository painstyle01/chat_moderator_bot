from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils import exceptions
import mysql.connector
import time
import asyncio
import config
import logging
import datetime
import traceback
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# Init main classes
db = mysql.connector.connect(host=config.db_host, user=config.db_user, password=config.db_pass, database=config.db_name)
db.autocommit = True
c = db.cursor(buffered=True)
db.close()
logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.bot_token)
dp = Dispatcher(bot)

read_only = types.ChatPermissions(can_send_messages=False, can_send_other_messages=False, can_send_polls=False,
                                 can_send_media_messages=False, can_invite_users=False)

allow = types.ChatPermissions(can_send_messages=True, can_send_other_messages=True, can_send_polls=True,
                              can_send_media_messages=True, can_invite_users=True)
# ============
scheduler = AsyncIOScheduler()

async def banNewMember(chat_id, user_obj):
    db.connect()
    await bot.restrict_chat_member(chat_id, user_obj.id, read_only)
    b1 = types.InlineKeyboardButton("Я не бот", callback_data="{}".format(user_obj.id))
    kb = types.InlineKeyboardMarkup(row_width=1).add(b1)
    c.execute("SELECT welcome_message FROM config WHERE id=1")
    msg = c.fetchone()[0]
    m = await bot.send_message(chat_id,
                           msg.format(f"[{user_obj.first_name}](tg://user?id={user_obj.id})"),
                           reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
    db.close()
    await asyncio.sleep(60)
    user = await bot.get_chat_member(chat_id, user_obj.id)
    if user.can_send_messages != True:
        await bot.delete_message(chat_id, m.message_id)
        await bot.kick_chat_member(chat_id, user_obj.id, time.time() + 11)
    else:
        await bot.delete_message(chat_id, m.message_id)

async def autopost(chats):
    db.connect()
    c.execute("SELECT autopostt FROM config WHERE id=1")
    msg = c.fetchone()[0]
    for chat in chats:
        try:
            await asyncio.sleep(0.5)
            await bot.send_message(chat, msg, parse_mode="Markdown")
        except Exception as e:
            print(e)

scheduler.add_job(autopost, 'interval', hours=config.autopost_interval_hours, args=[config.autopost_chat_id])
scheduler.start()

@dp.message_handler(commands=['post'])
async def post(message):
    await bot.delete_message(message.chat.id, message.message_id)
    await autopost(config.autopost_chat_id)

@dp.callback_query_handler()
async def call_handler(call):
    if call.data == "welcome_message":
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        db.connect()
        c.execute("SELECT welcome_message FROM config WHERE id=1")
        d = c.fetchone()[0]
        await bot.send_message(call.message.chat.id, f"Текущее приветствие: {d}\n\nНапишите новое приветствие.")
        c.execute("UPDATE users SET step='welcome_text' WHERE user_id={}".format(call.from_user.id))
        return True
    if call.data == "add_hint":
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        db.connect()
        await bot.send_message(call.message.chat.id, f"Введите вашу подсказку в формате:\n\nСлово - текст для подсказки.")
        c.execute("UPDATE users SET step='hint_text' WHERE user_id={}".format(call.from_user.id))
        return True
    if call.data == "remove_hint":
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        db.connect()
        c.execute("SELECT * FROM hints")
        s = ""
        for item in c.fetchall():
            s += f"{item[0]} - {item[1]}\n"
        await bot.send_message(call.message.chat.id, f"Ваши подсказки:\n\n{s}Введите слово которое хотите удалить.")
        c.execute("UPDATE users SET step='hint_delete' WHERE user_id={}".format(call.from_user.id))
        return True
    if call.data == "autopost_message":
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        db.connect()
        c.execute("SELECT autopostt FROM config WHERE id=1")
        d = c.fetchone()[0]
        await bot.send_message(call.message.chat.id, f"Текущее сообщение на автопостинг: {d}\n\nНапишите новое сообщение.")
        c.execute("UPDATE users SET step='autopost_text' WHERE user_id={}".format(call.from_user.id))
        return True
    if call.data == "filter_words":
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        db.connect()
        c.execute("SELECT ban_words FROM config WHERE id=1")
        d = c.fetchone()[0]
        await bot.send_message(call.message.chat.id,
                               f"Текущий словарь: {d}\n\nНапишите новый словать в формате\nслово1 слово2 слово3")
        c.execute("UPDATE users SET step='filter_text' WHERE user_id={}".format(call.from_user.id))
        return True
    try:
        d = call.data
        arr = d.split(" ")
        db.connect()
        c.execute(f"SELECT * FROM banhammer WHERE reported_id='{arr[1]}'")
        f = c.fetchall()
        reported_user = f[0][1]
        report_chat = int(f[0][4])
        reported_message = f[0][2]
        solve = None
        u = await bot.get_chat_member(report_chat, reported_user)
        u2 = await bot.get_chat_member(report_chat, f[0][5])
        if arr[0] == "rof":
            await bot.delete_message(report_chat, reported_message)
            await bot.restrict_chat_member(report_chat, reported_user, read_only)
            await bot.send_message(report_chat,
                                   f"[{u.user.first_name}](tg://user?id={u.user.id}) был поставлен RO навсегда по жалобе [{u2.user.first_name}](tg://user?id={u2.user.id})",
                                   parse_mode="Markdown")
            solve = "поставил ReadOnly навсегда"
        if arr[0] == "rod":
            await bot.delete_message(report_chat, reported_message)
            await bot.restrict_chat_member(report_chat, reported_user, read_only, until_date=datetime.datetime.now() + datetime.timedelta(days=1))
            await bot.send_message(report_chat,
                                   f"[{u.user.first_name}](tg://user?id={u.user.id}) был поставлен RO 1 день по жалобе [{u2.user.first_name}](tg://user?id={u2.user.id})",
                                   parse_mode="Markdown")
            solve = "поставил ReadOnly на день"
        if arr[0] == "roh":
            await bot.delete_message(report_chat, reported_message)
            await bot.restrict_chat_member(report_chat, reported_user, read_only, until_date=datetime.datetime.now() + datetime.timedelta(hours=1))
            await bot.send_message(report_chat,
                                   f"[{u.user.first_name}](tg://user?id={u.user.id}) был поставлен RO на 1 час по жалобе [{u2.user.first_name}](tg://user?id={u2.user.id})",
                                   parse_mode="Markdown")
            solve = "поставил ReadOnly на час"
        if arr[0] == "ban":
            await bot.delete_message(report_chat, reported_message)
            await bot.kick_chat_member(report_chat, reported_user)
            await bot.send_message(report_chat, f"[{u.user.first_name}](tg://user?id={u.user.id}) был забанен по жалобе [{u2.user.first_name}](tg://user?id={u2.user.id})", parse_mode="Markdown")
            solve = "забанил"
        if arr[0] == "leave":
            solve = "оставил"
            pass
        for object in f:
            await bot.edit_message_text(f"[{call.from_user.first_name}](tg://user?id={call.from_user.id}) {solve} [{u.user.first_name}](tg://user?id={u.user.id})", object[0], object[3], parse_mode="Markdown")
        c.execute(f"DELETE FROM banhammer WHERE reported_id={arr[1]}")
        db.close()
    except Exception as e:
        traceback.print_exc()
        try:
            if call.from_user.id != int(call.data):
                await bot.answer_callback_query(call.id, "Это не твоя кнопка.")
            else:
                await bot.answer_callback_query(call.id, "Вы вошли в чат, продуктивного общения!", show_alert=True)
                await bot.restrict_chat_member(call.message.chat.id, call.from_user.id, allow)
        except Exception as e:
            print(e)

@dp.message_handler(commands=['start'])
async def start_handler(message):
    db.connect()
    c.execute(f"INSERT INTO users VALUES('{message.from_user.id}', 'main_menu')")
    db.close()

@dp.message_handler(commands=["id"])
async def getId(message):
    await bot.send_message(message.chat.id, message.chat.id)

@dp.message_handler(commands=['ban'])
async def admin_panel(message):
    if message.chat.type == "private":
        try:
            t = message.text
            arr = t.split(" ")
            for chat in config.autopost_chat_id:
                try:
                    await bot.kick_chat_member(chat, arr[1])
                except:
                    pass
            await bot.send_message(message.chat.id, "Успешно")
        except exceptions.BadRequest as e:
            traceback.print_exc()
            await bot.send_message(message.chat.id, f"{e}")
        except IndexError:
            await bot.send_message(message.chat.id, f"Айди не найден")

@dp.message_handler(commands=['admin'])
async def admin_panel(message):
    if message.chat.type == "private":
        if message.from_user.id in config.total_admin:
            b1 = types.InlineKeyboardButton("Приветствие",
                                            callback_data="welcome_message")
            b2 = types.InlineKeyboardButton("Автопост",
                                            callback_data="autopost_message")
            b3 = types.InlineKeyboardButton("Бан слова",
                                            callback_data="filter_words")
            b4 = types.InlineKeyboardButton("Добавить подсказку",
                                            callback_data="add_hint")
            b5 = types.InlineKeyboardButton("Удалить подсказку",
                                            callback_data="remove_hint")
            kb = types.InlineKeyboardMarkup(row_width=2).add(b1, b2, b3, b4, b5)
            await bot.send_message(message.chat.id, "Что хотите изменить?", reply_markup=kb)

@dp.message_handler(commands=['report'])
async def get_report(message):
    print(message)
    await bot.delete_message(message.chat.id, message.message_id)
    if message.reply_to_message:
        db.connect()
        admins = await bot.get_chat_administrators(message.chat.id)
        for admin in admins:
            if admin.user.is_bot:
                pass
            else:
                try:
                    await asyncio.sleep(1)
                    b1 = types.InlineKeyboardButton("Забанить", callback_data="ban {}".format(message.reply_to_message.from_user.id))
                    b2 = types.InlineKeyboardButton("ReadOnly навсегда", callback_data="rof {}".format(message.reply_to_message.from_user.id))
                    b3 = types.InlineKeyboardButton("ReadOnly на сутки", callback_data="rod {}".format(message.reply_to_message.from_user.id))
                    b4 = types.InlineKeyboardButton("ReadOnly на час", callback_data="roh {}".format(message.reply_to_message.from_user.id))
                    b5 = types.InlineKeyboardButton("Оставить", callback_data="leave {}".format(message.reply_to_message.from_user.id))
                    kb = types.InlineKeyboardMarkup(row_width=2).add(b1,b2,b3,b4,b5)
                    print(f"https://t.me/{message.chat.username}/{message.reply_to_message.message_id}")
                    m = await bot.send_message(admin.user.id, f"Жалоба от [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n\n[Сообщение](https://t.me/{message.chat.username}/{message.reply_to_message.message_id})", reply_markup=kb, parse_mode="Markdown")
                    c.execute(f"INSERT INTO banhammer VALUES('{admin.user.id}', '{message.reply_to_message.from_user.id}','{message.reply_to_message.message_id}', '{m.message_id}', '{message.chat.id}', {message.from_user.id})")
                except:
                    await bot.send_message(config.total_admin[0], f"Не могу отправить сообщение [{admin.user.first_name}](tg://user?id={admin.user.id})", parse_mode='Markdown')
    else:
        m = await bot.send_message(message.chat.id, "Эта команда работает только в ответ на сообщение.")
        await asyncio.sleep(10)
        await bot.delete_message(message.chat.id, m.message_id)

@dp.message_handler(content_types=['new_chat_members'])
async def newMember(message):
    for user in message.new_chat_members:
        if user.is_bot:
            await bot.kick_chat_member(message.chat.id, user.id, time.time() + 31)
        else:
            asyncio.gather(banNewMember(message.chat.id, user))

@dp.message_handler()
async def text_handler(message):
    if message.chat.type == "private":
        db.connect()
        c.execute(f"SELECT step FROM users WHERE user_id={message.chat.id}")
        d = c.fetchone()[0]
        if d == "hint_text":
            try:
                t = message.text
                n = t.split(" - ")
                c.execute(f"INSERT INTO hints VALUES(\'{n[0]}\',\'{n[1]}\')")
                await bot.send_message(message.chat.id, "Подсказка добавлена")
                c.execute("UPDATE users SET step='main_menu' WHERE user_id='{}'".format(message.from_user.id))
            except:
                await bot.send_message(message.chat.id, 'Ошибка. Формат сообщения:\nСлово - текст подсказки.')
        if d == 'hint_delete':
            t = message.text
            c.execute(f"DELETE FROM hints WHERE word='{t.lower()}'")
            await bot.send_message(message.chat.id, "Подсказка удалена")
            c.execute("UPDATE users SET step='main_menu' WHERE user_id='{}'".format(message.from_user.id))
        if d == "filter_text":
            txt = message.text
            r = txt.replace(" ", "|")
            c.execute(f"UPDATE config SET ban_words=\'{r}\'")
            await bot.send_message(message.chat.id, f"Новый словарь - {r}")
            c.execute("UPDATE users SET step='main_menu' WHERE user_id='{}'".format(message.from_user.id))
        if d == "welcome_text":
            txt = message.text
            c.execute(f"UPDATE config SET welcome_message=\'{txt}\'")
            await bot.send_message(message.chat.id, f"Новое приветствие установлено", parse_mode="Markdown")
            c.execute("UPDATE users SET step='main_menu' WHERE user_id='{}'".format(message.from_user.id))
        if d == "autopost_text":
            txt = message.text
            c.execute(f"UPDATE config SET autopostt=\'{txt}\'")
            await bot.send_message(message.chat.id, f"Новое сообщение на автопост установлено", parse_mode="Markdown")
            c.execute("UPDATE users SET step='main_menu' WHERE user_id='{}'".format(message.from_user.id))
        db.close()
    else:
        db.connect()
        c.execute("SELECT ban_words FROM config WHERE id='1'")
        standart_words = "привет|пока"
        ban_list = standart_words
        data = c.fetchone()
        text = message.text
        caption = message.caption
        spl = text.split(" ")
        if data[0] is not None:
            ban_list = data[0]
        print(ban_list)
        if message.text is None:
            s = re.search(ban_list.lower(), caption.lower())
            url = re.search(r'[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
                            caption.lower())
        else:
            s = re.search(ban_list.lower(), text.lower())
            url = re.search(r'[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
                            text.lower())
        if url != None:
            pass #await bot.delete_message(message.chat.id, message.message_id)
        if s != None:
            await bot.delete_message(message.chat.id, message.message_id)
        else:
            for word in spl:
                print(word)
                c.execute(f"SELECT hint FROM hints WHERE word='{word.lower()}'")
                h = c.fetchone()
                if h is not None:
                    print(h[0])
                    await message.reply(h[0], parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    pass
        db.close()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)  # CHANGE TO FALSE IF WRECKLESS
