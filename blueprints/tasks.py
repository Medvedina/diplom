from flask import Blueprint, render_template, jsonify

bp = Blueprint('tasks', __name__)

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
@set_active_tab('tasks')
def list():
    """Список задач"""
    tasks = [
        {'id': 1, 'name': 'Ежедневный ping', 'type': 'scheduled', 'status': 'active', 'next_run': '2023-10-16 02:00'},
        {'id': 2, 'name': 'Обновление системы', 'type': 'scheduled', 'status': 'active', 'next_run': '2023-10-16 04:00'},
        {'id': 3, 'name': 'Бэкап конфигураций', 'type': 'manual', 'status': 'completed', 'next_run': 'N/A'},
        {'id': 4, 'name': 'Проверка дисков', 'type': 'scheduled', 'status': 'paused', 'next_run': '2023-10-17 01:00'},
    ]
    return render_template('tasks/list.html', tasks=tasks)