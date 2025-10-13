from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard():
    """Клавиатура основного меню"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавиться в очередь", callback_data="add_to_queue")],
        [InlineKeyboardButton("➖ Выйти с очереди", callback_data="remove_from_queue")],
        [InlineKeyboardButton("🔄 Поменяться местами", callback_data="start_swap")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_swap_confirmation_keyboard(swap_id):
    """Клавиатура подтверждения обмена"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"swap_confirm_{swap_id}")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"swap_cancel_{swap_id}")]
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