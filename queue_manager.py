import json
import os
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class PersistentQueueManager:
    def __init__(self, filename='queues_data.json'):
        # Получаем абсолютный путь к папке проекта
        self.project_dir = os.path.dirname(os.path.abspath(__file__))
        self.filename = os.path.join(self.project_dir, filename)

        self.queues = defaultdict(list)
        self.pending_swaps = {}
        self.queue_message_ids = defaultdict(lambda: None)  # topic_id: message_id основного сообщения
        self.load_data()

    def load_data(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Восстанавливаем queues
                    for topic_id_str, queue in data.get('queues', {}).items():
                        self.queues[int(topic_id_str)] = queue
                    self.pending_swaps = data.get('pending_swaps', {})
                    # Восстанавливаем queue_message_ids
                    self.queue_message_ids = {int(k): v for k, v in data.get('queue_message_ids', {}).items()}
                logger.info(f"Данные загружены из {self.filename}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            # Конвертируем topic_id в строки для JSON
            queues_serializable = {str(k): v for k, v in self.queues.items()}
            queue_message_ids_serializable = {str(k): v for k, v in self.queue_message_ids.items()}

            data = {
                'queues': queues_serializable,
                'pending_swaps': self.pending_swaps,
                'queue_message_ids': queue_message_ids_serializable,
                'last_save': datetime.now().isoformat()
            }

            # Создаем временный файл для безопасного сохранения
            temp_filename = self.filename + '.tmp'
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Заменяем старый файл новым
            if os.path.exists(self.filename):
                os.replace(temp_filename, self.filename)
            else:
                os.rename(temp_filename, self.filename)

            logger.info(f"Данные сохранены в {self.filename}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    def add_user_to_queue(self, topic_id, user_id, first_name, last_name, username):
        """Добавление пользователя в очередь с валидацией"""
        if not isinstance(topic_id, int) or not isinstance(user_id, int):
            logger.error(f"Invalid IDs: topic_id={topic_id}, user_id={user_id}")
            return False

        queue = self.queues[topic_id]

        # Проверяем, не добавлен ли уже пользователь
        if any(user['user_id'] == user_id for user in queue):
            return False

        user_data = {
            'user_id': user_id,
            'first_name': first_name or '',
            'last_name': last_name or '',
            'username': username or '',
            'display_name': f"{first_name or ''} {last_name or ''}".strip() or f"User_{user_id}",
            'joined_at': datetime.now().isoformat()
        }

        queue.append(user_data)
        self.save_data()
        logger.info(f"User {user_id} added to queue {topic_id}")
        return True

    def remove_user_from_queue(self, topic_id, user_id):
        queue = self.queues[topic_id]
        for i, user in enumerate(queue):
            if user['user_id'] == user_id:
                queue.pop(i)
                self.save_data()
                logger.info(f"User {user_id} removed from queue {topic_id}")
                return True
        return False

    def swap_users(self, topic_id, user1_id, user2_id):
        queue = self.queues[topic_id]
        user1_index = None
        user2_index = None

        for i, user in enumerate(queue):
            if user['user_id'] == user1_id:
                user1_index = i
            if user['user_id'] == user2_id:
                user2_index = i

        if user1_index is not None and user2_index is not None:
            queue[user1_index], queue[user2_index] = queue[user2_index], queue[user1_index]
            self.save_data()
            logger.info(f"Users {user1_id} and {user2_id} swapped in queue {topic_id}")
            return True
        return False

    def get_queue_text(self, topic_id):
        queue = self.queues[topic_id]
        if not queue:
            return "Очередь пуста"

        text = "📋 Текущая очередь:\n\n"
        for i, user in enumerate(queue, 1):
            username = f"(@{user['username']})" if user['username'] else ""
            text += f"{i}. {user['display_name']} {username}\n"

        return text

    def set_queue_message_id(self, topic_id, message_id):
        self.queue_message_ids[topic_id] = message_id
        self.save_data()

    def get_queue_message_id(self, topic_id):
        return self.queue_message_ids.get(topic_id)

    def add_pending_swap(self, swap_id, swap_data):
        self.pending_swaps[swap_id] = swap_data
        self.save_data()
        logger.info(f"Pending swap added: {swap_id}")

    def remove_pending_swap(self, swap_id):
        if swap_id in self.pending_swaps:
            del self.pending_swaps[swap_id]
            self.save_data()
            logger.info(f"Pending swap removed: {swap_id}")

    def get_pending_swap(self, swap_id):
        return self.pending_swaps.get(swap_id)


# Создаем глобальный экземпляр менеджера очередей
queue_manager = PersistentQueueManager()