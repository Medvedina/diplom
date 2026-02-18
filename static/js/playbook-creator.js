// Глобальные переменные
let tasks = [];
let currentTaskType = null;
let currentTaskConfig = {};
let selectedTargets = new Set();
let availableInventories = [];
let taskIdCounter = 0;
let tasksConfig = {};

// Загрузка конфигурации задач из шаблона
document.addEventListener('DOMContentLoaded', function() {
    // Получаем конфигурацию из data-атрибута или передаем через скрытое поле
    tasksConfig = window.TASKS_CONFIG || {};
    console.log('Tasks config loaded:', tasksConfig);
    
    initializePlaybookCreator();
});

// Инициализация
function initializePlaybookCreator() {
    console.log('Initializing playbook creator...');
    
    // Добавляем первую группу по умолчанию
    setTimeout(() => {
        addNewGroup();
        console.log('Default group added');
    }, 100);
    
    // Настраиваем автоматическое обновление для всех полей формы
    setupAutoUpdate();
    
    // Автосохранение черновика каждые 30 секунд
    setInterval(() => {
        const hasData = document.getElementById('playbookName').value || 
                       document.getElementById('playbookDescription').value ||
                       tasks.length > 0;
        
        if (hasData) {
            autoSaveDraft();
        }
    }, 30000);
    
    // Загружаем инвентари
    loadInventories();
}

// Настройка автоматического обновления
function setupAutoUpdate() {
    // Поля формы
    ['playbookName', 'playbookDescription'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', triggerYamlUpdate);
        }
    });
    
    // Радиокнопки
    document.querySelectorAll('input[name="targetType"]').forEach(radio => {
        radio.addEventListener('change', triggerYamlUpdate);
    });
    
    // Поле паттерна
    const pattern = document.getElementById('targetPattern');
    if (pattern) {
        pattern.addEventListener('input', triggerYamlUpdate);
    }
}

// Запуск обновления YAML с debounce
function triggerYamlUpdate() {
    if (window.updateTimeout) {
        clearTimeout(window.updateTimeout);
    }
    window.updateTimeout = setTimeout(() => {
        generateYamlPreview();
        window.updateTimeout = null;
    }, 300);
}

// Загрузка списка инвентарей
function loadInventories() {
    console.log('Загрузка списка инвентарей...');
    
    // Показываем индикатор загрузки
    const select = document.getElementById('inventorySelect');
    if (select) {
        select.innerHTML = '<option value="">Загрузка инвентарей...</option>';
        select.disabled = true;
    }
    
    fetch('/playbooks/api/get-inventories')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Получены данные инвентарей:', data);
            
            if (data.success) {
                availableInventories = data.inventories || [];
                const select = document.getElementById('inventorySelect');
                
                if (select) {
                    select.innerHTML = '<option value="">Выберите инвентарь...</option>';
                    select.disabled = false;
                    
                    if (availableInventories.length === 0) {
                        select.innerHTML = '<option value="">Нет доступных инвентарей</option>';
                        console.log('Нет инвентарей для отображения');
                    } else {
                        availableInventories.forEach(inv => {
                            const option = document.createElement('option');
                            option.value = inv.name;
                            option.textContent = `${inv.name} (${inv.groups.length} групп, ${inv.hosts.length} хостов)`;
                            select.appendChild(option);
                        });
                        console.log(`Загружено ${availableInventories.length} инвентарей`);
                    }
                }
            } else {
                console.error('Ошибка загрузки инвентарей:', data.message);
                if (select) {
                    select.innerHTML = '<option value="">Ошибка загрузки инвентарей</option>';
                }
            }
        })
        .catch(error => {
            console.error('Error loading inventories:', error);
            const select = document.getElementById('inventorySelect');
            if (select) {
                select.innerHTML = '<option value="">Ошибка загрузки: ' + error.message + '</option>';
            }
        });
}

// Загрузка целей для выбранного инвентаря
function loadInventoryTargets() {
    const invName = document.getElementById('inventorySelect').value;
    if (!invName) return;
    
    document.getElementById('loadingTargets').style.display = 'block';
    document.getElementById('targetsList').innerHTML = '';
    
    const inventory = availableInventories.find(inv => inv.name === invName);
    
    setTimeout(() => {
        let html = '';
        
        // Группы
        inventory.groups.forEach(group => {
            html += `<div class="target-item group" onclick="toggleTarget('${group.name}', true)">
                <i class="bi bi-folder me-2"></i>${group.name} 
                <span class="badge bg-secondary">${group.hosts.length} хостов</span>
            </div>`;
            
            // Хосты в группе
            group.hosts.forEach(host => {
                html += `<div class="target-item host" onclick="toggleTarget('${host}', false)">
                    <i class="bi bi-pc me-2"></i>${host}
                </div>`;
            });
        });
        
        // Отдельные хосты (если есть)
        inventory.hosts.forEach(host => {
            if (!inventory.groups.some(g => g.hosts.includes(host.name))) {
                html += `<div class="target-item host" onclick="toggleTarget('${host.name}', false)">
                    <i class="bi bi-pc me-2"></i>${host.name}
                </div>`;
            }
        });
        
        document.getElementById('targetsList').innerHTML = html;
        document.getElementById('loadingTargets').style.display = 'none';
    }, 300);
}

