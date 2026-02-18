from flask import Blueprint, render_template, jsonify, request, current_app
from datetime import datetime
import os
import json
import yaml
import shutil

bp = Blueprint('playbooks', __name__)

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

# Конфигурация доступных задач и протоколов
TASKS_CONFIG = {
    'ping': {
        'name': 'Ping тест',
        'icon': 'bi-wifi',
        'color': 'success',
        'description': 'Проверка доступности устройств',
        'module': 'ping',
        'params': [
            {'name': 'count', 'label': 'Количество пакетов', 'type': 'number', 'default': 3, 'min': 1, 'max': 10},
            {'name': 'size', 'label': 'Размер пакета (bytes)', 'type': 'number', 'default': 56, 'min': 0, 'max': 1500}
        ]
    },
    'interface_config': {
        'name': 'Настройка интерфейса',
        'icon': 'bi-ethernet',
        'color': 'primary',
        'description': 'Конфигурация сетевых интерфейсов',
        'module': 'ios_config',
        'params': [
            {'name': 'interface', 'label': 'Интерфейс', 'type': 'select', 
             'options': ['GigabitEthernet0/1', 'GigabitEthernet0/2', 'Vlan1', 'Loopback0']},
            {'name': 'description', 'label': 'Описание', 'type': 'text'},
            {'name': 'ip_address', 'label': 'IP адрес', 'type': 'text', 'placeholder': '192.168.1.1/24'},
            {'name': 'admin_state', 'label': 'Состояние', 'type': 'select', 
             'options': ['up', 'down']}
        ]
    },
    'ospf': {
        'name': 'OSPF',
        'icon': 'bi-diagram-3',
        'color': 'warning',
        'description': 'Настройка протокола OSPF',
        'module': 'ios_config',
        'params': [
            {'name': 'process_id', 'label': 'Process ID', 'type': 'number', 'default': 1, 'min': 1, 'max': 65535},
            {'name': 'router_id', 'label': 'Router ID', 'type': 'text', 'placeholder': '1.1.1.1'},
            {'name': 'network', 'label': 'Network', 'type': 'text', 'placeholder': '10.0.0.0 0.0.0.255 area 0'},
            {'name': 'area', 'label': 'Area', 'type': 'number', 'default': 0}
        ]
    },
    'isis': {
        'name': 'IS-IS',
        'icon': 'bi-grid-3x3-gap',
        'color': 'info',
        'description': 'Настройка протокола IS-IS',
        'module': 'ios_config',
        'params': [
            {'name': 'net', 'label': 'NET адрес', 'type': 'text', 
             'placeholder': '49.0001.0010.0100.1001.00'},
            {'name': 'system_id', 'label': 'System ID', 'type': 'text', 
             'placeholder': '0010.0100.1001'},
            {'name': 'area', 'label': 'Area', 'type': 'text', 'default': '49.0001'},
            {'name': 'level', 'label': 'Level', 'type': 'select', 
             'options': ['level-1', 'level-2', 'level-1-2']}
        ]
    },
    'stp': {
        'name': 'STP',
        'icon': 'bi-shield-shaded',
        'color': 'danger',
        'description': 'Настройка протокола STP',
        'module': 'ios_config',
        'params': [
            {'name': 'mode', 'label': 'Режим', 'type': 'select', 
             'options': ['pvst', 'rapid-pvst', 'mst']},
            {'name': 'priority', 'label': 'Приоритет', 'type': 'number', 
             'default': 32768, 'min': 0, 'max': 61440, 'step': 4096},
            {'name': 'vlan', 'label': 'VLAN', 'type': 'text', 'default': '1-4094'},
            {'name': 'root_primary', 'label': 'Root Primary', 'type': 'checkbox', 'default': False}
        ]
    },
    'rstp': {
        'name': 'RSTP',
        'icon': 'bi-shield',
        'color': 'warning',
        'description': 'Настройка Rapid STP',
        'module': 'ios_config',
        'params': [
            {'name': 'priority', 'label': 'Приоритет', 'type': 'number', 
             'default': 32768, 'min': 0, 'max': 61440, 'step': 4096},
            {'name': 'link_type', 'label': 'Тип линка', 'type': 'select', 
             'options': ['point-to-point', 'shared']},
            {'name': 'portfast', 'label': 'PortFast', 'type': 'checkbox', 'default': False},
            {'name': 'bpduguard', 'label': 'BPDU Guard', 'type': 'checkbox', 'default': False}
        ]
    },
    'vlan': {
        'name': 'VLAN',
        'icon': 'bi-tags',
        'color': 'success',
        'description': 'Управление VLAN',
        'module': 'ios_vlan',
        'params': [
            {'name': 'vlan_id', 'label': 'VLAN ID', 'type': 'number', 
             'required': True, 'min': 1, 'max': 4094},
            {'name': 'name', 'label': 'Имя VLAN', 'type': 'text', 'placeholder': 'VLAN Name'},
            {'name': 'state', 'label': 'Состояние', 'type': 'select', 
             'options': ['active', 'suspend']},
            {'name': 'interfaces', 'label': 'Интерфейсы', 'type': 'text', 
             'placeholder': 'Gi0/1, Gi0/2'}
        ]
    },
    'backup_config': {
        'name': 'Бэкап конфигурации',
        'icon': 'bi-cloud-download',
        'color': 'info',
        'description': 'Сохранение конфигурации устройств',
        'module': 'backup',
        'params': [
            {'name': 'destination', 'label': 'Директория', 'type': 'text', 
             'default': '/backups'},
            {'name': 'compress', 'label': 'Архивировать', 'type': 'checkbox', 'default': True},
            {'name': 'include_secrets', 'label': 'Включить секреты', 'type': 'checkbox', 'default': False}
        ]
    },
    'update_config': {
        'name': 'Обновление конфигурации',
        'icon': 'bi-arrow-repeat',
        'color': 'warning',
        'description': 'Массовое обновление конфигурации',
        'module': 'ios_config',
        'params': [
            {'name': 'lines', 'label': 'Команды', 'type': 'textarea', 
             'placeholder': 'Введите команды, по одной на строку'},
            {'name': 'parents', 'label': 'Контекст', 'type': 'text', 
             'placeholder': 'interface GigabitEthernet0/1'},
            {'name': 'save', 'label': 'Сохранить', 'type': 'checkbox', 'default': True},
            {'name': 'match', 'label': 'Режим', 'type': 'select', 
             'options': ['line', 'strict', 'exact', 'none']}
        ]
    }
}

