import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import atexit
import os
from dotenv import load_dotenv

from queue_manager import queue_manager
from handlers import start, init_queue_message, backup_command, handle_callback

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def setup_handlers(application):
    """Настройка обработчиков"""
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("init", init_queue_message))
    application.add_handler(CommandHandler("backup", backup_command))

    # Обработчики callback запросов
    application.add_handler(
        CallbackQueryHandler(handle_callback, pattern="^(add_to_queue|remove_from_queue|start_swap)"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_with_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_confirm_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_cancel_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^back_to_main$"))


async def callback_auto_save(context):
    """Автоматическое сохранение данных"""
    try:
        queue_manager.save_data()
        logger.debug("Data auto-saved")
    except Exception as e:
        logger.error(f"Error in auto-save: {e}")


async def test_job(context):
    """Тестовая задача для проверки job_queue"""
    logger.info("✅ Job queue is working! Test job executed.")


def main():
    """Основная функция"""
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        raise ValueError("Токен бота не найден в переменных окружения")

    # Создаем Application с JobQueue
    application = Application.builder().token(TOKEN).build()

    # Настройка обработчиков
    setup_handlers(application)

    # Настройка периодических задач
    job_queue = application.job_queue

    if job_queue:
        # Тестовая задача - каждые 30 секунд
        job_queue.run_repeating(
            test_job,
            interval=30,
            first=5
        )

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
    application.run_polling()


if __name__ == '__main__':
    main()