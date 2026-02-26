import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models.inventory_history import InventoryHistory

# Создаем контекст приложения
with app.app_context():
    print("Тестирование системы истории...")
    
    # 1. Проверяем пути
    print(f"BASE_DIR: {app.config.get('BASE_DIR')}")
    print(f"RECENT_EVENTS_FILE: {app.config.get('RECENT_EVENTS_FILE')}")
    
    # 2. Логируем тестовое событие
    print("\nЛогируем тестовое событие...")
    success = InventoryHistory.log_change(
        inventory_name="test_inventory",
        action="create",
        user="admin",
        comment="Тестовое создание инвентаря",
        changes={"test": "data"}
    )
    print(f"Логирование успешно: {success}")
    
    # 3. Читаем события
    print("\nЧитаем события...")
    events = InventoryHistory.get_recent_events()
    print(f"Получено событий: {len(events)}")
    
    if events:
        for i, event in enumerate(events[:3]):
            print(f"{i+1}. {event.get('inventory')} - {event.get('action')} - {event.get('comment')}")
    
    # 4. Проверяем файл
    recent_file = app.config.get('RECENT_EVENTS_FILE')
    if os.path.exists(recent_file):
        print(f"\nФайл {recent_file} существует")
        with open(recent_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"Размер файла: {len(content)} байт")
            print(f"Содержимое (первые 500 символов):\n{content[:500]}...")
    else:
        print(f"\nФайл {recent_file} НЕ существует!")
        
    print("\nТестирование завершено!")