@bp.route('/')
@set_active_tab('playbooks')
def pb_list():
    """Список плейбуков"""
    # Получаем реальные плейбуки из директории
    playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
    playbooks = []
    
    if os.path.exists(playbooks_path):
        for file in os.listdir(playbooks_path):
            if file.endswith(('.yml', '.yaml')):
                file_path = os.path.join(playbooks_path, file)
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                playbooks.append({
                    'name': file,
                    'description': get_playbook_description(file_path),
                    'last_run': get_playbook_last_run(file_path),
                    'created': mod_time.strftime('%Y-%m-%d %H:%M')
                })
    
    # Если нет плейбуков, показываем демо
    if not playbooks:
        playbooks = [
            {'name': 'ping_test.yml', 'description': 'Проверка доступности хостов', 'last_run': '2023-10-15 14:30'},
            {'name': 'ospf_config.yml', 'description': 'Настройка OSPF на маршрутизаторах', 'last_run': '2023-10-14 10:15'},
            {'name': 'vlan_setup.yml', 'description': 'Настройка VLAN на коммутаторах', 'last_run': '2023-10-13 09:45'},
            {'name': 'stp_config.yml', 'description': 'Конфигурация STP/RSTP', 'last_run': '2023-10-12 16:20'},
        ]
    
    return render_template('playbooks/pb_list.html', playbooks=playbooks)

