import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_swap_confirmation_keyboard, get_swap_users_keyboard

logger = logging.getLogger(__name__)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if update.message and update.message.is_topic_message:
        topic_id = update.message.message_thread_id
        await update.message.reply_text(
            f"Бот для управления очередью в этом топике!\n\n"
            f"Используйте кнопки ниже для управления очередью.",
            reply_markup=get_main_keyboard(),
            message_thread_id=topic_id
        )

async def init_queue_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инициализация сообщения с очередью в новом топике"""
    if update.message and update.message.is_topic_message:
        topic_id = update.message.message_thread_id
        await update.message.reply_text(
            queue_manager.get_queue_text(topic_id),
            reply_markup=get_main_keyboard(),
            message_thread_id=topic_id
        )

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для принудительного сохранения данных"""
    queue_manager.save_data()
    await update.message.reply_text("✅ Данные сохранены вручную")

# Обработчики callback'ов
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    topic_id = query.message.message_thread_id
    chat_id = query.message.chat_id
    
    if query.data == "add_to_queue":
        await add_to_queue_handler(query, topic_id, user_id)
    
    elif query.data == "remove_from_queue":
        await remove_from_queue_handler(query, topic_id, user_id)
    
    elif query.data == "start_swap":
        await start_swap_handler(query, topic_id, user_id, chat_id)
    
    elif query.data.startswith("swap_with_"):
        target_user_id = int(query.data.split("_")[2])
        await create_swap_proposal(query, topic_id, user_id, target_user_id, chat_id)
    
    elif query.data.startswith("swap_confirm_"):
        swap_id = query.data.split("_")[2]
        await confirm_swap(query, swap_id, topic_id, chat_id)
    
    elif query.data.startswith("swap_cancel_"):
        swap_id = query.data.split("_")[2]
        await cancel_swap(query, swap_id, chat_id)
    
    elif query.data == "back_to_main":
        await back_to_main_handler(query, topic_id)

# Обработчики конкретных действий
async def add_to_queue_handler(query, topic_id, user_id):
    """Добавление пользователя в очередь"""
    user = query.from_user
    success = queue_manager.add_user_to_queue(
        topic_id, user_id, user.first_name, user.last_name, user.username
    )
    
    if success:
        await query.edit_message_text(
            queue_manager.get_queue_text(topic_id),
            reply_markup=get_main_keyboard()
        )
    else:
        await query.answer("Вы уже в очереди!", show_alert=True)

async def remove_from_queue_handler(query, topic_id, user_id):
    """Удаление пользователя из очереди"""
    success = queue_manager.remove_user_from_queue(topic_id, user_id)
    
    if success:
        await query.edit_message_text(
            queue_manager.get_queue_text(topic_id),
            reply_markup=get_main_keyboard()
        )
    else:
        await query.answer("Вы не в очереди!", show_alert=True)

async def start_swap_handler(query, topic_id, user_id, chat_id):
    """Начало процесса обмена - показ списка пользователей"""
    queue = queue_manager.queues[topic_id]
    if len(queue) < 2:
        await query.answer("В очереди должно быть минимум 2 человека для обмена!", show_alert=True)
        return
    
    # СОЗДАЕМ НОВОЕ СООБЩЕНИЕ вместо редактирования старого
    await query.message.reply_text(
        "Выберите пользователя, с которым хотите поменяться местами:",
        reply_markup=get_swap_users_keyboard(queue, user_id),
        message_thread_id=topic_id
    )

async def create_swap_proposal(query, topic_id, user1_id, user2_id, chat_id):
    """Создание предложения об обмене"""
    queue = queue_manager.queues[topic_id]
    
    # Находим данные пользователей
    user1_data = next((u for u in queue if u['user_id'] == user1_id), None)
    user2_data = next((u for u in queue if u['user_id'] == user2_id), None)
    
    if not user1_data or not user2_data:
        await query.answer("Ошибка: пользователь не найден", show_alert=True)
        return
    
    # Создаем уникальный ID для обмена
    swap_id = f"{chat_id}_{topic_id}_{user1_id}_{user2_id}"
    
    # Сохраняем данные об обмене
    swap_data = {
        'topic_id': topic_id,
        'user1_id': user1_id,
        'user2_id': user2_id,
        'user1_name': user1_data['display_name'],
        'user2_name': user2_data['display_name'],
        'message_id': query.message.message_id
    }
    
    queue_manager.add_pending_swap(swap_id, swap_data)
    
    # СОЗДАЕМ НОВОЕ СООБЩЕНИЕ с предложением обмена
    swap_message = await query.message.reply_text(
        f"🔄 Предложение об обмене\n\n"
        f"{user1_data['display_name']} хочет поменяться местами с {user2_data['display_name']}\n\n"
        f"{user2_data['display_name']}, вы согласны на обмен?",
        reply_markup=get_swap_confirmation_keyboard(swap_id),
        message_thread_id=topic_id
    )
    
    # Обновляем ID сообщения в данных обмена
    swap_data['confirmation_message_id'] = swap_message.message_id
    queue_manager.add_pending_swap(swap_id, swap_data)

async def confirm_swap(query, swap_id, topic_id, chat_id):
    """Подтверждение обмена"""
    swap_data = queue_manager.get_pending_swap(swap_id)
    if not swap_data:
        await query.answer("Предложение об обмене устарело", show_alert=True)
        return
    
    # Проверяем, что подтверждает правильный пользователь
    if query.from_user.id != swap_data['user2_id']:
        await query.answer("Это предложение обмена не для вас!", show_alert=True)
        return
    
    # Выполняем обмен
    success = queue_manager.swap_users(
        topic_id, swap_data['user1_id'], swap_data['user2_id']
    )
    
    if success:
        # Обновляем основное сообщение с очередью
        main_message_text = queue_manager.get_queue_text(topic_id)
        
        # Редактируем основное сообщение (используем сохраненный message_id)
        try:
            await query.bot.edit_message_text(
                chat_id=chat_id,
                message_id=swap_data['message_id'],
                text=main_message_text,
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Error editing main message: {e}")
        
        # Удаляем сообщение с подтверждением
        await query.message.delete()
        
        # Отправляем сообщение об успешном обмене
        await query.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Обмен выполнен! {swap_data['user1_name']} и {swap_data['user2_name']} поменялись местами.",
            message_thread_id=topic_id
        )
    else:
        await query.answer("Ошибка при обмене", show_alert=True)
    
    # Удаляем данные об обмене
    queue_manager.remove_pending_swap(swap_id)

async def cancel_swap(query, swap_id, chat_id):
    """Отмена обмена"""
    swap_data = queue_manager.get_pending_swap(swap_id)
    if swap_data:
        # Проверяем, что отменяет правильный пользователь
        if query.from_user.id != swap_data['user2_id']:
            await query.answer("Это предложение обмена не для вас!", show_alert=True)
            return
        
        # Удаляем сообщение с подтверждением
        await query.message.delete()
        
        # Отправляем сообщение об отмене
        await query.bot.send_message(
            chat_id=chat_id,
            text=f"❌ {swap_data['user2_name']} отказался от обмена с {swap_data['user1_name']}.",
            message_thread_id=swap_data['topic_id']
        )
        
        queue_manager.remove_pending_swap(swap_id)

async def back_to_main_handler(query, topic_id):
    """Обработчик возврата в главное меню"""
    await query.edit_message_text(
        queue_manager.get_queue_text(topic_id),
        reply_markup=get_main_keyboard()
    )