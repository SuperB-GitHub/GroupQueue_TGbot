from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from queue_manager import queue_manager


def get_main_keyboard():
    """Клавиатура основного меню"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавиться в очередь", callback_data="add_to_queue")],
        [InlineKeyboardButton("➕ Добавить в очередь", callback_data="start_add_user")],
        [InlineKeyboardButton("➖ Выйти из очереди", callback_data="remove_from_queue")],
        [InlineKeyboardButton("🔄 Поменяться местами", callback_data="start_swap")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_swap_confirmation_keyboard(swap_id):
    """Клавиатура подтверждения обмена"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"swap_confirm_{swap_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"swap_cancel_{swap_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"swap_back_{swap_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_swap_users_keyboard(queue, current_user_id, initiator_id):
    """Клавиатура выбора пользователя для обмена"""
    keyboard = []
    for user in queue:
        if user['user_id'] != current_user_id:
            # Ограничиваем длину текста кнопки для предотвращения ошибок
            button_text = user['display_name']
            if user['username']:
                button_text += f" (@{user['username']})"

            # Обрезаем слишком длинные имена
            if len(button_text) > 50:
                button_text = button_text[:47] + "..."

            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"swap_with_{user['user_id']}_{initiator_id}"
            )])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


def get_add_users_keyboard(chat_id, topic_id, page=0):
    """Клавиатура выбора пользователя для добавления с пагинацией по 5"""
    users = queue_manager.get_known_users(chat_id)
    if not users:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])

    # Сортируем по display_name для удобства
    users = sorted(users, key=lambda u: u['display_name'])

    page_size = 5
    total_pages = (len(users) + page_size - 1) // page_size
    start = page * page_size
    end = start + page_size
    page_users = users[start:end]

    keyboard = []
    for user in page_users:
        button_text = user['display_name']
        if user['username']:
            button_text += f" (@{user['username']})"
        if len(button_text) > 50:
            button_text = button_text[:47] + "..."
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"add_user_{user['user_id']}_{topic_id}"
        )])

    # Кнопки навигации
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"add_page_{page-1}_{topic_id}"))
    nav_row.append(InlineKeyboardButton(f"Страница {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"add_page_{page+1}_{topic_id}"))
    if nav_row:
        keyboard.append(nav_row)

    # Кнопка назад в главное
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    return InlineKeyboardMarkup(keyboard)