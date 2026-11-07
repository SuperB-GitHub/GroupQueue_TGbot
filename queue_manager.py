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
        self.queue_message_ids = defaultdict(lambda: None)
        self.known_users = defaultdict(list)
        self.topic_to_chat = {}  # Новое: маппинг topic_id -> chat_id
        self.banned_users = {}
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
                    # Восстанавливаем known_users
                    self.known_users = defaultdict(list)
                    for chat_id_str, users in data.get('known_users', {}).items():
                        self.known_users[int(chat_id_str)] = [dict(u, is_bot=u.get('is_bot', False)) for u in users]
                    # Восстанавливаем topic_to_chat
                    self.topic_to_chat = {int(k): v for k, v in data.get('topic_to_chat', {}).items()}
                    self.banned_users = data.get('banned_users', {})

                    # Автоматически добавляем пользователей из очередей в known_users
                    self._sync_queue_users_to_known_users()
                    
                logger.info(f"Данные загружены из {self.filename}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")

    def _sync_queue_users_to_known_users(self):
        """Синхронизация пользователей из очередей в known_users"""
        for topic_id, queue in self.queues.items():
            if topic_id in self.topic_to_chat:
                chat_id = self.topic_to_chat[topic_id]
                for user in queue:
                    # Проверяем, нет ли уже такого пользователя
                    if not any(u['user_id'] == user['user_id'] for u in self.known_users[chat_id]):
                        self.add_known_user(
                            chat_id,
                            user['user_id'],
                            user['first_name'],
                            user['last_name'],
                            user['username'],
                            False  # is_bot
                        )

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            # Конвертируем ключи в строки для JSON
            queues_serializable = {str(k): v for k, v in self.queues.items()}
            queue_message_ids_serializable = {str(k): v for k, v in self.queue_message_ids.items()}
            known_users_serializable = {str(k): v for k, v in self.known_users.items()}
            topic_to_chat_serializable = {str(k): v for k, v in self.topic_to_chat.items()}

            data = {
                'queues': queues_serializable,
                'pending_swaps': self.pending_swaps,
                'queue_message_ids': queue_message_ids_serializable,
                'known_users': known_users_serializable,
                'topic_to_chat': topic_to_chat_serializable,
                'banned_users': self.banned_users,
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

        if self.is_banned(user_id):
            logger.info(f"Banned user {user_id} tried to join queue {topic_id}")
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
        
        # Автоматически добавляем пользователя в known_users для этого чата
        if topic_id in self.topic_to_chat:
            chat_id = self.topic_to_chat[topic_id]
            self.add_known_user(chat_id, user_id, first_name, last_name, username, False)
        
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

    def remove_user_by_username(self, topic_id, username):
        queue = self.queues[topic_id]
        for i, user in enumerate(queue):
            if user['username'] == username:
                queue.pop(i)
                self.save_data()
                logger.info(f"User @{username} removed from queue {topic_id}")
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

    def set_topic_chat_mapping(self, topic_id, chat_id):
        """Сохранить связь topic_id с chat_id"""
        self.topic_to_chat[topic_id] = chat_id
        self.save_data()

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

    def add_known_user(self, chat_id, user_id, first_name, last_name, username, is_bot=False):
        """Добавление известного пользователя из сообщений"""
        users = self.known_users[chat_id]
        if not any(u['user_id'] == user_id for u in users):
            user_data = {
                'user_id': user_id,
                'first_name': first_name or '',
                'last_name': last_name or '',
                'username': username or '',
                'display_name': f"{first_name or ''} {last_name or ''}".strip() or f"User_{user_id}",
                'is_bot': is_bot
            }
            users.append(user_data)
            self.save_data()
            logger.info(f"Known user {user_id} added for chat {chat_id}")

    def get_known_users(self, chat_id):
        """Получение списка известных пользователей"""
        return self.known_users[chat_id]

    def is_banned(self, user_id: int) -> bool:
        return str(user_id) in self.banned_users

    def ban_user(self, user_id: int, username: str) -> None:
        self.banned_users[str(user_id)] = {
            "username": username,
            "banned_at": datetime.now().isoformat()
        }
        # удаляем из всех очередей
        for topic_id, queue in self.queues.items():
            self.queues[topic_id] = [u for u in queue if u["user_id"] != user_id]
        self.save_data()

    def unban_user(self, user_id: int) -> bool:
        if str(user_id) in self.banned_users:
            del self.banned_users[str(user_id)]
            self.save_data()
            return True
        return False

    def find_user_by_username(self, username: str):
        """Ищем user_id по username среди забаненных, известных пользователей и очередей."""
        username = username.lstrip("@").lower()

        # 1) среди забаненных
        for uid, info in self.banned_users.items():
            if info.get("username", "").lower() == username:
                return int(uid), info.get("username")

        # 2) среди known_users (это dict chat_id -> list[user])
        for users_list in self.known_users.values():
            for u in users_list:
                if (u.get("username") or "").lower() == username:
                    return u["user_id"], u.get("username")

        # 3) среди участников очередей
        for queue in self.queues.values():
            for u in queue:
                if (u.get("username") or "").lower() == username:
                    return u["user_id"], u.get("username")

        return None, None


# Создаем глобальный экземпляр менеджера очередей
queue_manager = PersistentQueueManager()