from flask import Blueprint, render_template, jsonify, request, current_app, send_file
from datetime import datetime
import os
import json
import csv
import xlsxwriter
from io import BytesIO, StringIO

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
    """Страница отчетов о выполненных плейбуках"""
    return render_template('reports/index.html')

@bp.route('/api/results')
def api_get_results():
    """API для получения списка результатов"""
    try:
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        index_file = os.path.join(results_path, 'index.json')
        
        if not os.path.exists(index_file):
            return jsonify({'success': True, 'results': []})
        
        with open(index_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # Форматируем для отображения
        formatted_results = []
        for result in results:
            formatted_results.append({
                'id': result['id'],
                'timestamp': datetime.fromisoformat(result['timestamp']).strftime('%d.%m.%Y %H:%M:%S'),
                'playbook': result['playbook'],
                'inventory': result['inventory'],
                'status': result['status'],
                'summary': result['summary']
            })
        
        return jsonify({'success': True, 'results': formatted_results})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/result/<result_id>')
def api_get_result(result_id):
    """API для получения конкретного результата"""
    try:
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        result_file = os.path.join(results_path, f"{result_id}.json")
        
        if not os.path.exists(result_file):
            return jsonify({'success': False, 'message': 'Результат не найден'})
        
        with open(result_file, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        return jsonify({'success': True, 'result': result})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/export/<result_id>')
def api_export_result(result_id):
    """Экспорт результата в выбранном формате"""
    try:
        format_type = request.args.get('format', 'json')
        
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        result_file = os.path.join(results_path, f"{result_id}.json")
        
        if not os.path.exists(result_file):
            return jsonify({'success': False, 'message': 'Результат не найден'}), 404
        
        with open(result_file, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        filename_base = f"{result['playbook'].replace('.', '_')}_{result['inventory']}_{result['timestamp'][:10]}"
        
        if format_type == 'json':
            # Экспорт в JSON
            json_str = json.dumps(result, ensure_ascii=False, indent=2)
            buffer = BytesIO(json_str.encode('utf-8'))
            buffer.seek(0)
            
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{filename_base}.json",
                mimetype='application/json'
            )
            
        elif format_type == 'csv':
            # Экспорт в CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Заголовки
            writer.writerow(['Параметр', 'Значение'])
            writer.writerow(['ID', result['id']])
            writer.writerow(['Время выполнения', result['timestamp']])
            writer.writerow(['Плейбук', result['playbook']])
            writer.writerow(['Инвентарь', result['inventory']])
            writer.writerow(['Статус', result['status']])
            writer.writerow([])
            writer.writerow(['Статистика', ''])
            
            for key, value in result['summary'].items():
                writer.writerow([f'  {key}', value])
            
            writer.writerow([])
            writer.writerow(['Хосты', ''])
            writer.writerow(['Хост', 'OK', 'Changed', 'Failed', 'Unreachable', 'Skipped'])
            
            for host in result['hosts']:
                writer.writerow([
                    host['host'],
                    host['ok'],
                    host['changed'],
                    host['failed'],
                    host['unreachable'],
                    host['skipped']
                ])
            
            buffer = BytesIO()
            buffer.write(output.getvalue().encode('utf-8'))
            buffer.seek(0)
            
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"{filename_base}.csv",
                mimetype='text/csv'
            )
            
        elif format_type == 'xlsx':
            # Экспорт в Excel
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            
            # Стили
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#007bff',
                'color': 'white',
                'border': 1
            })
            
            cell_format = workbook.add_format({'border': 1})
            
            # Основная информация
            worksheet1 = workbook.add_worksheet('Информация')
            row = 0
            worksheet1.write(row, 0, 'Параметр', header_format)
            worksheet1.write(row, 1, 'Значение', header_format)
            row += 1
            
            info = [
                ['ID', result['id']],
                ['Время выполнения', result['timestamp']],
                ['Плейбук', result['playbook']],
                ['Инвентарь', result['inventory']],
                ['Статус', result['status']]
            ]
            
            for param, value in info:
                worksheet1.write(row, 0, param, cell_format)
                worksheet1.write(row, 1, value, cell_format)
                row += 1
            
            # Статистика
            row += 1
            worksheet1.write(row, 0, 'Статистика', header_format)
            worksheet1.write(row, 1, '', header_format)
            row += 1
            
            for key, value in result['summary'].items():
                worksheet1.write(row, 0, f'  {key}', cell_format)
                worksheet1.write(row, 1, value, cell_format)
                row += 1
            
            # Хосты
            worksheet2 = workbook.add_worksheet('Хосты')
            headers = ['Хост', 'OK', 'Changed', 'Failed', 'Unreachable', 'Skipped']
            for col, header in enumerate(headers):
                worksheet2.write(0, col, header, header_format)
            
            for row, host in enumerate(result['hosts'], start=1):
                worksheet2.write(row, 0, host['host'], cell_format)
                worksheet2.write(row, 1, host['ok'], cell_format)
                worksheet2.write(row, 2, host['changed'], cell_format)
                worksheet2.write(row, 3, host['failed'], cell_format)
                worksheet2.write(row, 4, host['unreachable'], cell_format)
                worksheet2.write(row, 5, host['skipped'], cell_format)
            
            # Полный вывод
            if result.get('output'):
                worksheet3 = workbook.add_worksheet('Вывод')
                worksheet3.write(0, 0, 'Вывод выполнения', header_format)
                worksheet3.write(1, 0, result['output'], cell_format)
            
            workbook.close()
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f"{filename_base}.xlsx",
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        return jsonify({'success': False, 'message': 'Неподдерживаемый формат'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
@bp.route('/api/delete/<result_id>', methods=['DELETE'])
def api_delete_result(result_id):
    """Удаляет конкретный результат"""
    try:
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        result_file = os.path.join(results_path, f"{result_id}.json")
        
        if not os.path.exists(result_file):
            return jsonify({'success': False, 'message': 'Результат не найден'})
        
        # Удаляем файл
        os.remove(result_file)
        
        # Обновляем индекс
        index_file = os.path.join(results_path, 'index.json')
        if os.path.exists(index_file):
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            index = [r for r in index if r['id'] != result_id]
            
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'message': 'Результат удален'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/clear-all', methods=['POST'])
def api_clear_all_results():
    """Удаляет все результаты"""
    try:
        results_path = os.path.join(current_app.root_path, 'ansible_data', 'results')
        
        # Удаляем все JSON файлы кроме index.json
        for file in os.listdir(results_path):
            if file.endswith('.json') and file != 'index.json':
                try:
                    os.remove(os.path.join(results_path, file))
                except:
                    pass
        
        # Очищаем индекс
        index_file = os.path.join(results_path, 'index.json')
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump([], f)
        
        return jsonify({'success': True, 'message': 'Все результаты удалены'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})