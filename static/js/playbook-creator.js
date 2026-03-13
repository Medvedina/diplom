// Глобальные переменные
let tasks = []; // Общие задачи
let hostTasks = {}; // Задачи для конкретных хостов {host1: [task1, task2], host2: [task3]}
let currentTaskType = null;
let currentTaskConfig = {};
let selectedTargets = new Set();
let availableInventories = [];
let taskIdCounter = 0;
let tasksConfig = {};
let currentTaskMode = 'common'; // 'common' или 'perhost'
let currentSelectedHost = null;

// Загрузка конфигурации задач из шаблона
document.addEventListener('DOMContentLoaded', function() {
    // Получаем конфигурацию из data-атрибута или передаем через скрытое поле
    tasksConfig = window.TASKS_CONFIG || {};
    console.log('Tasks config loaded:', tasksConfig);
    
    console.log('DOM загружен, инициализация...');
    
    // Загружаем инвентари
    loadInventories();
    
    // Настраиваем автоматическое обновление для всех полей формы
    setupAutoUpdate();
    
    // Обработчик переключения режима задач
    document.querySelectorAll('input[name="taskMode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            currentTaskMode = this.value;
            const hostSelector = document.getElementById('hostSelectorContainer');
            if (hostSelector) {
                hostSelector.style.display = currentTaskMode === 'perhost' ? 'block' : 'none';
            }
            
            // Обновляем список хостов при переключении
            if (currentTaskMode === 'perhost') {
                updateHostSelector();
            }
        });
    });
    
    // Автосохранение черновика каждые 30 секунд
    setInterval(() => {
        const hasData = document.getElementById('playbookName')?.value || 
                       document.getElementById('playbookDescription')?.value ||
                       tasks.length > 0 || Object.keys(hostTasks).length > 0;
        
        if (hasData) {
            autoSaveDraft();
        }
    }, 30000);
    
    // Проверяем режим редактирования
    if (window.EDIT_PLAYBOOK) {
        console.log('Редактирование плейбука:', window.EDIT_PLAYBOOK);
        
        const playbookData = window.EDIT_PLAYBOOK.data;
        const playbookName = window.EDIT_PLAYBOOK.name;
        
        // Устанавливаем имя плейбука
        if (playbookName) {
            document.getElementById('playbookName').value = playbookName;
        }
        
        // Парсим целевые устройства
        if (playbookData && Array.isArray(playbookData) && playbookData.length > 0) {
            const targetInfo = parsePlaybookTargets(playbookData);
            
            if (targetInfo.hosts !== 'all') {
                document.getElementById('targetSpecific').checked = true;
                toggleTargetSelection();
                
                // Сохраняем выбранные цели
                targetInfo.targets.forEach(target => selectedTargets.add(target));
                document.getElementById('selectedCount').textContent = selectedTargets.size;
                
                // Обновляем паттерн если есть
                if (targetInfo.hosts.includes('*')) {
                    document.getElementById('targetPattern').value = targetInfo.hosts;
                }
            }
            
            // Парсим задачи
            if (playbookData[0] && playbookData[0].tasks) {
                console.log('Задачи из плейбука:', playbookData[0].tasks);
                // Очищаем текущие задачи
                tasks = [];
                hostTasks = {};
                parsePlaybookTasks(playbookData[0].tasks);
            }
        }
    } else {
        console.log('Режим создания нового плейбука');
    }
    
    // Пытаемся восстановить черновик
    setTimeout(restoreDraft, 500);
});

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
                            // Подсчитываем общее количество хостов
                            let totalHosts = 0;
                            if (inv.groups) {
                                inv.groups.forEach(group => {
                                    totalHosts += group.hosts ? group.hosts.length : 0;
                                });
                            }
                            
                            const option = document.createElement('option');
                            option.value = inv.name;
                            option.textContent = `${inv.name} (${inv.groups.length} групп, ${totalHosts} хостов)`;
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
        if (inventory.groups) {
            inventory.groups.forEach(group => {
                // Проверяем, выбрана ли группа
                const isGroupSelected = selectedTargets.has(group.name);
                html += `<div class="target-item group ${isGroupSelected ? 'selected' : ''}" 
                            onclick="toggleTarget('${group.name}', true)">
                    <i class="bi bi-folder me-2"></i>${group.name} 
                    <span class="badge bg-secondary">${group.hosts ? group.hosts.length : 0} хостов</span>
                </div>`;
                
                // Хосты в группе
                if (group.hosts) {
                    group.hosts.forEach(host => {
                        const isHostSelected = selectedTargets.has(host);
                        html += `<div class="target-item host ${isHostSelected ? 'selected' : ''}" 
                                    onclick="toggleTarget('${host}', false)">
                            <i class="bi bi-pc me-2"></i>${host}
                        </div>`;
                    });
                }
            });
        }
        
        // Отдельные хосты (если есть)
        if (inventory.hosts) {
            inventory.hosts.forEach(host => {
                if (!inventory.groups || !inventory.groups.some(g => g.hosts && g.hosts.includes(host.name))) {
                    const isHostSelected = selectedTargets.has(host.name);
                    html += `<div class="target-item host ${isHostSelected ? 'selected' : ''}" 
                                onclick="toggleTarget('${host.name}', false)">
                        <i class="bi bi-pc me-2"></i>${host.name}
                    </div>`;
                }
            });
        }
        
        document.getElementById('targetsList').innerHTML = html;
        document.getElementById('loadingTargets').style.display = 'none';
        
        // Обновляем счетчик выбранных
        document.getElementById('selectedCount').textContent = selectedTargets.size;
        
        // Обновляем селектор хостов
        updateHostSelector();
    }, 300);
}

