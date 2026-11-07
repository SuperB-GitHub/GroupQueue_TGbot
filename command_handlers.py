import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import TimedOut, NetworkError

from queue_manager import queue_manager
from keyboards import get_main_keyboard
from utils import safe_edit_message, send_temp_message, callback_clear_cooldown_tick

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            chat_id = update.message.chat_id

            # Сохраняем маппинг topic_id -> chat_id
            queue_manager.set_topic_chat_mapping(topic_id, chat_id)
            
            # Собираем пользователя, который вызвал команду
            user = update.message.from_user
            queue_manager.add_known_user(
                chat_id,
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.is_bot
            )

            # Собираем администраторов и добавляем в known_users
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for member in admins:
                    user = member.user
                    queue_manager.add_known_user(
                        chat_id,
                        user.id,
                        user.first_name,
                        user.last_name,
                        user.username,
                        user.is_bot
                    )
            except Exception as e:
                logger.error(f"Error collecting admins in start: {e}")

            sent_message = await context.bot.send_message(
                chat_id=chat_id,
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
            chat_id = update.message.chat_id

            # Сохраняем маппинг topic_id -> chat_id
            queue_manager.set_topic_chat_mapping(topic_id, chat_id)
            
            # Собираем пользователя, который вызвал команду
            user = update.message.from_user
            queue_manager.add_known_user(
                chat_id,
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.is_bot
            )

            # Собираем администраторов и добавляем в known_users
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for member in admins:
                    user = member.user
                    queue_manager.add_known_user(
                        chat_id,
                        user.id,
                        user.first_name,
                        user.last_name,
                        user.username,
                        user.is_bot
                    )
            except Exception as e:
                logger.error(f"Error collecting admins in init: {e}")

            # Удаляем предыдущее сообщение с очередью, если оно существует
            old_message_id = queue_manager.get_queue_message_id(topic_id)
            if old_message_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=old_message_id)
                    logger.info(f"Deleted old queue message {old_message_id} for topic {topic_id}")
                except Exception as e:
                    logger.error(f"Error deleting old queue message {old_message_id}: {e}")

            # Отправляем новое сообщение с очередью
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=queue_manager.get_queue_text(topic_id),
                reply_markup=get_main_keyboard(),
                message_thread_id=topic_id
            )
            queue_manager.set_queue_message_id(topic_id, sent_message.message_id)

            # Удаляем сообщение с командой /init
            await update.message.delete()
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Timeout in init command: {e}")
    except Exception as e:
        logger.error(f"Error in init command: {e}")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для принудительного сохранения данных"""
    try:
        queue_manager.save_data()
        # Удаляем сообщение с командой /backup без отправки подтверждения
        await update.message.delete()
    except Exception as e:
        logger.error(f"Error in backup command: {e}")


async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /remove @username1 @username2 ... для админов (можно несколько через пробел)"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id

            # Собираем пользователя, который вызвал команду
            user = update.message.from_user
            queue_manager.add_known_user(
                chat_id,
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.is_bot
            )

            # Проверяем, является ли пользователь админом
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ['administrator', 'creator']:
                await send_temp_message(
                    context, chat_id, topic_id,
                    "❌ Только администраторы могут использовать /remove."
                )
                await update.message.delete()
                return

            if not context.args:
                await send_temp_message(
                    context, chat_id, topic_id,
                    "❌ Укажите @username для удаления.\n\n"
                    "Можно указать несколько пользователей через пробел:\n"
                    "<code>/remove @user1 @user2 @user3</code>"
                )
                await update.message.delete()
                return

            removed_users = []
            not_found_users = []
            
            # Обрабатываем всех переданных пользователей
            for arg in context.args:
                username = arg.lstrip('@')
                
                # Удаляем пользователя по username
                removed = queue_manager.remove_user_by_username(topic_id, username)
                
                if removed:
                    removed_users.append(f"@{username}")
                    logger.info(f"User @{username} removed by admin {user_id}")
                else:
                    not_found_users.append(f"@{username}")

            # Формируем отчет об удалении
            response_parts = []
            
            if removed_users:
                response_parts.append(f"✅ Удалено из очереди:\n{', '.join(removed_users)}")
            
            if not_found_users:
                response_parts.append(f"❌ Не найдено в очереди:\n{', '.join(not_found_users)}")
            
            if removed_users or not_found_users:
                # Обновляем основное сообщение с очередью, если были изменения
                if removed_users:
                    main_message_id = queue_manager.get_queue_message_id(topic_id)
                    if main_message_id:
                        await safe_edit_message(
                            context, chat_id, main_message_id,
                            queue_manager.get_queue_text(topic_id), get_main_keyboard()
                        )
                
                # Отправляем временное сообщение с отчетом
                response_text = "\n\n".join(response_parts)
                await send_temp_message(context, chat_id, topic_id, response_text)
            else:
                # Если не было ни одного аргумента с @
                await send_temp_message(
                    context, chat_id, topic_id,
                    "❌ Не указаны пользователи для удаления.\n\n"
                    "Используйте формат:\n"
                    "<code>/remove @user1 @user2</code>"
                )

            # Удаляем сообщение с командой /remove
            await update.message.delete()
            
    except Exception as e:
        logger.error(f"Error in remove command: {e}")
        try:
            if update.message:
                await send_temp_message(
                    context, update.message.chat_id, 
                    update.message.message_thread_id if update.message.is_topic_message else None,
                    "❌ Произошла ошибка при выполнении команды."
                )
                await update.message.delete()
        except:
            pass


async def insert_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /insert @username позиция - вставить пользователя на позицию"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id

            # Собираем пользователя, который вызвал команду
            user = update.message.from_user
            queue_manager.add_known_user(
                chat_id,
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.is_bot
            )

            # Проверяем, является ли пользователь админом
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status not in ['administrator', 'creator']:
                    await send_temp_message(
                        context, chat_id, topic_id,
                        "❌ Только администраторы могут использовать /insert."
                    )
                    await update.message.delete()
                    return
            except Exception as admin_error:
                logger.error(f"Error checking admin status: {admin_error}")
                await update.message.delete()
                return

            if not context.args or len(context.args) < 2:
                await send_temp_message(
                    context, chat_id, topic_id,
                    "❌ Формат команды: /insert @username позиция"
                )
                await update.message.delete()
                return

            username = context.args[0].lstrip('@')
            
            try:
                position = int(context.args[1])
                if position < 1:
                    await send_temp_message(
                        context, chat_id, topic_id,
                        "❌ Позиция должна быть положительным числом."
                    )
                    await update.message.delete()
                    return
            except ValueError:
                await send_temp_message(
                    context, chat_id, topic_id,
                    "❌ Позиция должна быть числом."
                )
                await update.message.delete()
                return

            # Ищем пользователя в known_users
            target_user = None
            known_users = queue_manager.get_known_users(chat_id)
            
            for user in known_users:
                if user['username'] == username:
                    target_user = user
                    break
            
            # Если не нашли в known_users
            if not target_user:
                await send_temp_message(
                    context, chat_id, topic_id,
                    f"❌ @{username} не найден среди известных."
                )
                await update.message.delete()
                return

            queue = queue_manager.queues[topic_id]
            
            # Проверяем, не в очереди ли уже пользователь
            for existing_user in queue:
                if existing_user['user_id'] == target_user['user_id']:
                    await send_temp_message(
                        context, chat_id, topic_id,
                        f"❌ @{username} уже в очереди."
                    )
                    await update.message.delete()
                    return

            # Вставляем пользователя на указанную позицию
            insert_position = min(position - 1, len(queue))

            user_data = {
                'user_id': target_user['user_id'],
                'first_name': target_user['first_name'],
                'last_name': target_user['last_name'],
                'username': target_user['username'],
                'display_name': target_user['display_name'],
            }

            queue.insert(insert_position, user_data)
            queue_manager.save_data()

            # Обновляем основное сообщение с очередью
            main_message_id = queue_manager.get_queue_message_id(topic_id)
            if main_message_id:
                try:
                    await safe_edit_message(
                        context, chat_id, main_message_id,
                        queue_manager.get_queue_text(topic_id), get_main_keyboard()
                    )
                except:
                    pass

            logger.info(f"User @{username} inserted at position {insert_position + 1} by admin {user_id}")
            
            # Удаляем сообщение с командой /insert
            await update.message.delete()
            
    except Exception as e:
        logger.error(f"Error in insert command: {e}")
        try:
            if update.message:
                await send_temp_message(
                    context, update.message.chat_id,
                    update.message.message_thread_id if update.message.is_topic_message else None,
                    "❌ Произошла ошибка при выполнении команды."
                )
                await update.message.delete()
        except:
            pass


async def clear_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /clear - очистка всей очереди (только для админов)"""
    try:
        if update.message and update.message.is_topic_message:
            topic_id = update.message.message_thread_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id

            # Собираем пользователя, который вызвал команду
            user = update.message.from_user
            queue_manager.add_known_user(
                chat_id,
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.is_bot
            )

            # Проверяем, является ли пользователь админом
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status not in ['administrator', 'creator']:
                    # Тихий отказ - просто удаляем сообщение
                    await update.message.delete()
                    return
            except Exception as admin_error:
                logger.error(f"Error checking admin status: {admin_error}")
                await update.message.delete()
                return

            # Проверяем, есть ли очередь для очистки
            queue = queue_manager.queues.get(topic_id)
            if not queue or len(queue) == 0:
                # Очередь уже пуста, просто удаляем команду
                await update.message.delete()
                return

            # Очищаем очередь
            queue_manager.queues[topic_id] = []
            queue_manager.save_data()

            # Обновляем основное сообщение с очередью
            main_message_id = queue_manager.get_queue_message_id(topic_id)
            if main_message_id:
                await safe_edit_message(
                    context, chat_id, main_message_id,
                    queue_manager.get_queue_text(topic_id), get_main_keyboard()
                )

            logger.info(f"Queue cleared in topic {topic_id} by admin {user_id}")

            cooldown_seconds = 30
            queue_manager.set_clear_cooldown(topic_id, cooldown_seconds)

            cooldown_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧹 Очередь очищена.\n\n"
                     f"⏳ Вступление в очередь будет доступно через {cooldown_seconds} сек.",
                message_thread_id=topic_id,
                disable_notification=True
            )

            if context.job_queue:
                context.job_queue.run_once(
                    callback_clear_cooldown_tick,
                    1,
                    data={
                        'chat_id': chat_id,
                        'message_id': cooldown_msg.message_id,
                        'topic_id': topic_id,
                    },
                    name=f"clear_cooldown_{topic_id}_{cooldown_msg.message_id}"
                )
            
            # Удаляем сообщение с командой /clear
            await update.message.delete()
            
    except Exception as e:
        logger.error(f"Error in clear command: {e}")
        try:
            await update.message.delete()
        except:
            pass


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ban @username — бан пользователя и удаление из всех очередей (только админы)"""
    try:
        if not update.message or not update.message.is_topic_message:
            return

        topic_id = update.message.message_thread_id
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id

        # Проверка прав администратора
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await send_temp_message(
                context, chat_id, topic_id,
                "❌ Только администраторы могут использовать /ban."
            )
            await update.message.delete()
            return

        if not context.args:
            await send_temp_message(
                context, chat_id, topic_id,
                "❌ Использование: /ban @username"
            )
            await update.message.delete()
            return

        username_arg = context.args[0]
        target_id, found_username = queue_manager.find_user_by_username(username_arg)

        if target_id is None:
            await send_temp_message(
                context, chat_id, topic_id,
                f"❌ Пользователь @{username_arg.lstrip('@')} не найден среди известных."
            )
            await update.message.delete()
            return

        queue_manager.ban_user(target_id, found_username or username_arg.lstrip('@'))

        # Обновляем все сообщения очередей, где мог быть этот пользователь
        for tid, mid in list(queue_manager.queue_message_ids.items()):
            if mid:
                cid = queue_manager.topic_to_chat.get(tid)
                if cid:
                    await safe_edit_message(
                        context, cid, mid,
                        queue_manager.get_queue_text(tid), get_main_keyboard()
                    )

        await send_temp_message(
            context, chat_id, topic_id,
            f"🚫 Пользователь @{found_username or username_arg.lstrip('@')} забанен и удалён из всех очередей."
        )
        await update.message.delete()

    except Exception as e:
        logger.error(f"Error in ban command: {e}")
        try:
            await update.message.delete()
        except:
            pass


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unban @username — разбан пользователя (только админы)"""
    try:
        if not update.message or not update.message.is_topic_message:
            return

        topic_id = update.message.message_thread_id
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id

        # Проверка прав администратора
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await send_temp_message(
                context, chat_id, topic_id,
                "❌ Только администраторы могут использовать /unban."
            )
            await update.message.delete()
            return

        if not context.args:
            await send_temp_message(
                context, chat_id, topic_id,
                "❌ Использование: /unban @username"
            )
            await update.message.delete()
            return

        username_arg = context.args[0]
        target_id, found_username = queue_manager.find_user_by_username(username_arg)

        if target_id is None or not queue_manager.unban_user(target_id):
            await send_temp_message(
                context, chat_id, topic_id,
                f"❌ Пользователь @{username_arg.lstrip('@')} не найден в бан-листе."
            )
            await update.message.delete()
            return

        await send_temp_message(
            context, chat_id, topic_id,
            f"✅ Пользователь @{found_username or username_arg.lstrip('@')} разбанен."
        )
        await update.message.delete()

    except Exception as e:
        logger.error(f"Error in unban command: {e}")
        try:
            await update.message.delete()
        except:
            pass

def register_command_handlers(application):
    """Регистрация обработчиков команд"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("init", init_queue_message))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("remove", remove_user_command))
    application.add_handler(CommandHandler("insert", insert_user_command))
    application.add_handler(CommandHandler("clear", clear_queue_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))