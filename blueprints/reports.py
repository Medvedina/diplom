from flask import Blueprint, render_template, jsonify

bp = Blueprint('reports', __name__)

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
@set_active_tab('reports')
def index():
    """Отчёты и аналитика"""
    return render_template('reports/index.html')

@bp.route('/api/uptime-stats')
def api_uptime_stats():
    """API для статистики uptime"""
    import random
    from datetime import datetime, timedelta
    
    # Генерация демо-данных
    days = 30
    data = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=days-i-1)).strftime('%Y-%m-%d')
        uptime = random.uniform(95, 100)
        data.append({
            'date': date,
            'uptime': round(uptime, 2),
            'incidents': random.randint(0, 3)
        })
    
    return jsonify(data)