// Переключение выбора цели
function toggleTarget(target, isGroup) {
    const elements = document.querySelectorAll('.target-item');
    
    if (selectedTargets.has(target)) {
        selectedTargets.delete(target);
        elements.forEach(el => {
            if (el.textContent.includes(target)) {
                el.classList.remove('selected');
            }
        });
    } else {
        selectedTargets.add(target);
        elements.forEach(el => {
            if (el.textContent.includes(target)) {
                el.classList.add('selected');
            }
        });
    }
    
    const countElement = document.getElementById('selectedCount');
    if (countElement) {
        countElement.textContent = selectedTargets.size;
    }
    
    updateTargetPreview();
}

// Переключение режима выбора целей
function toggleTargetSelection() {
    const isSpecific = document.getElementById('targetSpecific')?.checked;
    const targetDiv = document.getElementById('targetSelection');
    
    if (targetDiv) {
        targetDiv.style.display = isSpecific ? 'block' : 'none';
    }
    
    updateTargetPreview();
}

// Обновление предпросмотра цели
function updateTargetPreview() {
    const isAll = document.getElementById('targetAll')?.checked;
    let preview = '';
    
    if (isAll) {
        preview = 'all';
    } else {
        const pattern = document.getElementById('targetPattern')?.value;
        if (pattern) {
            preview = pattern;
        } else if (selectedTargets.size > 0) {
            preview = Array.from(selectedTargets).slice(0, 3).join(', ');
            if (selectedTargets.size > 3) preview += ` и ещё ${selectedTargets.size - 3}`;
        } else {
            preview = 'не выбрано';
        }
    }
    
    const previewElement = document.getElementById('targetPreview');
    if (previewElement) {
        previewElement.textContent = preview;
    }
    
    triggerYamlUpdate();
}

// Выбор всех хостов
function selectAllHosts() {
    document.querySelectorAll('.target-item.host').forEach(el => {
        const host = el.textContent.trim();
        if (!selectedTargets.has(host)) {
            selectedTargets.add(host);
            el.classList.add('selected');
        }
    });
    
    const countElement = document.getElementById('selectedCount');
    if (countElement) {
        countElement.textContent = selectedTargets.size;
    }
    
    updateTargetPreview();
}

// Очистка выбора
function clearSelection() {
    selectedTargets.clear();
    document.querySelectorAll('.target-item').forEach(el => {
        el.classList.remove('selected');
    });
    
    const countElement = document.getElementById('selectedCount');
    if (countElement) {
        countElement.textContent = 0;
    }
    
    const patternElement = document.getElementById('targetPattern');
    if (patternElement) {
        patternElement.value = '';
    }
    
    updateTargetPreview();
}

// Показать выбор задачи
function showTaskSelector() {
    const modal = new bootstrap.Modal(document.getElementById('taskSelectorModal'));
    modal.show();
}

// Выбор конкретной задачи
function selectTask(taskType) {
    currentTaskType = taskType;
    const task = window.TASKS_CONFIG[taskType];
    
    if (!task) {
        console.error('Task not found:', taskType);
        return;
    }
    
    const modalBody = document.getElementById('taskConfigBody');
    modalBody.innerHTML = `
        <div class="mb-3">
            <label class="form-label">Название задачи</label>
            <input type="text" class="form-control" id="taskName" value="${task.name}">
        </div>
        ${generateTaskParams(task.params)}
    `;
    
    const titleElement = document.getElementById('taskConfigTitle');
    if (titleElement) {
        titleElement.innerHTML = `
            <i class="bi ${task.icon} text-${task.color} me-2"></i>${task.name}
        `;
    }
    
    bootstrap.Modal.getInstance(document.getElementById('taskSelectorModal')).hide();
    const configModal = new bootstrap.Modal(document.getElementById('taskConfigModal'));
    configModal.show();
}

