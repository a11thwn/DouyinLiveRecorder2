// 建立WebSocket连接
const socket = io();

// DOM元素
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const mainConfigEditor = document.getElementById('mainConfigEditor');
const urlConfigEditor = document.getElementById('urlConfigEditor');
const logArea = document.getElementById('logArea');

// Bootstrap模态框
const mainConfigModal = new bootstrap.Modal(document.getElementById('mainConfigModal'));
const urlConfigModal = new bootstrap.Modal(document.getElementById('urlConfigModal'));

// 全局变量
let currentConfig = {
    main_config: {},
    url_config: {}
};

// 更新状态显示
function updateStatus(isRunning) {
    statusIndicator.className = 'status-indicator ' + (isRunning ? 'status-running' : 'status-stopped');
    statusText.textContent = isRunning ? '程序运行中' : '程序已停止';
    startBtn.disabled = isRunning;
    stopBtn.disabled = !isRunning;
}

// 创建主配置编辑表单
function createMainConfigForm(config) {
    mainConfigEditor.innerHTML = '';
    
    for (const [section, values] of Object.entries(config)) {
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'mb-4';
        
        const sectionTitle = document.createElement('h6');
        sectionTitle.textContent = section;
        sectionDiv.appendChild(sectionTitle);
        
        for (const [key, value] of Object.entries(values)) {
            const formGroup = document.createElement('div');
            formGroup.className = 'mb-3';
            
            const label = document.createElement('label');
            label.className = 'form-label';
            label.textContent = key;
            
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-control';
            input.value = value;
            input.dataset.section = section;
            input.dataset.key = key;
            
            formGroup.appendChild(label);
            formGroup.appendChild(input);
            sectionDiv.appendChild(formGroup);
        }
        
        mainConfigEditor.appendChild(sectionDiv);
    }
}

// 显示URL配置
function displayUrlConfig(config) {
    urlConfigEditor.value = config.content || '';
}

// 收集URL配置数据
function collectUrlConfig() {
    return {
        content: urlConfigEditor.value
    };
}

// 收集主配置表单数据
function collectMainConfigForm() {
    const config = {};
    const inputs = mainConfigEditor.querySelectorAll('input');
    
    inputs.forEach(input => {
        const section = input.dataset.section;
        const key = input.dataset.key;
        
        if (!config[section]) {
            config[section] = {};
        }
        
        config[section][key] = input.value;
    });
    
    return config;
}

// 显示主配置编辑器
function showMainConfigEditor() {
    createMainConfigForm(currentConfig.main_config);
    mainConfigModal.show();
}

// 显示URL配置编辑器
function showUrlConfigEditor() {
    displayUrlConfig(currentConfig.url_config);
    urlConfigModal.show();
}

// 处理未认证的响应
function handleUnauthenticated(response) {
    if (response.redirected && response.url.includes('/login')) {
        window.location.href = response.url;
        return true;
    }
    return false;
}

// 保存主配置
async function saveMainConfig() {
    const newMainConfig = collectMainConfigForm();
    
    try {
        // 验证配置数据
        if (!newMainConfig || Object.keys(newMainConfig).length === 0) {
            throw new Error('配置数据不能为空');
        }
        
        // 显示保存中提示
        const saveButton = document.querySelector('#mainConfigModal .btn-primary');
        const originalText = saveButton.textContent;
        saveButton.textContent = '保存中...';
        saveButton.disabled = true;
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                main_config: newMainConfig
            })
        });
        
        if (handleUnauthenticated(response)) return;
        
        const data = await response.json();
        if (data.status === 'success') {
            currentConfig.main_config = newMainConfig;
            mainConfigModal.hide();
            addLog('主配置保存成功');
        } else {
            throw new Error(data.message || '未知错误');
        }
    } catch (error) {
        console.error('保存主配置失败:', error);
        addLog('错误: 保存主配置失败 - ' + error.message);
        alert('保存主配置失败: ' + error.message);
    } finally {
        // 恢复保存按钮状态
        const saveButton = document.querySelector('#mainConfigModal .btn-primary');
        if (saveButton) {
            saveButton.textContent = '保存';
            saveButton.disabled = false;
        }
    }
}

