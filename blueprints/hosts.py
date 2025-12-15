from flask import Blueprint, render_template, jsonify, request
import socket
import subprocess
import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

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

@bp.route('/')
@set_active_tab('hosts')
def host_list():
    """Список всех хостов из всех инвентарей"""
    from app import list_inventories, load_inventory
    
    all_hosts = []
    inventories = list_inventories()
    
    for inv in inventories:
        inventory = load_inventory(inv['name'])
        if inventory:
            hosts = extract_hosts_from_inventory(inventory)
            for host in hosts:
                host['inventory'] = inv['name']
                all_hosts.append(host)
    
    return render_template('hosts/list.html', hosts=all_hosts)

@bp.route('/check/<hostname>')
@set_active_tab('hosts')
def check_host(hostname):
    """Проверка конкретного хоста"""
    # Получаем информацию о хосте
    from app import list_inventories, load_inventory
    
    host_info = None
    for inv in list_inventories():
        inventory = load_inventory(inv['name'])
        if inventory:
            hosts = extract_hosts_from_inventory(inventory)
            for host in hosts:
                if host['name'] == hostname:
                    host_info = host
                    host_info['inventory'] = inv['name']
                    break
    
    if not host_info:
        return "Хост не найден", 404
    
    # Проверяем доступность
    check_results = perform_host_check(host_info['address'])
    
    return render_template('hosts/check.html',
                         host=host_info,
                         results=check_results)

@bp.route('/api/ping-all')
@set_active_tab('hosts')
def api_ping_all():
    """API для пинга всех хостов"""
    from app import list_inventories, load_inventory
    
    all_hosts = []
    for inv in list_inventories():
        inventory = load_inventory(inv['name'])
        if inventory:
            hosts = extract_hosts_from_inventory(inventory)
            for host in hosts:
                all_hosts.append({
                    'name': host['name'],
                    'address': host['address'],
                    'inventory': inv['name']
                })
    
    # Параллельная проверка хостов
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_host = {
            executor.submit(check_single_host, host['address']): host 
            for host in all_hosts
        }
        
        for future in as_completed(future_to_host):
            host = future_to_host[future]
            try:
                status, response_time = future.result(timeout=10)
                results.append({
                    'host': host['name'],
                    'address': host['address'],
                    'status': status,
                    'response_time': response_time,
                    'timestamp': time.time()
                })
            except Exception as e:
                results.append({
                    'host': host['name'],
                    'address': host['address'],
                    'status': 'error',
                    'error': str(e),
                    'timestamp': time.time()
                })
    
    return jsonify({'results': results})

def perform_host_check(host_address):
    """Выполняет комплексную проверку хоста"""
    results = {
        'ping': check_ping(host_address),
        'ssh': check_ssh(host_address),
        'dns': check_dns(host_address),
        'ports': check_common_ports(host_address)
    }
    
    # Определяем общий статус
    if results['ping']['status'] == 'up':
        results['overall'] = 'up'
    elif results['ssh']['status'] == 'up':
        results['overall'] = 'ssh_only'
    else:
        results['overall'] = 'down'
    
    return results

def check_single_host(address):
    """Проверяет один хост"""
    start_time = time.time()
    
    # Пинг
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '1', address],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            status = 'up'
        else:
            status = 'down'
    except:
        status = 'error'
    
    response_time = int((time.time() - start_time) * 1000)
    
    return status, response_time

def check_ping(address):
    try:
        result = subprocess.run(
            ['ping', '-c', '3', '-W', '2', address],
            capture_output=True,
            text=True,
            timeout=5
        )
        return {
            'status': 'up' if result.returncode == 0 else 'down',
            'output': result.stdout
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def check_ssh(address, port=22, timeout=3):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(address, port=port, timeout=timeout)
        ssh.close()
        return {'status': 'up', 'port': port}
    except paramiko.AuthenticationException:
        return {'status': 'auth_error', 'port': port}
    except Exception as e:
        return {'status': 'down', 'error': str(e), 'port': port}

def check_dns(address):
    try:
        socket.gethostbyname(address)
        return {'status': 'resolved'}
    except socket.error:
        return {'status': 'unresolved'}

def check_common_ports(address):
    common_ports = [22, 80, 443, 8080, 3306, 5432]
    results = []
    
    for port in common_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((address, port))
        results.append({
            'port': port,
            'status': 'open' if result == 0 else 'closed'
        })
        sock.close()
    
    return results

def extract_hosts_from_inventory(inventory):
    """Извлекаем хосты из инвентаря (дублируется, но нужно для этого модуля)"""
    hosts = []
    
    if 'all' in inventory and 'children' in inventory['all']:
        for group_name, group_data in inventory['all']['children'].items():
            if 'hosts' in group_data:
                for host_name, host_vars in group_data['hosts'].items():
                    hosts.append({
                        'name': host_name,
                        'group': group_name,
                        'vars': host_vars,
                        'address': host_vars.get('ansible_host', host_name)
                    })
    
    return hosts

@bp.route('/api/stats')
def api_host_stats():
    """API для статистики хостов"""
    from app import list_inventories, load_inventory
    
    total_hosts = 0
    up_hosts = 0
    down_hosts = 0
    ssh_error_hosts = 0
    
    inventories = list_inventories()
    
    for inv in inventories:
        inventory = load_inventory(inv['name'])
        if inventory:
            hosts = extract_hosts_from_inventory(inventory)
            total_hosts += len(hosts)
            # Для демо - случайные статусы
            for _ in hosts:
                import random
                status = random.choice(['up', 'down', 'ssh_error'])
                if status == 'up':
                    up_hosts += 1
                elif status == 'down':
                    down_hosts += 1
                elif status == 'ssh_error':
                    ssh_error_hosts += 1
    
    return jsonify({
        'success': True,
        'total_hosts': total_hosts,
        'up_hosts': up_hosts,
        'down_hosts': down_hosts,
        'ssh_error_hosts': ssh_error_hosts,
        'inventories': len(inventories)
    })

@bp.route('/api/info/<hostname>')
def api_host_info(hostname):
    """API для информации о хосте"""
    from app import list_inventories, load_inventory
    
    for inv in list_inventories():
        inventory = load_inventory(inv['name'])
        if inventory:
            hosts = extract_hosts_from_inventory(inventory)
            for host in hosts:
                if host['name'] == hostname:
                    return jsonify({
                        'success': True,
                        'host': host
                    })
    
    return jsonify({'success': False, 'message': 'Host not found'})