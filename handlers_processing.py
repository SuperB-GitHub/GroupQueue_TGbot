from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from telegram.error import TimedOut, NetworkError
from callback_handlers.add_user_handler import *
from callback_handlers.add_yourself_handler import *
from callback_handlers.back_handler import *
from callback_handlers.remove_handler import *
from callback_handlers.swap_handler import *
from callback_handlers.give_handler import * 
logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов"""
    query = update.callback_query

    if not query or not query.data or not query.message:
        return

    # try:
    #     await query.answer()
    # except (TimedOut, NetworkError) as e:
    #     logger.warning(f"Timeout answering callback: {e}")
    # except Exception as e:
    #     logger.error(f"Error answering callback: {e}")

    user_id = query.from_user.id
    topic_id = query.message.message_thread_id
    chat_id = query.message.chat_id

    logger.info(f"Callback: {query.data} from user {user_id} in topic {topic_id}")

    # Валидация топика
    if not topic_id:
        await query.answer("Эта команда работает только в темах/топиках")
        return

    try:
        if query.data == "add_to_queue":
            await add_to_queue_handler(query, topic_id, user_id, context)

        elif query.data == "remove_from_queue":
            await remove_from_queue_handler(query, topic_id, user_id, context)

        elif query.data == "start_swap":
            await start_swap_handler(query, topic_id, user_id, chat_id, context)

        elif query.data.startswith("swap_with_"):
            parts = query.data.split("_")
            target_user_id = int(parts[2])
            initiator_id = int(parts[3])
            await create_swap_proposal(query, topic_id, initiator_id, target_user_id, chat_id, context)

        elif query.data.startswith("swap_confirm_"):
            swap_id = query.data.split("_", 2)[2]
            await confirm_swap(query, swap_id, chat_id, context)

        elif query.data.startswith("swap_cancel_"):
            swap_id = query.data.split("_", 2)[2]
            await cancel_swap(query, swap_id, chat_id, context)

        elif query.data.startswith("swap_back_"):
            swap_id = query.data.split("_", 2)[2]
            await swap_back_handler(query, swap_id, chat_id, context)

        elif query.data == "back_to_main":
            await back_to_main_handler(query, topic_id, context)

        elif query.data == "start_add_user":
            await start_add_user_handler(query, topic_id, user_id, chat_id, context)

        elif query.data.startswith("add_back_"):
            add_id = query.data.split("_", 2)[2]
            await add_back_handler(query, add_id, chat_id, context)

        elif query.data == "start_give_queue":
            await start_give_queue_handler(query, topic_id, user_id, chat_id, context)

        elif query.data.startswith("give_confirm_"):
            give_id = query.data.split("_", 2)[2]
            await give_confirm_handler(query, give_id, chat_id, context)

        elif query.data.startswith("give_cancel_"):
            give_id = query.data.split("_", 2)[2]
            await give_cancel_handler(query, give_id, chat_id, context)

        elif query.data.startswith("give_back_"):
            give_id = query.data.split("_", 2)[2]
            await give_back_handler(query, give_id, chat_id, context)

        elif query.data.startswith("give_take_"):
            give_id = query.data.split("_", 2)[2]
            await give_take_handler(query, give_id, chat_id, context)

    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        try:
            await query.answer("❌ Произошла ошибка. Попробуйте еще раз.")
        except:
            pass


def register_callback_handlers(application):
    """Регистрация обработчиков callback запросов"""
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Добавляем обработчик текстовых сообщений для ввода @username
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_user_input))