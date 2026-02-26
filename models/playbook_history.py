import json
from datetime import datetime
import os
from flask import current_app, request

class PlaybookHistory:
    """Класс для управления историей изменений плейбуков"""
    
    @staticmethod
    def log_change(playbook_name, action, user="admin", comment="", details=None):
        """Логирует изменение плейбука"""
        try:
            base_path = current_app.config.get('BASE_DIR', os.getcwd())
            history_dir = os.path.join(base_path, 'ansible_data', 'history', 'playbooks')
            os.makedirs(history_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_file = os.path.join(history_dir, f"{playbook_name}_{timestamp}.json")
            
            # Определяем иконку и цвет для действия
            icon, color = PlaybookHistory._get_action_icon_color(action)
            
            history_entry = {
                'playbook': playbook_name,
                'action': action,
                'user': user,
                'timestamp': datetime.now().isoformat(),
                'comment': comment,
                'details': details or {},
                'icon': icon,
                'color': color,
                'metadata': {
                    'ip': request.remote_addr if request else '127.0.0.1',
                    'user_agent': request.headers.get('User-Agent', '') if request else ''
                }
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_entry, f, ensure_ascii=False, indent=2)
            
            # Также добавляем в общий лог
            PlaybookHistory._add_to_recent_log(history_entry)
            
            print(f"✓ Запись добавлена в историю плейбуков: {playbook_name} - {action}")
            return True
            
        except Exception as e:
            print(f"✗ Ошибка логирования плейбука: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def log_run(playbook_name, inventory_name, user="admin", status="success", results=None):
        """Логирует выполнение плейбука"""
        try:
            base_path = current_app.config.get('BASE_DIR', os.getcwd())
            history_dir = os.path.join(base_path, 'ansible_data', 'history', 'playbooks', 'runs')
            os.makedirs(history_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_file = os.path.join(history_dir, f"{playbook_name}_{timestamp}.json")
            
            # Определяем цвет в зависимости от статуса
            color = 'success' if status == 'success' else 'danger' if status == 'failed' else 'warning'
            icon = 'bi-play-circle' if status == 'success' else 'bi-exclamation-triangle'
            
            history_entry = {
                'playbook': playbook_name,
                'action': 'run',
                'status': status,
                'inventory': inventory_name,
                'user': user,
                'timestamp': datetime.now().isoformat(),
                'results': results or {},
                'icon': icon,
                'color': color,
                'metadata': {
                    'ip': request.remote_addr if request else '127.0.0.1'
                }
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_entry, f, ensure_ascii=False, indent=2)
            
            # Также добавляем в общий лог
            PlaybookHistory._add_to_recent_log(history_entry)
            
            print(f"✓ Запись о выполнении добавлена: {playbook_name} на {inventory_name}")
            return True
            
        except Exception as e:
            print(f"✗ Ошибка логирования выполнения: {e}")
            return False
    
    @staticmethod
    def _add_to_recent_log(entry):
        """Добавляет запись в файл последних событий"""
        try:
            base_path = current_app.config.get('BASE_DIR', os.getcwd())
            recent_file = os.path.join(base_path, 'ansible_data', 'recent_events.json')
            
            os.makedirs(os.path.dirname(recent_file), exist_ok=True)
            
            # Читаем существующие события
            events = []
            if os.path.exists(recent_file):
                try:
                    with open(recent_file, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                        if not isinstance(events, list):
                            events = []
                except json.JSONDecodeError:
                    events = []
            
            # Определяем тип события
            event_type = 'playbook'
            if entry.get('action') in ['create', 'edit', 'delete', 'clone']:
                event_type = 'playbook'
            elif entry.get('action') == 'run':
                event_type = 'playbook_run'
            
            # Создаем новое событие
            new_event = {
                'id': f"playbook_{int(datetime.now().timestamp())}",
                'type': event_type,
                'action': entry['action'],
                'playbook': entry.get('playbook', entry.get('inventory', 'Unknown')),
                'user': entry['user'],
                'comment': entry.get('comment', ''),
                'status': entry.get('status', ''),
                'inventory': entry.get('inventory', ''),
                'timestamp': entry['timestamp'],
                'display_time': datetime.now().strftime('%H:%M'),
                'icon': entry.get('icon', 'bi-file-earmark'),
                'color': entry.get('color', 'secondary')
            }
            
            # Добавляем в начало
            events.insert(0, new_event)
            
            # Ограничиваем количество (последние 100)
            events = events[:100]
            
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"✗ Ошибка добавления в лог: {e}")
            return False
    
    @staticmethod
    def _get_action_icon_color(action):
        """Возвращает иконку и цвет для действия"""
        icons_colors = {
            'create': ('bi-plus-circle', 'success'),
            'edit': ('bi-pencil', 'warning'),
            'delete': ('bi-trash', 'danger'),
            'clone': ('bi-copy', 'info'),
            'run': ('bi-play-circle', 'primary'),
            'export': ('bi-download', 'primary'),
            'import': ('bi-upload', 'secondary'),
            'validate': ('bi-check-circle', 'success')
        }
        return icons_colors.get(action, ('bi-file-earmark', 'secondary'))
    
    @staticmethod
    def get_recent_events(limit=10):
        """Получает последние события из файла"""
        try:
            base_path = current_app.config.get('BASE_DIR', os.getcwd())
            recent_file = os.path.join(base_path, 'ansible_data', 'recent_events.json')
            
            if not os.path.exists(recent_file):
                return []
            
            with open(recent_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
                
            return events[:limit]
            
        except Exception as e:
            print(f"Ошибка чтения событий: {e}")
            return []
    
    @staticmethod
    def get_playbook_history(playbook_name, limit=20):
        """Получает историю конкретного плейбука"""
        try:
            base_path = current_app.config.get('BASE_DIR', os.getcwd())
            history_dir = os.path.join(base_path, 'ansible_data', 'history', 'playbooks')
            runs_dir = os.path.join(base_path, 'ansible_data', 'history', 'playbooks', 'runs')
            
            history = []
            
            # Собираем файлы из обеих директорий
            if os.path.exists(history_dir):
                for file in os.listdir(history_dir):
                    if file.startswith(f"{playbook_name}_") and file.endswith('.json'):
                        with open(os.path.join(history_dir, file), 'r', encoding='utf-8') as f:
                            history.append(json.load(f))
            
            if os.path.exists(runs_dir):
                for file in os.listdir(runs_dir):
                    if file.startswith(f"{playbook_name}_") and file.endswith('.json'):
                        with open(os.path.join(runs_dir, file), 'r', encoding='utf-8') as f:
                            history.append(json.load(f))
            
            # Сортируем по времени (новые сначала)
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return history[:limit]
            
        except Exception as e:
            print(f"Ошибка чтения истории плейбука: {e}")
            return []