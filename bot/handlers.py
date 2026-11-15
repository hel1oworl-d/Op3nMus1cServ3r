import os
import uuid
import html
import aiomysql
from pathlib import Path
from datetime import date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
import database as db
import keyboards as kb
import services
import lava_service

router = Router()

RELEASES_DIR = Path("/root/Op3nMus1cServ3r/uploads/releases")
RELEASES_DIR.mkdir(parents=True, exist_ok=True)

PLATFORM_EXTENSIONS = {
    "Android": [".apk", ".aab", ".zip"],
    "Windows": [".exe", ".msi", ".zip"],
    "Linux": [".deb", ".rpm", ".appimage", ".tar.gz", ".tar.xz", ".zip"],
    "macOS": [".dmg", ".pkg", ".zip", ".tar.gz"],
    "iOS": [".ipa", ".zip"],
}

SUB_PRICES = {
    "lite": {
        "name": "Lite",
        "1m": {"days": 30, "price": 90},
        "3m": {"days": 90, "price": 270},
        "1y": {"days": 365, "price": 1095},
    },
    "burzhuy": {
        "name": "Burzhuy",
        "1m": {"days": 30, "price": 150},
        "3m": {"days": 90, "price": 450},
        "1y": {"days": 365, "price": 1825},
    }
}

class UploadTrackState(StatesGroup):
    waiting_for_file = State()
    waiting_for_title = State()
    waiting_for_artist = State()
    waiting_for_playlist_choice = State()
    waiting_for_new_playlist_name = State()

class CreatePlaylistFSM(StatesGroup):
    waiting_for_title = State()

class AddSubAdminFSM(StatesGroup):
    waiting_for_user_input = State()
    waiting_for_custom_days = State()

def render_main_menu_text(user_data: dict) -> str:
    if not user_data:
        return "🎧 <b>Главное меню Hel1oMus1c</b>"
    fname = user_data.get("first_name") or ""
    uname = f"@{user_data['username']}" if user_data.get("username") else ""
    display_name = f"{fname} {uname}".strip() or "Пользователь"
    sub_date = user_data.get("expires_at")
    sub_plan = (user_data.get("sub_plan") or "lite").lower()

    if sub_date:
        today = date.today()
        if sub_date >= today:
            days_left = (sub_date - today).days
            badge = "👑 Burzhuy" if sub_plan == "burzhuy" else "⚡ Lite"
            sub_status = f"✅ Активна [{badge}] (осталось {days_left} дн.)"
        else:
            sub_status = f"❌ Истекла ({sub_date.strftime('%d.%m.%Y')})"
    else:
        sub_status = "⚪ Не оформлена"

    lines = [
        "🎧 <b>Главное меню Hel1oMus1c</b>",
        "",
        f"Добро пожаловать, {html.escape(display_name)}!",
        "",
        f"📚 <b>Ваша подписка:</b> {sub_status}",
        f"🎵 <b>Загружено треков:</b> {user_data.get('track_count', 0)}",
        f"📁 <b>Плейлистов:</b> {user_data.get('playlist_count', 0)}"
    ]
    nl = chr(10)
    return nl.join(lines)

@router.message(CommandStart(), StateFilter("*"))

