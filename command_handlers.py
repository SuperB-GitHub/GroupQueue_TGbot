import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import TimedOut, NetworkError

from queue_manager import queue_manager
from keyboards import get_main_keyboard
from utils import safe_edit_message

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
    """Команда /remove @username для админов"""
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
                # Toast-уведомление вместо постоянного сообщения
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Только администраторы могут использовать /remove.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                # Удаляем сообщение с командой
                await update.message.delete()
                return

            if not context.args:
                # Toast-уведомление
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Укажите @username для удаления.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                await update.message.delete()
                return

            username = context.args[0].lstrip('@')

            # Удаляем пользователя по username
            removed = queue_manager.remove_user_by_username(topic_id, username)
            if removed:
                # Обновляем основное сообщение с очередью
                main_message_id = queue_manager.get_queue_message_id(topic_id)
                if main_message_id:
                    await safe_edit_message(
                        context, chat_id, main_message_id,
                        queue_manager.get_queue_text(topic_id), get_main_keyboard()
                    )
                # Toast-уведомление об успехе
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Пользователь @{username} удалён из очереди.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                logger.info(f"User @{username} removed by admin {user_id}")
            else:
                # Toast-уведомление об ошибке
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Пользователь @{username} не найден в очереди.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )

            # Удаляем сообщение с командой /remove
            await update.message.delete()
    except Exception as e:
        logger.error(f"Error in remove command: {e}")
        try:
            # Toast-уведомление об общей ошибке
            if update.message:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="❌ Произошла ошибка при выполнении команды.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=update.message.message_thread_id if update.message.is_topic_message else None
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
                    # Toast-уведомление о недостатке прав
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ Только администраторы могут использовать /insert.",
                        reply_to_message_id=update.message.message_id,
                        message_thread_id=topic_id
                    )
                    await update.message.delete()
                    return
            except Exception as admin_error:
                logger.error(f"Error checking admin status: {admin_error}")
                await update.message.delete()
                return

            if not context.args or len(context.args) < 2:
                # Toast-уведомление о неправильном формате
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Формат команды: /insert @username позиция",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                await update.message.delete()
                return

            username = context.args[0].lstrip('@')
            
            try:
                position = int(context.args[1])
                if position < 1:
                    # Toast-уведомление о неправильной позиции
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ Позиция должна быть положительным числом.",
                        reply_to_message_id=update.message.message_id,
                        message_thread_id=topic_id
                    )
                    await update.message.delete()
                    return
            except ValueError:
                # Toast-уведомление о неправильной позиции
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Позиция должна быть числом.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                await update.message.delete()
                return

            # Ищем пользователя в known_users
            target_user = None
            known_users = queue_manager.get_known_users(chat_id)
            
            # Сначала ищем в known_users
            for user in known_users:
                if user['username'] == username:
                    target_user = user
                    break
            
            # Если не нашли в known_users
            if not target_user:
                # Toast-уведомление
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Пользователь @{username} не найден среди известных.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=topic_id
                )
                await update.message.delete()
                return

            queue = queue_manager.queues[topic_id]
            
            # Проверяем, не в очереди ли уже пользователь
            for existing_user in queue:
                if existing_user['user_id'] == target_user['user_id']:
                    # Toast-уведомление
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Пользователь @{username} уже в очереди.",
                        reply_to_message_id=update.message.message_id,
                        message_thread_id=topic_id
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

            # Toast-уведомление об успехе
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Пользователь @{username} вставлен на позицию {insert_position + 1}.",
                reply_to_message_id=update.message.message_id,
                message_thread_id=topic_id
            )
            
            logger.info(f"User @{username} inserted at position {insert_position + 1} by admin {user_id}")
            
            # Удаляем сообщение с командой /insert
            await update.message.delete()
            
    except Exception as e:
        logger.error(f"Error in insert command: {e}")
        try:
            if update.message:
                # Toast-уведомление об общей ошибке
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="❌ Произошла ошибка при выполнении команды.",
                    reply_to_message_id=update.message.message_id,
                    message_thread_id=update.message.message_thread_id if update.message.is_topic_message else None
                )
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