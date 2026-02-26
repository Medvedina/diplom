class HostMonitor {
    constructor(hosts) {
        this.hosts = hosts;
        this.updateInterval = 30000; // 30 секунд
    }
    
    startMonitoring() {
        this.updateStatus();
        setInterval(() => this.updateStatus(), this.updateInterval);
    }
    
    updateStatus() {
        this.hosts.forEach(host => {
            fetch(`/inventory/api/host-status/${host}`)
                .then(response => response.json())
                .then(data => {
                    this.updateUI(host, data.status);
                });
        });
    }
    
    updateUI(host, status) {
        const element = document.querySelector(`[data-host="${host}"]`);
        if (!element) return;
        
        element.className = `host-status status-${status}`;
        element.title = `Статус: ${this.getStatusText(status)}`;
    }
    
    getStatusText(status) {
        const statusMap = {
            'up': 'Доступен',
            'down': 'Недоступен',
            'ssh_error': 'Ошибка SSH',
            'unknown': 'Неизвестно'
        };
        return statusMap[status] || 'Неизвестно';
    }
}