// Генерация HTML для параметров задачи
function generateTaskParams(params) {
    let html = '';
    
    params.forEach(param => {
        html += `<div class="mb-3">`;
        
        // Добавляем подсказку к параметру
        const paramHelp = getParamHelp(currentTaskType, param.name);
        html += `<div class="d-flex justify-content-between align-items-center">
            <label class="form-label">${param.label}</label>
            ${paramHelp ? `<small class="text-muted cursor-help" onclick="showParamHelp('${currentTaskType}', '${param.name}')">
                <i class="bi bi-question-circle"></i>
            </small>` : ''}
        </div>`;
        
        if (param.type === 'text') {
            html += `
                <input type="text" class="form-control" id="param_${param.name}" 
                       placeholder="${param.placeholder || ''}" ${param.required ? 'required' : ''}>
            `;
        } else if (param.type === 'number') {
            html += `
                <input type="number" class="form-control" id="param_${param.name}" 
                       value="${param.default || ''}" min="${param.min || 0}" max="${param.max || 9999}">
            `;
        } else if (param.type === 'select') {
            html += `
                <select class="form-select" id="param_${param.name}">
            `;
            param.options.forEach(opt => {
                html += `<option value="${opt}" ${opt === param.default ? 'selected' : ''}>${opt}</option>`;
            });
            html += `</select>`;
        } else if (param.type === 'checkbox') {
            html += `
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="param_${param.name}" 
                           ${param.default ? 'checked' : ''}>
                    <label class="form-check-label" for="param_${param.name}">${param.label}</label>
                </div>
            `;
        } else if (param.type === 'textarea') {
            html += `
                <textarea class="form-control" id="param_${param.name}" rows="3" 
                          placeholder="${param.placeholder || ''}"></textarea>
            `;
        }
        
        html += `</div>`;
    });
    
    return html;
}

// Добавление настроенной задачи
function addConfiguredTask() {
    const taskName = document.getElementById('taskName').value;
    const task = window.TASKS_CONFIG[currentTaskType];
    
    const taskConfig = {
        id: taskIdCounter++,
        type: currentTaskType,
        name: taskName,
        icon: task.icon,
        color: task.color,
        params: {}
    };
    
    // Собираем параметры
    task.params.forEach(param => {
        const element = document.getElementById(`param_${param.name}`);
        if (element) {
            if (param.type === 'checkbox') {
                taskConfig.params[param.name] = element.checked;
            } else {
                taskConfig.params[param.name] = element.value;
            }
        }
    });
    
    tasks.push(taskConfig);
    renderTasks();
    triggerYamlUpdate();
    
    bootstrap.Modal.getInstance(document.getElementById('taskConfigModal')).hide();
}

