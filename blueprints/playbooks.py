from flask import Blueprint, render_template, jsonify, request
from flask import current_app

bp = Blueprint('playbooks', __name__)

# Локальная функция для использования декоратора
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
@set_active_tab('playbooks')
def list():
    """Список плейбуков"""
    playbooks = [
        {'name': 'ping_test.yml', 'description': 'Проверка доступности хостов', 'last_run': '2023-10-15 14:30'},
        {'name': 'system_update.yml', 'description': 'Обновление системы', 'last_run': '2023-10-14 10:15'},
        {'name': 'deploy_web.yml', 'description': 'Деплой веб-приложения', 'last_run': '2023-10-13 09:45'},
        {'name': 'backup_config.yml', 'description': 'Бэкап конфигураций', 'last_run': '2023-10-12 16:20'},
    ]
    return render_template('playbooks/list.html', playbooks=playbooks)

@bp.route('/run/<playbook_name>')
@set_active_tab('playbooks')
def run(playbook_name):
    """Запуск плейбука"""
    return render_template('playbooks/run.html', playbook_name=playbook_name)

@bp.route('/api/run-playbook', methods=['POST'])
def api_run_playbook():
    """API для запуска плейбука"""
    data = request.json
    playbook = data.get('playbook')
    inventory = data.get('inventory')
    
    # Здесь будет реальный запуск Ansible
    # Для демо возвращаем симулированный результат
    import time
    time.sleep(2)  # Имитация выполнения
    
    return jsonify({
        'success': True,
        'playbook': playbook,
        'inventory': inventory,
        'output': 'Playbook executed successfully',
        'timestamp': time.time()
    })