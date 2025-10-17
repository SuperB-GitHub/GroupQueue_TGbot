import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.error import TimedOut, NetworkError

from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_swap_confirmation_keyboard, get_swap_users_keyboard

logger = logging.getLogger(__name__)


# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"Бот для управления очередью в этом топике!\n\n"
                     f"Используйте кнопки ниже для управления очередью.",
                reply_markup=get_main_keyboard(),
                message_thread_id=topic_id
            )
            queue_manager.set_queue_message_id(topic_id, sent_message.message_id)
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Timeout in start command: {e}")
    except Exception as e:
        logger.error(f"Error in start command: {e}")


async def init_queue_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инициализация сообщения с очередью в новом топике"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            sent_message = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=queue_manager.get_queue_text(topic_id),
                reply_markup=get_main_keyboard(),
                message_thread_id=topic_id
            )
            queue_manager.set_queue_message_id(topic_id, sent_message.message_id)
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Timeout in init command: {e}")
    except Exception as e:
        logger.error(f"Error in init command: {e}")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для принудительного сохранения данных"""
    try:
        queue_manager.save_data()
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="✅ Данные сохранены вручную",
            message_thread_id=update.message.message_thread_id
        )
    except Exception as e:
        logger.error(f"Error in backup command: {e}")


# Обработчики callback'ов
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов"""
    query = update.callback_query

    if not query or not query.data or not query.message:
        return

    try:
        await query.answer()
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Timeout answering callback: {e}")
    except Exception as e:
        logger.error(f"Error answering callback: {e}")

    user_id = query.from_user.id
    topic_id = query.message.message_thread_id
    chat_id = query.message.chat_id

    logger.info(f"Callback: {query.data} from user {user_id} in topic {topic_id}")

    # Валидация топика
    if not topic_id:
        await query.answer("Эта команда работает только в темах/топиках", show_alert=True)
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

        elif query.data == "back_to_main":
            await back_to_main_handler(query, topic_id, context)

    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        try:
            await query.answer("❌ Произошла ошибка. Попробуйте еще раз.", show_alert=True)
        except:
            pass


# Обработчики конкретных действий
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
        else:
            await query.answer("Вы уже в очереди!", show_alert=True)
    except Exception as e:
        logger.error(f"Error in add_to_queue: {e}")
        await query.answer("Ошибка при добавлении в очередь", show_alert=True)


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


async def start_swap_handler(query, topic_id, user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса обмена - показ списка пользователей"""
    try:
        queue = queue_manager.queues[topic_id]
        if len(queue) < 2:
            await query.answer("В очереди должно быть минимум 2 человека для обмена!", show_alert=True)
            return

        # Создаем новое самостоятельное сообщение со списком пользователей
        initiator_username = query.from_user.username or query.from_user.first_name
        text = f"Пользователь @{initiator_username} хочет поменяться местами. Выберите пользователя:"
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_swap_users_keyboard(queue, user_id, user_id),
            message_thread_id=topic_id
        )
    except Exception as e:
        logger.error(f"Error in start_swap: {e}")
        await query.answer("Ошибка при начале обмена", show_alert=True)


async def create_swap_proposal(query, topic_id, user1_id, user2_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Создание предложения обмена"""
    try:
        # Проверяем доступность JobQueue
        if not context.job_queue:
            logger.error("JobQueue is not available! Cannot set timeout for swap proposal")
            await query.answer("Ошибка: система временных задач недоступна", show_alert=True)
            return

        if query.from_user.id != user1_id:
            await query.answer("Это меню только для инициатора обмена!", show_alert=True)
            return

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
            'user2_username': user2_data['username'],
            'chat_id': chat_id,
            'proposal_message_id': query.message.message_id
        }

        queue_manager.add_pending_swap(swap_id, swap_data)

        # Обновляем сообщение со списком на предложение обмена с пингом
        ping = f"@{user2_data['username']}" if user2_data['username'] else user2_data['display_name']
        await query.edit_message_text(
            f"🔄 Предложение обмена\n\n"
            f"{user1_data['display_name']} хочет поменяться местами с {user2_data['display_name']}\n\n"
            f"{ping}, вы согласны на обмен?\n\n"
            f"⏰ Сообщение удалится через 5 секунд",
            reply_markup=get_swap_confirmation_keyboard(swap_id)
        )

        # Запускаем таймер на удаление через 5 секунд
        context.job_queue.run_once(
            callback_delete_proposal,
            5,
            data={
                'chat_id': chat_id,
                'message_id': query.message.message_id,
                'swap_id': swap_id
            },
            name=f"swap_timeout_{swap_id}"
        )

        logger.info(f"Swap proposal created with ID: {swap_id}, timeout scheduled for 5 seconds")

    except Exception as e:
        logger.error(f"Error in create_swap_proposal: {e}")
        await query.answer("Ошибка при создании предложения обмена", show_alert=True)