// Обновление селектора хостов
function updateHostSelector() {
    const select = document.getElementById('hostSelector');
    if (!select) return;
    
    const invName = document.getElementById('inventorySelect').value;
    if (!invName) {
        select.innerHTML = '<option value="">-- Сначала выберите инвентарь --</option>';
        return;
    }
    
    const inventory = availableInventories.find(inv => inv.name === invName);
    if (!inventory) return;
    
    let html = '<option value="">-- Выберите хост --</option>';
    
    // Добавляем все хосты из инвентаря
    if (inventory.hosts) {
        inventory.hosts.forEach(host => {
            html += `<option value="${host.name}">${host.name} (${host.group})</option>`;
        });
    }
    
    select.innerHTML = html;
    
    // Восстанавливаем выбранный хост если был
    if (currentSelectedHost) {
        select.value = currentSelectedHost;
    }
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
        
        // Если включен режим выбора и есть предвыбранные цели, загружаем инвентарь
        if (isSpecific && selectedTargets.size > 0) {
            // Пытаемся определить инвентарь по первому выбранному хосту
            const firstTarget = Array.from(selectedTargets)[0];
            const inventory = availableInventories.find(inv => 
                inv.hosts?.some(h => h.name === firstTarget) || 
                inv.groups?.some(g => g.name === firstTarget)
            );
            
            if (inventory) {
                document.getElementById('inventorySelect').value = inventory.name;
                loadInventoryTargets();
            }
        }
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
    if (currentTaskMode === 'perhost') {
        const host = document.getElementById('hostSelector').value;
        if (!host) {
            showAlert('Сначала выберите хост для настройки', 'warning');
            return;
        }
        currentSelectedHost = host;
    }
    
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
    
    // Добавляем задачу в зависимости от режима
    if (currentTaskMode === 'perhost' && currentSelectedHost) {
        if (!hostTasks[currentSelectedHost]) {
            hostTasks[currentSelectedHost] = [];
        }
        hostTasks[currentSelectedHost].push(taskConfig);
        showAlert(`Задача добавлена для хоста ${currentSelectedHost}`, 'success');
    } else {
        tasks.push(taskConfig);
        showAlert('Общая задача добавлена', 'success');
    }
    
    renderTasks();
    triggerYamlUpdate();
    
    bootstrap.Modal.getInstance(document.getElementById('taskConfigModal')).hide();
}

