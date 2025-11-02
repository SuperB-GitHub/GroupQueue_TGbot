import logging
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError

from queue_manager import queue_manager  # Импорт, если нужен для таймеров

logger = logging.getLogger(__name__)


async def safe_edit_message(context, chat_id, message_id, text, reply_markup):
    """Безопасное обновление сообщения с обработкой ошибок"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        logger.error(f"Error editing message {message_id}: {e}")
        return False


async def callback_delete_proposal(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения обмена по таймеру через 60 секунд"""
    job = context.job
    if not job:
        logger.error("No job context in callback_delete_proposal")
        return

    job_data = job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']
    swap_id = job_data['swap_id']

    logger.info(f"Timeout callback triggered for swap {swap_id}, deleting message {message_id}")

    # Проверяем, не был ли обмен уже обработан
    if not queue_manager.get_pending_swap(swap_id):
        logger.info(f"Swap {swap_id} already processed, skipping deletion")
        return

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted swap message {message_id} for swap {swap_id}")
    except Exception as e:
        logger.error(f"Failed to delete swap message {message_id}: {e}")
        # Пытаемся отредактировать сообщение, если удаление не удалось
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Время для ответа истекло. Предложение обмена отменено.",
                reply_markup=None
            )
            logger.info(f"Edited expired swap message {message_id}")
        except Exception as edit_error:
            logger.error(f"Failed to edit expired swap message {message_id}: {edit_error}")

    # Удаляем данные об обмене независимо от результата
    queue_manager.remove_pending_swap(swap_id)
    logger.info(f"Removed pending swap {swap_id} from storage")


async def callback_delete_selection(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения выбора пользователя по таймеру через 60 секунд"""
    job = context.job
    if not job:
        logger.error("No job context in callback_delete_selection")
        return

    job_data = job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']
    selection_id = job_data['selection_id']

    logger.info(f"Timeout callback triggered for selection {selection_id}, deleting message {message_id}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted selection message {message_id}")
    except Exception as e:
        logger.error(f"Failed to delete selection message {message_id}: {e}")
        # Пытаемся отредактировать, если удаление не удалось
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Время для выбора истекло.",
                reply_markup=None
            )
            logger.info(f"Edited expired selection message {message_id}")
        except Exception as edit_error:
            logger.error(f"Failed to edit expired selection message {message_id}: {edit_error}")


async def callback_delete_success(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения об успешном обмене по таймеру через 10 минут"""
    job = context.job
    if not job:
        logger.error("No job context in callback_delete_success")
        return

    job_data = job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']

    logger.info(f"Timeout callback triggered for success message {message_id}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted success message {message_id}")
    except Exception as e:
        logger.error(f"Failed to delete success message {message_id}: {e}")


async def callback_delete_cancel(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения об отмене обмена по таймеру через 2 минуты"""
    job = context.job
    if not job:
        logger.error("No job context in callback_delete_cancel")
        return

    job_data = job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']

    logger.info(f"Timeout callback triggered for cancel message {message_id}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted cancel message {message_id}")
    except Exception as e:
        logger.error(f"Failed to delete cancel message {message_id}: {e}")


async def callback_delete_add_user(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения добавления пользователя по таймеру через 60 секунд"""
    job = context.job
    if not job:
        logger.error("No job context in callback_delete_add_user")
        return

    job_data = job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']
    add_id = job_data['add_id']

    logger.info(f"Timeout callback triggered for add_user {add_id}, deleting message {message_id}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted add_user message {message_id}")
    except Exception as e:
        logger.error(f"Failed to delete add_user message {message_id}: {e}")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Время для ввода истекло.",
                reply_markup=None
            )
            logger.info(f"Edited expired add_user message {message_id}")
        except Exception as edit_error:
            logger.error(f"Failed to edit expired add_user message {message_id}: {edit_error}")