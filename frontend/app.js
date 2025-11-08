const tg = window.Telegram.WebApp;
tg.expand();

const API_URL = window.location.origin + '/api';
const userId = tg.initDataUnsafe?.user?.id || 123456;

let clickBuffer = 0;
let syncTimeout = null;
const SYNC_DELAY = 5000; // 5 ÑÐµÐºÑƒÐ½Ð´

// Ð¡Ð¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ
let appState = {
    balance: 0,
    totalClicks: 0,
    clickPower: 1,
    clickLevel: 1,
    upgradeCost: 100,
    farms: [],
    dailyStreak: 0
};

// Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ
async function init() {
    await loadUserStats();
    setupEventListeners();
    setupTabs();
}

// Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸
async function loadUserStats() {
    try {
        const response = await fetch(`${API_URL}/clicker/stats/${userId}`);
        const data = await response.json();
        
        appState.balance = data.balance;
        appState.totalClicks = data.total_clicks;
        appState.clickPower = data.click_power;
        appState.clickLevel = data.click_level;
        appState.upgradeCost = data.upgrade_cost;
        
        updateUI();
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸:', error);
    }
}

// ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ UI
function updateUI() {
    document.getElementById('balance').textContent = appState.balance.toLocaleString();
    document.getElementById('click-power').textContent = appState.clickPower;
    document.getElementById('total-clicks').textContent = appState.totalClicks.toLocaleString();
    document.getElementById('click-level').textContent = appState.clickLevel;
    document.getElementById('current-power').textContent = appState.clickPower;
    document.getElementById('next-power').textContent = appState.clickPower + 1;
    document.getElementById('upgrade-cost').textContent = appState.upgradeCost.toLocaleString();
    
    const upgradeBtn = document.getElementById('upgrade-btn');
    upgradeBtn.disabled = appState.balance < appState.upgradeCost;
}

// ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÐºÐ»Ð¸ÐºÐ°
async function handleClick(event) {
    const button = event.currentTarget;
    
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
    
    button.style.transform = 'scale(0.95)';
    setTimeout(() => button.style.transform = 'scale(1)', 100);
    
    showClickEffect(event);
    
    clickBuffer++;
    appState.balance += appState.clickPower;
    appState.totalClicks += 1;
    updateUI();
    
    if (syncTimeout) {
        clearTimeout(syncTimeout);
    }
    
    syncTimeout = setTimeout(() => {
        syncClicks();
    }, SYNC_DELAY);
}

// Ð­Ñ„Ñ„ÐµÐºÑ‚ ÐºÐ»Ð¸ÐºÐ°
function showClickEffect(event) {
    const effect = document.getElementById('click-effect');
    effect.textContent = `+${appState.clickPower}`;
    effect.style.left = event.clientX + 'px';
    effect.style.top = event.clientY + 'px';
    effect.style.opacity = '1';
    effect.style.animation = 'none';
    
    setTimeout(() => {
        effect.style.animation = 'floatUp 1s forwards';
    }, 10);
    
    setTimeout(() => {
        effect.style.opacity = '0';
    }, 1000);
}

// Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ñ ÐºÐ»Ð¸ÐºÐ¾Ð²
async function syncClicks() {
    if (clickBuffer === 0) return;
    
    const clicksToSync = clickBuffer;
    clickBuffer = 0;
    
    console.log(`ðŸ“¤ ÐžÑ‚Ð¿Ñ€Ð°Ð²ÐºÐ° ${clicksToSync} ÐºÐ»Ð¸ÐºÐ¾Ð² Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€...`);
    
    try {
        const response = await fetch(`${API_URL}/clicker/click`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                telegram_id: userId,
                clicks: clicksToSync
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            appState.totalClicks = data.total_clicks;
            updateUI();
            console.log(`âœ… ÐšÐ»Ð¸ÐºÐ¸ ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½Ñ‹. Ð‘Ð°Ð»Ð°Ð½Ñ: ${data.balance}`);
        } else {
            console.error('âŒ ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐµÑ€Ð²ÐµÑ€Ð°:', data.error);
            clickBuffer += clicksToSync;
        }
    } catch (error) {
        console.error('âŒ ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ð¸:', error);
        clickBuffer += clicksToSync;
    }
}

// Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð¿Ñ€Ð¸ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ð¸
window.addEventListener('beforeunload', () => {
    if (clickBuffer > 0) {
        navigator.sendBeacon(
            `${API_URL}/clicker/click`, 
            JSON.stringify({ telegram_id: userId, clicks: clickBuffer })
        );
    }
});

if (tg.onEvent) {
    tg.onEvent('viewportChanged', () => {
        if (!tg.isExpanded && clickBuffer > 0) {
            syncClicks();
        }
    });
}

