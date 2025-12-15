from flask import Flask, render_template, request, session
import os
import yaml
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['INVENTORY_PATH'] = 'ansible_data/inventories'
app.config['TABS_CONFIG'] = {
    'dashboard': {'name': 'Dashboard', 'icon': 'speedometer2', 'url': 'dashboard.index'},
    'inventory': {'name': 'Инвентари', 'icon': 'list-check', 'url': 'inventory.inventory_list'},
    'hosts': {'name': 'Хосты', 'icon': 'pc-display', 'url': 'hosts.host_list'},
    'playbooks': {'name': 'Плейбуки', 'icon': 'play-circle', 'url': 'playbooks.list'},
    'tasks': {'name': 'Задачи', 'icon': 'clock-history', 'url': 'tasks.list'},
    'reports': {'name': 'Отчёты', 'icon': 'graph-up', 'url': 'reports.index'},
    'settings': {'name': 'Настройки', 'icon': 'gear', 'url': 'settings.index'}
}
app.config['HISTORY_PATH'] = 'ansible_data/history'
app.config['RECENT_EVENTS_FILE'] = 'ansible_data/recent_events.json'

# Директории для хранения истории изменения инвентарей
with app.app_context():
    os.makedirs('ansible_data/history', exist_ok=True)
    os.makedirs('ansible_data/inventories/backups', exist_ok=True)

# Декортор для установки активной вкладки
def set_active_tab(tab_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session['active_tab'] = tab_name
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_config():
    """Добавляем конфигурационные значения в шаблоны"""
    return dict(
        inventory_path=app.config.get('INVENTORY_PATH', 'ansible_data/inventories'),
        # Можно добавить другие конфигурационные значения
        app_name=app.config.get('APP_NAME', 'Ansible Control Panel')
    )

@app.context_processor
def inject_functions():
    def list_inventories():
        """Функция для шаблонов"""
        import os
        from datetime import datetime
        
        inventories = []
        path = app.config.get('INVENTORY_PATH', 'ansible_data/inventories')
        
        if not os.path.exists(path):
            return inventories
        
        for file in os.listdir(path):
            if file.endswith(('.yaml', '.yml')):
                inventory_name = os.path.splitext(file)[0]
                inventories.append({
                    'name': inventory_name,
                    'modified': datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(path, file))
                    ).strftime('%Y-%m-%d %H:%M:%S')
                })
        return inventories
    
    return dict(list_inventories=list_inventories)
# Вспомогательные функции (должны быть ДО импорта блюпринтов)
def load_inventory(inventory_name):
    """Загрузка инвентаря из YAML файла"""
    try:
        path = os.path.join(app.config['INVENTORY_PATH'], f"{inventory_name}.yaml")
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading inventory: {e}")
        return None

def list_inventories():
    """Список всех инвентарей"""
    inventories = []
    path = app.config['INVENTORY_PATH']
    
    if not os.path.exists(path):
        return inventories
    
    for file in os.listdir(path):
        if file.endswith(('.yaml', '.yml')):
            inventory_name = os.path.splitext(file)[0]
            inventories.append({
                'name': inventory_name,
                'path': os.path.join(path, file),
                'modified': datetime.fromtimestamp(
                    os.path.getmtime(os.path.join(path, file))
                ).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    return inventories

@app.context_processor
def inject_tabs():
    """Добавляем вкладки и активную вкладку в контекст всех шаблонов"""
    active_tab = session.get('active_tab', 'dashboard')
    return dict(
        tabs_config=app.config['TABS_CONFIG'],
        active_tab=active_tab,
        list_inventories=list_inventories,
        load_inventory=load_inventory
    )

@app.template_filter('datetime_filter')
def datetime_filter(value):
    """Фильтр для форматирования даты"""
    if not value:
        return ""
    
    try:
        # Пытаемся распарсить строку даты
        if isinstance(value, str):
            # Пробуем разные форматы
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime('%d.%m.%Y')
                except ValueError:
                    continue
            return value
        
        # Если это объект datetime
        elif isinstance(value, datetime):
            return value.strftime('%d.%m.%Y')
        
        # Если это что-то другое
        return str(value)
    except Exception:
        return str(value)

@app.template_filter('truncate')
def truncate_filter(value, length=30):
    """Обрезает строку до указанной длины"""
    if not value:
        return ""
    if len(value) <= length:
        return value
    return value[:length-3] + "..."

# Обновляем utility_processor чтобы добавить фильтры в контекст
@app.context_processor
def utility_processor():
    """Дополнительные утилиты для шаблонов"""
    def get_host_status_color(status):
        colors = {
            'up': 'success',
            'down': 'danger',
            'ssh_error': 'warning',
            'unknown': 'secondary'
        }
        return colors.get(status, 'secondary')
    
    def is_active_tab(tab_name):
        return 'active' if session.get('active_tab') == tab_name else ''
    
    def now():
        """Возвращает текущую дату и время"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return dict(
        get_host_status_color=get_host_status_color,
        is_active_tab=is_active_tab,
        now=now,
        # Добавляем фильтры как функции для обратной совместимости
        datetime_filter=datetime_filter,
        truncate=truncate_filter
    )

@app.context_processor
def utility_processor():
    """Дополнительные утилиты для шаблонов"""
    def get_host_status_color(status):
        colors = {
            'up': 'success',
            'down': 'danger',
            'ssh_error': 'warning',
            'unknown': 'secondary'
        }
        return colors.get(status, 'secondary')
    
    def is_active_tab(tab_name):
        return 'active' if session.get('active_tab') == tab_name else ''
    
    return dict(
        get_host_status_color=get_host_status_color,
        is_active_tab=is_active_tab
    )
@app.context_processor
def utility_processor():
    """Дополнительные утилиты для шаблонов"""
    def get_host_status_color(status):
        colors = {
            'up': 'success',
            'down': 'danger',
            'ssh_error': 'warning',
            'unknown': 'secondary'
        }
        return colors.get(status, 'secondary')
    
    def is_active_tab(tab_name):
        return 'active' if session.get('active_tab') == tab_name else ''
    
    # --- ДОБАВЬТЕ ЭТУ ФУНКЦИЮ СЮДА ---
    def now():
        """Возвращает текущую дату и время"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return dict(
        get_host_status_color=get_host_status_color,
        is_active_tab=is_active_tab,
        now=now  # <-- Передаем функцию в шаблоны
    )
# Теперь импортируем и регистрируем блюпринты
with app.app_context():
    from blueprints.dashboard import bp as dashboard_bp
    from blueprints.inventory import bp as inventory_bp
    from blueprints.hosts import bp as hosts_bp
#    from blueprints.auth import bp as auth_bp
    from blueprints.playbooks import bp as playbooks_bp
    from blueprints.tasks import bp as tasks_bp
    from blueprints.reports import bp as reports_bp
    from blueprints.settings import bp as settings_bp
    
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(hosts_bp, url_prefix='/hosts')
#    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(playbooks_bp, url_prefix='/playbooks')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp, url_prefix='/settings')

@app.route('/')
@set_active_tab('dashboard')
def index():
    return render_template('dashboard/index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)