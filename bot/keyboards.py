from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_branch_badge(branch_type: str, build_type: str = "release") -> str:
    branch = (branch_type or "").lower()
    btype = (build_type or "release").capitalize()
    if branch == "release":
        icon = "🟢"
    elif branch in ("beta", "alpha"):
        icon = "🟡"
    elif branch == "testing":
        icon = "🔴"
    else:
        icon = "⚪"
    return f"{icon} {branch.capitalize()} {btype}"

def get_main_inline_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="menu:account"),
            InlineKeyboardButton(text="📂 Мои плейлисты", callback_data="menu:playlists")
        ],
        [
            InlineKeyboardButton(text="⭐ Купить подписку", callback_data="menu:buy_sub"),
            InlineKeyboardButton(text="🎵 Загрузить трек", callback_data="menu:upload_track")
        ],
        [
            InlineKeyboardButton(text="📥 Скачать клиент", callback_data="menu:download_client")
        ]
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_api_key_kb(has_key: bool = False) -> InlineKeyboardMarkup:
    btn_text = "🔄 Перегенерировать ключ" if has_key else "⚡ Сгенерировать ключ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data="action:gen_api_key")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")]
        ]
    )

def get_admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Список юзеров", callback_data="admin:users"),
                InlineKeyboardButton(text="📁 Все треки", callback_data="admin:tracks")
            ],
            [
                InlineKeyboardButton(text="🎁 Выдать/Продлить подписку", callback_data="admin:add_sub_start"),
                InlineKeyboardButton(text="🧪 Выдать бета-доступ", callback_data="admin:give_beta_prompt")
            ],
            [
                InlineKeyboardButton(text="📥 Загрузить билд (/addver)", callback_data="admin:addver")
            ],
            [
                InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")
            ]
        ]
    )

def get_admin_sub_plan_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Lite", callback_data=f"adm_sub_plan:{target_id}:lite")],
            [InlineKeyboardButton(text="👑 Burzhuy (с бета-тестом)", callback_data=f"adm_sub_plan:{target_id}:burzhuy")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:menu")]
        ]
    )

def get_admin_sub_period_kb(target_id: int, plan: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 мес (30 дн.)", callback_data=f"adm_sub_days:{target_id}:{plan}:30"),
                InlineKeyboardButton(text="3 мес (90 дн.)", callback_data=f"adm_sub_days:{target_id}:{plan}:90")
            ],
            [
                InlineKeyboardButton(text="1 год (365 дн.)", callback_data=f"adm_sub_days:{target_id}:{plan}:365"),
                InlineKeyboardButton(text="✏️ Свой вариант", callback_data=f"adm_sub_custom:{target_id}:{plan}")
            ],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data=f"adm_sub_back_plan:{target_id}")]
        ]
    )

def get_back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")]]
    )

def get_back_to_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В админку", callback_data="admin:menu")]]
    )

def get_cancel_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="upload:cancel")]]
    )