// Ð£Ð»ÑƒÑ‡ÑˆÐµÐ½Ð¸Ðµ ÐºÐ»Ð¸ÐºÐ°
async function handleUpgrade() {
    if (appState.balance < appState.upgradeCost) return;
    
    try {
        const response = await fetch(`${API_URL}/clicker/upgrade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegram_id: userId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            appState.clickLevel = data.new_level;
            appState.clickPower = data.new_power;
            appState.upgradeCost = data.next_upgrade_cost;
            
            updateUI();
            showNotification('âœ… ÐšÐ»Ð¸Ðº ÑƒÐ»ÑƒÑ‡ÑˆÐµÐ½!', 'success');
            
            if (tg.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred('success');
            }
        } else {
            showNotification(data.error, 'error');
        }
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° ÑƒÐ»ÑƒÑ‡ÑˆÐµÐ½Ð¸Ñ:', error);
    }
}

// Ð•Ð¶ÐµÐ´Ð½ÐµÐ²Ð½Ñ‹Ð¹ Ð±Ð¾Ð½ÑƒÑ
async function handleDailyBonus() {
    try {
        const response = await fetch(`${API_URL}/daily/claim/${userId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            appState.dailyStreak = data.streak;
            
            updateUI();
            showNotification(`ðŸŽ +${data.bonus} Ð¼Ð¾Ð½ÐµÑ‚! Ð¡Ñ‚Ñ€Ð¸Ðº: ${data.streak} Ð´Ð½ÐµÐ¹`, 'success');
            
            document.getElementById('daily-btn').disabled = true;
            document.getElementById('daily-streak').textContent = data.streak;
        } else {
            showNotification(data.error, 'error');
        }
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° Ð±Ð¾Ð½ÑƒÑÐ°:', error);
    }
}

// ÐŸÐ¾ÐºÑƒÐ¿ÐºÐ° Ñ„ÐµÑ€Ð¼Ñ‹
async function handleBuyFarm(farmType) {
    try {
        const response = await fetch(`${API_URL}/farms/buy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_id: userId,
                farm_type: farmType
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            updateUI();
            await loadFarms();
            showNotification('âœ… Ð¤ÐµÑ€Ð¼Ð° ÐºÑƒÐ¿Ð»ÐµÐ½Ð°!', 'success');
        } else {
            showNotification(data.error, 'error');
        }
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾ÐºÑƒÐ¿ÐºÐ¸:', error);
    }
}

// Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° Ñ„ÐµÑ€Ð¼
async function loadFarms() {
    try {
        const response = await fetch(`${API_URL}/farms/${userId}`);
        const farms = await response.json();
        
        const container = document.getElementById('my-farms');
        
        if (farms.length === 0) {
            container.innerHTML = '<div class="empty-state">Ð£ Ð²Ð°Ñ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ‚ Ñ„ÐµÑ€Ð¼</div>';
            return;
        }
        
        container.innerHTML = farms.map(farm => `
            <div class="farm-item">
                <div class="farm-header">
                    <span class="farm-name">${farm.name} (ÑƒÑ€. ${farm.level})</span>
                    <span class="farm-status ${farm.is_active ? '' : 'inactive'}">
                        ${farm.is_active ? 'âœ… ÐÐºÑ‚Ð¸Ð²Ð½Ð°' : 'â¸ï¸ ÐÐµÐ°ÐºÑ‚Ð¸Ð²Ð½Ð°'}
                    </span>
                </div>
                <div class="farm-stats">
                    <span>ðŸ’µ ${farm.income_per_hour}/Ñ‡Ð°Ñ</span>
                    <span>ðŸ’° ÐÐ°ÐºÐ¾Ð¿Ð»ÐµÐ½Ð¾: ${farm.accumulated}</span>
                </div>
                <button class="collect-btn" onclick="collectFarm(${farm.id})" ${farm.accumulated === 0 ? 'disabled' : ''}>
                    Ð¡Ð¾Ð±Ñ€Ð°Ñ‚ÑŒ ${farm.accumulated} ðŸ’°
                </button>
            </div>
        `).join('');
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ñ„ÐµÑ€Ð¼:', error);
    }
}

// Ð¡Ð±Ð¾Ñ€ Ñ Ñ„ÐµÑ€Ð¼Ñ‹
async function collectFarm(farmId) {
    try {
        const response = await fetch(`${API_URL}/farms/collect/${farmId}?telegram_id=${userId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            updateUI();
            await loadFarms();
            showNotification(`âœ… Ð¡Ð¾Ð±Ñ€Ð°Ð½Ð¾ ${data.earned} Ð¼Ð¾Ð½ÐµÑ‚!`, 'success');
        }
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ±Ð¾Ñ€Ð°:', error);
    }
}

// Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° Ð»Ð¸Ð´ÐµÑ€Ð±Ð¾Ñ€Ð´Ð°
async function loadLeaderboard() {
    try {
        const response = await fetch(`${API_URL}/leaderboard/`);
        const players = await response.json();
        
        const container = document.getElementById('leaderboard-list');
        const medals = ['ðŸ¥‡', 'ðŸ¥ˆ', 'ðŸ¥‰'];
        
        container.innerHTML = players.map((player, index) => `
            <div class="leaderboard-item ${player.telegram_id === userId ? 'me' : ''}">
                <div class="rank">${medals[index] || (index + 1)}</div>
                <div class="player-info">
                    <div class="player-name">${player.username}</div>
                    <div class="player-stats">
                        ðŸ’° ${player.balance.toLocaleString()} | ðŸ“ˆ ${player.total_clicks.toLocaleString()} ÐºÐ»Ð¸ÐºÐ¾Ð²
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ñ‚Ð¾Ð¿Ð°:', error);
    }
}

// ÐŸÐµÑ€ÐµÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð²ÐºÐ»Ð°Ð´Ð¾Ðº
function setupTabs() {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
            
            if (tabName === 'farms') {
                loadFarms();
            } else if (tabName === 'leaderboard') {
                loadLeaderboard();
            }
        });
    });
}

// Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ñ
function showNotification(message, type = 'info') {
    tg.showAlert(message);
}

// ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸ÐºÐ¸ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹
function setupEventListeners() {
    document.getElementById('click-btn').addEventListener('click', handleClick);
    document.getElementById('upgrade-btn').addEventListener('click', handleUpgrade);
    document.getElementById('daily-btn').addEventListener('click', handleDailyBonus);
    
    document.querySelectorAll('.buy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const farmType = btn.dataset.type;
            handleBuyFarm(farmType);
        });
    });
}

// Ð—Ð°Ð¿ÑƒÑÐº
init();