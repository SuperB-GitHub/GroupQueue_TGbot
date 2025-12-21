from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard
from utils import safe_edit_message
import logging


logger = logging.getLogger(__name__)


async def back_to_main_handler(query, topic_id, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата в главное меню"""
    try:
        # Отменяем таймер удаления сообщения выбора, если он активен
        selection_id = f"selection_{query.message.chat_id}_{topic_id}_{query.from_user.id}_{query.message.message_id}"
        current_jobs = context.job_queue.get_jobs_by_name(f"selection_timeout_{selection_id}")
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Cancelled selection timeout for {selection_id}")

        # Удаляем сообщение со списком
        await context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id
        )
        # Обновляем основное сообщение
        main_message_id = queue_manager.get_queue_message_id(topic_id)
        if main_message_id:
            await safe_edit_message(
                context, query.message.chat_id, main_message_id,
                queue_manager.get_queue_text(topic_id), get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in back_to_main: {e}")
        await query.answer("Ошибка при возврате в меню")