// Отображение задач
function renderTasks() {
    const container = document.getElementById('tasksContainer');
    
    if (tasks.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                Нажмите "Добавить задачу" чтобы начать создание плейбука
            </div>
        `;
        return;
    }
    
    let html = '';
    
    tasks.forEach((task, index) => {
        html += `
            <div class="card task-card ${task.type}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="d-flex">
                            <div class="me-3">
                                <i class="bi ${task.icon} text-${task.color} fs-4"></i>
                            </div>
                            <div>
                                <h6 class="mb-1">
                                    ${index + 1}. ${task.name}
                                </h6>
                                <div class="d-flex flex-wrap gap-2 mt-2">
                                    ${renderTaskParams(task.params)}
                                </div>
                            </div>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-outline-warning me-1" onclick="editTask(${index})">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteTask(${index})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Рендер параметров задачи
function renderTaskParams(params) {
    let html = '';
    
    Object.entries(params).forEach(([key, value]) => {
        if (value && value !== '') {
            if (typeof value === 'boolean') {
                if (value) {
                    html += `<span class="badge bg-secondary">${key}</span>`;
                }
            } else if (key !== 'type') {
                html += `<span class="badge bg-light text-dark">${key}: ${value}</span>`;
            }
        }
    });
    
    return html || '<span class="text-muted">Нет параметров</span>';
}

// Редактирование задачи
function editTask(index) {
    const task = tasks[index];
    currentTaskType = task.type;
    
    const modalBody = document.getElementById('taskConfigBody');
    const taskConfig = window.TASKS_CONFIG[task.type];
    
    modalBody.innerHTML = `
        <div class="mb-3">
            <label class="form-label">Название задачи</label>
            <input type="text" class="form-control" id="taskName" value="${task.name}">
        </div>
        ${generateTaskParams(taskConfig.params)}
    `;
    
    // Заполняем сохраненные значения
    taskConfig.params.forEach(param => {
        const element = document.getElementById(`param_${param.name}`);
        if (element) {
            if (param.type === 'checkbox') {
                element.checked = task.params[param.name] || false;
            } else {
                element.value = task.params[param.name] || '';
            }
        }
    });
    
    const titleElement = document.getElementById('taskConfigTitle');
    if (titleElement) {
        titleElement.innerHTML = `
            <i class="bi ${taskConfig.icon} text-${taskConfig.color} me-2"></i>Редактирование задачи
        `;
    }
    
    const configModal = new bootstrap.Modal(document.getElementById('taskConfigModal'));
    configModal.show();
    
    // Сохраняем индекс для редактирования
    window.currentEditIndex = index;
}

// Удаление задачи
function deleteTask(index) {
    tasks.splice(index, 1);
    renderTasks();
    triggerYamlUpdate();
}

// Генерация предпросмотра YAML
function generateYamlPreview() {
    const name = document.getElementById('playbookName')?.value || 'playbook';
    const description = document.getElementById('playbookDescription')?.value || 'Ansible Playbook';
    const isAll = document.getElementById('targetAll')?.checked;
    
    let target = 'all';
    if (!isAll) {
        const pattern = document.getElementById('targetPattern')?.value;
        if (pattern) {
            target = pattern;
        } else if (selectedTargets.size > 0) {
            target = Array.from(selectedTargets).join(':');
        }
    }
    
    // Формируем структуру плейбука для предпросмотра
    const playbookData = [{
        name: description,
        hosts: target,
        gather_facts: true,
        connection: 'network_cli',
        tasks: tasks.map(task => {
            const taskItem = {
                name: task.name
            };
            
            // Для каждого типа задачи создаем упрощенную структуру
            switch(task.type) {
                case 'ping':
                    taskItem.ping = {};
                    if (task.params.count) taskItem.ping.count = parseInt(task.params.count);
                    if (task.params.size) taskItem.ping.size = parseInt(task.params.size);
                    break;
                    
                case 'interface_config':
                    taskItem.ios_config = {
                        lines: [
                            `interface ${task.params.interface || 'GigabitEthernet0/1'}`,
                            task.params.description ? ` description ${task.params.description}` : null,
                            task.params.ip_address ? ` ip address ${task.params.ip_address}` : null,
                            task.params.admin_state ? ` ${task.params.admin_state === 'up' ? 'no shutdown' : 'shutdown'}` : null
                        ].filter(line => line !== null)
                    };
                    break;
                    
                case 'ospf':
                    taskItem.ios_config = {
                        lines: [
                            `router ospf ${task.params.process_id || 1}`,
                            task.params.router_id ? ` router-id ${task.params.router_id}` : null,
                            task.params.network ? ` network ${task.params.network}` : null
                        ].filter(line => line !== null)
                    };
                    break;
                    
                case 'isis':
                    taskItem.ios_config = {
                        lines: [
                            'router isis',
                            task.params.net ? ` net ${task.params.net}` : null,
                            task.params.level ? ` is-type ${task.params.level}` : null
                        ].filter(line => line !== null)
                    };
                    break;
                    
                case 'stp':
                case 'rstp':
                    taskItem.ios_config = {
                        lines: []
                    };
                    if (task.params.mode) {
                        taskItem.ios_config.lines.push(`spanning-tree mode ${task.params.mode}`);
                    }
                    if (task.params.priority && task.params.vlan) {
                        taskItem.ios_config.lines.push(`spanning-tree vlan ${task.params.vlan} priority ${task.params.priority}`);
                    }
                    if (task.params.root_primary) {
                        taskItem.ios_config.lines.push(`spanning-tree vlan ${task.params.vlan || 1} root primary`);
                    }
                    if (task.params.portfast) {
                        taskItem.ios_config.lines.push('spanning-tree portfast default');
                    }
                    if (task.params.bpduguard) {
                        taskItem.ios_config.lines.push('spanning-tree portfast bpduguard default');
                    }
                    break;
                    
                case 'vlan':
                    taskItem.ios_vlan = {
                        vlan_id: parseInt(task.params.vlan_id) || 10,
                        name: task.params.name || 'VLAN',
                        state: task.params.state || 'active'
                    };
                    if (task.params.interfaces) {
                        taskItem.ios_vlan.interfaces = task.params.interfaces.split(',').map(i => i.trim());
                    }
                    break;
                    
                case 'backup_config':
                    taskItem.ios_command = {
                        commands: ['show running-config']
                    };
                    taskItem.register = 'config_output';
                    break;
                    
                case 'update_config':
                    if (task.params.lines) {
                        taskItem.ios_config = {
                            lines: task.params.lines.split('\n').filter(l => l.trim()),
                            parents: task.params.parents ? [task.params.parents] : [],
                            save: task.params.save || true,
                            match: task.params.match || 'line'
                        };
                    }
                    break;
                    
                default:
                    taskItem.debug = {
                        msg: `Task: ${task.type}`
                    };
            }
            
            return taskItem;
        })
    }];
    
    try {
        const yamlStr = jsyaml.dump(playbookData, {
            indent: 2,
            lineWidth: -1,
            noRefs: true
        });
        document.getElementById('yamlPreview').textContent = yamlStr;
    } catch (e) {
        document.getElementById('yamlPreview').textContent = '# Ошибка генерации YAML: ' + e.message;
    }
}

// Сохранение плейбука
function savePlaybook() {
    const name = document.getElementById('playbookName').value.trim();
    const description = document.getElementById('playbookDescription').value.trim();
    
    if (!name) {
        showAlert('Введите название плейбука', 'warning');
        return;
    }
    
    if (tasks.length === 0) {
        showAlert('Добавьте хотя бы одну задачу', 'warning');
        return;
    }
    
    const isAll = document.getElementById('targetAll').checked;
    let target = 'all';
    
    if (!isAll) {
        const pattern = document.getElementById('targetPattern').value;
        if (pattern) {
            target = pattern;
        } else if (selectedTargets.size > 0) {
            target = Array.from(selectedTargets).join(':');
        } else {
            showAlert('Выберите целевые устройства или укажите паттерн', 'warning');
            return;
        }
    }
    
    // Формируем данные плейбука для сохранения
    const playbookTasks = [];
    
    tasks.forEach(task => {
        switch(task.type) {
            case 'backup_config':
                // Первая задача - сбор конфигурации
                playbookTasks.push({
                    name: task.name + ' - сбор конфигурации',
                    ios_command: {
                        commands: ['show running-config']
                    },
                    register: 'config_output'
                });
                
                // Вторая задача - сохранение (только если указана директория)
                if (task.params.destination) {
                    playbookTasks.push({
                        name: task.name + ' - сохранение',
                        copy: {
                            content: '{{ config_output.stdout[0] }}',
                            dest: task.params.destination + '/{{ inventory_hostname }}_backup.cfg'
                        }
                    });
                    
                    // Если нужно архивировать
                    if (task.params.compress) {
                        playbookTasks.push({
                            name: task.name + ' - архивация',
                            archive: {
                                path: task.params.destination + '/{{ inventory_hostname }}_backup.cfg',
                                dest: task.params.destination + '/{{ inventory_hostname }}_backup.tar.gz',
                                format: 'gz'
                            }
                        });
                    }
                }
                break;
                
            default:
                // Для остальных задач - одна задача
                playbookTasks.push(createTaskItem(task));
        }
    });
    
    const playbookData = [{
        name: description || `Playbook: ${name}`,
        hosts: target,
        gather_facts: true,
        connection: 'network_cli',
        tasks: playbookTasks
    }];
    
    const saveBtn = document.querySelector('button[onclick="savePlaybook()"]');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Сохранение...';
    saveBtn.disabled = true;
    
    fetch('/playbooks/api/save-playbook', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: name,
            description: description,
            playbook_data: playbookData,
            hosts: target
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Плейбук успешно сохранен', 'success');
            setTimeout(() => {
                window.location.href = '/playbooks';
            }, 1500);
        } else {
            showAlert('Ошибка: ' + data.message, 'error');
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
    })
    .catch(error => {
        showAlert('Ошибка сети: ' + error.message, 'error');
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    });
}

// Вспомогательная функция для создания задачи
function createTaskItem(task) {
    const taskItem = {
        name: task.name
    };
    
    switch(task.type) {
        case 'ping':
            taskItem.ping = {};
            if (task.params.count) taskItem.ping.count = parseInt(task.params.count);
            if (task.params.size) taskItem.ping.size = parseInt(task.params.size);
            break;
            
        case 'interface_config':
            taskItem.ios_config = {
                lines: [
                    `interface ${task.params.interface || 'GigabitEthernet0/1'}`
                ]
            };
            if (task.params.description) {
                taskItem.ios_config.lines.push(` description ${task.params.description}`);
            }
            if (task.params.ip_address) {
                taskItem.ios_config.lines.push(` ip address ${task.params.ip_address}`);
            }
            if (task.params.admin_state) {
                taskItem.ios_config.lines.push(` ${task.params.admin_state === 'up' ? 'no shutdown' : 'shutdown'}`);
            }
            break;
            
        case 'ospf':
            taskItem.ios_config = {
                lines: [
                    `router ospf ${task.params.process_id || 1}`
                ]
            };
            if (task.params.router_id) {
                taskItem.ios_config.lines.push(` router-id ${task.params.router_id}`);
            }
            if (task.params.network) {
                taskItem.ios_config.lines.push(` network ${task.params.network}`);
            }
            break;
            
        case 'isis':
            taskItem.ios_config = {
                lines: ['router isis']
            };
            if (task.params.net) {
                taskItem.ios_config.lines.push(` net ${task.params.net}`);
            }
            if (task.params.level) {
                taskItem.ios_config.lines.push(` is-type ${task.params.level}`);
            }
            break;
            
        case 'stp':
        case 'rstp':
            taskItem.ios_config = {
                lines: []
            };
            if (task.params.mode) {
                taskItem.ios_config.lines.push(`spanning-tree mode ${task.params.mode}`);
            }
            if (task.params.priority && task.params.vlan) {
                taskItem.ios_config.lines.push(`spanning-tree vlan ${task.params.vlan} priority ${task.params.priority}`);
            }
            if (task.params.root_primary) {
                taskItem.ios_config.lines.push(`spanning-tree vlan ${task.params.vlan || 1} root primary`);
            }
            if (task.params.portfast) {
                taskItem.ios_config.lines.push('spanning-tree portfast default');
            }
            if (task.params.bpduguard) {
                taskItem.ios_config.lines.push('spanning-tree portfast bpduguard default');
            }
            break;
            
        case 'vlan':
            taskItem.ios_vlan = {
                vlan_id: parseInt(task.params.vlan_id) || 10,
                name: task.params.name || 'VLAN',
                state: task.params.state || 'active'
            };
            if (task.params.interfaces) {
                taskItem.ios_vlan.interfaces = task.params.interfaces.split(',').map(i => i.trim());
            }
            break;
            
        case 'update_config':
            if (task.params.lines) {
                taskItem.ios_config = {
                    lines: task.params.lines.split('\n').filter(l => l.trim()),
                    parents: task.params.parents ? [task.params.parents] : [],
                    save: task.params.save || true,
                    match: task.params.match || 'line'
                };
            }
            break;
            
        default:
            taskItem.debug = {
                msg: `Task: ${task.type}`
            };
    }
    
    return taskItem;
}

// Валидация плейбука
function validatePlaybook() {
    const yamlContent = document.getElementById('yamlPreview').textContent;
    
    fetch('/playbooks/api/validate-playbook', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content: yamlContent})
    })
    .then(response => response.json())
    .then(data => {
        if (data.valid) {
            showAlert('Плейбук валиден', 'success');
        } else {
            showAlert('Ошибка: ' + data.message, 'error');
        }
    });
}