// Отображение задач
function renderTasks() {
    const container = document.getElementById('tasksContainer');
    
    if (!container) {
        console.error('Контейнер задач не найден!');
        return;
    }
    
    if (tasks.length === 0 && Object.keys(hostTasks).length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle me-2"></i>
                Нажмите "Добавить задачу" чтобы начать создание плейбука
            </div>
        `;
        return;
    }
    
    let html = '';
    
    // Отображаем общие задачи
    if (tasks.length > 0) {
        html += '<h6 class="mb-3"><i class="bi bi-people me-2"></i>Общие задачи для всех хостов:</h6>';
        tasks.forEach((task, index) => {
            html += renderTaskCard(task, index, 'common');
        });
    }
    
    // Отображаем задачи для конкретных хостов
    if (Object.keys(hostTasks).length > 0) {
        html += '<h6 class="mb-3 mt-4"><i class="bi bi-person me-2"></i>Задачи для конкретных хостов:</h6>';
        
        for (const [host, hostTaskList] of Object.entries(hostTasks)) {
            html += `<div class="mb-3 p-3 bg-light rounded">
                <h6 class="text-primary"><i class="bi bi-pc-display me-2"></i>Хост: ${host}</h6>`;
            
            hostTaskList.forEach((task, idx) => {
                html += renderTaskCard(task, `${host}_${idx}`, 'host', host);
            });
            
            html += '</div>';
        }
    }
    
    container.innerHTML = html;
    console.log(`Отображено ${tasks.length} общих задач и задач для ${Object.keys(hostTasks).length} хостов`);
}

// Вспомогательная функция для рендера карточки задачи
function renderTaskCard(task, index, type, host = null) {
    let paramsHtml = '';
    Object.entries(task.params).forEach(([key, value]) => {
        if (value && value !== '') {
            if (typeof value === 'boolean') {
                if (value) paramsHtml += `<span class="badge bg-secondary me-1">${key}</span>`;
            } else {
                paramsHtml += `<span class="badge bg-light text-dark me-1">${key}: ${value}</span>`;
            }
        }
    });
    
    return `
        <div class="card task-card ${task.type} mb-2">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="d-flex">
                        <div class="me-3">
                            <i class="bi ${task.icon} text-${task.color} fs-4"></i>
                        </div>
                        <div>
                            <h6 class="mb-1">${index + 1}. ${task.name}</h6>
                            <div class="d-flex flex-wrap gap-2 mt-2">${paramsHtml}</div>
                        </div>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteTask('${type}', ${typeof index === 'string' ? `'${index}'` : index}, '${host || ''}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Удаление задачи
function deleteTask(type, index, host = '') {
    if (type === 'common') {
        tasks.splice(index, 1);
    } else if (type === 'host' && host) {
        if (hostTasks[host]) {
            hostTasks[host].splice(index, 1);
            if (hostTasks[host].length === 0) {
                delete hostTasks[host];
            }
        }
    }
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
        tasks: []
    }];
    
    // Добавляем общие задачи
    tasks.forEach(task => {
        playbookData[0].tasks.push(createTaskPreview(task));
    });
    
    // Добавляем задачи для конкретных хостов с условиями
    for (const [host, hostTaskList] of Object.entries(hostTasks)) {
        hostTaskList.forEach(task => {
            const taskItem = createTaskPreview(task);
            taskItem.when = `inventory_hostname == '${host}'`;
            playbookData[0].tasks.push(taskItem);
        });
    }
    
    try {
        const yamlStr = jsyaml.dump(playbookData, {
            indent: 2,
            lineWidth: -1,
            noRefs: true
        });
        const previewElement = document.getElementById('yamlPreview');
        if (previewElement) {
            previewElement.textContent = yamlStr;
        }
    } catch (e) {
        console.error('Ошибка генерации YAML:', e);
        const previewElement = document.getElementById('yamlPreview');
        if (previewElement) {
            previewElement.textContent = '# Ошибка генерации YAML: ' + e.message;
        }
    }
}

// Вспомогательная функция для создания предпросмотра задачи
function createTaskPreview(task) {
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
}

// Функция для парсинга задач из плейбука
// Функция для парсинга задач из плейбука
function parsePlaybookTasks(tasksData) {
    if (!tasksData || !Array.isArray(tasksData)) {
        console.log('Нет задач для парсинга');
        return;
    }
    
    console.log('Парсинг задач из плейбука...');
    
    // Очищаем текущие задачи
    tasks = [];
    hostTasks = {};
    
    tasksData.forEach((task, index) => {
        // Определяем тип задачи по модулю
        let taskType = null;
        let taskParams = {};
        let taskName = task.name || `Задача ${index + 1}`;
        
        if (task.ping) {
            taskType = 'ping';
            taskParams = task.ping || {};
        } else if (task.ios_config) {
            const lines = task.ios_config.lines || [];
            const joinedLines = lines.join(' ');
            
            if (joinedLines.includes('router ospf')) {
                taskType = 'ospf';
                taskParams = parseOspfParams(lines);
            } else if (joinedLines.includes('router isis')) {
                taskType = 'isis';
                taskParams = parseIsisParams(lines);
            } else if (joinedLines.includes('spanning-tree')) {
                taskType = joinedLines.includes('rapid') ? 'rstp' : 'stp';
                taskParams = parseStpParams(lines);
            } else if (joinedLines.includes('interface')) {
                taskType = 'interface_config';
                taskParams = parseInterfaceParams(lines);
            } else {
                taskType = 'update_config';
                taskParams = {
                    lines: lines.join('\n'),
                    parents: task.ios_config.parents ? task.ios_config.parents[0] : '',
                    save: task.ios_config.save || true,
                    match: task.ios_config.match || 'line'
                };
            }
        } else if (task.ios_vlan) {
            taskType = 'vlan';
            taskParams = task.ios_vlan || {};
        } else if (task.ios_command) {
            taskType = 'custom_command';
            taskParams = {
                commands: (task.ios_command.commands || []).join('\n'),
                export_output: false
            };
        }
        
        if (taskType) {
            const taskConfig = TASKS_CONFIG[taskType] || {
                icon: 'bi-gear',
                color: 'secondary'
            };
            
            // Проверяем, есть ли условие для конкретного хоста
            if (task.when && task.when.includes('inventory_hostname')) {
                const match = task.when.match(/inventory_hostname == '([^']+)'/);
                if (match) {
                    const host = match[1];
                    if (!hostTasks[host]) {
                        hostTasks[host] = [];
                    }
                    hostTasks[host].push({
                        id: taskIdCounter++,
                        type: taskType,
                        name: taskName,
                        icon: taskConfig.icon,
                        color: taskConfig.color,
                        params: taskParams
                    });
                }
            } else {
                tasks.push({
                    id: taskIdCounter++,
                    type: taskType,
                    name: taskName,
                    icon: taskConfig.icon,
                    color: taskConfig.color,
                    params: taskParams
                });
            }
        }
    });
    
    renderTasks();
    triggerYamlUpdate();
}

