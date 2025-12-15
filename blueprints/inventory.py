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
    # Используем локальную функцию загрузки
    inventory = load_inventory_local(inventory_name)
    
    if not inventory:
        return render_template('errors/404.html', 
                             message=f"Инвентарь '{inventory_name}' не найден"), 404
    
    # Извлекаем хосты и симулируем их статус для демонстрации
    all_hosts = extract_hosts_from_inventory(inventory)
    
    # Создаем словарь статусов хостов
    host_statuses = {}
    for host in all_hosts:
        # Симулируем статус для демонстрации
        statuses = ['up', 'down', 'ssh_error', 'unknown']
        host_statuses[host['name']] = random.choice(statuses)
    
    return render_template('inventory/detail.html',
                         inventory=inventory,
                         inventory_name=inventory_name,
                         host_statuses=host_statuses)

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
@bp.route('/api/create', methods=['POST'])
def api_create_inventory():
    """API для создания нового инвентаря"""
    try:
        data = request.json
        inventory_name = data.get('name', '').strip()
        description = data.get('description', '')
        
        if not inventory_name:
            return jsonify({'success': False, 'message': 'Название инвентаря обязательно'})
        
        # Проверяем допустимость имени
        if not re.match(r'^[a-zA-Z0-9_\-]+$', inventory_name):
            return jsonify({'success': False, 'message': 'Недопустимые символы в названии'})
        
        # Проверяем, не существует ли уже
        inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        file_path = os.path.join(inventory_path, f"{inventory_name}.yaml")
        
        if os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'Инвентарь с таким именем уже существует'})
        
        # Создаем базовую структуру для сетевого оборудования
        base_inventory = {
            'all': {
                'vars': {
                    'ansible_network_os': 'ios',
                    'ansible_connection': 'network_cli',
                    'ansible_user': 'admin',
                    'ansible_ssh_private_key_file': '~/.ssh/id_rsa',
                    'ansible_become': 'yes',
                    'ansible_become_method': 'enable'
                },
                'children': {
                    'routers': {
                        'hosts': {},
                        'vars': {
                            'device_type': 'router',
                            'description': 'Маршрутизаторы'
                        }
                    },
                    'switches': {
                        'hosts': {},
                        'vars': {
                            'device_type': 'switch',
                            'description': 'Коммутаторы'
                        }
                    }
                }
            }
        }
        
        # Добавляем описание если есть
        if description:
            base_inventory['all']['vars']['inventory_description'] = description
        
        # Сохраняем YAML файл
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(base_inventory, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        InventoryHistory.log_change(
            inventory_name=inventory_name,
            action='create',
            user='admin',  # В реальном приложении получать из сессии
            comment=f"Создан новый инвентарь: {description}" if description else "Создан новый инвентарь",
            changes={
                'description': description,
                'template': 'network_base'
            }
        )
        
        return jsonify({
            'success': True, 
            'message': 'Инвентарь создан',
            'path': file_path,
            'name': inventory_name
        })
        
    except Exception as e:
        current_app.logger.error(f"Error creating inventory: {e}")
        return jsonify({'success': False, 'message': f'Ошибка создания: {str(e)}'})
        
    except Exception as e:
        current_app.logger.error(f"Error creating inventory: {e}")
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