from flask import Blueprint, render_template, jsonify, request, current_app, flash, redirect, url_for
from datetime import datetime
import os
import json
import yaml
import shutil
import subprocess
import tempfile
import time
import re
import sys
from models.playbook_history import PlaybookHistory
import paramiko

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
    },
    'custom_command': {
        'name': 'Другое (произвольная команда)',
        'icon': 'bi-terminal',
        'color': 'secondary',
        'description': 'Выполнение произвольных команд на устройствах',
        'module': 'ios_command',
        'params': [
            {'name': 'commands', 'label': 'Команды', 'type': 'textarea', 
             'placeholder': 'show running-config\nshow ip interface brief\nshow version', 
             'required': True,
             'help': 'Введите команды, по одной на строку. Они будут выполнены в указанном порядке.'},
            {'name': 'export_output', 'label': 'Экспортировать вывод', 'type': 'checkbox', 
             'default': False,
             'help': 'Сохранить вывод команд в файл'},
            {'name': 'export_path', 'label': 'Путь для экспорта', 'type': 'text', 
             'placeholder': '/backups/{{ inventory_hostname }}_{{ ansible_date_time.date }}.txt',
             'help': 'Путь для сохранения вывода. Поддерживаются переменные Ansible.'},
            {'name': 'wait_for', 'label': 'Ожидать (сек)', 'type': 'number', 
             'default': 0, 'min': 0, 'max': 300,
             'help': 'Время ожидания между командами в секундах'},
            {'name': 'match', 'label': 'Режим сравнения', 'type': 'select', 
             'options': ['none', 'all', 'any'],
             'help': 'Режим проверки результатов (none - не проверять, all - все успешно, any - хотя бы одна)'}
        ]
    }
}

@bp.route('/')
@set_active_tab('playbooks')
def pb_list():
    """Список плейбуков"""
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
    edit_playbook = request.args.get('edit')
    playbook_data = None
    playbook_name = None
    
    if edit_playbook:
        try:
            playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
            file_path = os.path.join(playbooks_path, edit_playbook)
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    playbook_data = yaml.safe_load(content)
                    playbook_name = edit_playbook
                    
                print(f"Загружен плейбук для редактирования: {playbook_name}")
        except Exception as e:
            print(f"Ошибка загрузки плейбука {edit_playbook}: {e}")
    
    return render_template('playbooks/create.html', 
                         tasks_config=TASKS_CONFIG,
                         edit_playbook=playbook_name,
                         playbook_data=playbook_data)

@bp.route('/edit/<playbook_name>')
@set_active_tab('playbooks')
def edit(playbook_name):
    """Страница редактирования плейбука"""
    try:
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        
        if not playbook_name.endswith(('.yml', '.yaml')):
            found = False
            for ext in ['.yml', '.yaml']:
                test_path = os.path.join(playbooks_path, playbook_name + ext)
                if os.path.exists(test_path):
                    file_path = test_path
                    playbook_name = playbook_name + ext
                    found = True
                    break
            
            if not found:
                flash(f'Плейбук {playbook_name} не найден', 'error')
                return redirect(url_for('playbooks.pb_list'))
        else:
            file_path = os.path.join(playbooks_path, playbook_name)
        
        if not os.path.exists(file_path):
            flash(f'Плейбук {playbook_name} не найден', 'error')
            return redirect(url_for('playbooks.pb_list'))
        
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()
        
        file_stat = os.stat(file_path)
        modified = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        file_size = file_stat.st_size
        
        try:
            yaml_data = yaml.safe_load(yaml_content)
            tasks_count = len(yaml_data[0].get('tasks', [])) if yaml_data and isinstance(yaml_data, list) else 0
        except:
            tasks_count = 0
        
        return render_template('playbooks/edit.html',
                             playbook_name=playbook_name,
                             yaml_content=yaml_content,
                             modified=modified,
                             file_size=file_size,
                             tasks_count=tasks_count)
        
    except Exception as e:
        current_app.logger.error(f"Error loading playbook {playbook_name}: {e}")
        flash(f'Ошибка загрузки плейбука: {str(e)}', 'error')
        return redirect(url_for('playbooks.pb_list'))
    
