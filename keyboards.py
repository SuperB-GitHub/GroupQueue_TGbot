from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_keyboard():
    """Клавиатура основного меню"""
    keyboard = [
        [InlineKeyboardButton("⬆️ Добавиться", callback_data="add_to_queue"),
         InlineKeyboardButton("⬇️ Выйти", callback_data="remove_from_queue")],
        [InlineKeyboardButton("🔄 Обмен", callback_data="start_swap"),
         InlineKeyboardButton("⤵️ Отдать", callback_data="start_give_queue"),
         InlineKeyboardButton("👨‍👦 Добавить", callback_data="start_add_user")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="show_info")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_give_confirmation_keyboard(give_id: str):
    """Клавиатура подтверждения отдачи места"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"give_confirm_{give_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"give_cancel_{give_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_give_selection_keyboard(give_id: str):
    """Клавиатура выбора места для взятия"""
    keyboard = [
        [InlineKeyboardButton("🎯 Взять место", callback_data=f"give_take_{give_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"give_back_{give_id}")]
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
            button_text = user['display_name']
            if user['username']:
                button_text += f" (@{user['username']})"

            if len(button_text) > 50:
                button_text = button_text[:47] + "..."

            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"swap_with_{user['user_id']}_{initiator_id}"
            )])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


def get_add_user_keyboard(add_id):
    """Клавиатура для ввода username с кнопкой Назад"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data=f"add_back_{add_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)