@bp.route('/create')
@set_active_tab('playbooks')
def create():
    """Страница создания плейбука"""
    return render_template('playbooks/create.html', tasks_config=TASKS_CONFIG)

@bp.route('/edit/<playbook_name>')
@set_active_tab('playbooks')
def edit(playbook_name):
    """Страница редактирования плейбука"""
    return render_template('playbooks/edit.html', playbook_name=playbook_name)

@bp.route('/run/<playbook_name>')
@set_active_tab('playbooks')
def run(playbook_name):
    """Запуск плейбука"""
    # Получаем список доступных инвентарей для выбора
    inventories = []
    inv_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
    
    if os.path.exists(inv_path):
        for file in os.listdir(inv_path):
            if file.endswith(('.yml', '.yaml')):
                inventories.append(os.path.splitext(file)[0])
    
    return render_template('playbooks/run.html', 
                         playbook_name=playbook_name,
                         inventories=inventories)
@bp.route('/api/delete', methods=['POST'])
def api_delete_playbook():
    """API для удаления плейбука"""
    try:
        data = request.json
        playbook_name = data.get('name')
        
        if not playbook_name:
            return jsonify({'success': False, 'message': 'Не указано имя плейбука'})
        
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        file_path = os.path.join(playbooks_path, playbook_name)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Плейбук не найден'})
        
        # Создаем backup
        backup_dir = os.path.join(playbooks_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{playbook_name}_{timestamp}.bak")
        shutil.copy2(file_path, backup_path)
        
        # Удаляем файл
        os.remove(file_path)
        
        return jsonify({
            'success': True,
            'message': 'Плейбук удален',
            'backup': backup_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error deleting playbook: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/api/get-inventories')
def api_get_inventories():
    """API для получения списка инвентарей и их структуры"""
    try:
        inventories = []
        inv_path = current_app.config.get('INVENTORY_PATH', 'ansible_data\inventories')
        
        # Используем абсолютный путь
        if not os.path.isabs(inv_path):
            inv_path = os.path.join(current_app.root_path, inv_path)
        
        print(f"Поиск инвентарей в: {inv_path}")
        
        if os.path.exists(inv_path):
            for file in os.listdir(inv_path):
                if file.endswith(('.yml', '.yaml')):
                    inv_name = os.path.splitext(file)[0]
                    file_path = os.path.join(inv_path, file)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            inv_data = yaml.safe_load(f)
                        # Извлекаем группы и хосты
                        groups = []
                        hosts = []
                        
                        if inv_data and 'all' in inv_data and 'children' in inv_data['all']:
                            for group_name, group_data in inv_data['all']['children'].items():
                                if group_data and 'hosts' in group_data:
                                    print(group_data['hosts'].keys())
                                    host_list = list(group_data['hosts'].keys()) if group_data['hosts'] else []
                                    groups.append({
                                        'name': group_name,
                                        'hosts': host_list
                                    })
                                    for host_name, host_vars in group_data['hosts'].items():
                                        hosts.append({
                                            'name': host_name,
                                            'group': group_name,
                                            'address': host_vars.get('ansible_host', host_name)
                                        })
                        
                        inventories.append({
                            'name': inv_name,
                            'groups': groups,
                            'hosts': hosts
                        })
                    except Exception as e:
                        print(f"Ошибка загрузки инвентаря {inv_name}: {e}")
        
        print(f"Загружено {len(inventories)} инвентарей")
        return jsonify({'success': True, 'inventories': inventories})
        
    except Exception as e:
        print(f"Ошибка получения инвентарей: {e}")
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/save-playbook', methods=['POST'])
def api_save_playbook():
    """API для сохранения плейбука"""
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')
        playbook_data = data.get('playbook_data')
        hosts = data.get('hosts', 'all')
        
        if not name or not name.endswith(('.yml', '.yaml')):
            name = name + '.yml' if '.' not in name else name
        
        if not playbook_data or len(playbook_data) == 0:
            return jsonify({'success': False, 'message': 'Нет данных для сохранения'})
        
        # Обновляем метаданные
        playbook_data[0]['name'] = description or f"Playbook: {name}"
        playbook_data[0]['hosts'] = hosts
        
        # Конвертируем в YAML
        yaml_output = yaml.dump(playbook_data, default_flow_style=False, indent=2, allow_unicode=True)
        
        # Сохраняем файл
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        os.makedirs(playbooks_path, exist_ok=True)
        
        file_path = os.path.join(playbooks_path, name)
        
        # Проверяем существование файла
        if os.path.exists(file_path):
            base, ext = os.path.splitext(name)
            counter = 1
            while os.path.exists(os.path.join(playbooks_path, f"{base}_{counter}{ext}")):
                counter += 1
            file_path = os.path.join(playbooks_path, f"{base}_{counter}{ext}")
            name = f"{base}_{counter}{ext}"
        
        # Добавляем комментарий
        header = f"# {description}\n# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n# Target: {hosts}\n\n"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(header + yaml_output)
        
        return jsonify({
            'success': True, 
            'message': 'Плейбук сохранен',
            'filename': name,
            'path': file_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error saving playbook: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/api/run-playbook', methods=['POST'])
def api_run_playbook():
    """API для запуска плейбука"""
    data = request.json
    playbook = data.get('playbook')
    inventory = data.get('inventory')
    
    # Здесь будет реальный запуск Ansible
    # Для демо возвращаем симулированный результат
    import time
    import random
    
    time.sleep(2)  # Имитация выполнения
    
    # Генерируем случайные результаты
    hosts = ['router-01', 'router-02', 'switch-01', 'switch-02']
    results = []
    
    for host in hosts:
        success = random.random() > 0.2  # 80% успеха
        results.append({
            'host': host,
            'success': success,
            'changed': success and random.random() > 0.5,
            'output': f"Task completed successfully" if success else "Connection timeout"
        })
    
    return jsonify({
        'success': True,
        'playbook': playbook,
        'inventory': inventory,
        'results': results,
        'summary': {
            'ok': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success']),
            'changed': sum(1 for r in results if r.get('changed')),
            'total': len(results)
        },
        'output': 'Playbook execution completed',
        'timestamp': time.time()
    })

@bp.route('/api/validate-playbook', methods=['POST'])
def api_validate_playbook():
    """API для валидации YAML плейбука"""
    try:
        data = request.json
        content = data.get('content')
        
        if not content:
            return jsonify({'valid': False, 'message': 'Пустое содержимое'})
        
        # Пробуем загрузить YAML
        yaml_data = yaml.safe_load(content)
        
        if not isinstance(yaml_data, list):
            return jsonify({'valid': False, 'message': 'Плейбук должен быть списком'})
        
        return jsonify({'valid': True, 'message': 'Синтаксис корректен'})
        
    except yaml.YAMLError as e:
        return jsonify({'valid': False, 'message': f'Ошибка YAML: {str(e)}'})
    except Exception as e:
        return jsonify({'valid': False, 'message': f'Ошибка: {str(e)}'})

def load_inventory_file(file_path):
    """Загружает инвентарный файл"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except:
        return None

def get_playbook_description(file_path):
    """Получает описание плейбука из комментария"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if first_line.startswith('#'):
                return first_line[1:].strip()
    except:
        pass
    return 'Без описания'

def get_playbook_last_run(file_path):
    """Получает время последнего запуска (из истории)"""
    # Здесь можно реализовать логику получения времени последнего запуска
    import random
    from datetime import datetime, timedelta
    
    # Для демо возвращаем случайное время
    days_ago = random.randint(0, 7)
    hours_ago = random.randint(0, 23)
    last_run = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
    return last_run.strftime('%Y-%m-%d %H:%M')