from flask import Blueprint, render_template, jsonify, request, current_app
import os
import yaml
import socket
import subprocess
import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime

bp = Blueprint('hosts', __name__)

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

def load_all_hosts():
    """Загружает все хосты из всех инвентарей"""
    all_hosts = []
    inventory_path = current_app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
    
    if not os.path.exists(inventory_path):
        return all_hosts
    
    for file in os.listdir(inventory_path):
        if file.endswith(('.yml', '.yaml')):
            inventory_name = os.path.splitext(file)[0]
            file_path = os.path.join(inventory_path, file)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    inv_data = yaml.safe_load(f)
                
                if inv_data and 'all' in inv_data and 'children' in inv_data['all']:
                    for group_name, group_data in inv_data['all']['children'].items():
                        if group_data and 'hosts' in group_data:
                            for host_name, host_vars in group_data['hosts'].items():
                                # Определяем роль из переменных
                                role = 'unknown'
                                if isinstance(host_vars, dict):
                                    # Приоритет 1: явно указанный device_type
                                    if host_vars.get('device_type'):
                                        role = host_vars['device_type']
                                    # Приоритет 2: явно указанный role
                                    elif host_vars.get('role'):
                                        role = host_vars['role']
                                    # Приоритет 3: определение по имени хоста
                                    elif 'router' in host_name.lower():
                                        role = 'router'
                                    elif 'switch' in host_name.lower():
                                        role = 'switch'
                                    elif 'fw' in host_name.lower() or 'firewall' in host_name.lower():
                                        role = 'firewall'
                                
                                # Формируем объект хоста с ВСЕМИ полями
                                host_obj = {
                                    'name': host_name,
                                    'inventory': inventory_name,
                                    'group': group_name,
                                    'address': host_vars.get('ansible_host', host_name) if isinstance(host_vars, dict) else host_name,
                                    'port': host_vars.get('ansible_port', 22) if isinstance(host_vars, dict) else 22,
                                    'user': host_vars.get('ansible_user', 'admin') if isinstance(host_vars, dict) else 'admin',
                                    'vars': host_vars if isinstance(host_vars, dict) else {},
                                    'role': role,
                                    'status': 'unknown',
                                    'last_check': None,
                                    'response_time': None
                                }
                                all_hosts.append(host_obj)
            except Exception as e:
                print(f"Error loading inventory {inventory_name}: {e}")
    
    return all_hosts

def check_host_status(host):
    """Проверяет статус одного хоста"""
    result = {
        'name': host['name'],
        'status': 'unknown',
        'response_time': None,
        'error': None
    }
    
    address = host['address']
    port = host.get('port', 22)
    
    # Проверка ping
    try:
        start_time = time.time()
        
        # Для Windows
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
                # Хост доступен, но нет авторизации
                result['status'] = 'up'
                result['response_time'] = int((time.time() - start_time) * 1000)
            except Exception as e:
                # SSH недоступен
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

@bp.route('/')
@set_active_tab('hosts')
def host_list():
    """Список всех хостов"""
    hosts = load_all_hosts()
    return render_template('hosts/list.html', hosts=hosts)

@bp.route('/api/check-all', methods=['POST'])
def api_check_all():
    """API для проверки всех хостов"""
    try:
        hosts = load_all_hosts()
        results = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(check_host_status, host): host for host in hosts}
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=10)
                    results.append(result)
                except Exception as e:
                    host = futures[future]
                    results.append({
                        'name': host['name'],
                        'status': 'down',
                        'response_time': None,
                        'error': str(e)
                    })
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/check-host', methods=['POST'])
def api_check_host():
    """API для проверки конкретного хоста"""
    try:
        data = request.json
        host_name = data.get('host')
        
        # Находим хост по имени
        hosts = load_all_hosts()
        host = next((h for h in hosts if h['name'] == host_name), None)
        
        if not host:
            return jsonify({'success': False, 'message': 'Хост не найден'})
        
        result = check_host_status(host)
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/stats')
def api_host_stats():
    """API для статистики хостов"""
    try:
        hosts = load_all_hosts()
        
        # Проверяем статусы (для демо используем случайные, в реальности нужно кэшировать)
        import random
        up_count = 0
        down_count = 0
        ssh_error_count = 0
        
        for host in hosts:
            # В реальном приложении здесь должны быть реальные статусы из кэша
            r = random.random()
            if r < 0.7:
                up_count += 1
            elif r < 0.85:
                down_count += 1
            else:
                ssh_error_count += 1
        
        return jsonify({
            'success': True,
            'total_hosts': len(hosts),
            'up_hosts': up_count,
            'down_hosts': down_count,
            'ssh_error_hosts': ssh_error_count,
            'inventories': len(set([h['inventory'] for h in hosts]))
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/info/<hostname>')
def api_host_info(hostname):
    """API для информации о хосте"""
    try:
        hosts = load_all_hosts()
        host = next((h for h in hosts if h['name'] == hostname), None)
        
        if not host:
            return jsonify({'success': False, 'message': 'Хост не найден'})
        
        # Проверяем текущий статус
        status_result = check_host_status(host)
        host['status'] = status_result['status']
        host['response_time'] = status_result['response_time']
        host['last_check'] = datetime.now().strftime('%H:%M:%S')
        
        return jsonify({
            'success': True,
            'host': host
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})