// Загрузка шаблона
function loadTemplate(template) {
    if (template === 'network_basic') {
        document.getElementById('playbookName').value = 'network_basic.yml';
        document.getElementById('playbookDescription').value = 'Базовая настройка сетевых устройств';
        
        tasks = [
            {
                id: taskIdCounter++,
                type: 'ping',
                name: 'Проверка доступности',
                icon: 'bi-wifi',
                color: 'success',
                params: {count: 3}
            },
            {
                id: taskIdCounter++,
                type: 'ospf',
                name: 'Настройка OSPF',
                icon: 'bi-diagram-3',
                color: 'warning',
                params: {process_id: 1, router_id: '1.1.1.1', area: 0}
            }
        ];
        
        renderTasks();
        triggerYamlUpdate();
    } else if (template === 'stp_vlan') {
        document.getElementById('playbookName').value = 'stp_vlan.yml';
        document.getElementById('playbookDescription').value = 'Настройка STP и VLAN на коммутаторах';
        
        tasks = [
            {
                id: taskIdCounter++,
                type: 'stp',
                name: 'Настройка STP',
                icon: 'bi-shield-shaded',
                color: 'danger',
                params: {mode: 'rapid-pvst', priority: 32768, vlan: '1-100'}
            },
            {
                id: taskIdCounter++,
                type: 'vlan',
                name: 'Создание VLAN',
                icon: 'bi-tags',
                color: 'success',
                params: {vlan_id: 10, name: 'Users', state: 'active'}
            },
            {
                id: taskIdCounter++,
                type: 'vlan',
                name: 'Создание VLAN для гостей',
                icon: 'bi-tags',
                color: 'success',
                params: {vlan_id: 20, name: 'Guests', state: 'active'}
            }
        ];
        
        renderTasks();
        triggerYamlUpdate();
    }
    
    showAlert('Шаблон загружен', 'success');
}

