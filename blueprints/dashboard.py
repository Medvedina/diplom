from flask import Blueprint, render_template, jsonify, request, current_app
from datetime import datetime
import os
import json

bp = Blueprint('dashboard', __name__)

def set_active_tab(tab_name):
    from functools import wraps
    from flask import session
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session['active_tab'] = tab_name
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def read_recent_events_from_file():
    """Читает события из файла recent_events.json"""
    try:
        # Определяем путь к файлу
        base_dir = current_app.config.get('BASE_DIR', os.getcwd())
        events_file = os.path.join(base_dir, 'ansible_data', 'recent_events.json')
        
        print(f"Пытаемся прочитать файл событий: {events_file}")
        print(f"Файл существует: {os.path.exists(events_file)}")
        
        if not os.path.exists(events_file):
            print("Файл не найден, возвращаем пустой список")
            return []
        
        # Читаем файл
        with open(events_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            if not content:
                print("Файл пустой")
                return []
            
            try:
                events = json.loads(content)
                print(f"Успешно загружено {len(events)} событий из файла")
                
                # Форматируем для отображения
                formatted_events = []
                for event in events[:10]:  # Берем последние 10
                    # Преобразуем timestamp в время
                    event_time = "??:??"
                    if 'timestamp' in event:
                        try:
                            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                            event_time = dt.strftime('%H:%M')
                        except:
                            pass
                    elif 'display_time' in event:
                        event_time = event['display_time']
                    
                    # Определяем иконку и цвет по типу действия
                    icon, color = get_action_icon_and_color(event.get('action', ''))
                    
                    formatted_events.append({
                        'time': event_time,
                        'title': get_action_title(event.get('action', ''), event.get('inventory', 'Unknown')),
                        'description': event.get('comment', 'Без комментария'),
                        'user': event.get('user', 'admin'),
                        'icon': icon,
                        'color': color,
                        'badge': get_action_badge(event.get('action', '')),
                        'raw_event': event  # Для отладки
                    })
                
                print(f"Отформатировано {len(formatted_events)} событий")
                return formatted_events
                
            except json.JSONDecodeError as e:
                print(f"Ошибка JSON в файле: {e}")
                return []
                
    except Exception as e:
        print(f"Ошибка чтения файла событий: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_action_icon_and_color(action):
    """Возвращает иконку и цвет для действия"""
    icons_colors = {
        'create': ('bi-plus-circle', 'success'),
        'edit': ('bi-pencil', 'warning'),
        'delete': ('bi-trash', 'danger'),
        'clone': ('bi-copy', 'info'),
        'export': ('bi-download', 'primary'),
        'import': ('bi-upload', 'secondary'),
        'validate': ('bi-check-circle', 'success')
    }
    return icons_colors.get(action, ('bi-file-earmark', 'secondary'))

def get_action_title(action, inventory):
    """Возвращает заголовок для действия"""
    titles = {
        'create': f'Создан инвентарь: {inventory}',
        'edit': f'Изменен инвентарь: {inventory}',
        'delete': f'Удален инвентарь: {inventory}',
        'clone': f'Клонирован инвентарь: {inventory}',
        'export': f'Экспортирован инвентарь: {inventory}',
        'import': f'Импортирован инвентарь: {inventory}',
        'validate': f'Проверен инвентарь: {inventory}'
    }
    return titles.get(action, f'Действие с инвентарем: {inventory}')

def get_action_badge(action):
    """Возвращает текст бейджа для действия"""
    badges = {
        'create': 'Создание',
        'edit': 'Изменение',
        'delete': 'Удаление',
        'clone': 'Клонирование',
        'export': 'Экспорт',
        'import': 'Импорт',
        'validate': 'Проверка'
    }
    return badges.get(action, 'Действие')

def get_demo_events():
    """Возвращает демо события если нет реальных"""
    return [
        {
            'time': datetime.now().strftime('%H:%M'),
            'title': 'Создан тестовый инвентарь',
            'description': 'Это демо-событие. Создайте реальный инвентарь',
            'user': 'system',
            'icon': 'bi-info-circle',
            'color': 'info',
            'badge': 'Демо'
        }
    ]

@bp.route('/')
@set_active_tab('dashboard')
def index():
    """Главная страница дашборда"""
    # Статистика для демонстрации
    stats = {
        'total_hosts': 42,
        'active_hosts': 38,
        'inventories': 5,
        'playbooks': 12,
        'last_activity': datetime.now().strftime('%H:%M:%S')
    }
    
    # Читаем реальные события из файла
    recent_events = read_recent_events_from_file()
    
    # Если нет реальных событий, показываем демо
    if not recent_events:
        print("Нет реальных событий, показываем демо")
        recent_events = get_demo_events()
    
    print(f"Всего событий для шаблона: {len(recent_events)}")
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_events=recent_events)

@bp.route('/overview')
@set_active_tab('dashboard')
def overview():
    """Обзорная панель"""
    return render_template('dashboard/overview.html')

@bp.route('/api/system-stats')
def api_system_stats():
    """API для получения статистики системы"""
    import psutil
    import platform
    
    # Считаем реальное количество инвентарей
    inventories_count = 0
    playbooks_count = 0
    
    try:
        base_dir = current_app.config.get('BASE_DIR', os.getcwd())
        inventories_path = os.path.join(base_dir, 'ansible_data', 'inventories')
        playbooks_path = os.path.join(base_dir, 'ansible_data', 'playbooks')
        
        if os.path.exists(inventories_path):
            inventories_count = len([f for f in os.listdir(inventories_path) 
                                   if f.endswith(('.yaml', '.yml'))])
        
        if os.path.exists(playbooks_path):
            playbooks_count = len([f for f in os.listdir(playbooks_path) 
                                 if f.endswith(('.yaml', '.yml', '.yml'))])
    except:
        pass
    
    stats = {
        'system': {
            'os': platform.system(),
            'version': platform.version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'memory_used': psutil.virtual_memory().used,
        },
        'ansible': {
            'inventories': inventories_count,
            'playbooks': playbooks_count,
        },
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(stats)

def read_recent_events_from_file():
    """Читает события из файла recent_events.json"""
    try:
        base_dir = current_app.config.get('BASE_DIR', os.getcwd())
        events_file = os.path.join(base_dir, 'ansible_data', 'recent_events.json')
        
        print(f"Пытаемся прочитать файл событий: {events_file}")
        print(f"Файл существует: {os.path.exists(events_file)}")
        
        if not os.path.exists(events_file):
            print("Файл не найден, возвращаем пустой список")
            return []
        
        with open(events_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
            if not content:
                print("Файл пустой")
                return []
            
            try:
                events = json.loads(content)
                print(f"Успешно загружено {len(events)} событий из файла")
                
                # Форматируем для отображения
                formatted_events = []
                for event in events[:10]:
                    event_time = "??:??"
                    if 'timestamp' in event:
                        try:
                            dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                            event_time = dt.strftime('%H:%M')
                        except:
                            pass
                    elif 'display_time' in event:
                        event_time = event['display_time']
                    
                    # Определяем заголовок в зависимости от типа события
                    if event.get('type') == 'playbook_run':
                        title = f"Выполнен плейбук: {event.get('playbook')}"
                        description = f"Запуск на инвентаре {event.get('inventory')} - {event.get('status')}"
                        badge = "Запуск"
                    elif event.get('type') == 'playbook':
                        if event.get('action') == 'create':
                            title = f"Создан плейбук: {event.get('playbook')}"
                            description = event.get('comment', 'Новый плейбук')
                            badge = "Создание"
                        elif event.get('action') == 'edit':
                            title = f"Изменен плейбук: {event.get('playbook')}"
                            description = event.get('comment', 'Внесены изменения')
                            badge = "Изменение"
                        elif event.get('action') == 'delete':
                            title = f"Удален плейбук: {event.get('playbook')}"
                            description = event.get('comment', 'Плейбук удален')
                            badge = "Удаление"
                        else:
                            title = f"Плейбук: {event.get('playbook')}"
                            description = event.get('comment', 'Действие с плейбуком')
                            badge = "Плейбук"
                    else:
                        # Событие инвентаря
                        title = get_action_title(event.get('action', ''), event.get('inventory', 'Unknown'))
                        description = event.get('comment', 'Без комментария')
                        badge = get_action_badge(event.get('action', ''))
                    
                    formatted_events.append({
                        'time': event_time,
                        'title': title,
                        'description': description,
                        'user': event.get('user', 'admin'),
                        'icon': event.get('icon', 'bi-file-earmark'),
                        'color': event.get('color', 'secondary'),
                        'badge': badge
                    })
                
                print(f"Отформатировано {len(formatted_events)} событий")
                return formatted_events
                
            except json.JSONDecodeError as e:
                print(f"Ошибка JSON в файле: {e}")
                return []
                
    except Exception as e:
        print(f"Ошибка чтения файла событий: {e}")
        import traceback
        traceback.print_exc()
        return []
    
def get_action_icon_and_color(action):
    """Возвращает иконку и цвет для действия"""
    icons_colors = {
        'create': ('bi-plus-circle', 'success'),
        'edit': ('bi-pencil', 'warning'),
        'delete': ('bi-trash', 'danger'),
        'clone': ('bi-copy', 'info'),
        'export': ('bi-download', 'primary'),
        'import': ('bi-upload', 'secondary'),
        'validate': ('bi-check-circle', 'success'),
        'run': ('bi-play-circle', 'primary')
    }
    return icons_colors.get(action, ('bi-file-earmark', 'secondary'))   