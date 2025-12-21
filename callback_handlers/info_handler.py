import logging

logger = logging.getLogger(__name__)


async def show_info_handler(query):
    """
    Обработчик для кнопки 'Информация'
    Показывает всплывающее окно с краткой информацией
    """
    info_text = """📋 Инфо о боте:

⬆️ - Добавиться самому в очередь
⬇️ - Выйти самому из очереди
🔄 - Обмен местами с кем-то
⤵️ - Отдать место любому
👨‍👦 - Добавить по @username

⏱️ 60 сек на действия"""
    
    try:
        await query.answer(
            text=info_text,
            show_alert=True
        )
        logger.info(f"Info shown to user {query.from_user.id}")
    except Exception as e:
        logger.error(f"Error showing info: {e}")