from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_give_confirmation_keyboard, get_give_selection_keyboard
from utils import safe_edit_message, callback_delete_success
import logging
import uuid

logger = logging.getLogger(__name__)

# Хранилище активных сессий раздачи места
active_give_sessions = {}  # give_id: dict с данными сессии


async def start_give_queue_handler(query, topic_id, user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса раздачи места — подтверждение"""
    try:
        if not context.job_queue:
            logger.error("JobQueue недоступен для give_queue")
            await query.answer("Ошибка: система временных задач недоступна", show_alert=True)
            return

        queue = queue_manager.queues[topic_id]
        if not any(u['user_id'] == user_id for u in queue):
            await query.answer("Вы не в очереди!", show_alert=True)
            return

        give_id = str(uuid.uuid4())

        reply_markup = get_give_confirmation_keyboard(give_id)

        text = (f"Вы уверены, что хотите отдать своё место в очереди?\n\n"
                f"⏰ Сообщение удалится через 1 минуту")

        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            message_thread_id=topic_id
        )

        active_give_sessions[give_id] = {
            'chat_id': chat_id,
            'topic_id': topic_id,
            'message_id': sent.message_id,
            'giver_id': user_id,
            'stage': 'confirm'
        }

        context.job_queue.run_once(
            callback_delete_give_session,
            60,
            data={'give_id': give_id, 'chat_id': chat_id, 'message_id': sent.message_id},
            name=f"give_timeout_{give_id}"
        )

        logger.info(f"Give session started: {give_id}")

    except Exception as e:
        logger.error(f"Error in start_give_queue: {e}")
        await query.answer("Ошибка при начале раздачи", show_alert=True)


async def give_confirm_handler(query, give_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение — переход к выбору taker'а"""
    try:
        session = active_give_sessions.get(give_id)
        if not session or session['giver_id'] != query.from_user.id:
            await query.answer("Это не ваша сессия!", show_alert=True)
            return

        _cancel_give_timeout(context, give_id)

        queue = queue_manager.queues[session['topic_id']]
        giver = next((u for u in queue if u['user_id'] == session['giver_id']), None)
        if not giver:
            await query.edit_message_text("Вы больше не в очереди.")
            _cleanup_give_session(give_id)
            return

        reply_markup = get_give_selection_keyboard(give_id)

        giver_mention = f"@{giver['username']}" if giver['username'] else giver['display_name']
        text = (f"Место пользователя {giver_mention} свободно!\n\n"
                f"Нажмите «Взять место», чтобы занять его.\n\n"
                f"⏰ Сообщение удалится через 1 минуту")

        await query.edit_message_text(text=text, reply_markup=reply_markup)

        session['stage'] = 'selection'
        active_give_sessions[give_id] = session

        context.job_queue.run_once(
            callback_delete_give_session,
            60,
            data={'give_id': give_id, 'chat_id': chat_id, 'message_id': query.message.message_id},
            name=f"give_selection_timeout_{give_id}"
        )

    except Exception as e:
        logger.error(f"Error in give_confirm: {e}")
        await query.answer("Ошибка", show_alert=True)


async def give_cancel_handler(query, give_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Отмена на этапе подтверждения"""
    try:
        session = active_give_sessions.get(give_id)
        if not session or session['giver_id'] != query.from_user.id:
            return

        _cancel_give_timeout(context, give_id)
        await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        _cleanup_give_session(give_id)

    except Exception as e:
        logger.error(f"Error in give_cancel: {e}")


async def give_back_handler(query, give_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Назад от выбора — только giver"""
    try:
        session = active_give_sessions.get(give_id)
        if not session or session['giver_id'] != query.from_user.id:
            await query.answer("Только инициатор может вернуться!", show_alert=True)
            return

        _cancel_give_timeout(context, give_id)
        await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        _cleanup_give_session(give_id)

    except Exception as e:
        logger.error(f"Error in give_back: {e}")


async def give_take_handler(query, give_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Взятие места — любой пользователь"""
    try:
        session = active_give_sessions.get(give_id)
        if not session or session['stage'] != 'selection':
            await query.answer("Сессия недействительна", show_alert=True)
            return

        taker_id = query.from_user.id
        topic_id = session['topic_id']

        # Отмена таймера
        _cancel_give_timeout(context, give_id)

        # Удаляем taker из очереди, если он там
        queue_manager.remove_user_from_queue(topic_id, taker_id)

        # Находим позицию giver
        queue = queue_manager.queues[topic_id]
        giver_pos = next((i for i, u in enumerate(queue) if u['user_id'] == session['giver_id']), None)
        if giver_pos is None:
            await query.edit_message_text("Место уже недоступно.")
            _cleanup_give_session(give_id)
            return

        # Удаляем giver
        giver = queue.pop(giver_pos)

        # Добавляем taker на место giver
        taker_data = {
            'user_id': taker_id,
            'first_name': query.from_user.first_name or '',
            'last_name': query.from_user.last_name or '',
            'username': query.from_user.username or '',
            'display_name': f"{query.from_user.first_name or ''} {query.from_user.last_name or ''}".strip() or f"User_{taker_id}",
            'joined_at': datetime.now().isoformat()
        }
        queue.insert(giver_pos, taker_data)

        queue_manager.save_data()

        # Формируем сообщение
        giver_mention = f"@{giver['username']}" if giver['username'] else giver['display_name']
        taker_mention = f"@{query.from_user.username}" if query.from_user.username else query.from_user.first_name
        success_text = f"✅ {taker_mention} взял место {giver_mention}!\n\n⏰ Сообщение удалится через 10 секунд"

        await query.edit_message_text(success_text, reply_markup=None)

        # Таймер удаления
        context.job_queue.run_once(
            callback_delete_success,
            10,
            data={'chat_id': chat_id, 'message_id': query.message.message_id},
            name=f"give_success_timeout_{give_id}"
        )

        # Обновляем основное сообщение с очередью
        main_msg_id = queue_manager.get_queue_message_id(topic_id)
        if main_msg_id:
            await safe_edit_message(
                context, chat_id, main_msg_id,
                queue_manager.get_queue_text(topic_id),
                get_main_keyboard()
            )

        _cleanup_give_session(give_id)

    except Exception as e:
        logger.error(f"Error in give_take: {e}")
        await query.answer("Ошибка при взятии места", show_alert=True)


# Вспомогательные функции
def _cancel_give_timeout(context: ContextTypes.DEFAULT_TYPE, give_id: str):
    jobs = context.job_queue.get_jobs_by_name(f"give_timeout_{give_id}") + \
           context.job_queue.get_jobs_by_name(f"give_selection_timeout_{give_id}")
    for job in jobs:
        job.schedule_removal()

def _cleanup_give_session(give_id: str):
    active_give_sessions.pop(give_id, None)


async def callback_delete_give_session(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения по таймауту"""
    job = context.job
    data = job.data
    give_id = data['give_id']
    chat_id = data['chat_id']
    message_id = data['message_id']

    if give_id in active_give_sessions:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete give message: {e}")
        _cleanup_give_session(give_id)