// Вспомогательные функции для парсинга параметров
function parseOspfParams(lines) {
    const params = {
        process_id: 1,
        router_id: '',
        network: '',
        area: 0
    };
    
    lines.forEach(line => {
        if (line.includes('router ospf')) {
            const match = line.match(/router ospf (\d+)/);
            if (match) params.process_id = parseInt(match[1]);
        } else if (line.includes('router-id')) {
            params.router_id = line.replace('router-id', '').trim();
        } else if (line.includes('network')) {
            params.network = line.replace('network', '').trim();
        }
    });
    
    return params;
}

function parseIsisParams(lines) {
    const params = {
        net: '',
        system_id: '',
        area: '',
        level: 'level-1-2'
    };
    
    lines.forEach(line => {
        if (line.includes('net')) {
            params.net = line.replace('net', '').trim();
        } else if (line.includes('is-type')) {
            params.level = line.replace('is-type', '').trim();
        }
    });
    
    return params;
}

function parseStpParams(lines) {
    const params = {
        mode: 'pvst',
        priority: 32768,
        vlan: '1',
        root_primary: false,
        portfast: false,
        bpduguard: false
    };
    
    lines.forEach(line => {
        if (line.includes('spanning-tree mode')) {
            params.mode = line.replace('spanning-tree mode', '').trim();
        } else if (line.includes('priority')) {
            const match = line.match(/priority (\d+)/);
            if (match) params.priority = parseInt(match[1]);
        } else if (line.includes('root primary')) {
            params.root_primary = true;
        } else if (line.includes('portfast default')) {
            params.portfast = true;
        } else if (line.includes('bpduguard default')) {
            params.bpduguard = true;
        }
    });
    
    return params;
}