// Назад к списку
function goBack() {
    if (tasks.length > 0 && confirm('Все несохраненные изменения будут потеряны. Продолжить?')) {
        window.location.href = '/playbooks';
    } else if (tasks.length === 0) {
        window.location.href = '/playbooks';
    }
}

// Автосохранение черновика
function autoSaveDraft() {
    const draft = {
        playbookName: document.getElementById('playbookName').value,
        description: document.getElementById('playbookDescription').value,
        tasks: tasks,
        targetType: document.querySelector('input[name="targetType"]:checked')?.value || 'all',
        targetPattern: document.getElementById('targetPattern')?.value || '',
        selectedTargets: Array.from(selectedTargets),
        timestamp: new Date().toISOString()
    };
    
    localStorage.setItem('playbook_draft', JSON.stringify(draft));
    console.log('Draft auto-saved');
}

// Восстановление черновика
function restoreDraft() {
    const draftData = localStorage.getItem('playbook_draft');
    if (!draftData) return;
    
    try {
        const draft = JSON.parse(draftData);
        
        document.getElementById('playbookName').value = draft.playbookName || '';
        document.getElementById('playbookDescription').value = draft.description || '';
        
        if (draft.targetType === 'specific') {
            document.getElementById('targetSpecific').checked = true;
            toggleTargetSelection();
        }
        
        document.getElementById('targetPattern').value = draft.targetPattern || '';
        
        if (draft.tasks) {
            tasks = draft.tasks;
            renderTasks();
        }
        
        if (draft.selectedTargets) {
            selectedTargets = new Set(draft.selectedTargets);
            const countElement = document.getElementById('selectedCount');
            if (countElement) {
                countElement.textContent = selectedTargets.size;
            }
        }
        
        triggerYamlUpdate();
        showAlert('Черновик восстановлен', 'info');
        
    } catch (e) {
        console.error('Error restoring draft:', e);
    }
}

