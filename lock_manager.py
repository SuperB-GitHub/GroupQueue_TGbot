import logging
import time

logger = logging.getLogger(__name__)

class SimpleLockManager:
    """
    Простой менеджер блокировок для предотвращения спама
    Блокирует топик при запуске операции, разблокирует при завершении
    """
    def __init__(self):
        # topic_id: {'locked': bool, 'user_id': int, 'operation': str, 'timestamp': float}
        self.locks = {}
        # Таймаут блокировки на случай зависания (2 минуты)
        self.timeout = 120
    
    def is_locked(self, topic_id: int) -> bool:
        """Проверяет, заблокирован ли топик"""
        if topic_id not in self.locks:
            return False
        
        lock = self.locks[topic_id]
        # Проверяем таймаут
        if time.time() - lock['timestamp'] > self.timeout:
            logger.warning(f"Lock timeout for topic {topic_id}, auto-unlocking")
            del self.locks[topic_id]
            return False
        
        return lock['locked']
    
    def get_lock_info(self, topic_id: int) -> dict:
        """Получить информацию о блокировке"""
        if topic_id in self.locks:
            lock = self.locks[topic_id]
            # Проверяем таймаут
            if time.time() - lock['timestamp'] > self.timeout:
                del self.locks[topic_id]
                return None
            return lock
        return None
    
    def lock(self, topic_id: int, user_id: int, operation: str) -> bool:
        """Заблокировать топик для операции"""
        if self.is_locked(topic_id):
            return False
        
        self.locks[topic_id] = {
            'locked': True,
            'user_id': user_id,
            'operation': operation,
            'timestamp': time.time()
        }
        logger.info(f"Topic {topic_id} locked by {user_id} for {operation}")
        return True
    
    def unlock(self, topic_id: int) -> bool:
        """Разблокировать топик"""
        if topic_id in self.locks:
            logger.info(f"Topic {topic_id} unlocked")
            del self.locks[topic_id]
            return True
        return False
    
    def unlock_by_user(self, topic_id: int, user_id: int) -> bool:
        """Разблокировать топик, если он заблокирован этим пользователем"""
        if topic_id in self.locks and self.locks[topic_id]['user_id'] == user_id:
            return self.unlock(topic_id)
        return False

# Глобальный экземпляр
lock_manager = SimpleLockManager()