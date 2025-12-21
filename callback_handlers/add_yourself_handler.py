from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard
from utils import safe_edit_message
import logging


logger = logging.getLogger(__name__)


async def add_to_queue_handler(query, topic_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Добавление пользователя в очередь"""
    try:
        user = query.from_user
        success = queue_manager.add_user_to_queue(
            topic_id, user_id, user.first_name, user.last_name, user.username
        )

        if success:
            main_message_id = queue_manager.get_queue_message_id(topic_id)
            if main_message_id:
                await safe_edit_message(
                    context, query.message.chat_id, main_message_id,
                    queue_manager.get_queue_text(topic_id), get_main_keyboard()
                )
            await query.answer("✅ Вы успешно добавлены в очередь!")
        else:
            await query.answer("❌ Вы уже в очереди!")
    except Exception as e:
        logger.error(f"Error in add_to_queue: {e}")
        await query.answer("Ошибка при добавлении в очередь")