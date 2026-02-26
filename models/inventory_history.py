import json
from datetime import datetime
import os
from flask import current_app, request

class InventoryHistory:
    """Класс для управления историей изменений инвентарей"""
    @staticmethod
    def _get_base_path():
        """Возвращает базовый путь к директории данных"""
        try:
            # Пробуем получить из конфигурации
            base_path = current_app.config.get('BASE_DIR', '')
            if base_path:
                return base_path
            
            # Или определяем относительно текущего файла
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            return project_root
            
        except:
            # По умолчанию текущая директория
            return os.getcwd()
    
    @staticmethod
    def log_change(inventory_name, action, user="admin", comment="", changes=None):
        """Логирует изменение инвентаря"""
        try:
            base_path = InventoryHistory._get_base_path()
            history_dir = os.path.join(base_path, 'ansible_data', 'history')
            os.makedirs(history_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_file = os.path.join(history_dir, f"{inventory_name}_{timestamp}.json")
            
            history_entry = {
                'inventory': inventory_name,
                'action': action,
                'user': user,
                'timestamp': datetime.now().isoformat(),
                'comment': comment,
                'changes': changes or {}
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_entry, f, ensure_ascii=False, indent=2)
            
            # Также добавляем в общий лог
            InventoryHistory._add_to_recent_log(history_entry)
            
            print(f"✓ Запись добавлена в историю: {inventory_name} - {action}")
            return True
            
        except Exception as e:
            print(f"✗ Ошибка логирования: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def _add_to_recent_log(entry):
        """Добавляет запись в файл последних событий"""
        try:
            base_path = InventoryHistory._get_base_path()
            recent_file = os.path.join(base_path, 'ansible_data', 'recent_events.json')
            
            # Создаем директорию если нужно
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
                except Exception as e:
                    print(f"Ошибка чтения файла событий: {e}")
                    events = []
            
            # Создаем новое событие
            new_event = {
                'id': f"inv_{int(datetime.now().timestamp())}",
                'type': 'inventory',
                'action': entry['action'],
                'inventory': entry['inventory'],
                'user': entry['user'],
                'comment': entry['comment'],
                'timestamp': entry['timestamp'],
                'display_time': datetime.now().strftime('%H:%M'),
                'icon': InventoryHistory._get_action_icon(entry['action']),
                'color': InventoryHistory._get_action_color(entry['action'])
            }
            
            # Добавляем в начало
            events.insert(0, new_event)
            
            # Ограничиваем количество (последние 50)
            events = events[:50]
            
            # Сохраняем обратно
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Событие добавлено в recent_events.json: {entry['inventory']}")
            return True
            
        except Exception as e:
            print(f"✗ Ошибка добавления в лог: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def get_recent_events(limit=10):
        """Получает последние события"""
        try:
            base_path = InventoryHistory._get_base_path()
            recent_file = os.path.join(base_path, 'ansible_data', 'recent_events.json')
            
            print(f"Пытаемся прочитать файл: {recent_file}")
            print(f"Файл существует: {os.path.exists(recent_file)}")
            
            if not os.path.exists(recent_file):
                print("Файл recent_events.json не найден, возвращаем пустой список")
                return []
            
            # Читаем файл
            with open(recent_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
                if not content:
                    print("Файл recent_events.json пустой")
                    return []
                
                try:
                    events = json.loads(content)
                    if not isinstance(events, list):
                        print("Данные не являются списком, исправляем")
                        events = []
                    
                    print(f"Успешно загружено {len(events)} событий")
                    return events[:limit]
                    
                except json.JSONDecodeError as e:
                    print(f"Ошибка JSON в файле: {e}")
                    # Создаем новый правильный файл
                    with open(recent_file, 'w', encoding='utf-8') as f:
                        json.dump([], f, indent=2)
                    return []
                    
        except Exception as e:
            print(f"Критическая ошибка чтения событий: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def _get_action_icon(action):
        """Возвращает иконку для действия"""
        icons = {
            'create': 'bi-plus-circle',
            'edit': 'bi-pencil',
            'delete': 'bi-trash',
            'clone': 'bi-copy',
            'export': 'bi-download',
            'import': 'bi-upload',
            'validate': 'bi-check-circle'
        }
        return icons.get(action, 'bi-file-earmark')
    
    @staticmethod
    def _get_action_color(action):
        """Возвращает цвет для действия"""
        colors = {
            'create': 'success',
            'edit': 'warning',
            'delete': 'danger',
            'clone': 'info',
            'export': 'primary',
            'import': 'secondary',
            'validate': 'success'
        }
        return colors.get(action, 'secondary')
    
    @staticmethod
    def get_inventory_history(inventory_name, limit=20):
        """Получает историю изменений конкретного инвентаря"""
        try:
            history_dir = current_app.config.get('HISTORY_PATH', 'ansible_data/history')
            
            if not os.path.exists(history_dir):
                return []
            
            history_files = []
            for file in os.listdir(history_dir):
                if file.startswith(f"{inventory_name}_") and file.endswith('.json'):
                    history_files.append(os.path.join(history_dir, file))
            
            # Сортируем по времени (новые сначала)
            history_files.sort(reverse=True)
            
            history = []
            for file_path in history_files[:limit]:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        entry = json.load(f)
                        history.append(entry)
                except:
                    continue
            
            return history
        except Exception as e:
            current_app.logger.error(f"Error reading inventory history: {e}")
            return []
    
    @staticmethod
    def compare_inventories(old_content, new_content, inventory_name):
        """Сравнивает две версии инвентаря и возвращает изменения"""
        try:
            import yaml
            
            old_yaml = yaml.safe_load(old_content) if old_content else {}
            new_yaml = yaml.safe_load(new_content) if new_content else {}
            
            changes = {
                'added_hosts': [],
                'removed_hosts': [],
                'modified_hosts': [],
                'added_groups': [],
                'removed_groups': [],
                'modified_vars': []
            }
            
            # Функция для извлечения всех хостов
            def extract_hosts(inventory_data):
                hosts = {}
                if inventory_data and 'all' in inventory_data and 'children' in inventory_data['all']:
                    for group_name, group_data in inventory_data['all']['children'].items():
                        if 'hosts' in group_data:
                            for host_name, host_vars in group_data['hosts'].items():
                                hosts[host_name] = {
                                    'group': group_name,
                                    'vars': host_vars
                                }
                return hosts
            
            old_hosts = extract_hosts(old_yaml)
            new_hosts = extract_hosts(new_yaml)
            
            # Находим изменения в хостах
            all_hosts = set(list(old_hosts.keys()) + list(new_hosts.keys()))
            
            for host in all_hosts:
                if host in new_hosts and host not in old_hosts:
                    changes['added_hosts'].append({
                        'host': host,
                        'group': new_hosts[host]['group'],
                        'vars': new_hosts[host]['vars']
                    })
                elif host in old_hosts and host not in new_hosts:
                    changes['removed_hosts'].append({
                        'host': host,
                        'group': old_hosts[host]['group']
                    })
                elif host in old_hosts and host in new_hosts:
                    # Проверяем изменения в переменных
                    if old_hosts[host]['vars'] != new_hosts[host]['vars']:
                        changes['modified_hosts'].append({
                            'host': host,
                            'old_vars': old_hosts[host]['vars'],
                            'new_vars': new_hosts[host]['vars']
                        })
            
            # Находим изменения в группах
            old_groups = set(old_yaml.get('all', {}).get('children', {}).keys() if old_yaml else [])
            new_groups = set(new_yaml.get('all', {}).get('children', {}).keys() if new_yaml else [])
            
            changes['added_groups'] = list(new_groups - old_groups)
            changes['removed_groups'] = list(old_groups - new_groups)
            
            return changes
        except Exception as e:
            current_app.logger.error(f"Error comparing inventories: {e}")
            return {}