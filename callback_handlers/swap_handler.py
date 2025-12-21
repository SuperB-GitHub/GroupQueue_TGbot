from telegram.ext import ContextTypes
from queue_manager import queue_manager
from keyboards import get_main_keyboard, get_swap_confirmation_keyboard, get_swap_users_keyboard
from utils import (safe_edit_message, callback_delete_selection, callback_delete_proposal, callback_delete_success,
                   callback_delete_cancel)
import logging
from lock_manager import lock_manager


logger = logging.getLogger(__name__)



async def start_swap_handler(query, topic_id, user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса обмена - показ списка пользователей"""
    try:
        queue = queue_manager.queues[topic_id]
        if len(queue) < 2:
            lock_manager.unlock(topic_id)  # Разблокируем т.к. операция не началась
            await query.answer("В очереди должно быть минимум 2 человека для обмена!")
            return

        # Проверяем доступность JobQueue
        if not context.job_queue:
            lock_manager.unlock(topic_id)
            logger.error("JobQueue is not available! Cannot set timeout for swap selection")
            await query.answer("Ошибка: система временных задач недоступна")
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
        lock_manager.unlock(topic_id)  # Разблокируем при ошибке
        logger.error(f"Error in start_swap: {e}")
        await query.answer("Ошибка при начале обмена")


async def create_swap_proposal(query, topic_id, user1_id, user2_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Создание предложения обмена"""
    try:
        # Проверяем доступность JobQueue
        if not context.job_queue:
            logger.error("JobQueue is not available! Cannot set timeout for swap proposal")
            await query.answer("Ошибка: система временных задач недоступна")
            return

        if query.from_user.id != user1_id:
            await query.answer("Это меню только для инициатора обмена!")
            return

        # Удаляем сообщение с выбором пользователя
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)
        except Exception as e:
            logger.error(f"Error deleting selection message: {e}")

        # Находим данные пользователей
        queue = queue_manager.queues[topic_id]
        user1 = next((u for u in queue if u['user_id'] == user1_id), None)
        user2 = next((u for u in queue if u['user_id'] == user2_id), None)

        if not user1 or not user2:
            await query.answer("Пользователь не найден в очереди")
            return

        # Создаем уникальный ID для обмена
        swap_id = f"chat{chat_id}_topic{topic_id}_{user1_id}_{user2_id}"

        # Сохраняем данные обмена
        swap_data = {
            'topic_id': topic_id,
            'user1_id': user1_id,
            'user2_id': user2_id,
            'user1_name': user1['display_name'],
            'user2_name': user2['display_name'],
            'user1_username': user1['username'],
            'user2_username': user2['username'],
            'chat_id': chat_id
        }
        queue_manager.add_pending_swap(swap_id, swap_data)

        # Отправляем предложение второму пользователю
        proposal_text = f"@{user2['username']} или {user2['display_name']}, пользователь @{user1['username']} или {user1['display_name']} хочет поменяться с вами местами в очереди. Согласны?\n\n⏰ Время на ответ: 1 минута"
        sent_proposal = await context.bot.send_message(
            chat_id=chat_id,
            text=proposal_text,
            reply_markup=get_swap_confirmation_keyboard(swap_id),
            message_thread_id=topic_id
        )

        # Сохраняем ID сообщения предложения
        swap_data['proposal_message_id'] = sent_proposal.message_id
        queue_manager.add_pending_swap(swap_id, swap_data)  # Обновляем

        # Запускаем таймер на удаление через 60 секунд
        context.job_queue.run_once(
            callback_delete_proposal,
            60,
            data={
                'chat_id': chat_id,
                'message_id': sent_proposal.message_id,
                'swap_id': swap_id
            },
            name=f"swap_timeout_{swap_id}"
        )

        logger.info(f"Swap proposal created for {swap_id}, timeout scheduled")

    except Exception as e:
        logger.error(f"Error in create_swap_proposal: {e}")
        await query.answer("Ошибка при создании предложения обмена")


