from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard
from utils import safe_edit_message
import logging


logger = logging.getLogger(__name__)


async def remove_from_queue_handler(query, topic_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Удаление пользователя из очереди"""
    try:
        success = queue_manager.remove_user_from_queue(topic_id, user_id)

        if success:
            # Очистка связанных pending_swaps
            to_remove = []
            for swap_id, swap_data in queue_manager.pending_swaps.items():
                if swap_data['topic_id'] == topic_id and (
                        swap_data['user1_id'] == user_id or swap_data['user2_id'] == user_id):
                    to_remove.append(swap_id)
                    try:
                        await context.bot.delete_message(
                            chat_id=swap_data['chat_id'],
                            message_id=swap_data.get('proposal_message_id')
                        )
                    except Exception as e:
                        logger.error(f"Error deleting proposal message on remove: {e}")

            for sid in to_remove:
                queue_manager.remove_pending_swap(sid)

            main_message_id = queue_manager.get_queue_message_id(topic_id)
            if main_message_id:
                await safe_edit_message(
                    context, query.message.chat_id, main_message_id,
                    queue_manager.get_queue_text(topic_id), get_main_keyboard()
                )
        else:
            await query.answer("Вы не в очереди!", show_alert=True)
    except Exception as e:
        logger.error(f"Error in remove_from_queue: {e}")
        await query.answer("Ошибка при выходе из очереди", show_alert=True)