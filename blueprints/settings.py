from flask import Blueprint, render_template, jsonify, request

bp = Blueprint('settings', __name__)

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
@set_active_tab('settings')
def index():
    """Настройки системы"""
    settings = {
        'ansible_path': '/usr/bin/ansible',
        'inventory_path': 'ansible_data/inventories',
        'playbook_path': 'ansible_data/playbooks',
        'ssh_timeout': 30,
        'check_interval': 300,
        'notifications': True,
        'email_alerts': False,
        'telegram_alerts': True,
    }
    return render_template('settings/index.html', settings=settings)

@bp.route('/save', methods=['POST'])
def save():
    """Сохранение настроек"""
    data = request.json
    # Здесь будет сохранение в конфиг или БД
    return jsonify({'success': True, 'message': 'Настройки сохранены'})