function parseInterfaceParams(lines) {
    const params = {
        interface: 'GigabitEthernet0/1',
        description: '',
        ip_address: '',
        admin_state: 'up'
    };
    
    lines.forEach(line => {
        if (line.startsWith('interface')) {
            params.interface = line.replace('interface', '').trim();
        } else if (line.includes('description')) {
            params.description = line.replace('description', '').trim();
        } else if (line.includes('ip address')) {
            params.ip_address = line.replace('ip address', '').trim();
        } else if (line.includes('shutdown')) {
            params.admin_state = 'down';
        } else if (line.includes('no shutdown')) {
            params.admin_state = 'up';
        }
    });
    
    return params;
}

// Функция для парсинга целевых устройств из плейбука
function parsePlaybookTargets(playbookData) {
    if (!playbookData || !Array.isArray(playbookData) || playbookData.length === 0) {
        return { hosts: 'all', targets: new Set() };
    }
    
    const firstPlay = playbookData[0];
    const target = firstPlay.hosts || 'all';
    
    console.log('Цель плейбука:', target);
    
    if (target === 'all') {
        return { hosts: 'all', targets: new Set() };
    }
    
    // Если это список хостов через двоеточие
    if (target.includes(':')) {
        const hosts = target.split(':').map(h => h.trim());
        return { hosts: target, targets: new Set(hosts) };
    }
    
    // Если это один хост или группа
    return { hosts: target, targets: new Set([target]) };
}

// Сохранение плейбука
// Сохранение плейбука
function savePlaybook() {
    const name = document.getElementById('playbookName').value.trim();
    const description = document.getElementById('playbookDescription').value.trim();
    
    if (!name) {
        showAlert('Введите название плейбука', 'warning');
        return;
    }
    
    if (tasks.length === 0 && Object.keys(hostTasks).length === 0) {
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
    
    // Подготавливаем задачи без метаданных
    const commonTasks = tasks.map(task => ({
        name: task.name,
        type: task.type,
        params: task.params
    }));
    
    const perHostTasks = {};
    for (const [host, hostTaskList] of Object.entries(hostTasks)) {
        perHostTasks[host] = hostTaskList.map(task => ({
            name: task.name,
            type: task.type,
            params: task.params
        }));
    }
    
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
            tasks: commonTasks,
            host_tasks: perHostTasks,
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
    return {
        name: task.name,
        type: task.type,
        params: task.params
    };
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
    if (tasks.length > 0 || Object.keys(hostTasks).length > 0) {
        if (confirm('Все несохраненные изменения будут потеряны. Продолжить?')) {
            window.location.href = '/playbooks';
        }
    } else {
        window.location.href = '/playbooks';
    }
}

// Автосохранение черновика
function autoSaveDraft() {
    const draft = {
        playbookName: document.getElementById('playbookName').value,
        description: document.getElementById('playbookDescription').value,
        tasks: tasks,
        hostTasks: hostTasks,
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
        }
        
        if (draft.hostTasks) {
            hostTasks = draft.hostTasks;
        }
        
        if (draft.selectedTargets) {
            selectedTargets = new Set(draft.selectedTargets);
            const countElement = document.getElementById('selectedCount');
            if (countElement) {
                countElement.textContent = selectedTargets.size;
            }
        }
        
        renderTasks();
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

// Утилита для показа уведомлений
function showAlert(message, type) {
    // Маппинг типов на классы Bootstrap
    const typeMap = {
        'success': 'success',      // зеленый
        'error': 'danger',         // красный
        'warning': 'warning',      // желтый
        'info': 'info',            // голубой
        'danger': 'danger'         // красный
    };
    
    // Получаем правильный класс для Bootstrap
    const bootstrapType = typeMap[type] || 'info';
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${bootstrapType} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
    
    // Выбираем иконку в зависимости от типа
    let icon = 'bi-info-circle';
    if (type === 'success') icon = 'bi-check-circle';
    else if (type === 'error' || type === 'danger') icon = 'bi-x-circle';
    else if (type === 'warning') icon = 'bi-exclamation-triangle';
    
    alertDiv.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="bi ${icon} me-2"></i>
            <div>${message}</div>
            <button type="button" class="btn-close ms-auto" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    document.body.appendChild(alertDiv);
    setTimeout(() => {
        if (alertDiv.parentElement) alertDiv.remove();
    }, 5000);
}

// Добавляем новые функции, которые были в шаблоне
function addNewGroup() {
    console.log('addNewGroup is deprecated');
}