// Функции для показа справки
function showHelp(protocol) {
    const helpTexts = {
        'ospf': `**OSPF (Open Shortest Path First)**
        
• Тип: Link-state протокол
• Алгоритм: SPF (Dijkstra)
• Метрика: Cost (пропускная способность)
• Области: Позволяет делить сеть на зоны
• Поддерживает: VLSM, CIDR, аутентификацию

**Параметры:**
• Process ID - идентификатор процесса (1-65535)
• Router ID - уникальный идентификатор маршрутизатора (обычно IP-адрес)
• Network - сеть для анонсирования
• Area - номер области (0 для backbone)`,
        
        'isis': `**IS-IS (Intermediate System to Intermediate System)**

• Тип: Link-state протокол
• Алгоритм: SPF (Dijkstra)
• Метрика: По умолчанию 10, можно настраивать
• Особенность: Работает на 2 уровне OSI
• Масштабирование: Отлично подходит для очень крупных сетей

**Параметры:**
• NET - Network Entity Title (NSAP адрес)
• System ID - уникальный идентификатор системы
• Area - номер области
• Level - уровень (level-1, level-2, level-1-2)`,
        
        'stp': `**STP (Spanning Tree Protocol)**

• Назначение: Предотвращение петель в сети
• Алгоритм: STA (Spanning Tree Algorithm)
• Время конвергенции: 30-50 секунд
• Состояния портов: Blocking, Listening, Learning, Forwarding

**Параметры:**
• Mode - режим работы (PVST, Rapid-PVST, MST)
• Priority - приоритет моста (0-61440, шаг 4096)
• VLAN - VLAN для применения
• Root Primary - сделать мост корневым`,
        
        'rstp': `**RSTP (Rapid Spanning Tree Protocol)**

• Назначение: Быстрое восстановление при изменениях топологии
• Время конвергенции: 1-3 секунды
• Состояния портов: Discarding, Learning, Forwarding
• Роли портов: Root, Designated, Alternate, Backup

**Параметры:**
• Priority - приоритет моста
• Link Type - тип соединения (point-to-point/shared)
• Portfast - быстрый перевод порта в forwarding
• BPDU Guard - защита от BPDU`,
        
        'vlan': `**VLAN (Virtual Local Area Network)**

• Назначение: Логическое разделение сети
• Диапазон ID: 1-4094
• VLAN 1 - административный (обычно не используется для данных)
• Trunk - передает несколько VLAN

**Параметры:**
• VLAN ID - идентификатор VLAN (1-4094)
• Name - имя VLAN (описательное)
• State - состояние (active/suspend)
• Interfaces - порты, входящие в VLAN`,
        
        'interface_config': `**Настройка интерфейса**

• Конфигурация физических и логических интерфейсов
• Настройка IP-адресов
• Управление состоянием интерфейса

**Параметры:**
• Interface - тип и номер интерфейса
• Description - текстовое описание
• IP Address - IP-адрес с маской
• Admin State - административное состояние (up/down)`,
        
        'ping': `**Ping тест**

• Проверка доступности устройств
• Измерение задержек
• Диагностика сетевых проблем

**Параметры:**
• Count - количество отправляемых пакетов
• Size - размер пакета в байтах`,
        
        'backup_config': `**Бэкап конфигурации**

• Сохранение текущей конфигурации устройств
• Автоматическое резервное копирование
• Версионирование конфигураций

**Параметры:**
• Destination - директория для сохранения
• Compress - архивировать файлы
• Include Secrets - включить пароли в бэкап`,
        
        'update_config': `**Обновление конфигурации**

• Массовое применение команд
• Обновление настроек устройств
• Проверка и сохранение конфигурации

**Параметры:**
• Lines - команды для выполнения
• Parents - родительский контекст
• Save - сохранить конфигурацию
• Match - режим сравнения команд`
    };
    
    const helpModal = new bootstrap.Modal(document.getElementById('helpModal'));
    document.getElementById('helpTitle').textContent = `Справка: ${protocol.toUpperCase()}`;
    document.getElementById('helpContent').innerHTML = helpTexts[protocol] || 'Информация отсутствует';
    helpModal.show();
}