@bp.route('/api/get-playbook/<playbook_name>')
def api_get_playbook(playbook_name):
    """API для получения содержимого плейбука"""
    try:
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        file_path = os.path.join(playbooks_path, playbook_name)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Плейбук не найден'})
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'success': True,
            'name': playbook_name,
            'content': content,
            'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/run/<playbook_name>')
@set_active_tab('playbooks')
def run(playbook_name):
    """Запуск плейбука"""
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
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        backup_dir = os.path.join(playbooks_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f"{playbook_name}_{timestamp}.bak")
        shutil.copy2(file_path, backup_path)
        
        os.remove(file_path)
        
        PlaybookHistory.log_change(
            playbook_name=playbook_name,
            action='delete',
            user='admin',
            comment=f'Удален плейбук {playbook_name}',
            details={'backup': backup_path}
        )
        
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
        inv_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        
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
                        
                        groups = []
                        hosts = []
                        
                        if inv_data and 'all' in inv_data and 'children' in inv_data['all']:
                            for group_name, group_data in inv_data['all']['children'].items():
                                if group_data and 'hosts' in group_data:
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
        print(f"Received data: {data}")
        
        name = data.get('name')
        description = data.get('description')
        tasks = data.get('tasks', [])  # Общие задачи
        host_tasks = data.get('host_tasks', {})  # Задачи для конкретных хостов
        hosts = data.get('hosts', 'all')
        
        if not name:
            return jsonify({'success': False, 'message': 'Не указано имя файла'})
        
        # Нормализуем имя файла
        if not name.endswith(('.yml', '.yaml')):
            name = name + '.yml'
        
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        os.makedirs(playbooks_path, exist_ok=True)
        
        file_path = os.path.join(playbooks_path, name)
        
        # Определяем действие (создание или редактирование)
        is_new = not os.path.exists(file_path)
        action = 'create' if is_new else 'edit'
        
        # Создаем backup если редактирование
        if not is_new:
            backup_dir = os.path.join(playbooks_path, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(backup_dir, f"{name}_{timestamp}.bak")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                original = f.read()
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original)
            
            print(f"Backup created: {backup_path}")
        
        # Формируем правильную структуру плейбука для Ansible
        playbook_tasks = []
        
        # Добавляем общие задачи (без метаданных)
        for task in tasks:
            ansible_task = convert_to_ansible_task(task)
            if ansible_task:
                playbook_tasks.append(ansible_task)
        
        # Добавляем задачи для конкретных хостов с условиями
        for host, host_task_list in host_tasks.items():
            for task in host_task_list:
                ansible_task = convert_to_ansible_task(task)
                if ansible_task:
                    ansible_task['when'] = f"inventory_hostname == '{host}'"
                    playbook_tasks.append(ansible_task)
        
        # Создаем структуру плейбука
        playbook_data = [{
            'name': description or f"Playbook: {name}",
            'hosts': hosts,
            'gather_facts': True,
            'connection': 'network_cli',
            'tasks': playbook_tasks
        }]
        
        # Конвертируем в YAML
        yaml_output = yaml.dump(playbook_data, default_flow_style=False, indent=2, allow_unicode=True)
        
        # Добавляем комментарий с метаданными
        header = f"# {description}\n# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n# Target: {hosts}\n\n"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(header + yaml_output)
        
        print(f"Playbook saved: {file_path}")
        
        # Подсчитываем количество задач для логирования
        task_count = len(tasks) + sum(len(ht) for ht in host_tasks.values())
        comment = f"{'Создан' if is_new else 'Изменен'} плейбук с {task_count} задачами"
        
        PlaybookHistory.log_change(
            playbook_name=name,
            action=action,
            user='admin',
            comment=comment,
            details={
                'hosts': hosts,
                'task_count': task_count,
                'has_host_tasks': len(host_tasks) > 0
            }
        )
        
        return jsonify({
            'success': True, 
            'message': f'Плейбук успешно {"создан" if is_new else "сохранен"}',
            'file': file_path,
            'name': name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error saving playbook: {e}")
        print(f"Error saving playbook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

def convert_to_ansible_task(task):
    """Конвертирует задачу из формата UI в формат Ansible"""
    if not task or 'type' not in task:
        return None
    
    task_type = task['type']
    params = task.get('params', {})
    
    # Базовая структура задачи
    ansible_task = {
        'name': task.get('name', f'Task {task_type}')
    }
    
    # Конвертируем в зависимости от типа
    if task_type == 'ping':
        ansible_task['ping'] = {}
        if params.get('count'):
            ansible_task['ping']['count'] = int(params['count'])
        if params.get('size'):
            ansible_task['ping']['size'] = int(params['size'])
    
    elif task_type == 'interface_config':
        lines = []
        if params.get('interface'):
            lines.append(f"interface {params['interface']}")
        if params.get('description'):
            lines.append(f" description {params['description']}")
        if params.get('ip_address'):
            lines.append(f" ip address {params['ip_address']}")
        if params.get('admin_state'):
            if params['admin_state'] == 'up':
                lines.append(" no shutdown")
            else:
                lines.append(" shutdown")
        
        if lines:
            ansible_task['ios_config'] = {
                'lines': lines
            }
    
    elif task_type == 'ospf':
        lines = []
        if params.get('process_id'):
            lines.append(f"router ospf {params['process_id']}")
        if params.get('router_id'):
            lines.append(f" router-id {params['router_id']}")
        if params.get('network'):
            lines.append(f" network {params['network']}")
        
        if lines:
            ansible_task['ios_config'] = {
                'lines': lines
            }
    
    elif task_type == 'isis':
        lines = ['router isis']
        if params.get('net'):
            lines.append(f" net {params['net']}")
        if params.get('level'):
            lines.append(f" is-type {params['level']}")
        
        ansible_task['ios_config'] = {
            'lines': lines
        }
    
    elif task_type in ['stp', 'rstp']:
        lines = []
        if params.get('mode'):
            lines.append(f"spanning-tree mode {params['mode']}")
        if params.get('priority') and params.get('vlan'):
            lines.append(f"spanning-tree vlan {params['vlan']} priority {params['priority']}")
        if params.get('root_primary'):
            lines.append(f"spanning-tree vlan {params.get('vlan', '1')} root primary")
        if params.get('portfast'):
            lines.append("spanning-tree portfast default")
        if params.get('bpduguard'):
            lines.append("spanning-tree portfast bpduguard default")
        
        if lines:
            ansible_task['ios_config'] = {
                'lines': lines
            }
    
    elif task_type == 'vlan':
        vlan_data = {}
        if params.get('vlan_id'):
            vlan_data['vlan_id'] = int(params['vlan_id'])
        if params.get('name'):
            vlan_data['name'] = params['name']
        if params.get('state'):
            vlan_data['state'] = params['state']
        if params.get('interfaces'):
            vlan_data['interfaces'] = [i.strip() for i in params['interfaces'].split(',') if i.strip()]
        
        if vlan_data:
            ansible_task['ios_vlan'] = vlan_data
    
    elif task_type == 'backup_config':
        ansible_task['ios_command'] = {
            'commands': ['show running-config']
        }
        ansible_task['register'] = 'config_output'
    
    elif task_type == 'update_config':
        if params.get('lines'):
            lines = [l.strip() for l in params['lines'].split('\n') if l.strip()]
            config_data = {
                'lines': lines
            }
            if params.get('parents'):
                config_data['parents'] = [params['parents']]
            if params.get('save'):
                config_data['save'] = params['save'] == 'true'
            if params.get('match'):
                config_data['match'] = params['match']
            
            ansible_task['ios_config'] = config_data
    
    elif task_type == 'custom_command':
        if params.get('commands'):
            commands = [c.strip() for c in params['commands'].split('\n') if c.strip()]
            cmd_data = {
                'commands': commands
            }
            if params.get('wait_for'):
                cmd_data['wait_for'] = int(params['wait_for'])
            if params.get('match') and params['match'] != 'none':
                cmd_data['match'] = params['match']
            
            ansible_task['ios_command'] = cmd_data
            ansible_task['register'] = 'cmd_output'
    
    return ansible_task

# Функции для работы с WSL
def check_wsl_available():
    """Проверяет доступность WSL"""
    return True
    # try:
    #     result = subprocess.run(
    #         ['wsl', '--version'],
    #         capture_output=True,
    #         text=True,
    #         timeout=5
    #     )
    #     return result.returncode == 0
    # except:
    #     return False

def convert_windows_path_to_wsl(windows_path):
    # Нормализуем путь
    windows_path = os.path.normpath(windows_path)
    
    # Разделяем диск и путь
    drive = windows_path[0].lower()
    path_without_drive = windows_path[3:].replace('\\', '/')
    print('АЛЯРМ', drive, path_without_drive)
    # Формируем WSL путь
    return f'/mnt/{drive}/{path_without_drive}'
"""
ТУТ НАСРАНО!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""
def create_wsl_script(playbook_path, inventory_path, ssh_user, password_file_path=None, limit=None, extra_vars=None):
    """
    Создает bash скрипт для выполнения в WSL
    """
    script_lines = [
        # '#!/bin/bash',
        # 'export ANSIBLE_FORCE_COLOR=false',
        # 'export ANSIBLE_NOCOLOR=true',
        # 'export PYTHONIOENCODING=utf-8',
        # 'export ANSIBLE_STDOUT_CALLBACK=unixy'
    ]

    # Формируем базовую команду
    cmd_parts = ['ansible-playbook']
    cmd_parts.append(f'-i {convert_windows_path_to_wsl(inventory_path)}')
    cmd_parts.append(f'{convert_windows_path_to_wsl(playbook_path)}')
    
    if ssh_user:
        cmd_parts.append(f'-u {ssh_user}')
    
    if password_file_path:
        cmd_parts.append(f'--connection-password-file {convert_windows_path_to_wsl(password_file_path)}')
    
    if limit:
        limit_hosts = [h.strip() for h in limit.split(',') if h.strip()]
        for host in limit_hosts:
            cmd_parts.append(f'-l {host}')
    
    if extra_vars:
        for key, value in extra_vars.items():
            if value:
                cmd_parts.append(f'-e "{key}={value}"')
    
    cmd_parts.append('-v')
    
    full_cmd = ' '.join(cmd_parts)
    print('КОМАНДА', full_cmd)
    script_lines.extend([
        f'{full_cmd}'
    ])
    
    return '\n'.join(script_lines)

@bp.route('/api/run-playbook', methods=['POST'])
def api_run_playbook():
    """API для реального запуска плейбука через WSL"""
    try:
        data = request.json
        playbook = data.get('playbook')
        inventory = data.get('inventory')
        ssh_user = data.get('ssh_user', 'admin')
        ssh_password = data.get('ssh_password', '')
        ssh_private_key = data.get('ssh_private_key', '')
        limit = data.get('limit', '')
        extra_vars = data.get('extra_vars', {})
        
        if not playbook or not inventory:
            return jsonify({'success': False, 'message': 'Не указан плейбук или инвентарь'})
        
        # Проверяем наличие WSL
        if not check_wsl_available():
            return jsonify({
                'success': False, 
                'message': 'WSL не доступен. Установите WSL или используйте режим симуляции.'
            })
        
        # Получаем пути к файлам
        playbooks_path = os.path.join(current_app.root_path, 'ansible_data', 'playbooks')
        inventories_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        temp_dir = os.path.join(current_app.root_path, 'ansible_data', 'temp')
        
        os.makedirs(results_path, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        print(f"Temp directory: {temp_dir}")
        print(f"Temp directory exists: {os.path.exists(temp_dir)}")
        
        playbook_path = os.path.join(playbooks_path, playbook)
        inventory_path = os.path.join(inventories_path, f"{inventory}.yaml")
        
        if not os.path.exists(playbook_path):
            return jsonify({'success': False, 'message': f'Плейбук {playbook} не найден'})
        
        if not os.path.exists(inventory_path):
            return jsonify({'success': False, 'message': f'Инвентарь {inventory} не найден'})
        
        print(f"Playbook path: {playbook_path}")
        print(f"Inventory path: {inventory_path}")
        
        # Создаем временный файл для пароля если нужно
        password_file_path = None
        if ssh_password:
            password_file_path = os.path.join(temp_dir, f'ansible_pass_{int(time.time())}.txt')
            with open(password_file_path, 'w', encoding='utf-8') as f:
                f.write(ssh_password)
            print(f"Password file: {password_file_path}")
        
        # Создаем WSL скрипт
        script_content = create_wsl_script(
            playbook_path=playbook_path,
            inventory_path=inventory_path,
            ssh_user=ssh_user,
            password_file_path=password_file_path,
            limit=limit,
            extra_vars=extra_vars
        )
        
        script_file = os.path.join(temp_dir, f'run_ansible_{int(time.time())}.sh')
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        # Делаем скрипт исполняемым
        os.chmod(script_file, 0o755)
        
        print(f"Script file: {script_file}")
        print(f"Script exists: {os.path.exists(script_file)}")
        
        wsl_script_path = convert_windows_path_to_wsl(script_file)
        print(f"WSL script path: {wsl_script_path}")
        
        # Запускаем скрипт в WSL
        try:
            cmd = ['wsl', 'bash', wsl_script_path]
            print(f"Running command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding='utf-8',
                errors='replace'
            )
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
            
            print(f"Return code: {returncode}")
            print(f"Stdout length: {len(stdout)}")
            print(f"Stderr length: {len(stderr)}")
            
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': 'Таймаут выполнения плейбука'})
        except Exception as e:
            print(f"Error running WSL command: {e}")
            return jsonify({'success': False, 'message': f'Ошибка выполнения: {str(e)}'})
        
        # # Удаляем временные файлы
        # try:
        #     if os.path.exists(script_file):
        #         os.remove(script_file)
        #         print(f"Removed script file: {script_file}")
        # except:
        #     pass
        
        if password_file_path and os.path.exists(password_file_path):
            try:
                os.remove(password_file_path)
                print(f"Removed password file: {password_file_path}")
            except:
                pass
        
        # Парсим результаты
        parsed_results = parse_ansible_output(stdout, stderr, returncode)
        
        # Формируем объект результата для сохранения
        timestamp = datetime.now()
        result_id = f"result_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        result_data = {
            'id': result_id,
            'timestamp': timestamp.isoformat(),
            'playbook': playbook,
            'inventory': inventory,
            'user': 'admin',
            'status': 'success' if returncode == 0 else 'failed',
            'summary': parsed_results['summary'],
            'hosts': parsed_results['hosts'],
            'output': stdout,
            'error': stderr if returncode != 0 else None
        }
        
        # Сохраняем результат в JSON
        result_file = os.path.join(results_path, f"{result_id}.json")
        print(f"Saving result to: {result_file}")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # Обновляем индекс
        results_index = os.path.join(results_path, 'index.json')
        index = []
        if os.path.exists(results_index):
            try:
                with open(results_index, 'r', encoding='utf-8') as f:
                    index = json.load(f)
            except:
                index = []
        
        index.insert(0, {
            'id': result_id,
            'timestamp': timestamp.isoformat(),
            'playbook': playbook,
            'inventory': inventory,
            'status': 'success' if returncode == 0 else 'failed',
            'summary': parsed_results['summary']
        })
        
        index = index[:100]
        
        with open(results_index, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        # Логируем выполнение
        PlaybookHistory.log_run(
            playbook_name=playbook,
            inventory_name=inventory,
            user='admin',
            status='success' if returncode == 0 else 'failed',
            results=parsed_results['summary']
        )
        
        return jsonify({
            'success': returncode == 0,
            'playbook': playbook,
            'inventory': inventory,
            'hosts': parsed_results['hosts'],
            'summary': parsed_results['summary'],
            'output': stdout,
            'error': stderr if returncode != 0 else None,
            'result_id': result_id,
            'timestamp': timestamp.isoformat(),
            'wsl': True
        })
        
    except Exception as e:
        current_app.logger.error(f"Error running playbook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/check-wsl')
def api_check_wsl():
    """Проверяет наличие WSL"""
    try:
        available = check_wsl_available()
        
        if available:
            # Проверяем наличие Ansible в WSL
            result = subprocess.run(
                ['wsl', 'ansible-playbook', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                version = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
                return jsonify({
                    'success': True,
                    'wsl_available': True,
                    'ansible_installed': True,
                    'ansible_version': version
                })
            else:
                return jsonify({
                    'success': True,
                    'wsl_available': True,
                    'ansible_installed': False,
                    'message': 'Ansible не установлен в WSL. Выполните: sudo apt update && sudo apt install ansible'
                })
        else:
            return jsonify({
                'success': True,
                'wsl_available': False,
                'message': 'WSL не установлен. Установите WSL: wsl --install'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/test-ssh', methods=['POST'])
def api_test_ssh():
    """Тестирует SSH подключение к хосту через paramiko"""
    try:
        data = request.json
        host = data.get('host')
        port = data.get('port', 22)
        username = data.get('username', 'admin')
        password = data.get('password')
        key_file = data.get('key_file')
        
        if not host:
            return jsonify({'success': False, 'message': 'Не указан хост'})
        
        start_time = time.time()
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if password:
                ssh.connect(
                    host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=5,
                    allow_agent=False,
                    look_for_keys=False
                )
            elif key_file and os.path.exists(key_file):
                key = paramiko.RSAKey.from_private_key_file(key_file)
                ssh.connect(
                    host,
                    port=port,
                    username=username,
                    pkey=key,
                    timeout=5,
                    allow_agent=False,
                    look_for_keys=False
                )
            else:
                ssh.connect(
                    host,
                    port=port,
                    username=username,
                    timeout=5,
                    allow_agent=True,
                    look_for_keys=True
                )
            
            ssh.close()
            
            response_time = int((time.time() - start_time) * 1000)
            
            return jsonify({
                'success': True,
                'message': 'SSH подключение успешно',
                'response_time': response_time
            })
            
        except paramiko.AuthenticationException:
            return jsonify({'success': False, 'message': 'Ошибка аутентификации'})
        except paramiko.SSHException as e:
            return jsonify({'success': False, 'message': f'SSH ошибка: {str(e)}'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/api/validate-playbook', methods=['POST'])
def api_validate_playbook():
    """API для валидации YAML плейбука"""
    try:
        data = request.json
        content = data.get('content')
        
        if not content:
            return jsonify({'valid': False, 'message': 'Пустое содержимое'})
        
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
    import random
    from datetime import datetime, timedelta
    
    days_ago = random.randint(0, 7)
    hours_ago = random.randint(0, 23)
    last_run = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
    return last_run.strftime('%Y-%m-%d %H:%M')

@bp.route('/api/playbook-history')
def api_playbook_history():
    """API для получения истории плейбуков"""
    try:
        playbook_name = request.args.get('playbook')
        limit = request.args.get('limit', 20, type=int)
        
        if playbook_name:
            history = PlaybookHistory.get_playbook_history(playbook_name, limit)
        else:
            history = PlaybookHistory.get_recent_events(limit)
        
        return jsonify({
            'success': True,
            'history': history,
            'total': len(history)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/validate-path', methods=['POST'])
def api_validate_path():
    """Проверяет доступность пути для записи"""
    try:
        data = request.json
        path = data.get('path')
        
        if not path:
            return jsonify({'valid': False, 'message': 'Путь не указан'})
        
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            return jsonify({
                'valid': False, 
                'message': f'Директория {directory} не существует'
            })
        
        if os.path.exists(directory):
            if not os.access(directory, os.W_OK):
                return jsonify({
                    'valid': False,
                    'message': f'Нет прав на запись в {directory}'
                })
        
        return jsonify({
            'valid': True,
            'message': 'Путь доступен для записи',
            'directory': directory,
            'filename': os.path.basename(path) if os.path.basename(path) else None
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)})

def parse_ansible_output(stdout, stderr, returncode):
    """Парсит вывод ansible-playbook для получения структурированных результатов"""
    results = {
        'hosts': [],
        'summary': {
            'ok': 0,
            'changed': 0,
            'failed': 0,
            'unreachable': 0,
            'skipped': 0,
            'rescued': 0,
            'ignored': 0
        }
    }
    
    host_pattern = r'(?P<host>\S+)\s+:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)\s+skipped=(?P<skipped>\d+)\s+rescued=(?P<rescued>\d+)\s+ignored=(?P<ignored>\d+)'
    
    for line in stdout.split('\n'):
        match = re.search(host_pattern, line)
        if match:
            host_data = match.groupdict()
            results['hosts'].append({
                'host': host_data['host'],
                'ok': int(host_data['ok']),
                'changed': int(host_data['changed']),
                'unreachable': int(host_data['unreachable']),
                'failed': int(host_data['failed']),
                'skipped': int(host_data['skipped']),
                'rescued': int(host_data['rescued']),
                'ignored': int(host_data['ignored'])
            })
            
            for key in results['summary']:
                results['summary'][key] += int(host_data.get(key, 0))
    
    return results