def get_playlists_menu_kb(playlists: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for pl in playlists:
        buttons.append([InlineKeyboardButton(text=f"📁 {pl['title']} ({pl['tracks_count']})", callback_data=f"pl_view:{pl['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Создать плейлист", callback_data="pl_action:create")])
    buttons.append([InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_playlist_view_kb(playlist_id: int, tracks: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for t in tracks:
        buttons.append([InlineKeyboardButton(text=f"▶️ {t['artist']} — {t['title']}", callback_data=f"track_play:{playlist_id}:{t['id']}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить этот плейлист", callback_data=f"pl_action:delete:{playlist_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ К списку плейлистов", callback_data="menu:playlists")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_track_manage_kb(playlist_id: int, track_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💥 Удалить трек насовсем", callback_data=f"track_action:delete_srv:{track_id}")],
            [InlineKeyboardButton(text="◀️ Назад в плейлист", callback_data=f"pl_view:{playlist_id}")]
        ]
    )

def get_playlist_selection_keyboard(playlists: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📁 {pl['title']}", callback_data=f"pl_select:{pl['id']}")]
        for pl in playlists
    ]
    rows.append([InlineKeyboardButton(text="➕ Создать новый плейлист", callback_data="pl_new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_sub_plan_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Lite (3 ₽ / день)", callback_data="buy_plan:lite")],
            [InlineKeyboardButton(text="👑 Burzhuy (5 ₽ / день)", callback_data="buy_plan:burzhuy")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")]
        ]
    )

def get_sub_period_kb(plan: str) -> InlineKeyboardMarkup:
    prices = {
        "lite": {"1m": (30, 90), "3m": (90, 270), "1y": (365, 1095)},
        "burzhuy": {"1m": (30, 150), "3m": (90, 450), "1y": (365, 1825)},
    }
    p = prices[plan]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"1 месяц ({p['1m'][0]} дн.) — {p['1m'][1]} ₽", callback_data=f"buy_sub_confirm:{plan}:1m")],
            [InlineKeyboardButton(text=f"3 месяца ({p['3m'][0]} дн.) — {p['3m'][1]} ₽", callback_data=f"buy_sub_confirm:{plan}:3m")],
            [InlineKeyboardButton(text=f"1 год ({p['1y'][0]} дн.) — {p['1y'][1]} ₽", callback_data=f"buy_sub_confirm:{plan}:1y")],
            [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="menu:buy_sub")]
        ]
    )

def get_client_downloads_kb(grouped_versions: list[dict], has_beta_access: bool) -> InlineKeyboardMarkup:
    buttons = []
    for g in grouped_versions:
        branch = g["branch_type"]
        if not has_beta_access and branch != "release":
            continue
        if branch == "release":
            icon = "🟢"
        elif branch in ("beta", "alpha"):
            icon = "🟡"
        elif branch == "testing":
            icon = "🔴"
        else:
            icon = "⚪"
        btn_text = f"{icon} {branch.capitalize()} v{g['version_num']} ({g['platform']})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"dl_group:{branch}:{g['version_num']}:{g['platform']}")])
    buttons.append([InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_group_builds_kb(builds: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for b in builds:
        btype = (b.get("build_type") or "release").capitalize()
        branch = (b.get("branch_type") or "testing").capitalize()
        # Например: 🔴 Testing Release или 🔴 Testing Debug
        icon = "🔴" if b.get("branch_type") == "testing" else ("🟢" if b.get("branch_type") == "release" else "🟡")
        btn_text = f"{icon} {branch} {btype}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"dl_build_info:{b['id']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад к версиям", callback_data="menu:download_client")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_build_actions_kb(build_id: int, direct_url: str, can_send_in_tg: bool, group_back: str = "") -> InlineKeyboardMarkup:
    rows = []
    # Кнопка прямой ссылки для скачивания в браузере
    rows.append([InlineKeyboardButton(text="🌐 Скачать по прямой ссылке", url=direct_url)])
    # Кнопка отправки файлом в Telegram, если файл < 50MB
    if can_send_in_tg:
        rows.append([InlineKeyboardButton(text="💬 Отправить файлом в Telegram", callback_data=f"dl_build_file:{build_id}")])
    back_cb = f"dl_group:{group_back}" if group_back else "menu:download_client"
    rows.append([InlineKeyboardButton(text="◀️ Назад к выбору сборки", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_addver_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Release", callback_data="addver_type:release"),
                InlineKeyboardButton(text="🛠 Debug", callback_data="addver_type:debug")
            ],
            [
                InlineKeyboardButton(text="🟡 Beta", callback_data="addver_type:beta"),
                InlineKeyboardButton(text="🔴 Testing", callback_data="addver_type:testing")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="addver_cancel")]
        ]
    )

def get_addver_platform_kb() -> InlineKeyboardMarkup:
    platforms = ["Android", "iOS", "Windows", "Linux", "macOS"]
    rows = [
        [InlineKeyboardButton(text=p, callback_data=f"addver_plat:{p}") for p in platforms[:2]],
        [InlineKeyboardButton(text=p, callback_data=f"addver_plat:{p}") for p in platforms[2:]],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="addver_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