function showParamHelp(protocol, paramName) {
    const paramHelpTexts = {
        'ospf': {
            'process_id': '**Process ID** - уникальный номер процесса OSPF на маршрутизаторе. Может быть от 1 до 65535. На одном устройстве можно запустить несколько процессов OSPF с разными ID.',
            'router_id': '**Router ID** - 32-битное число, идентифицирующее маршрутизатор в OSPF. Обычно используется IP-адрес loopback интерфейса или самый высокий IP-адрес.',
            'network': '**Network** - сеть для анонсирования в формате "10.0.0.0 0.0.0.255 area 0". Wildcard-маска обратна обычной маске подсети.',
            'area': '**Area** - номер области OSPF. Область 0 (backbone) должна соединять все остальные области. Может быть от 0 до 4294967295.'
        },
        'isis': {
            'net': '**NET (Network Entity Title)** - адрес NSAP в формате XX.XXXX.XXXX.XXXX.XX. Пример: 49.0001.0010.0100.1001.00',
            'system_id': '**System ID** - уникальный идентификатор системы в сети IS-IS. Обычно 6 байт в формате XXXX.XXXX.XXXX',
            'area': '**Area** - номер области IS-IS. Области помогают масштабировать сеть и ограничивать распространение информации.',
            'level': '**Level** - уровень IS-IS: level-1 (внутри области), level-2 (между областями), level-1-2 (оба уровня)'
        },
        'stp': {
            'mode': '**Mode** - режим работы STP: PVST (Per VLAN Spanning Tree), Rapid-PVST (быстрая сходимость), MST (Multiple Spanning Tree)',
            'priority': '**Priority** - приоритет моста (0-61440, шаг 4096). Меньшее значение = более высокий приоритет. Мост с наименьшим приоритетом становится корневым.',
            'vlan': '**VLAN** - VLAN, для которого применяются настройки. Можно указать диапазон (1-100) или список (1,3,5)',
            'root_primary': '**Root Primary** - делает текущий коммутатор корневым для указанного VLAN'
        },
        'vlan': {
            'vlan_id': '**VLAN ID** - уникальный идентификатор VLAN от 1 до 4094. VLAN 1 обычно используется для управления и не рекомендуется для данных.',
            'name': '**Name** - текстовое имя VLAN для удобной идентификации. Например: "Sales", "Engineering", "Guest"',
            'state': '**State** - состояние VLAN: active (активен) или suspend (приостановлен). В suspend трафик не передается.',
            'interfaces': '**Interfaces** - список интерфейсов, входящих в VLAN. Формат: Gi0/1, Gi0/2-5, Fa0/1'
        }
    };
    
    const help = paramHelpTexts[protocol]?.[paramName] || 'Нет описания для этого параметра';
    
    const helpModal = new bootstrap.Modal(document.getElementById('helpModal'));
    document.getElementById('helpTitle').textContent = `Параметр: ${paramName}`;
    document.getElementById('helpContent').innerHTML = help;
    helpModal.show();
}

function getParamHelp(protocol, paramName) {
    const paramHelpTexts = {
        'ospf': {
            'process_id': '**Process ID** - уникальный номер процесса OSPF на маршрутизаторе (1-65535)',
            'router_id': '**Router ID** - идентификатор маршрутизатора в OSPF (обычно IP-адрес)',
            'network': '**Network** - сеть для анонсирования в формате "10.0.0.0 0.0.0.255 area 0"',
            'area': '**Area** - номер области OSPF (0 для backbone)'
        },
        'isis': {
            'net': '**NET** - адрес NSAP в формате XX.XXXX.XXXX.XXXX.XX',
            'system_id': '**System ID** - уникальный идентификатор системы (XXXX.XXXX.XXXX)',
            'area': '**Area** - номер области IS-IS',
            'level': '**Level** - уровень IS-IS (level-1, level-2, level-1-2)'
        },
        'stp': {
            'mode': '**Mode** - режим STP: pvst, rapid-pvst, mst',
            'priority': '**Priority** - приоритет моста (0-61440, шаг 4096)',
            'vlan': '**VLAN** - VLAN для применения настроек',
            'root_primary': '**Root Primary** - сделать коммутатор корневым'
        },
        'vlan': {
            'vlan_id': '**VLAN ID** - идентификатор VLAN (1-4094)',
            'name': '**Name** - имя VLAN',
            'state': '**State** - состояние VLAN (active/suspend)',
            'interfaces': '**Interfaces** - порты в VLAN'
        }
    };
    
    return paramHelpTexts[protocol]?.[paramName] || null;
}

// Уведомления
function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
    alertDiv.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="bi ${type === 'success' ? 'bi-check-circle' : 
                         type === 'error' ? 'bi-x-circle' : 
                         type === 'warning' ? 'bi-exclamation-triangle' : 
                         'bi-info-circle'} me-2"></i>
            <div>${message}</div>
            <button type="button" class="btn-close ms-auto" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    document.body.appendChild(alertDiv);
    setTimeout(() => {
        if (alertDiv.parentElement) alertDiv.remove();
    }, 5000);
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
    // Загружаем конфигурацию задач из data-атрибута или передаем через глобальную переменную
    if (window.TASKS_CONFIG) {
        tasksConfig = window.TASKS_CONFIG;
    }
    
    initializePlaybookCreator();
    
    // Пытаемся восстановить черновик
    setTimeout(restoreDraft, 500);
});

// Добавляем новые функции, которые были в шаблоне
function addNewGroup() {
    // Эта функция больше не используется в новой версии
    console.log('addNewGroup is deprecated');
}