// 保存URL配置
async function saveUrlConfig() {
    const newUrlConfig = collectUrlConfig();
    
    try {
        // 显示保存中提示
        const saveButton = document.querySelector('#urlConfigModal .btn-primary');
        const originalText = saveButton.textContent;
        saveButton.textContent = '保存中...';
        saveButton.disabled = true;
        
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url_config: newUrlConfig
            })
        });
        
        if (handleUnauthenticated(response)) return;
        
        const data = await response.json();
        if (data.status === 'success') {
            currentConfig.url_config = newUrlConfig;
            urlConfigModal.hide();
            addLog('URL配置保存成功');
        } else {
            throw new Error(data.message || '未知错误');
        }
    } catch (error) {
        console.error('保存URL配置失败:', error);
        addLog('错误: 保存URL配置失败 - ' + error.message);
        alert('保存URL配置失败: ' + error.message);
    } finally {
        // 恢复保存按钮状态
        const saveButton = document.querySelector('#urlConfigModal .btn-primary');
        if (saveButton) {
            saveButton.textContent = '保存';
            saveButton.disabled = false;
        }
    }
}

// 添加日志
function addLog(message) {
    const div = document.createElement('div');
    div.textContent = message;
    
    // 添加时间戳
    const timestamp = new Date().toLocaleTimeString();
    div.textContent = `[${timestamp}] ${message}`;
    
    // 设置样式
    if (message.startsWith('错误:')) {
        div.style.color = 'red';
    } else if (message.includes('已启动')) {
        div.style.color = 'green';
    } else if (message.includes('已停止')) {
        div.style.color = 'orange';
    }
    
    logArea.appendChild(div);
    
    // 保持滚动到最新的日志
    logArea.scrollTop = logArea.scrollHeight;
    
    // 如果日志太多，删除旧的
    const maxLogs = 1000;
    while (logArea.children.length > maxLogs) {
        logArea.removeChild(logArea.firstChild);
    }
}

// 事件监听器
startBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/control/start', { method: 'POST' });
        if (handleUnauthenticated(response)) return;
        
        const data = await response.json();
        if (data.status === 'success') {
            updateStatus(true);
        } else {
            alert('启动失败: ' + data.message);
        }
    } catch (error) {
        alert('启动失败: ' + error.message);
    }
});

stopBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/control/stop', { method: 'POST' });
        if (handleUnauthenticated(response)) return;
        
        const data = await response.json();
        if (data.status === 'success') {
            updateStatus(false);
        } else {
            alert('停止失败: ' + data.message);
        }
    } catch (error) {
        alert('停止失败: ' + error.message);
    }
});

// WebSocket事件处理
socket.on('connect', () => {
    console.log('WebSocket已连接');
    addLog('已连接到服务器');
});

socket.on('disconnect', () => {
    console.log('WebSocket连接断开');
    addLog('与服务器的连接已断开');
});

socket.on('status', (data) => {
    console.log('收到状态更新:', data);
    updateStatus(data.is_running);
    
    // 如果状态变为停止，禁用停止按钮
    if (!data.is_running) {
        stopBtn.disabled = true;
    }
});

socket.on('log', (data) => {
    console.log('收到日志:', data);
    if (data && data.data) {
        addLog(data.data);
        
        // 如果是重启相关的消息，更新UI状态
        if (data.data.includes('正在重启程序')) {
            startBtn.disabled = true;
            stopBtn.disabled = true;
        } else if (data.data.includes('程序已重启')) {
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else if (data.data.includes('重启失败')) {
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }
});

// 初始化
async function init() {
    try {
        // 清空日志区域
        logArea.innerHTML = '';
        addLog('初始化中...');
        
        // 获取配置
        const response = await fetch('/api/config');
        if (handleUnauthenticated(response)) return;
        
        const config = await response.json();
        currentConfig = config;
        
        // 获取初始状态
        const statusResponse = await fetch('/api/status');
        if (handleUnauthenticated(statusResponse)) return;
        
        const statusData = await statusResponse.json();
        updateStatus(statusData.is_running);
        
        addLog('初始化完成');
    } catch (error) {
        console.error('初始化失败:', error);
        addLog('初始化失败: ' + error.message);
        alert('初始化失败: ' + error.message);
    }
}

init(); 