async def swap_back_handler(query, swap_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки Назад в предложении обмена"""
    try:
        topic_id = query.message.message_thread_id
        user_id = query.from_user.id
        
        # Отменяем таймер удаления предложения
        job_name = f"swap_timeout_{swap_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Cancelled timeout job for swap {swap_id}")

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)

        # Разблокируем топик
        lock_manager.unlock_by_user(topic_id, user_id)

        # Возвращаем к списку пользователей для выбора
        queue = queue_manager.queues[topic_id]

        initiator_username = query.from_user.username
        initiator_name = query.from_user.first_name
        text = f"Пользователь {initiator_name} @{initiator_username} хочет поменяться местами. Выберите пользователя:\n\n⏰ Сообщение удалится через 1 минуту"

        await query.edit_message_text(
            text=text,
            reply_markup=get_swap_users_keyboard(queue, user_id, user_id)
        )

        # Создаем уникальный ID для сообщения выбора (selection_id)
        selection_id = f"selection_{chat_id}_{topic_id}_{user_id}_{query.message.message_id}"

        # Запускаем новый таймер на удаление сообщения выбора через 60 секунд
        context.job_queue.run_once(
            callback_delete_selection,
            60,
            data={
                'chat_id': chat_id,
                'message_id': query.message.message_id,
                'selection_id': selection_id
            },
            name=f"selection_timeout_{selection_id}"
        )

        logger.info(f"Returned to swap selection for swap {swap_id}, new timeout scheduled")

    except Exception as e:
        logger.error(f"Error in swap_back_handler: {e}")
        await query.answer("Ошибка при возврате к выбору")


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
            await query.answer("Предложение обмена устарело")
            return

        topic_id = swap_data['topic_id']
        
        # Проверяем, что подтверждает правильный пользователь
        if query.from_user.id != swap_data['user2_id']:
            await query.answer("Это предложение обмена не для вас!")
            return

        # Проверяем, что оба пользователя все еще в очереди
        queue = queue_manager.queues[topic_id]
        if not any(u['user_id'] == swap_data['user1_id'] for u in queue) or not any(
                u['user_id'] == swap_data['user2_id'] for u in queue):
            await query.answer("Один из пользователей вышел из очереди. Обмен отменён.")
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=swap_data['proposal_message_id']
                )
            except Exception as e:
                logger.error(f"Error deleting proposal message: {e}")
            queue_manager.remove_pending_swap(swap_id)
            lock_manager.unlock(topic_id)  # Разблокируем
            return

        # Выполняем обмен
        success = queue_manager.swap_users(
            topic_id, swap_data['user1_id'], swap_data['user2_id']
        )

        if success:
            # Формируем текст в указанном формате
            user1Mention = f"{swap_data['user1_name']} (@{swap_data['user1_username']})" if swap_data['user1_username'] else swap_data['user1_name']
            user2Mention = f"{swap_data['user2_name']} (@{swap_data['user2_username']})" if swap_data['user2_username'] else swap_data['user2_name']
            success_text = f"✅ {user1Mention} обменялся с {user2Mention}!\n\n⏰ Сообщение удалится через 1 минуту"

            # Обновляем сообщение с предложением обмена
            try:
                await query.edit_message_text(
                    success_text,
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error updating confirmation message: {e}")

            # Запускаем таймер на удаление через 1 минуту (60 секунд)
            context.job_queue.run_once(
                callback_delete_success,
                60,
                data={
                    'chat_id': chat_id,
                    'message_id': query.message.message_id
                },
                name=f"success_timeout_{swap_id}"
            )

            # Обновляем основное сообщение с очередью
            main_message_id = queue_manager.get_queue_message_id(topic_id)
            if main_message_id:
                await safe_edit_message(
                    context, chat_id, main_message_id,
                    queue_manager.get_queue_text(topic_id),
                    get_main_keyboard()
                )
        else:
            await query.answer("Ошибка при обмене")

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)
        
        # Разблокируем топик
        lock_manager.unlock(topic_id)

    except Exception as e:
        logger.error(f"Error in confirm_swap: {e}")
        await query.answer("Ошибка при подтверждении обмена")
        # При ошибке разблокируем
        if 'topic_id' in locals():
            lock_manager.unlock(topic_id)


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
            await query.answer("Предложение обмена устарело")
            return

        topic_id = swap_data['topic_id']
        
        # Проверяем, что отменяет правильный пользователь
        if query.from_user.id != swap_data['user2_id']:
            await query.answer("Это предложение обмена не для вас!")
            return

        # Обновляем сообщение с отменой
        try:
            await query.edit_message_text(
                "❌ Обмен отменен\n\n⏰ Сообщение удалится через 10 секунд",
                reply_markup=None
            )
        except Exception as e:
            logger.error(f"Error updating cancellation message: {e}")

        # Запускаем таймер на удаление через 10 секунд
        context.job_queue.run_once(
            callback_delete_cancel,
            10,
            data={
                'chat_id': chat_id,
                'message_id': query.message.message_id
            },
            name=f"cancel_timeout_{swap_id}"
        )

        # Удаляем данные об обмене
        queue_manager.remove_pending_swap(swap_id)
        
        # Разблокируем топик
        lock_manager.unlock(topic_id)

    except Exception as e:
        logger.error(f"Error in cancel_swap: {e}")
        await query.answer("Ошибка при отмене обмена")
        # При ошибке разблокируем
        if 'topic_id' in locals():
            lock_manager.unlock(topic_id)