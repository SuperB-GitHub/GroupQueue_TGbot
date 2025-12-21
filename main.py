import logging
import atexit
import os
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters
from queue_manager import queue_manager
from lock_manager import lock_manager
from command_handlers import register_command_handlers
from handlers_processing import register_callback_handlers

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def callback_auto_save(context):
    """Автоматическое сохранение данных"""
    try:
        queue_manager.save_data()
        logger.debug("Data auto-saved")
    except Exception as e:
        logger.error(f"Error in auto-save: {e}")


async def collect_users(update, context):
    """Сбор известных пользователей из всех типов сообщений"""
    chat_id = None
    user = None
    
    # Обработка обычных сообщений
    if update.message:
        chat_id = update.message.chat_id
        user = update.message.from_user
    # Обработка callback запросов
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
        user = update.callback_query.from_user
    # Обработка inline запросов (если будут)
    elif update.inline_query:
        chat_id = update.inline_query.from_user.id
        user = update.inline_query.from_user
    else:
        return
    
    # Добавляем пользователя в известные
    if user and chat_id:
        queue_manager.add_known_user(
            chat_id,
            user.id,
            user.first_name,
            user.last_name,
            user.username,
            user.is_bot
        )


def main():
    """Основная функция"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        raise ValueError("Токен бота не найден в переменных окружения")

    # Создаем Application с JobQueue
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков из модулей
    register_command_handlers(application)
    register_callback_handlers(application)

    # Добавляем handler для сбора пользователей
    application.add_handler(MessageHandler(filters.ALL, collect_users))

    # Настройка периодических задач
    job_queue = application.job_queue

    if job_queue:
        # Автосохранение каждые 5 минут
        job_queue.run_repeating(
            callback_auto_save,
            interval=300,
            first=10
        )
        logger.info("JobQueue initialized successfully")
    else:
        logger.error("JobQueue is not available!")

    # Автоматическое сохранение при завершении
    atexit.register(queue_manager.save_data)

    # Запуск бота
    logger.info("Бот запущен...")
    logger.info(f"Система блокировок активна. Таймаут: {lock_manager.timeout} секунд")
    application.run_polling()


if __name__ == '__main__':
    main()