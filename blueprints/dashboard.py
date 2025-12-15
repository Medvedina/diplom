from flask import Blueprint, render_template, jsonify
import os
import yaml
from datetime import datetime

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
    
    # Последние события
    recent_events = [
        {'time': '10:25', 'host': 'web1.test.local', 'action': 'Проверка', 'status': 'success'},
        {'time': '10:20', 'host': 'db2.test.local', 'action': 'Обновление', 'status': 'warning'},
        {'time': '10:15', 'host': 'lb1.test.local', 'action': 'Перезагрузка', 'status': 'success'},
        {'time': '10:10', 'host': 'dev1.test.local', 'action': 'Мониторинг', 'status': 'success'},
        {'time': '10:05', 'host': 'web2.test.local', 'action': 'Проверка', 'status': 'error'},
    ]
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_events=recent_events)

@bp.route('/overview')
@set_active_tab('dashboard')
def overview():
    """Обзорная панель"""
    return render_template('dashboard/overview.html')

@bp.route('/api/system-stats')
@set_active_tab('dashboard')
def api_system_stats():
    """API для получения статистики системы"""
    import psutil
    import platform
    
    stats = {
        'system': {
            'os': platform.system(),
            'version': platform.version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total,
            'memory_used': psutil.virtual_memory().used,
        },
        'ansible': {
            'inventories': len(os.listdir('ansible_data/inventories')),
            'playbooks': len(os.listdir('ansible_data/playbooks')),
        },
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(stats)