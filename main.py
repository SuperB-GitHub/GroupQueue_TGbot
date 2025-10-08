import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import atexit

from queue_manager import queue_manager
from handlers import start, init_queue_message, backup_command, handle_callback

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
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^(add_to_queue|remove_from_queue|start_swap)"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_with_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_confirm_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^swap_cancel_"))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^back_to_main$"))

def main():
    """Основная функция"""
    TOKEN = '7746170419:AAGymhi99dS0hNLFicCgyK-tLRCTKRkVRWw'
    
    application = Application.builder().token(TOKEN).build()
    
    # Настройка обработчиков
    setup_handlers(application)
    
    # Автоматическое сохранение при завершении
    atexit.register(queue_manager.save_data)
    
    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()