async def callback_delete_proposal(context: ContextTypes.DEFAULT_TYPE):
    """Удаление сообщения обмена по таймеру через 5 секунд"""
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


async def confirm_swap(query, swap_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение обмена"""
    try:
        # Отменяем таймер удаления, так как пользователь ответил
        job_name = f"swap_timeout_{swap_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Cancelled timeout job for swap {swap_id}")

        swap_data = queue_manager.get_pending_swap(swap_id)
        if not swap_data:
            await query.answer("Предложение обмена устарело", show_alert=True)
            return

        # Проверяем, что подтверждает правильный пользователь
        if query.from_user.id != swap_data['user2_id']:
            await query.answer("Это предложение обмена не для вас!", show_alert=True)
            return

        # Проверяем, что оба пользователя все еще в очереди
        queue = queue_manager.queues[swap_data['topic_id']]
        if not any(u['user_id'] == swap_data['user1_id'] for u in queue) or not any(
                u['user_id'] == swap_data['user2_id'] for u in queue):
            await query.answer("Один из пользователей вышел из очереди. Обмен отменён.", show_alert=True)
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=swap_data['proposal_message_id']
                )
            except Exception as e:
                logger.error(f"Error deleting proposal message: {e}")
            queue_manager.remove_pending_swap(swap_id)
            return

        # Выполняем обмен
        success = queue_manager.swap_users(
            swap_data['topic_id'], swap_data['user1_id'], swap_data['user2_id']
        )

        if success:
            # Обновляем сообщение с предложением обмена
            try:
                await query.edit_message_text(
                    "✅ Обмен успешно выполнен!",
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error updating confirmation message: {e}")

            # Обновляем основное сообщение с очередью
            main_message_id = queue_manager.get_queue_message_id(swap_data['topic_id'])
            if main_message_id:
                await safe_edit_message(
                    context, chat_id, main_message_id,
                    queue_manager.get_queue_text(swap_data['topic_id']),
                    get_main_keyboard()
                )
        else:
            await query.answer("Ошибка при обмене", show_alert=True)

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)

    except Exception as e:
        logger.error(f"Error in confirm_swap: {e}")
        await query.answer("Ошибка при подтверждении обмена", show_alert=True)


async def cancel_swap(query, swap_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Отмена обмена"""
    try:
        # Отменяем таймер удаления, так как пользователь ответил
        job_name = f"swap_timeout_{swap_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Cancelled timeout job for swap {swap_id}")

        swap_data = queue_manager.get_pending_swap(swap_id)
        if not swap_data:
            await query.answer("Предложение обмена устарело", show_alert=True)
            return

        # Проверяем, что отменяет правильный пользователь
        if query.from_user.id != swap_data['user2_id']:
            await query.answer("Это предложение обмена не для вас!", show_alert=True)
            return

        # Обновляем сообщение с отменой
        try:
            await query.edit_message_text(
                "❌ Обмен отменен",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Error updating cancellation message: {e}")

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)

    except Exception as e:
        logger.error(f"Error in cancel_swap: {e}")
        await query.answer("Ошибка при отмене обмена", show_alert=True)


async def back_to_main_handler(query, topic_id, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата в главное меню"""
    try:
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
        await query.answer("Ошибка при возврате в меню", show_alert=True)


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