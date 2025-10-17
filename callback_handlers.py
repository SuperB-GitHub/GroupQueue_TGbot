import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.error import TimedOut, NetworkError

from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_swap_confirmation_keyboard, get_swap_users_keyboard
from utils import safe_edit_message, callback_delete_proposal, callback_delete_selection, callback_delete_success, callback_delete_cancel

logger = logging.getLogger(__name__)


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

        # Проверяем доступность JobQueue
        if not context.job_queue:
            logger.error("JobQueue is not available! Cannot set timeout for swap selection")
            await query.answer("Ошибка: система временных задач недоступна", show_alert=True)
            return

        # Создаем новое самостоятельное сообщение со списком пользователей
        initiator_username = query.from_user.username
        initiator_name = query.from_user.first_name
        text = f"Пользователь {initiator_name} @{initiator_username} хочет поменяться местами. Выберите пользователя:\n\n⏰ Сообщение удалится через 1 минуту"
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=get_swap_users_keyboard(queue, user_id, user_id),
            message_thread_id=topic_id
        )

        # Создаем уникальный ID для сообщения выбора (selection_id)
        selection_id = f"selection_{chat_id}_{topic_id}_{user_id}_{sent_message.message_id}"

        # Запускаем таймер на удаление сообщения выбора через 60 секунд
        context.job_queue.run_once(
            callback_delete_selection,
            60,
            data={
                'chat_id': chat_id,
                'message_id': sent_message.message_id,
                'selection_id': selection_id
            },
            name=f"selection_timeout_{selection_id}"
        )

        logger.info(f"Swap selection message created, timeout scheduled for 60 seconds")

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

        # Отменяем таймер удаления сообщения выбора
        selection_id = f"selection_{chat_id}_{topic_id}_{user1_id}_{query.message.message_id}"
        current_jobs = context.job_queue.get_jobs_by_name(f"selection_timeout_{selection_id}")
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Cancelled selection timeout for {selection_id}")

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
            'user1_username': user1_data['username'],
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
            f"⏰ Сообщение удалится через 1 минуту",
            reply_markup=get_swap_confirmation_keyboard(swap_id)
        )

        # Запускаем таймер на удаление через 60 секунд
        context.job_queue.run_once(
            callback_delete_proposal,
            60,
            data={
                'chat_id': chat_id,
                'message_id': query.message.message_id,
                'swap_id': swap_id
            },
            name=f"swap_timeout_{swap_id}"
        )

        logger.info(f"Swap proposal created with ID: {swap_id}, timeout scheduled for 60 seconds")

    except Exception as e:
        logger.error(f"Error in create_swap_proposal: {e}")
        await query.answer("Ошибка при создании предложения обмена", show_alert=True)


async def confirm_swap(query, swap_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение обмена"""
    try:
        # Отменяем таймер удаления предложения
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
            # Формируем текст в указанном формате
            user1Mention = f"{swap_data['user1_name']} (@{swap_data['user1_username']})" if swap_data['user1_username'] else swap_data['user1_name']
            user2Mention = f"{swap_data['user2_name']} (@{swap_data['user2_username']})" if swap_data['user2_username'] else swap_data['user2_name']
            success_text = f"✅ {user1Mention} обменялся с {user2Mention}!\n\n⏰ Сообщение удалится через 10 минут"

            # Обновляем сообщение с предложением обмена
            try:
                await query.edit_message_text(
                    success_text,
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error updating confirmation message: {e}")

            # Запускаем таймер на удаление через 10 минут (600 секунд)
            context.job_queue.run_once(
                callback_delete_success,
                600,
                data={
                    'chat_id': chat_id,
                    'message_id': query.message.message_id
                },
                name=f"success_timeout_{swap_id}"
            )

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
        # Отменяем таймер удаления предложения
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
                "❌ Обмен отменен\n\n⏰ Сообщение удалится через 2 минуты",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Error updating cancellation message: {e}")

        # Запускаем таймер на удаление через 2 минуты (120 секунд)
        context.job_queue.run_once(
            callback_delete_cancel,
            120,
            data={
                'chat_id': chat_id,
                'message_id': query.message.message_id
            },
            name=f"cancel_timeout_{swap_id}"
        )

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)

    except Exception as e:
        logger.error(f"Error in cancel_swap: {e}")
        await query.answer("Ошибка при отмене обмена", show_alert=True)


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
        await query.answer("Ошибка при возврате в меню", show_alert=True)


def register_callback_handlers(application):
    """Регистрация обработчиков callback запросов"""
    # Основной обработчик callback'ов
    application.add_handler(CallbackQueryHandler(handle_callback))