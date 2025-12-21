from telegram import Update
from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_add_user_keyboard
from utils import safe_edit_message, callback_delete_add_user
from lock_manager import lock_manager
import logging


logger = logging.getLogger(__name__)

# Хранилище активных сессий добавления пользователя
active_add_sessions = {}  # add_id: {'chat_id': int, 'topic_id': int, 'message_id': int, 'initiator_id': int}


async def start_add_user_handler(query, topic_id, user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления пользователя - запрос @username"""
    try:
        if not context.job_queue:
            logger.error("JobQueue is not available! Cannot set timeout for add_user")
            lock_manager.unlock(topic_id)  # Разблокируем
            await query.answer("Ошибка: система временных задач недоступна")
            return

        # Создаем уникальный ID для сессии добавления
        add_id = f"add_{chat_id}_{topic_id}_{user_id}_{query.message.message_id}"

        # Текст запроса
        text = ("👤 Добавление пользователя в очередь\n\n"
                "Отправьте @username пользователя из чата (бот его знает).\n\n"
                "⏰ Сообщение удалится через 1 минуту")

        # Отправляем новое сообщение
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_add_user_keyboard(add_id),
            message_thread_id=topic_id
        )

        # Сохраняем сессию
        active_add_sessions[add_id] = {
            'chat_id': chat_id,
            'topic_id': topic_id,
            'message_id': sent_message.message_id,
            'initiator_id': user_id,
            'input_message_id': None  # будет сохранено при получении сообщения
        }

        # Таймер на удаление через 60 секунд
        context.job_queue.run_once(
            callback_delete_add_user,
            60,
            data={
                'chat_id': chat_id,
                'message_id': sent_message.message_id,
                'add_id': add_id
            },
            name=f"add_user_timeout_{add_id}"
        )

        logger.info(f"Add user session started: {add_id}")

    except Exception as e:
        lock_manager.unlock(topic_id)  # Разблокируем при ошибке
        logger.error(f"Error in start_add_user: {e}")
        await query.answer("Ошибка при начале добавления")


async def add_back_handler(query, add_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки Назад в добавлении пользователя"""
    try:
        session = active_add_sessions.get(add_id)
        if not session or session['initiator_id'] != query.from_user.id:
            await query.answer("Это не ваша сессия добавления!")
            return

        topic_id = session['topic_id']
        
        # Отменяем таймер
        job_name = f"add_user_timeout_{add_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        # Удаляем сообщение
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        except Exception as e:
            logger.error(f"Error deleting add message on back: {e}")

        # Удаляем сессию
        active_add_sessions.pop(add_id, None)
        
        # Разблокируем топик
        lock_manager.unlock(topic_id)

        logger.info(f"Add user session cancelled: {add_id}")

    except Exception as e:
        logger.error(f"Error in add_back_handler: {e}")
        await query.answer("Ошибка при возврате")


async def handle_add_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстового ввода @username для добавления"""
    if not update.message or not update.message.text or update.message.chat.type == 'private':
        return

    topic_id = update.message.message_thread_id
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    input_text = update.message.text.strip().lstrip('@')

    if not topic_id:
        return

    # Ищем активную сессию для этого топика и инициатора
    session = None
    session_add_id = None
    for add_id, data in list(active_add_sessions.items()):
        if data['topic_id'] == topic_id and data['initiator_id'] == user_id:
            session = data
            session_add_id = add_id
            break

    if not session:
        return  # Не в сессии добавления

    # Сохраняем ID сообщения ввода
    if session['input_message_id'] is None:
        session['input_message_id'] = update.message.message_id

    # Проверяем JobQueue
    if not context.job_queue:
        await update.message.reply_text("Ошибка: система временных задач недоступна")
        return

    # Ищем пользователя среди known_users
    known_users = queue_manager.get_known_users(chat_id)
    target_user = None
    for user in known_users:
        if user['username'] and user['username'].lower() == input_text.lower():
            target_user = user
            break

    if not target_user:
        # Пользователь не найден
        await safe_edit_message(
            context,
            chat_id,
            session['message_id'],
            f"❌ Пользователь @{input_text} не найден среди известных.\n\n"
            "Отправьте другой @username.\n\n"
            "⏰ Сообщение удалится через 1 минуту",
            get_add_user_keyboard(session_add_id)
        )
        # Удаляем сообщение ввода
        try:
            await update.message.delete()
        except:
            pass
        return

    if target_user.get('is_bot', False):
        await safe_edit_message(
            context,
            chat_id,
            session['message_id'],
            f"❌ Нельзя добавить бота @{input_text} в очередь!\n\n"
            "Отправьте другой @username.\n\n"
            "⏰ Сообщение удалится через 1 минуту",
            get_add_user_keyboard(session_add_id)
        )
        try:
            await update.message.delete()
        except:
            pass
        return

    # Добавляем в очередь
    success = queue_manager.add_user_to_queue(
        topic_id,
        target_user['user_id'],
        target_user['first_name'],
        target_user['last_name'],
        target_user['username']
    )

    if not success:
        await safe_edit_message(
            context,
            chat_id,
            session['message_id'],
            f"❌ Пользователь @{input_text} уже в очереди!\n\n"
            "⏰ Сообщение удалится через 10 секунд",
            None
        )
    else:
        await safe_edit_message(
            context,
            chat_id,
            session['message_id'],
            f"✅ Пользователь @{input_text} добавлен в очередь!\n\n"
            "⏰ Сообщение удалится через 10 секунд",
            None
        )

        # Обновляем основное сообщение очереди
        main_message_id = queue_manager.get_queue_message_id(topic_id)
        if main_message_id:
            await safe_edit_message(
                context, chat_id, main_message_id,
                queue_manager.get_queue_text(topic_id), get_main_keyboard()
            )

    # Удаляем сообщение ввода
    try:
        await update.message.delete()
    except:
        pass

    # Отменяем старый таймер
    job_name = f"add_user_timeout_{session_add_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    # Новый таймер на 10 секунд для удаления итогового сообщения
    context.job_queue.run_once(
        callback_delete_add_user,
        10,
        data={
            'chat_id': chat_id,
            'message_id': session['message_id'],
            'add_id': session_add_id
        },
        name=f"add_user_final_timeout_{session_add_id}"
    )

    # Удаляем сессию
    active_add_sessions.pop(session_add_id, None)
    
    # Разблокируем топик
    lock_manager.unlock(topic_id)

    logger.info(f"Add user completed for @{input_text} in topic {topic_id}")