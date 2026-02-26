from flask import Blueprint, render_template, jsonify, request, current_app, send_file
import os
import yaml
import shutil
from datetime import datetime
import random
import tempfile
import json
import re
from models.inventory_history import InventoryHistory
import subprocess
bp = Blueprint('inventory', __name__)

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

def load_inventory_local(inventory_name):
    """Локальная версия функции загрузки инвентаря"""
    try:
        # Получаем путь из конфигурации приложения
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if not os.path.exists(path):
            current_app.logger.warning(f"Inventory file not found: {path}")
            return None
            
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        current_app.logger.error(f"Error loading inventory {inventory_name}: {e}")
        return None

def extract_hosts_from_inventory(inventory):
    """Извлекаем все хосты из инвентаря"""
    hosts = []
    
    if not inventory or not isinstance(inventory, dict):
        return hosts
    
    if 'all' in inventory and 'children' in inventory['all']:
        for group_name, group_data in inventory['all']['children'].items():
            if 'hosts' in group_data and group_data['hosts']:
                for host_name, host_vars in group_data['hosts'].items():
                    hosts.append({
                        'name': host_name,
                        'group': group_name,
                        'vars': host_vars,
                        'address': host_vars.get('ansible_host', host_name)
                    })
    
    return hosts

@bp.route('/')
@set_active_tab('inventory')
def inventory_list():
    """Список всех инвентарей"""
    inventories = []
    inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
    
    if not os.path.exists(inventory_path):
        os.makedirs(inventory_path, exist_ok=True)
        return render_template('inventory/list.html', inventories=inventories)
    
    for file in os.listdir(inventory_path):
        if file.endswith(('.yaml', '.yml')):
            inventory_name = os.path.splitext(file)[0]
            file_path = os.path.join(inventory_path, file)
            inventories.append({
                'name': inventory_name,
                'path': file_path,
                'modified': datetime.fromtimestamp(
                    os.path.getmtime(file_path)
                ).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return render_template('inventory/list.html', inventories=inventories)

@bp.route('/<inventory_name>')
@set_active_tab('inventory')
def inventory_detail(inventory_name):
    """Детальная страница инвентаря"""
    inventory = load_inventory_local(inventory_name)
    
    if not inventory:
        return render_template('errors/404.html', 
                             message=f"Инвентарь '{inventory_name}' не найден"), 404
    
    # Извлекаем хосты и определяем их роли
    all_hosts = extract_hosts_from_inventory(inventory)
    
    # Создаем словарь статусов хостов (пока unknown, будут обновлены через AJAX)
    host_statuses = {}
    host_roles = {}
    
    for host in all_hosts:
        host_statuses[host['name']] = 'unknown'
        
        # Определяем роль хоста
        role = 'unknown'
        if host['vars']:
            if host['vars'].get('device_type'):
                role = host['vars']['device_type']
            elif host['vars'].get('role'):
                role = host['vars']['role']
            elif 'router' in host['name'].lower():
                role = 'router'
            elif 'switch' in host['name'].lower():
                role = 'switch'
            elif 'fw' in host['name'].lower() or 'firewall' in host['name'].lower():
                role = 'firewall'
        
        host_roles[host['name']] = role
    
    return render_template('inventory/detail.html',
                         inventory=inventory,
                         inventory_name=inventory_name,
                         host_statuses=host_statuses,
                         host_roles=host_roles)

@bp.route('/api/check-inventory-hosts', methods=['POST'])
def api_check_inventory_hosts():
    """API для проверки статуса хостов в конкретном инвентаре"""
    try:
        data = request.json
        inventory_name = data.get('inventory')
        hosts = data.get('hosts', [])
        
        results = []
        
        # Загружаем инвентарь для получения полной информации о хостах
        inventory = load_inventory_local(inventory_name)
        if not inventory:
            return jsonify({'success': False, 'message': 'Инвентарь не найден'})
        
        # Создаем словарь с информацией о хостах
        host_info = {}
        if 'all' in inventory and 'children' in inventory['all']:
            for group_name, group_data in inventory['all']['children'].items():
                if group_data and 'hosts' in group_data:
                    for host_name, host_vars in group_data['hosts'].items():
                        host_info[host_name] = {
                            'name': host_name,
                            'group': group_name,
                            'address': host_vars.get('ansible_host', host_name) if isinstance(host_vars, dict) else host_name,
                            'port': host_vars.get('ansible_port', 22) if isinstance(host_vars, dict) else 22,
                            'user': host_vars.get('ansible_user', 'admin') if isinstance(host_vars, dict) else 'admin',
                            'vars': host_vars if isinstance(host_vars, dict) else {}
                        }
        
        # Проверяем каждый хост
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        def check_single_host(host_name):
            host = host_info.get(host_name)
            if not host:
                return {
                    'host': host_name,
                    'status': 'unknown',
                    'response_time': None,
                    'error': 'Host info not found'
                }
            
            address = host['address']
            port = host.get('port', 22)
            
            result = {
                'host': host_name,
                'status': 'unknown',
                'response_time': None,
                'error': None
            }
            
            # Проверка ping
            try:
                start_time = time.time()
                
                if os.name == 'nt':
                    ping_cmd = ['ping', '-n', '1', '-w', '2000', address]
                else:
                    ping_cmd = ['ping', '-c', '1', '-W', '2', address]
                
                ping_result = subprocess.run(
                    ping_cmd,
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                
                if ping_result.returncode == 0:
                    # Пинг успешен, проверяем SSH
                    try:
                        import paramiko
                        ssh = paramiko.SSHClient()
                        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        ssh.connect(
                            address,
                            port=port,
                            username=host.get('user', 'admin'),
                            timeout=3,
                            allow_agent=False,
                            look_for_keys=False
                        )
                        ssh.close()
                        result['status'] = 'up'
                        result['response_time'] = int((time.time() - start_time) * 1000)
                    except paramiko.AuthenticationException:
                        result['status'] = 'up'
                        result['response_time'] = int((time.time() - start_time) * 1000)
                    except Exception as e:
                        result['status'] = 'ssh_error'
                        result['error'] = str(e)
                        result['response_time'] = int((time.time() - start_time) * 1000)
                else:
                    result['status'] = 'down'
                    result['response_time'] = int((time.time() - start_time) * 1000)
                    
            except subprocess.TimeoutExpired:
                result['status'] = 'down'
                result['error'] = 'Timeout'
            except Exception as e:
                result['status'] = 'down'
                result['error'] = str(e)
            
            return result
        
        # Параллельная проверка хостов
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(check_single_host, host): host for host in hosts}
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=10)
                    results.append(result)
                except Exception as e:
                    host = futures[future]
                    results.append({
                        'host': host,
                        'status': 'error',
                        'response_time': None,
                        'error': str(e)
                    })
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error checking inventory hosts: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/api/check-hosts', methods=['POST'])
def api_check_hosts():
    """API для проверки статуса хостов"""
    data = request.json
    hosts = data.get('hosts', [])
    
    # Для демо возвращаем симулированные данные
    results = []
    from datetime import datetime
    
    for host in hosts:
        status = random.choice(['up', 'down', 'ssh_error'])
        results.append({
            'host': host,
            'status': status,
            'last_check': datetime.now().isoformat(),
            'response_time': random.randint(10, 500)  # ms
        })
    
    return jsonify({'results': results})

# Добавляем в inventory.py новый маршрут после inventory_list()
@bp.route('/api/debug/<inventory_name>')
def api_debug_inventory(inventory_name):
    """API для отладки - проверка сохраненного инвентаря"""
    try:
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь не найден'})
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Пытаемся распарсить
        parsed = None
        parse_error = None
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as e:
            parse_error = str(e)
        
        return jsonify({
            'success': True,
            'name': inventory_name,
            'file_path': file_path,
            'file_size': os.path.getsize(file_path),
            'content_length': len(content),
            'content_preview': content[:500] + "..." if len(content) > 500 else content,
            'parsed': parsed is not None,
            'parse_error': parse_error,
            'structure': parsed
        })
        
    except Exception as e:
        current_app.logger.error(f"Debug error: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/create')
@set_active_tab('inventory')
def inventory_create():
    """Страница создания инвентаря с визуальным конструктором"""
    return render_template('inventory/create.html')

#API для создания инвентаря

@bp.route('/api/create', methods=['POST'])
def api_create_inventory():
    """API для создания нового инвентаря - УПРОЩЕННАЯ ВЕРСИЯ"""
    try:
        # Получаем данные
        data = request.get_json()
        
        if not data:
            current_app.logger.error("No JSON data received")
            return jsonify({'success': False, 'message': 'Отсутствуют данные'})
        print('ДАТА', data)
        inventory_name = data.get('name', '').strip()
        description = data.get('description', '')
        yaml_content = data.get('content', '')  # YAML из предпросмотра
        print('ЯМЛЬ КОНТЕНТ\n', yaml_content)

        # ВАЖНО: Логируем то, что получаем
        current_app.logger.info(f"=== Создание инвентаря '{inventory_name}' ===")
        current_app.logger.info(f"Описание: {description}")
        current_app.logger.info(f"Длина YAML контента: {len(yaml_content)}")
        
        # Берем первые 500 символов YAML для отладки
        if yaml_content:
            preview = yaml_content[:500] + "..." if len(yaml_content) > 500 else yaml_content
            current_app.logger.info(f"YAML (первые 500 символов):\n{preview}")
        
        # Валидация имени
        if not inventory_name:
            return jsonify({'success': False, 'message': 'Название инвентаря обязательно'})
        
        if not re.match(r'^[a-zA-Z0-9_\-]+$', inventory_name):
            return jsonify({'success': False, 'message': 'Недопустимые символы в названии'})
        
        # Проверяем, не существует ли уже
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь с таким именем уже существует'})
        
        # ГЛАВНОЕ ИЗМЕНЕНИЕ: Всегда используем переданный YAML из предпросмотра
        if not yaml_content or yaml_content.strip() == '':
            current_app.logger.warning("Пустой YAML контент, создаю базовую структуру")
            # Создаем минимальную структуру
            base_yaml = {
                'all': {
                    'vars': {
                        'ansible_network_os': 'ios',
                        'ansible_connection': 'network_cli',
                        'ansible_user': 'admin',
                        'ansible_ssh_private_key_file': '~/.ssh/id_rsa'
                    },
                    'children': {}
                }
            }
            
            if description:
                base_yaml['all']['vars']['inventory_description'] = description
            
            yaml_content = yaml.dump(base_yaml, default_flow_style=False, allow_unicode=True, sort_keys=False)
            current_app.logger.info(f"Сгенерирован базовый YAML:\n{yaml_content}")
        else:
            # Проверяем валидность полученного YAML
            try:
                parsed = yaml.safe_load(yaml_content)
                current_app.logger.info(f"YAML успешно распарсен, структура: {type(parsed)}")
                
                if not parsed:
                    current_app.logger.error("Распарсенный YAML пуст")
                    return jsonify({'success': False, 'message': 'Пустой YAML контент'})
                
                # Простая проверка структуры
                if not isinstance(parsed, dict):
                    current_app.logger.error(f"YAML должен быть словарем, получен: {type(parsed)}")
                    return jsonify({'success': False, 'message': 'Некорректная структура YAML'})
                
                # Если есть 'all' - проверяем его структуру
                if 'all' in parsed:
                    if not isinstance(parsed['all'], dict):
                        current_app.logger.error("Ключ 'all' должен быть словарем")
                        return jsonify({'success': False, 'message': "Ключ 'all' должен быть словарем"})
                    
                    # Проверяем наличие 'children'
                    if 'children' not in parsed['all']:
                        current_app.logger.warning("Отсутствует ключ 'children', добавляю")
                        parsed['all']['children'] = {}
                    
                    # Проверяем наличие 'vars'
                    if 'vars' not in parsed['all']:
                        current_app.logger.warning("Отсутствует ключ 'vars', добавляю")
                        parsed['all']['vars'] = {}
                    
                    # Добавляем недостающие обязательные переменные
                    required_vars = {
                        'ansible_network_os': 'ios',
                        'ansible_connection': 'network_cli',
                        'ansible_user': 'admin',
                        'ansible_ssh_private_key_file': '~/.ssh/id_rsa'
                    }
                    
                    for var_name, default_value in required_vars.items():
                        if var_name not in parsed['all']['vars']:
                            parsed['all']['vars'][var_name] = default_value
                            current_app.logger.info(f"Добавлена переменная: {var_name} = {default_value}")
                    
                    # Добавляем описание если оно было в форме
                    if description and 'inventory_description' not in parsed['all']['vars']:
                        parsed['all']['vars']['inventory_description'] = description
                    
                    # Пересоздаем YAML с исправлениями
                    yaml_content = yaml.dump(parsed, default_flow_style=False, allow_unicode=True, sort_keys=False)
                
            except yaml.YAMLError as e:
                current_app.logger.error(f"Ошибка парсинга YAML: {str(e)}")
                # Пробуем сохранить как есть, возможно это валидный YAML
                current_app.logger.warning("Сохраняю YAML как есть, несмотря на ошибку парсинга")
        
        # Создаем директорию если не существует
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Сохраняем файл
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        
        # Проверяем, что файл создан
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            current_app.logger.info(f"Файл сохранен: {file_path}, размер: {file_size} байт")
            
            # Читаем обратно для проверки
            with open(file_path, 'r', encoding='utf-8') as f:
                saved_content = f.read()
            
            current_app.logger.info(f"Проверка сохраненного файла, первые 500 символов:\n{saved_content[:500]}...")
        else:
            current_app.logger.error(f"Файл не был создан: {file_path}")
            return jsonify({'success': False, 'message': 'Ошибка создания файла'})
        
        # Логируем создание
        InventoryHistory.log_change(
            inventory_name=inventory_name,
            action='create',
            user='admin',
            comment=f"Создан через визуальный конструктор" + (f": {description}" if description else ""),
            changes={'method': 'visual_editor', 'content_length': len(yaml_content)}
        )
        
        return jsonify({
            'success': True, 
            'message': 'Инвентарь успешно создан',
            'path': file_path,
            'name': inventory_name,
            'content_preview': yaml_content[:200] + "..." if len(yaml_content) > 200 else yaml_content
        })
        
    except Exception as e:
        current_app.logger.error(f"Критическая ошибка при создании инвентаря: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Ошибка создания: {str(e)}'})
    
# API для получения содержимого инвентаря для редактирования
@bp.route('/api/get/<inventory_name>')
def api_get_inventory(inventory_name):
    """API для получения содержимого инвентаря"""
    try:
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь не найден'})
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'success': True,
            'name': inventory_name,
            'content': content,
            'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        current_app.logger.error(f"Error reading inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка чтения: {str(e)}'})

# API для сохранения инвентаря

@bp.route('/api/save', methods=['POST'])
def api_save_inventory():
    """API для сохранения изменений инвентаря"""
    try:
        data = request.json
        inventory_name = data.get('name')
        content = data.get('content')
        comment = data.get('comment', '')
        create_backup = data.get('backup', True)
        
        if not inventory_name or not content:
            return jsonify({'success': False, 'message': 'Отсутствуют обязательные данные'})
        
        # Пробуем загрузить YAML для проверки синтаксиса
        try:
            parsed_yaml = yaml.safe_load(content)
        except yaml.YAMLError as e:
            return jsonify({'success': False, 'message': f'Ошибка YAML синтаксиса: {str(e)}'})
        
        # Сохраняем файл
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        old_content = ''
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                old_content = f.read()

        # Создаем backup если нужно
        backup_path = None
        if create_backup and os.path.exists(file_path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(inventory_path, f"backups/{inventory_name}_{timestamp}.yaml")
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy2(file_path, backup_path)
            
            # Добавляем комментарий к backup
            if comment:
                backup_info = {
                    'original_file': file_path,
                    'backup_time': datetime.now().isoformat(),
                    'comment': comment,
                    'backup_path': backup_path
                }
                info_path = f"{backup_path}.info.json"
                with open(info_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_info, f, ensure_ascii=False, indent=2)
        
        # Сохраняем основной файл
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        changes = InventoryHistory.compare_inventories(old_content, content, inventory_name)
        
        # Логируем редактирование
        InventoryHistory.log_change(
            inventory_name=inventory_name,
            action='edit',
            user='admin',
            comment=comment if comment else "Изменения в инвентаре",
            changes=changes
        )
        
        return jsonify({
            'success': True,
            'message': 'Инвентарь сохранен',
            'changes': changes,
            'backup_created': backup_path is not None
        })
        
    except Exception as e:
        current_app.logger.error(f"Error saving inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка сохранения: {str(e)}'})

# API для удаления инвентаря
@bp.route('/api/delete', methods=['POST'])
def api_delete_inventory():
    """API для удаления инвентаря"""
    try:
        data = request.json
        inventory_name = data.get('name')
        comment = data.get('comment', '')

        if not inventory_name:
            return jsonify({'success': False, 'message': 'Не указано название инвентаря'})
        
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь не найден'})
       
        InventoryHistory.log_change(
                inventory_name=inventory_name,
                action='delete',
                user='admin',
                comment=comment if comment else "Инвентарь удален",
                changes={'content_length': len(content)}
            )
        # Перемещаем в корзину (создаем папку trash)
        trash_path = os.path.join(inventory_path, 'trash')
        os.makedirs(trash_path, exist_ok=True)
        
        trash_file = os.path.join(trash_path, f"{inventory_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml")
        shutil.move(file_path, trash_file)
        
        return jsonify({
            'success': True,
            'message': 'Инвентарь перемещен в корзину',
            'trash_path': trash_file
        })
        
    except Exception as e:
        current_app.logger.error(f"Error deleting inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка удаления: {str(e)}'})
# API для редактирования инвентаря

@bp.route('/<inventory_name>/edit')
@set_active_tab('inventory')
def inventory_edit(inventory_name):
    """Страница редактирования инвентаря"""
    # Используем локальную функцию загрузки
    inventory = load_inventory_local(inventory_name)
    
    if not inventory:
        return render_template('errors/404.html', 
                             message=f"Инвентарь '{inventory_name}' не найден"), 404
    
    # Получаем содержимое YAML файла для редактора
    try:
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()
            
        return render_template('inventory/edit.html',
                             inventory_name=inventory_name,
                             yaml_content=yaml_content,
                             modified=datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S'))
        
    except Exception as e:
        current_app.logger.error(f"Error reading inventory for edit: {e}")
        return render_template('errors/500.html', 
                             message=f'Ошибка загрузки инвентаря: {str(e)}'), 500
    
# API для клонирования инвентаря
@bp.route('/api/clone', methods=['POST'])
def api_clone_inventory():
    """API для клонирования инвентаря"""
    try:
        data = request.json
        source_name = data.get('source')
        target_name = data.get('target')
        comment = data.get('comment', '')

        if not source_name or not target_name:
            return jsonify({'success': False, 'message': 'Не указаны имена инвентарей'})
        
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        source_path = os.path.join(inventory_path, f"{source_name}.yaml")
        target_path = os.path.join(inventory_path, f"{target_name}.yaml")
        
        if not os.path.exists(source_path):
            return jsonify({'success': False, 'message': 'Исходный инвентарь не найден'})
        
        if os.path.exists(target_path):
            return jsonify({'success': False, 'message': 'Инвентарь с таким именем уже существует'})
        
        # Копируем файл
        shutil.copy2(source_path, target_path)
        
        # Обновляем метаданные если нужно
        with open(target_path, 'r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
        
        if content and 'all' in content and 'vars' in content['all']:
            content['all']['vars']['cloned_from'] = source_name
            content['all']['vars']['cloned_date'] = datetime.now().strftime('%Y-%m-%d')
            
            with open(target_path, 'w', encoding='utf-8') as f:
                yaml.dump(content, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
       
        InventoryHistory.log_change(
            inventory_name=source_name,
            action='clone',
            user='admin',
            comment=f"Клонирован как {target_name}. {comment}" if comment else f"Клонирован как {target_name}",
            changes={'cloned_to': target_name}
        )
        
        InventoryHistory.log_change(
            inventory_name=target_name,
            action='create',
            user='admin',
            comment=f"Создан клон из {source_name}. {comment}" if comment else f"Создан клон из {source_name}",
            changes={'cloned_from': source_name}
        )
        return jsonify({
            'success': True,
            'message': 'Инвентарь скопирован',
            'source': source_name,
            'target': target_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error cloning inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка клонирования: {str(e)}'})
@bp.route('/api/history/<inventory_name>')
def api_inventory_history(inventory_name):
    """API для получения истории изменений инвентаря"""
    try:
        history = InventoryHistory.get_inventory_history(inventory_name)
        return jsonify({
            'success': True,
            'inventory': inventory_name,
            'history': history,
            'total': len(history)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting inventory history: {e}")
        return jsonify({'success': False, 'message': str(e)})

# Endpoint для получения последних событий
@bp.route('/api/recent-events')
def api_recent_events():
    """API для получения последних событий"""
    try:
        limit = request.args.get('limit', 10, type=int)
        events = InventoryHistory.get_recent_events(limit)
        
        # Форматируем для отображения
        formatted_events = []
        for event in events:
            formatted_events.append({
                'id': event.get('id'),
                'type': 'inventory',
                'action': event.get('action'),
                'title': InventoryHistory._get_action_title(event.get('action'), event.get('inventory')),
                'description': event.get('comment') or InventoryHistory._get_action_description(event.get('action')),
                'inventory': event.get('inventory'),
                'user': event.get('user'),
                'time': event.get('display_time'),
                'timestamp': event.get('timestamp'),
                'icon': event.get('icon'),
                'color': event.get('color'),
                'badge': InventoryHistory._get_action_badge(event.get('action'))
            })
        
        return jsonify({
            'success': True,
            'events': formatted_events,
            'total': len(formatted_events)
        })
    except Exception as e:
        current_app.logger.error(f"Error getting recent events: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
# API для экспорта инвентаря
@bp.route('/api/export/<inventory_name>')
def api_export_inventory(inventory_name):
    """API для экспорта инвентаря"""
    try:
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь не найден'}), 404
        
        # Отправляем файл как вложение
        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{inventory_name}.yaml",
            mimetype='application/x-yaml'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка экспорта: {str(e)}'}), 500

# API для проверки YAML
@bp.route('/api/validate', methods=['POST'])
def api_validate_yaml():
    """API для проверки YAML синтаксиса"""
    try:
        data = request.json
        content = data.get('content')
        
        if not content:
            return jsonify({'valid': False, 'error': 'Пустое содержимое'})
        
        # Пробуем загрузить YAML
        yaml.safe_load(content)
        
        return jsonify({'valid': True, 'error': None})
        
    except yaml.YAMLError as e:
        return jsonify({'valid': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'valid': False, 'error': f'Неизвестная ошибка: {str(e)}'})

# API для пакетного удаления
@bp.route('/api/batch-delete', methods=['POST'])
def api_batch_delete():
    """API для удаления нескольких инвентарей"""
    try:
        data = request.json
        inventories = data.get('inventories', [])
        
        if not inventories:
            return jsonify({'success': False, 'message': 'Не выбраны инвентари'})
        
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        trash_path = os.path.join(inventory_path, 'trash')
        os.makedirs(trash_path, exist_ok=True)
        
        deleted = []
        errors = []
        
        for inv_name in inventories:
            try:
                file_path = os.path.join(inventory_path, f"{inv_name}.yaml")
                
                if os.path.exists(file_path):
                    trash_file = os.path.join(trash_path, f"{inv_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml")
                    shutil.move(file_path, trash_file)
                    deleted.append(inv_name)
                else:
                    errors.append(f"{inv_name}: не найден")
            except Exception as e:
                errors.append(f"{inv_name}: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'Удалено {len(deleted)} из {len(inventories)} инвентарей',
            'deleted': deleted,
            'errors': errors
        })
        
    except Exception as e:
        current_app.logger.error(f"Error batch deleting inventories: {e}")
        return jsonify({'success': False, 'message': f'Ошибка удаления: {str(e)}'})

# API для экспорта нескольких инвентарей
@bp.route('/api/export-multiple')
def api_export_multiple():
    """API для экспорта нескольких инвентарей в архив"""
    try:
        inventory_names = request.args.getlist('inventories')
        
        if not inventory_names:
            return jsonify({'success': False, 'message': 'Не выбраны инвентари'})
        
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        
        # Создаем временный zip архив
        import zipfile
        
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for inv_name in inventory_names:
                file_path = os.path.join(inventory_path, f"{inv_name}.yaml")
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=f"{inv_name}.yaml")
        
        temp_zip.close()
        
        # Отправляем архив
        return send_file(
            temp_zip.name,
            as_attachment=True,
            download_name=f"inventories_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mimetype='application/zip'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting multiple inventories: {e}")
        return jsonify({'success': False, 'message': f'Ошибка экспорта: {str(e)}'}), 500


def extract_hosts_from_inventory(inventory):
    """Извлекаем все хосты из инвентаря с определением ролей"""
    hosts = []
    
    if not inventory or not isinstance(inventory, dict):
        return hosts
    
    if 'all' in inventory and 'children' in inventory['all']:
        for group_name, group_data in inventory['all']['children'].items():
            if 'hosts' in group_data and group_data['hosts']:
                for host_name, host_vars in group_data['hosts'].items():
                    # Определяем роль
                    role = 'unknown'
                    if isinstance(host_vars, dict):
                        if host_vars.get('device_type'):
                            role = host_vars['device_type']
                        elif host_vars.get('role'):
                            role = host_vars['role']
                        elif 'router' in host_name.lower():
                            role = 'router'
                        elif 'switch' in host_name.lower():
                            role = 'switch'
                        elif 'fw' in host_name.lower() or 'firewall' in host_name.lower():
                            role = 'firewall'
                    
                    hosts.append({
                        'name': host_name,
                        'group': group_name,
                        'vars': host_vars if isinstance(host_vars, dict) else {},
                        'address': host_vars.get('ansible_host', host_name) if isinstance(host_vars, dict) else host_name,
                        'role': role
                    })
    
    return hosts

@bp.route('/<inventory_name>/history')
@set_active_tab('inventory')
def inventory_history(inventory_name):
    """Страница истории изменений инвентаря"""
    inventory = load_inventory_local(inventory_name)
    
    if not inventory:
        return render_template('errors/404.html', 
                             message=f"Инвентарь '{inventory_name}' не найден"), 404
    
    return render_template('inventory/history.html',
                         inventory_name=inventory_name)