async def handle_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    tg_id = message.from_user.id
    raw_text = message.text or ""
    print(f"DEBUG: Получен /start: '{raw_text}' от {tg_id}", flush=True)

    internal_id, is_new = await db.upsert_user(
        tg_id=tg_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    if is_new:
        uname = f"@{message.from_user.username}" if message.from_user.username else "<i>нет</i>"
        fname = html.escape(message.from_user.first_name or "Без имени")
        notify_text = (
            "🔔 <b>Новый пользователь в боте!</b>\n\n"
            f"• Имя: <b>{fname}</b>\n• Юзернейм: {uname}\n"
            f"• Telegram ID: <code>{tg_id}</code>\n• ID в базе: <code>#{internal_id}</code>"
        )
        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(chat_id=admin_id, text=notify_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    parts = raw_text.split()
    if len(parts) > 1:
        param = parts[1].strip()
        if param.startswith("auth_") or len(param) == 8:
            challenge = param
            ch_data = await db.approve_auth_challenge(tg_id, challenge)
            if ch_data:
                dev = html.escape(ch_data.get("device_name") or "Новое устройство")
                ver = html.escape(ch_data.get("client_version") or "1.0.0")
                await message.answer(
                    f"🛡️ <b>Вход в Hel1oMus1c подтверждён!</b>\n\n"
                    f"📱 Устройство: <b>{dev}</b>\n"
                    f"📦 Версия клиента: <code>{ver}</code>\n\n"
                    f"<i>Вы успешно вошли в аккаунт. Теперь можете вернуться в приложение.</i>",
                    parse_mode=ParseMode.HTML
                )
                return
            else:
                await message.answer(
                    "❌ <b>Ошибка входа</b>\n\n"
                    "Запрос на авторизацию устарел, был отклонён или уже использован.\n"
                    "Пожалуйста, повторите вход в приложении.",
                    parse_mode=ParseMode.HTML
                )
                return
        elif "login_" in param:
            await message.answer(
                "⚠️ <b>Вход заблокирован: Старая версия приложения</b>\n\n"
                "Ваша версия приложения Hel1oMus1c устарела и больше не поддерживается по соображениям безопасности.\n\n"
                "Пожалуйста, скачайте актуальное обновление в разделе 📥 Скачать клиент.",
                parse_mode=ParseMode.HTML
            )
            return

    user_data = await db.get_user_profile(tg_id)
    is_admin = await db.is_user_admin(tg_id)
    await message.answer(render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "menu:main", StateFilter("*"))
async def handle_return_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    tg_id = call.from_user.id
    user_data = await db.get_user_profile(tg_id)
    is_admin = await db.is_user_admin(tg_id)
    await call.message.edit_text(render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)
    await call.answer()

@router.message(Command("cancel"), StateFilter("*"))
@router.callback_query(F.data == "upload:cancel", StateFilter("*"))
async def handle_cancel_action(event: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "track_id" not in data and "file_path" in data:
        services.remove_temp_file(data.get("file_path"))
    await state.clear()
    tg_id = event.from_user.id
    user_data = await db.get_user_profile(tg_id)
    is_admin = await db.is_user_admin(tg_id)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)
        await event.answer("Отменено")
    else:
        await event.answer(render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "menu:account")
async def handle_account(call: CallbackQuery):
    data = await db.get_user_profile(call.from_user.id)
    if not data:
        await call.answer("Профиль не найден.", show_alert=True)
        return

    sub_date = data.get("expires_at")
    sub_plan = (data.get("sub_plan") or "lite").lower()
    badge_label = ""
    banner_str = ""

    if sub_date and sub_date >= date.today():
        if sub_plan == "burzhuy":
            badge_label = " 👑 [Burzhuy Member]"
            banner_str = "\n🖼 <b>Баннер профиля:</b> Эксклюзивный баннер активен ✨"
            sub_str = f"✅ Активна (до {sub_date.strftime('%d.%m.%Y')})"
        else:
            badge_label = " ⚡ [Lite Member]"
            sub_str = f"✅ Активна (до {sub_date.strftime('%d.%m.%Y')})"
    elif sub_date:
        sub_str = f"❌ Истекла ({sub_date.strftime('%d.%m.%Y')})"
    else:
        sub_str = "⚪ Нет подписки"

    role_str = "🛡 <b>Администратор</b>" if data.get("is_admin") == 1 else "Обычный"
    uname = f"@{html.escape(data['username'])}" if data.get('username') else "отсутствует"

    # Бейджи администратора
    badges_list = await db.get_user_admin_badges(call.from_user.id)
    badge_lines = []
    for b in badges_list:
        a_name = (b.get("admin_name") or "").strip()
        tg_u = (b.get("tg_username") or "").strip()
        display_admin = a_name if a_name else (tg_u if tg_u else "Администратор")
        badge_lines.append(f"Админ ({html.escape(display_admin)})")
    
    badges_str = ""
    if badge_lines:
        badges_str = f"\n🏷 <b>Бейджи:</b> {', '.join(badge_lines)}"

    text = (
        f"👤 <b>Личный кабинет</b>{badge_label}\n\n"
        f"🆔 <b>ID в системе:</b> <code>{data['id']}</code>\n"
        f"🔗 <b>Username:</b> {uname}\n"
        f"👑 <b>Статус:</b> {role_str}{badges_str}\n"
        f"⭐ <b>Подписка:</b> {sub_str}"
        f"{banner_str}\n\n"
        f"🎵 Треков загружено: <b>{data['track_count']}</b>\n"
        f"📂 Плейлистов: <b>{data['playlist_count']}</b>"
    )
    await call.message.edit_text(text, reply_markup=kb.get_back_to_main_kb(), parse_mode=ParseMode.HTML)
    await call.answer()

# --- Плейлисты и Треки ---

@router.callback_query(F.data == "menu:playlists", StateFilter("*"))
async def handle_playlists_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    playlists = await db.get_user_playlists(call.from_user.id)
    text = "📂 <b>Ваши плейлисты</b>\n\nВыберите плейлист:"
    if not playlists:
        text = "📂 У вас пока нет созданных плейлистов.\nНажмите кнопку ниже, чтобы создать:"
    await call.message.edit_text(text, reply_markup=kb.get_playlists_menu_kb(playlists), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "pl_action:create")
async def handle_pl_create_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(CreatePlaylistFSM.waiting_for_title)
    await call.message.edit_text("📝 Введите <b>название</b> нового плейлиста:\n\n/cancel для отмены", parse_mode=ParseMode.HTML)
    await call.answer()

@router.message(CreatePlaylistFSM.waiting_for_title, F.text)
async def handle_pl_create_save(message: Message, state: FSMContext):
    title = message.text.strip()
    await db.create_user_playlist(message.from_user.id, title)
    await state.clear()
    playlists = await db.get_user_playlists(message.from_user.id)
    await message.answer(f"✅ Плейлист <b>{html.escape(title)}</b> успешно создан!", reply_markup=kb.get_playlists_menu_kb(playlists), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("pl_view:"))
async def handle_pl_view(call: CallbackQuery):
    pl_id = int(call.data.split(":")[1])
    playlist = await db.get_playlist(pl_id, call.from_user.id)
    if not playlist:
        await call.answer("Плейлист не найден.", show_alert=True)
        return
    tracks = await db.get_playlist_tracks(pl_id)
    text = f"📁 Плейлист: <b>{html.escape(playlist['title'])}</b>\n\nВсего треков: <b>{len(tracks)}</b>\n\n"
    text += "<i>В этом плейлисте пока нет треков.</i>" if not tracks else "Нажмите на трек, чтобы прослушать его:"
    await call.message.edit_text(text, reply_markup=kb.get_playlist_view_kb(pl_id, tracks), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data.startswith("pl_action:delete:"))
async def handle_pl_delete(call: CallbackQuery):
    pl_id = int(call.data.split(":")[2])
    success = await db.delete_user_playlist(pl_id, call.from_user.id)
    await call.answer("Плейлист удален!" if success else "Не удалось удалить.")
    playlists = await db.get_user_playlists(call.from_user.id)
    await call.message.edit_text("📂 <b>Ваши плейлисты</b>", reply_markup=kb.get_playlists_menu_kb(playlists), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("track_play:"))
async def handle_track_play(call: CallbackQuery, bot: Bot):
    _, pl_id_str, track_id_str = call.data.split(":")
    pl_id, track_id = int(pl_id_str), int(track_id_str)
    tracks = await db.get_playlist_tracks(pl_id)
    track = next((t for t in tracks if t["id"] == track_id), None)

    if not track:
        await call.answer("Трек не найден.", show_alert=True)
        return

    file_path = track["file_path"]
    if not os.path.exists(file_path):
        await call.answer("❌ Файл физически отсутствует на сервере.", show_alert=True)
        return

    await call.answer("Отправляю трек...")
    await bot.send_audio(
        chat_id=call.from_user.id,
        audio=FSInputFile(file_path, filename=track["file_name"]),
        title=track["title"],
        performer=track["artist"]
    )

    text = (
        f"🎵 <b>Сейчас играет:</b>\n\n"
        f"• Исполнитель: <b>{html.escape(track['artist'])}</b>\n"
        f"• Название: <b>{html.escape(track['title'])}</b>\n\n"
        "Трек отправлен в чат. Если нужно удалить трек полностью — нажмите кнопку ниже:"
    )
    await call.message.edit_text(text, reply_markup=kb.get_track_manage_kb(pl_id, track_id), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("track_action:delete_srv:"))
async def handle_track_delete_server(call: CallbackQuery):
    track_id = int(call.data.split(":")[2])
    is_admin = await db.is_user_admin(call.from_user.id)
    file_path = await db.delete_track_completely(track_id, call.from_user.id, is_admin=is_admin)

    if file_path:
        services.remove_temp_file(file_path)
        await call.answer("Трек полностью удален с сервера!", show_alert=True)
    else:
        await call.answer("Трек не найден или нет прав.", show_alert=True)

    playlists = await db.get_user_playlists(call.from_user.id)
    await call.message.edit_text("📂 <b>Ваши плейлисты</b>", reply_markup=kb.get_playlists_menu_kb(playlists), parse_mode=ParseMode.HTML)

# --- Подписки через Lava.ru ---

@router.callback_query(F.data == "menu:buy_sub")
async def handle_buy_sub_menu(call: CallbackQuery):
    text = (
        "⭐ <b>Тарифные планы подписок Hel1oMus1c</b>\n\n"
        "⚡ <b>Lite — 3 ₽ / день</b>\n"
        "1. Скачивание музыки в клиенте\n"
        "2. Неограниченная выгрузка треков в Telegram\n"
        "3. Специальный значок ⚡ в профиле\n"
        "4. Приоритетная поддержка\n\n"
        "👑 <b>Burzhuy — 5 ₽ / день</b>\n"
        "1. Премиальный статус и значок 👑 в профиле\n"
        "2. Персональный баннер в профиле\n"
        "3. Доступ ко всем Бета-версиям клиента\n"
        "4. Закрытый чат напрямую с разработчиком в TG\n"
        "5. Все привилегии тарифа Lite\n\n"
        "Выберите тариф для оплаты через <b>Lava.ru</b>:"
    )
    await call.message.edit_text(text, reply_markup=kb.get_sub_plan_kb(), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data.startswith("buy_plan:"))
async def handle_buy_sub_plan(call: CallbackQuery):
    plan = call.data.split(":")[1]
    plan_info = SUB_PRICES[plan]
    text = (
        f"⭐ Вы выбрали тариф <b>{plan_info['name']}</b>\n\n"
        "Выберите период подписки:\n"
        f"• 1 месяц (30 дн.) — {plan_info['1m']['price']} ₽\n"
        f"• 3 месяца (90 дн.) — {plan_info['3m']['price']} ₽\n"
        f"• 1 год (365 дн.) — {plan_info['1y']['price']} ₽"
    )
    await call.message.edit_text(text, reply_markup=kb.get_sub_period_kb(plan), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data.startswith("buy_sub_confirm:"))
async def handle_buy_sub_confirm(call: CallbackQuery, bot: Bot):
    _, plan, period = call.data.split(":")
    plan_info = SUB_PRICES[plan]
    item = plan_info[period]
    tg_id = call.from_user.id

    order_id = f"sub_{tg_id}_{uuid.uuid4().hex[:8]}"
    amount = float(item["price"])
    days = int(item["days"])
    comment = f"Hel1oMus1c {plan_info['name']} ({days} дн.)"

    await call.answer("Генерирую счет Lava.ru...")
    invoice_data = await lava_service.create_invoice(amount, order_id, comment)

    if invoice_data and invoice_data.get("url"):
        pay_url = invoice_data["url"]
        invoice_id = invoice_data.get("id", "")
        async with db.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT id FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
                u = await cur.fetchone()
                await cur.execute("""
                    INSERT INTO orders (order_id, invoice_id, user_id, plan, days, amount, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending');
                """, (order_id, invoice_id, u["id"], plan, days, amount))

        pay_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате (Lava.ru)", url=pay_url)],
                [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_lava:{order_id}:{invoice_id}")],
                [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu:buy_sub")]
            ]
        )
        text = (
            f"💳 <b>Счет на оплату в Lava.ru готов!</b>\n\n"
            f"• Тариф: <b>{plan_info['name']}</b> ({days} дн.)\n"
            f"• К оплате: <b>{amount} ₽</b>\n\n"
            "Оплатите по кнопке ниже и затем нажмите <b>«Проверить оплату»</b>."
        )
        await call.message.edit_text(text, reply_markup=pay_kb, parse_mode=ParseMode.HTML)
    else:
        await call.message.edit_text(
            "⚠️ <b>Ошибка платежного шлюза Lava.ru!</b>\n\n"
            "Проверьте настройки LAVA_PROJECT_ID и LAVA_SECRET_KEY в config.py или напишите @Hel1ow0rld.",
            reply_markup=kb.get_back_to_main_kb(),
            parse_mode=ParseMode.HTML
        )

    await call.answer()

@router.callback_query(F.data.startswith("check_lava:"))
async def handle_check_lava_payment(call: CallbackQuery):
    _, order_id, invoice_id = call.data.split(":")
    tg_id = call.from_user.id
    status = await lava_service.check_invoice_status(invoice_id, order_id)

    if status == "success":
        async with db.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM orders WHERE order_id = %s LIMIT 1;", (order_id,))
                order = await cur.fetchone()
                if not order or order["status"] == "completed":
                    await call.answer("Заказ уже выполнен!", show_alert=True)
                    return
                await cur.execute("UPDATE orders SET status = 'completed' WHERE order_id = %s;", (order_id,))

        days = order["days"]
        plan = order["plan"]
        new_expires = await db.extend_user_subscription(tg_id, days, plan=plan)

        user_data = await db.get_user_profile(tg_id)
        is_admin = await db.is_user_admin(tg_id)
        badge = "👑 Burzhuy" if plan == "burzhuy" else "⚡ Lite"
        await call.message.edit_text(
            f"🎉 <b>Оплата через Lava подтверждена!</b>\n\n"
            f"Тариф <b>{badge}</b> активирован!\n"
            f"Подписка активна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n" + render_main_menu_text(user_data),
            reply_markup=kb.get_main_inline_kb(is_admin=is_admin),
            parse_mode=ParseMode.HTML
        )
    else:
        await call.answer("Платеж еще не подтвержден в системе Lava. Попробуйте через полминуты.", show_alert=True)

# --- Скачивание сборок ---

@router.callback_query(F.data == "menu:download_client")
async def handle_download_client(call: CallbackQuery):
    user = await db.get_user_profile(call.from_user.id)
    is_admin = await db.is_user_admin(call.from_user.id)
    plan = (user.get("sub_plan") or "").lower() if user else None
    manual_beta = bool(user.get("beta_access", 0)) if user else False
    
    # Доступ к бета/альфа/testing сборкам: админ, статус beta_access или подписка Burzhuy
    has_beta_access = is_admin or manual_beta or (plan == "burzhuy")

    async with db.db_pool.acquire() as conn:
        async with conn.cursor(db.aiomysql.DictCursor) as cur:
            # Группируем по ветке, версии и платформе
            await cur.execute("""
                SELECT branch_type, version_num, platform, COUNT(*) as count 
                FROM client_builds 
                GROUP BY branch_type, version_num, platform 
                ORDER BY MAX(id) DESC LIMIT 15;
            """)
            groups = await cur.fetchall()
    if not groups:
        await call.answer("Сборок пока нет.", show_alert=True)
        return
    await call.message.edit_text("📱 <b>Скачать клиент Hel1oMus1c</b>\n\nВыберите версию:", reply_markup=kb.get_client_downloads_kb(groups, has_beta_access), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("dl_group:"))
async def handle_download_group(call: CallbackQuery):
    parts = call.data.split(":")
    branch_type = parts[1]
    version_num = parts[2]
    platform = parts[3]
    
    async with db.db_pool.acquire() as conn:
        async with conn.cursor(db.aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM client_builds 
                WHERE branch_type = %s AND version_num = %s AND platform = %s
                ORDER BY id ASC;
            """, (branch_type, version_num, platform))
            builds = await cur.fetchall()
            
    if not builds:
        await call.answer("Сборки не найдены.", show_alert=True)
        return
        
    branch_icon = "🔴" if branch_type == "testing" else ("🟢" if branch_type == "release" else "🟡")
    text = (
        f"📱 <b>{branch_icon} {branch_type.capitalize()} v{version_num} ({platform})</b>\n\n"
        f"Выберите тип сборки для скачивания:"
    )
    await call.message.edit_text(text, reply_markup=kb.get_group_builds_kb(builds), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data.startswith("dl_build_info:"))
async def handle_build_info(call: CallbackQuery):
    build_id = int(call.data.split(":")[1])
    async with db.db_pool.acquire() as conn:
        async with conn.cursor(db.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM client_builds WHERE id = %s LIMIT 1;", (build_id,))
            build = await cur.fetchone()
    if not build or not os.path.exists(build["file_path"]):
        await call.answer("❌ Файл отсутствует на сервере.", show_alert=True)
        return
    
    file_size_bytes = os.path.getsize(build["file_path"])
    size_mb = file_size_bytes / (1024 * 1024)
    can_send_in_tg = file_size_bytes < 50 * 1024 * 1024
    direct_url = f"http://222.167.248.24/api/download/build/{build['id']}"
    badge = kb.get_branch_badge(build["branch_type"], build.get("build_type", "release"))
    group_back = f"{build['branch_type']}:{build['version_num']}:{build['platform']}"
    
    caption = (
        f"📱 <b>Сборка:</b> {badge}\n"
        f"🔢 <b>Версия:</b> <code>{build['version_num']}</code>\n"
        f"💻 <b>Платформа:</b> {build['platform']}\n"
        f"📦 <b>Размер файла:</b> {size_mb:.1f} МБ\n\n"
        f"Вы можете скачать файл по прямой ссылке на высокой скорости или получить его файлом прямо в Telegram (если размер меньше 50 МБ)."
    )
    await call.message.edit_text(
        caption,
        reply_markup=kb.get_build_actions_kb(build["id"], direct_url, can_send_in_tg, group_back),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.callback_query(F.data.startswith("dl_build_file:"))
async def handle_send_build(call: CallbackQuery):
    build_id = int(call.data.split(":")[1])
    async with db.db_pool.acquire() as conn:
        async with conn.cursor(db.aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM client_builds WHERE id = %s LIMIT 1;", (build_id,))
            build = await cur.fetchone()
    if not build or not os.path.exists(build["file_path"]):
        await call.answer("❌ Файл отсутствует на сервере.", show_alert=True)
        return
    
    file_size_bytes = os.path.getsize(build["file_path"])
    if file_size_bytes >= 50 * 1024 * 1024:
        await call.answer("⚠️ Файл больше 50 МБ, Telegram запрещает ботам отправлять такие файлы напрямую. Используйте прямую ссылку!", show_alert=True)
        return
        
    badge = kb.get_branch_badge(build["branch_type"], build.get("build_type", "release"))
    await call.answer("Отправляю файл в чат...")
    await call.message.answer_document(
        document=FSInputFile(build["file_path"], filename=build["file_name"]),
        caption=f"📱 <b>Сборка:</b> {badge}\n🔢 <b>Версия:</b> <code>{build['version_num']}</code>\n💻 <b>Платформа:</b> {build['platform']}",
        parse_mode=ParseMode.HTML
    )

# --- Загрузка треков ---

@router.callback_query(F.data == "menu:upload_track", StateFilter("*"))
async def handle_start_upload(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(UploadTrackState.waiting_for_file)
    await call.message.edit_text("🎵 <b>Отправь аудиофайл</b> (до 20 МБ):\n\n/cancel для отмены", reply_markup=kb.get_cancel_inline_kb(), parse_mode=ParseMode.HTML)
    await call.answer()

@router.message(UploadTrackState.waiting_for_file, F.audio | F.document)
async def handle_receive_file(message: Message, state: FSMContext, bot: Bot):
    media = message.audio or message.document
    if media.file_size and media.file_size > 1024 * 1024 * 1024:
        await message.answer("❌ Файл больше 1 ГБ.")
        return
    msg_wait = await message.answer("⏳ Скачиваю аудиофайл...")
    try:
        filename, filepath = await services.download_media_file(bot, media)
    except Exception as e:
        await msg_wait.edit_text(f"❌ Ошибка: {e}")
        await state.clear()
        return

    title, artist = services.parse_audio_metadata(filepath, media)
    await state.update_data(file_path=str(filepath), file_name=filename, auto_title=title, auto_artist=artist)
    await msg_wait.delete()
    await state.set_state(UploadTrackState.waiting_for_title)
    prompt = f" (из тегов: <code>{html.escape(title)}</code>)" if title else ""
    await message.answer(f"Введи <b>название трека</b> (или <code>-</code> чтобы оставить{prompt or ' Без названия'}):", parse_mode=ParseMode.HTML)

@router.message(UploadTrackState.waiting_for_title, F.text)
async def handle_receive_title(message: Message, state: FSMContext):
    data = await state.get_data()
    val = message.text.strip()
    title = data.get("auto_title") if val == "-" and data.get("auto_title") else ("Без названия" if val == "-" else val)
    await state.update_data(title=title)
    await state.set_state(UploadTrackState.waiting_for_artist)
    prompt = f" (из тегов: <code>{html.escape(data.get('auto_artist'))}</code>)" if data.get("auto_artist") else ""
    await message.answer(f"Укажи <b>исполнителя</b> (или <code>-</code> чтобы оставить{prompt or ' Неизвестный артист'}):", parse_mode=ParseMode.HTML)

@router.message(UploadTrackState.waiting_for_artist, F.text)
async def handle_receive_artist(message: Message, state: FSMContext):
    data = await state.get_data()
    val = message.text.strip()
    artist = data.get("auto_artist") if val == "-" and data.get("auto_artist") else ("Неизвестный артист" if val == "-" else val)
    title = data["title"]
    user_id, track_id = await db.save_track(
        tg_id=message.from_user.id, filename=data["file_name"], filepath=data["file_path"], title=title, artist=artist
    )
    playlists = await db.get_user_playlists(message.from_user.id)
    await state.update_data(track_id=track_id, user_id=user_id, title=title, artist=artist)
    clean_artist, clean_title = html.escape(artist), html.escape(title)

    if not playlists:
        await state.set_state(UploadTrackState.waiting_for_new_playlist_name)
        await message.answer(f"🎵 <b>{clean_artist} — {clean_title}</b> сохранен!\n\nВведите название первого плейлиста:", parse_mode=ParseMode.HTML)
    else:
        await state.set_state(UploadTrackState.waiting_for_playlist_choice)
        await message.answer(f"🎵 <b>{clean_artist} — {clean_title}</b> сохранен!\n\nВыберите плейлист:", reply_markup=kb.get_playlist_selection_keyboard(playlists), parse_mode=ParseMode.HTML)

@router.callback_query(UploadTrackState.waiting_for_playlist_choice, F.data.startswith("pl_select:"))
async def handle_track_playlist_selected(call: CallbackQuery, state: FSMContext):
    playlist_id = int(call.data.split(":")[1])
    data = await state.get_data()
    pl_title = await db.add_track_to_playlist(playlist_id, data["track_id"])
    await state.clear()
    tg_id = call.from_user.id
    user_data = await db.get_user_profile(tg_id)
    is_admin = await db.is_user_admin(tg_id)
    await call.message.edit_text(f"✅ Трек добавлен в <b>{html.escape(pl_title)}</b>!\n\n" + render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(UploadTrackState.waiting_for_playlist_choice, F.data == "pl_new")
async def handle_track_create_new_pl(call: CallbackQuery, state: FSMContext):
    await state.set_state(UploadTrackState.waiting_for_new_playlist_name)
    await call.message.edit_text("Введи название нового плейлиста:")
    await call.answer()

@router.message(UploadTrackState.waiting_for_new_playlist_name, F.text)
async def handle_track_save_new_pl(message: Message, state: FSMContext):
    new_title = message.text.strip()
    data = await state.get_data()
    await db.create_playlist_with_track(data["user_id"], new_title, data["track_id"])
    await state.clear()
    tg_id = message.from_user.id
    user_data = await db.get_user_profile(tg_id)
    is_admin = await db.is_user_admin(tg_id)
    await message.answer(f"✅ Создан плейлист <b>{html.escape(new_title)}</b>!\n\n" + render_main_menu_text(user_data), reply_markup=kb.get_main_inline_kb(is_admin=is_admin), parse_mode=ParseMode.HTML)

# ==================== АДМИН-ПАНЕЛЬ И /add_sub /give_sub ====================

@router.message(Command("admin"), StateFilter("*"))
@router.callback_query(F.data == "admin:menu", StateFilter("*"))
async def handle_admin_menu(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    if not await db.is_user_admin(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещен.", show_alert=True)
        return

    text = (
        "🛠 <b>Панель управления администратора</b>\n\n"
        "Выберите действие в меню или используйте быстрые команды:\n"
        "• <code>/add_sub @username</code> — Меню выдачи подписки\n"
        "• <code>/give_beta @username</code> — Выдать бета-доступ\n"
        "• <code>/take_beta @username</code> — Забрать бета-доступ\n"
        "• <code>/deltrack &lt;ID&gt;</code> — Удалить трек"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb.get_admin_menu_kb(), parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb.get_admin_menu_kb(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "admin:users")
@router.message(Command("users"), StateFilter("*"))
async def handle_admin_users(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    if not await db.is_user_admin(user_id):
        return

    users = await db.get_admin_recent_users()
    if not users:
        msg = "Пользователей нет."
    else:
        msg = "👥 <b>Список пользователей:</b>\n\n"
        for u in users:
            admin_mark = " 🛡" if u.get("is_admin") == 1 else ""
            uname = f"@{html.escape(u['username'])}" if u['username'] else "нет юзера"
            fname = html.escape(u['first_name'] or "Без имени")
            msg += f"• <code>[ID {u['id']}]</code> {fname}{admin_mark} ({uname}) — ID: <code>{u['tg_id']}</code> | Треков: {u['tracks_cnt']}\n"

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(msg, reply_markup=kb.get_back_to_admin_kb(), parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(msg, reply_markup=kb.get_back_to_admin_kb(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "admin:tracks")
@router.message(Command("tracks"), StateFilter("*"))
async def handle_admin_tracks(event: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    if not await db.is_user_admin(user_id):
        return

    tracks = await db.get_admin_recent_tracks()
    if not tracks:
        msg = "Треков нет."
    else:
        msg = "📁 <b>Все треки на сервере:</b>\n\n"
        for t in tracks:
            author = f"@{html.escape(t['username'])}" if t['username'] else html.escape(t['first_name'] or "Пользователь")
            msg += f"• <code>[#{t['id']}]</code> <b>{html.escape(t['artist'])}</b> — {html.escape(t['title'])} (от {author})\n"

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(msg, reply_markup=kb.get_back_to_admin_kb(), parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(msg, reply_markup=kb.get_back_to_admin_kb(), parse_mode=ParseMode.HTML)

# --- ИНТЕРАКТИВНОЕ МЕНЮ /add_sub и /give_sub ---

@router.callback_query(F.data == "admin:add_sub_start")
async def handle_admin_add_sub_button(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddSubAdminFSM.waiting_for_user_input)
    await call.message.edit_text(
        "🎁 <b>Выдача / продление подписки</b>\n\n"
        "Отправьте <b>@username</b> или <b>Telegram ID</b> пользователя:\n"
        "(или напишите /cancel)",
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(Command("add_sub"), StateFilter("*"))
@router.message(Command("give_sub"), StateFilter("*"))
async def handle_add_sub_command(message: Message, state: FSMContext):
    if not await db.is_user_admin(message.from_user.id):
        return
    await state.clear()

    args = message.text.split()
    if len(args) > 1:
        target = args[1].strip()
        target_user = await db.get_user_by_identity(target)
        if not target_user:
            await message.answer(f"❌ Пользователь <code>{html.escape(target)}</code> не найден в базе.", parse_mode=ParseMode.HTML)
            return

        target_tg_id = target_user["tg_id"]
        target_name = target_user["first_name"] or target_user["username"] or "Юзер"
        await message.answer(
            f"👤 Пользователь: <b>{html.escape(target_name)}</b> (<code>{target_tg_id}</code>)\n\n"
            "Выберите <b>уровень подписки</b>:",
            reply_markup=kb.get_admin_sub_plan_kb(target_tg_id),
            parse_mode=ParseMode.HTML
        )
    else:
        await state.set_state(AddSubAdminFSM.waiting_for_user_input)
        await message.answer(
            "🎁 Введите <b>@username</b> или <b>Telegram ID</b> пользователя для выдачи/продления подписки:",
            parse_mode=ParseMode.HTML
        )

@router.message(AddSubAdminFSM.waiting_for_user_input, F.text)
async def handle_add_sub_user_received(message: Message, state: FSMContext):
    target = message.text.strip()
    target_user = await db.get_user_by_identity(target)
    if not target_user:
        await message.answer(f"❌ Пользователь <code>{html.escape(target)}</code> не найден в базе. Попробуйте еще раз или /cancel:", parse_mode=ParseMode.HTML)
        return

    await state.clear()
    target_tg_id = target_user["tg_id"]
    target_name = target_user["first_name"] or target_user["username"] or "Юзер"
    await message.answer(
        f"👤 Пользователь: <b>{html.escape(target_name)}</b> (<code>{target_tg_id}</code>)\n\n"
        "Выберите <b>уровень подписки</b>:",
        reply_markup=kb.get_admin_sub_plan_kb(target_tg_id),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("adm_sub_plan:"))
async def handle_admin_sub_plan_choice(call: CallbackQuery):
    _, target_id_str, plan = call.data.split(":")
    target_id = int(target_id_str)
    plan_name = "⚡ Lite" if plan == "lite" else "👑 Burzhuy"

    await call.message.edit_text(
        f"Выбран уровень: <b>{plan_name}</b>\n\n"
        "Выберите срок подписки или свой вариант:",
        reply_markup=kb.get_admin_sub_period_kb(target_id, plan),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.callback_query(F.data.startswith("adm_sub_back_plan:"))
async def handle_admin_sub_back_plan(call: CallbackQuery):
    target_id = int(call.data.split(":")[1])
    await call.message.edit_text(
        f"👤 Пользователь ID: <code>{target_id}</code>\n\nВыберите <b>уровень подписки</b>:",
        reply_markup=kb.get_admin_sub_plan_kb(target_id),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.callback_query(F.data.startswith("adm_sub_days:"))
async def handle_admin_sub_days_apply(call: CallbackQuery, bot: Bot):
    _, target_id_str, plan, days_str = call.data.split(":")
    target_tg_id = int(target_id_str)
    days = int(days_str)

    new_expires = await db.extend_user_subscription(target_tg_id, days, plan=plan)

    plan_title = "⚡ Lite" if plan == "lite" else "👑 Burzhuy"
    try:
        await bot.send_message(
            chat_id=target_tg_id,
            text=(
                f"🎉 Вам выдана/продлена подписка <b>{plan_title}</b> на <b>{days} дн.</b>!\n"
                f"📅 Активна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    await call.message.edit_text(
        f"✅ <b>Подписка успешно обновлена!</b>\n\n"
        f"• Пользователь Telegram ID: <code>{target_tg_id}</code>\n"
        f"• Уровень: <b>{plan_title}</b>\n"
        f"• Добавлено дней: <b>{days}</b>\n"
        f"• Итоговая дата окончания: <code>{new_expires.strftime('%d.%m.%Y')}</code>",
        reply_markup=kb.get_back_to_admin_kb(),
        parse_mode=ParseMode.HTML
    )
    await call.answer("Готово!")

@router.callback_query(F.data.startswith("adm_sub_custom:"))
async def handle_admin_sub_custom_start(call: CallbackQuery, state: FSMContext):
    _, target_id_str, plan = call.data.split(":")
    await state.set_state(AddSubAdminFSM.waiting_for_custom_days)
    await state.update_data(target_id=int(target_id_str), plan=plan)

    await call.message.edit_text(
        "✏️ Введите количество дней числом (например: <code>15</code>, <code>45</code>, <code>180</code>):\n\n/cancel для отмены",
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(AddSubAdminFSM.waiting_for_custom_days, F.text)
async def handle_admin_sub_custom_save(message: Message, state: FSMContext, bot: Bot):
    val = message.text.strip()
    if not val.isdigit() or int(val) <= 0:
        await message.answer("❌ Введите целое положительное число дней (например: <code>30</code>):", parse_mode=ParseMode.HTML)
        return

    days = int(val)
    data = await state.get_data()
    target_tg_id = data["target_id"]
    plan = data["plan"]
    await state.clear()

    new_expires = await db.extend_user_subscription(target_tg_id, days, plan=plan)

    plan_title = "⚡ Lite" if plan == "lite" else "👑 Burzhuy"
    try:
        await bot.send_message(
            chat_id=target_tg_id,
            text=(
                f"🎉 Вам выдана/продлена подписка <b>{plan_title}</b> на <b>{days} дн.</b>!\n"
                f"📅 Активна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    await message.answer(
        f"✅ <b>Подписка успешно обновлена!</b>\n\n"
        f"• Пользователь Telegram ID: <code>{target_tg_id}</code>\n"
        f"• Уровень: <b>{plan_title}</b>\n"
        f"• Добавлено дней: <b>{days}</b>\n"
        f"• Итоговая дата окончания: <code>{new_expires.strftime('%d.%m.%Y')}</code>",
        reply_markup=kb.get_back_to_admin_kb(),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "admin:give_beta_prompt")
async def handle_give_beta_prompt(call: CallbackQuery):
    await call.message.edit_text(
        "🧪 <b>Управление бета-доступом</b>\n\nКоманды:\n• <code>/give_beta @username</code>\n• <code>/take_beta @username</code>",
        reply_markup=kb.get_back_to_admin_kb(),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(Command("deltrack"), StateFilter("*"))
async def handle_admin_deltrack(message: Message):
    if not await db.is_user_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Использование: <code>/deltrack &lt;ID трека&gt;</code>", parse_mode=ParseMode.HTML)
        return
    track_id = int(args[1])
    file_path = await db.delete_track_completely(track_id, message.from_user.id, is_admin=True)
    if file_path:
        services.remove_temp_file(file_path)
        await message.answer(f"✅ Трек <code>#{track_id}</code> удален!", parse_mode=ParseMode.HTML)
    else:
        await message.answer("❌ Трек не найден.", parse_mode=ParseMode.HTML)

@router.message(Command("give_beta"), StateFilter("*"))
async def handle_give_beta(message: Message, bot: Bot):
    if not await db.is_user_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: <code>/give_beta @username</code>", parse_mode=ParseMode.HTML)
        return
    target = args[1].strip()
    target_user = await db.get_user_by_identity(target)
    if not target_user:
        await message.answer(f"❌ Пользователь <code>{html.escape(target)}</code> не найден.")
        return
    await db.set_user_beta_access(target_user["tg_id"], status=1)
    try:
        await bot.send_message(chat_id=target_user["tg_id"], text="🧪 Вам выдан доступ к бета-сборкам клиента!", parse_mode=ParseMode.HTML)
    except Exception:
        pass
    target_name = target_user["first_name"] or target_user["username"] or "Юзер"
    await message.answer(f"✅ Пользователю <b>{html.escape(target_name)}</b> выдан доступ к бета-тесту!", parse_mode=ParseMode.HTML)

@router.message(Command("take_beta"), StateFilter("*"))
async def handle_take_beta(message: Message, bot: Bot):
    if not await db.is_user_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: <code>/take_beta @username</code>", parse_mode=ParseMode.HTML)
        return
    target = args[1].strip()
    target_user = await db.get_user_by_identity(target)
    if not target_user:
        await message.answer(f"❌ Пользователь <code>{html.escape(target)}</code> не найден.")
        return
    await db.set_user_beta_access(target_user["tg_id"], status=0)
    try:
        await bot.send_message(chat_id=target_user["tg_id"], text="🔒 Доступ к бета-сборкам клиента отозван.", parse_mode=ParseMode.HTML)
    except Exception:
        pass
    target_name = target_user["first_name"] or target_user["username"] or "Юзер"
    await message.answer(f"🚫 У <b>{html.escape(target_name)}</b> отозван доступ к бета-тесту.", parse_mode=ParseMode.HTML)

# --- API Ключи ---

@router.callback_query(F.data == "menu:api_key", StateFilter("*"))
@router.message(Command("key"), StateFilter("*"))
async def handle_api_key_menu(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        await event.answer("⚠️ Генерация API-ключей временно отключена.", show_alert=True)
    else:
        await event.answer("⚠️ Генерация API-ключей временно отключена.")
    return
    await state.clear()
    user_id = event.from_user.id
    current_key = await db.get_user_api_key(user_id)
    
    if current_key:
        text = (
            "🔑 <b>Ваш API-ключ:</b>\n\n"
            f"<code>{html.escape(current_key)}</code>\n\n"
            "<i>Используйте этот ключ для доступа к API и интеграциям. "
            "Никому не передавайте его! При повторной генерации старый ключ перестанет действовать.</i>"
        )
        kb_markup = kb.get_api_key_kb(has_key=True)
    else:
        text = (
            "🔑 <b>API-ключ не создан</b>\n\n"
            "Вы можете сгенерировать персональный API-ключ для авторизации в плеере и сторонних сервисах."
        )
        kb_markup = kb.get_api_key_kb(has_key=False)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb_markup, parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb_markup, parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "action:gen_api_key")
async def handle_generate_api_key(call: CallbackQuery):
    user_id = call.from_user.id
    new_key = await db.generate_user_api_key(user_id)
    if not new_key:
        await call.answer("Ошибка при создании ключа. Попробуйте позже.", show_alert=True)
        return

    text = (
        "✅ <b>Новый API-ключ успешно создан!</b>\n\n"
        f"<code>{html.escape(new_key)}</code>\n\n"
        "<i>Нажмите на ключ, чтобы скопировать.</i>"
    )
    await call.message.edit_text(text, reply_markup=kb.get_api_key_kb(has_key=True), parse_mode=ParseMode.HTML)
    await call.answer("Ключ обновлен!", show_alert=False)


# Fallback для любых необработанных текстовых сообщений вне FSM
@router.message(F.text, StateFilter(None))
async def handle_unknown_message(message: Message, state: FSMContext, bot: Bot):
    await handle_start(message, state, bot)
