const tg = window.Telegram.WebApp;
tg.expand();

const API_URL = window.location.origin + '/api';
const userId = tg.initDataUnsafe?.user?.id || 123456;

let clickBuffer = 0;
let syncTimeout = null;
const SYNC_DELAY = 1000;
let isSyncing = false;
let isBlockedByPlatform = false;       // флаг блокировки платформой
let loadingStats = false;              // защита от параллельных вызовов loadUserStats
let blockedSince = 0;                  // время (ms) когда стала активна блокировка
const MIN_BLOCK_DURATION = 8000;       // минимум 8 сек блокировки (защита от ложного снятия)
let statsDebounceTimer = null;         // дебаунс для частых viewportChanged

let dailyStatusData = null; 
let dailyTimerInterval = null; 

let appState = {
    balance: 0,
    totalClicks: 0,
    clickPower: 1,
    clickLevel: 1,
    upgradeCost: 100,
    farms: [],
    dailyStreak: 0,
    dailyClaimAvailable: true,
    referralCode: '',
    referralCount: 0,
    referralEarnings: 0
};

async function init() {
    // Кнопка отключена до загрузки статистики (предотвращает гонку)
    const clickBtn = document.getElementById('click-btn');
    if (clickBtn) clickBtn.disabled = true;

    await loadUserStats();  // устанавливает isBlockedByPlatform и разблокирует кнопку

    await loadDailyStatus();
    await checkReferralCode();
    setupEventListeners();
    setupTabs();

    // Периодическая проверка статуса блокировки (каждые 5 сек)
    setInterval(async () => {
        await loadUserStats();
    }, 5000);
    
    document.addEventListener('visibilitychange', async () => {
        if (!document.hidden) {
            console.log('📱 Приложение снова активно — перепроверяем блокировку и daily');
            await loadUserStats();   // ← сбрасывает/восстанавливает блокировку
            await loadDailyStatus();
        }
    });

    if (tg.onEvent) {
        // Дебаунс: viewportChanged стреляет очень часто — ждём 500ms после последнего события
        tg.onEvent('viewportChanged', () => {
            if (statsDebounceTimer) clearTimeout(statsDebounceTimer);
            statsDebounceTimer = setTimeout(async () => {
                statsDebounceTimer = null;
                console.log('📱 viewportChanged (debounced) — перепроверяем блокировку');
                await loadUserStats();
            }, 500);
        });
    }
}

async function checkReferralCode() {
    const urlParams = new URLSearchParams(window.location.search);
    const refCode = urlParams.get('ref');
    
    if (refCode) {
        console.log('🎁 Обнаружен реферальный код:', refCode);
        await activateReferral(refCode);
    }
}

async function activateReferral(code) {
    try {
        const response = await fetch(`${API_URL}/referral/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_id: userId,
                referral_code: code
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(
                `🎉 Бонус активирован! Вы получили ${data.user_bonus} 💰\n` +
                `Пригласил: ${data.referrer_username}`,
                'success'
            );
            await loadUserStats();
        } else {
            console.log('Реферальный код не активирован:', data.error);
        }
    } catch (error) {
        console.error('Ошибка активации реферала:', error);
    }
}

async function loadUserStats() {
    // Защита от параллельных вызовов (viewportChanged стреляет очень часто)
    if (loadingStats) return;
    loadingStats = true;
    try {
        const response = await fetch(`${API_URL}/clicker/stats/${userId}`);
        const data = await response.json();

        appState.balance = data.balance;
        appState.totalClicks = data.total_clicks;
        appState.clickPower = data.click_power;
        appState.clickLevel = data.click_level;
        appState.upgradeCost = data.upgrade_cost;

        // Синхронизировать состояние блокировки с сервером
        if (data.is_locked) {
            // Сервер говорит — заблокировано (MC активен)
            setBlockedState(true, data.locked_by || 'minecraft');
        } else {
            // Сервер говорит — разблокировано.
            // Не снимать блокировку раньше MIN_BLOCK_DURATION после её установки.
            const now = Date.now();
            if (!isBlockedByPlatform || (now - blockedSince) >= MIN_BLOCK_DURATION) {
                setBlockedState(false, null);
            } else {
                console.log(`⏳ Блокировка ещё активна (${Math.round((now - blockedSince)/1000)}s < ${MIN_BLOCK_DURATION/1000}s)`);
            }
        }

        updateUI();
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    } finally {
        loadingStats = false;
    }
}

async function loadDailyStatus() {
    try {
        const response = await fetch(`${API_URL}/daily/status/${userId}`);
        
        if (!response.ok) {
            console.error('Ошибка статуса daily:', response.status);
            return;
        }
        
        dailyStatusData = await response.json();
        dailyStatusData.loadedAt = Date.now(); 
        
        updateDailyUI();

        if (dailyTimerInterval) clearInterval(dailyTimerInterval);
        dailyTimerInterval = setInterval(updateDailyUI, 1000);
        
        console.log('Daily status загружен:', dailyStatusData);
    } catch (error) {
        console.error('Ошибка loadDailyStatus:', error);
    }
}

function updateDailyUI() {
    if (!dailyStatusData) return;
    
    const dailyBtn = document.getElementById('daily-btn');
    const dailyStreakEl = document.getElementById('daily-streak');
    
    if (!dailyBtn || !dailyStreakEl) return;
    
    dailyStreakEl.textContent = dailyStatusData.streak;
    appState.dailyStreak = dailyStatusData.streak;

    const elapsed = (Date.now() - dailyStatusData.loadedAt) / 1000;
    const timeLeft = Math.max(0, dailyStatusData.time_left_seconds - elapsed);
    
    if (timeLeft === 0) {
        dailyBtn.disabled = false;
        dailyBtn.textContent = '🎁 Забрать ежедневный бонус';
        appState.dailyClaimAvailable = true;
    } else {
        dailyBtn.disabled = true;
        const hours = Math.floor(timeLeft / 3600);
        const minutes = Math.floor((timeLeft % 3600) / 60);
        const seconds = Math.floor(timeLeft % 60);
        dailyBtn.textContent = `⏰ ${hours}ч ${minutes}м ${seconds}с`;
        appState.dailyClaimAvailable = false;
    }
}

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

async function handleClick(event) {
    // Если заблокированы платформой — блокировать любым способом
    if (isBlockedByPlatform) {
        event.preventDefault();
        event.stopPropagation();
        console.warn('⛔ Клик отклонён: платформа заблокирована');
        return;
    }

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

async function syncClicks() {
    if (clickBuffer === 0 || isSyncing) return;
    
    const clicksToSync = clickBuffer;
    clickBuffer = 0;
    isSyncing = true;
    
    console.log(`📤 Отправка ${clicksToSync} кликов на сервер...`);
    
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
            // Успех — снять блокировку, применить серверный баланс
            setBlockedState(false, null);
            appState.balance = data.balance;
            appState.totalClicks = data.total_clicks;
            updateUI();
            console.log(`✅ Клики синхронизированы. Баланс: ${data.balance}`);
        } else if (data.blocked_by) {
            // Заблокированы платформой — показать баннер, откатить баланс
            console.warn(`⛔ Клики заблокированы платформой: ${data.blocked_by}`);
            setBlockedState(true, data.blocked_by);
            await loadUserStats();  // откатить баланс до серверного значения
        } else {
            // Другая ошибка — вернуть клики в буфер
            console.error('❌ Ошибка сервера:', data.error);
            clickBuffer += clicksToSync;
        }
    } catch (error) {
        console.error('Ошибка синхронизации:', error);
        clickBuffer += clicksToSync;
    } finally {
        isSyncing = false;
    }
}

window.addEventListener('beforeunload', async () => {
    if (clickBuffer > 0) {
        await fetch(`${API_URL}/clicker/click`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                telegram_id: userId, 
                clicks: clickBuffer 
            }),
            keepalive: true
        }).catch(err => console.error('Ошибка финальной синхронизации:', err));
    }
});

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
            showNotification('✅ Клик улучшен!', 'success');
            
            if (tg.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred('success');
            }
        } else {
            showNotification(data.error, 'error');
        }
    } catch (error) {
        console.error('Ошибка улучшения:', error);
    }
}

async function handleDailyBonus() {
    const dailyBtn = document.getElementById('daily-btn');
    if (dailyBtn.disabled) return;
    
    dailyBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_URL}/daily/claim/${userId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            appState.balance = data.balance;
            appState.dailyStreak = data.streak;
            
            updateUI();
            showNotification(`🎁 +${data.bonus} монет! Стрик: ${data.streak} дней`, 'success');

            await loadDailyStatus();
        } else {
            showNotification(data.error, 'error');
            await loadDailyStatus();
        }
    } catch (error) {
        console.error('Ошибка бонуса:', error);
        dailyBtn.disabled = false;
    }
}

async function loadReferralInfo() {
    try {
        const response = await fetch(`${API_URL}/referral/info/${userId}`);
        const data = await response.json();
        
        appState.referralCode = data.referral_code;
        appState.referralCount = data.referral_count;
        appState.referralEarnings = data.referral_earnings;
        
        document.getElementById('referral-code').textContent = data.referral_code;
        document.getElementById('referral-count').textContent = data.referral_count;
        document.getElementById('referral-earnings').textContent = `${data.referral_earnings} 💰`;
        document.getElementById('bonus-amount').textContent = data.bonus_per_referral;
        
        await loadFriendsList();
    } catch (error) {
        console.error('Ошибка загрузки реферальной информации:', error);
    }
}

async function loadFriendsList() {
    try {
        const response = await fetch(`${API_URL}/referral/list/${userId}`);
        const friends = await response.json();
        
        const container = document.getElementById('friends-list');
        
        if (friends.length === 0) {
            container.innerHTML = '<div class="empty-state">Вы ещё никого не пригласили</div>';
            return;
        }
        
        container.innerHTML = friends.map(friend => `
            <div class="friend-item">
                <div class="friend-icon">👤</div>
                <div class="friend-info">
                    <div class="friend-name">${friend.username}</div>
                    <div class="friend-stats">💰 ${friend.balance.toLocaleString()} | Присоединился: ${friend.joined_at}</div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки списка друзей:', error);
    }
}

async function handleInvite() {
    const botUsername = 'tetrisfn_bot';  
    const inviteUrl = `https://t.me/${botUsername}?start=${appState.referralCode}`;
    
    const shareText = `🎮 Присоединяйся к Clicker Game!\n\n💰 Получи ${document.getElementById('bonus-amount').textContent} монет при регистрации!\n🎁 Кликай, зарабатывай и побеждай!`;
    
    if (tg.openTelegramLink) {
        tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(inviteUrl)}&text=${encodeURIComponent(shareText)}`);
    } else {
        tg.openLink(`https://t.me/share/url?url=${encodeURIComponent(inviteUrl)}&text=${encodeURIComponent(shareText)}`);
    }
}

async function handleCopyLink() {
    const botUsername = 'tetrisfn_bot'; 
    const inviteUrl = `https://t.me/${botUsername}?start=${appState.referralCode}`;
    
    try {
        if (navigator.clipboard) {
            await navigator.clipboard.writeText(inviteUrl);
            showNotification('Ссылка скопирована!', 'success');
        } else {
            const textArea = document.createElement('textarea');
            textArea.value = inviteUrl;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            showNotification('Ссылка скопирована!', 'success');
        }
        
        if (tg.HapticFeedback) {
            tg.HapticFeedback.notificationOccurred('success');
        }
    } catch (error) {
        console.error('Ошибка копирования:', error);
        showNotification('Не удалось скопировать', 'error');
    }
}

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
            showNotification('Ферма куплена!', 'success');
        } else {
            showNotification(data.error, 'error');
        }
    } catch (error) {
        console.error('Ошибка покупки:', error);
    }
}

async function loadFarms() {
    try {
        const response = await fetch(`${API_URL}/farms/${userId}`);
        const farms = await response.json();
        
        const container = document.getElementById('my-farms');
        
        if (farms.length === 0) {
            container.innerHTML = '<div class="empty-state">У вас пока нет ферм</div>';
            return;
        }
        
        container.innerHTML = farms.map(farm => `
            <div class="farm-item">
                <div class="farm-header">
                    <span class="farm-name">${farm.name} (ур. ${farm.level})</span>
                    <span class="farm-status ${farm.is_active ? '' : 'inactive'}">
                        ${farm.is_active ? '✅ Активна' : '⏸️ Неактивна'}
                    </span>
                </div>
                <div class="farm-stats">
                    <span>💵 ${farm.income_per_hour}/час</span>
                    <span>💰 Накоплено: ${farm.accumulated}</span>
                </div>
                <button class="collect-btn" onclick="collectFarm(${farm.id})" ${farm.accumulated === 0 ? 'disabled' : ''}>
                    Собрать ${farm.accumulated} 💰
                </button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки ферм:', error);
    }
}

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
            showNotification(`✅ Собрано ${data.earned} монет!`, 'success');
        }
    } catch (error) {
        console.error('Ошибка сбора:', error);
    }
}

async function loadLeaderboard() {
    try {
        const response = await fetch(`${API_URL}/leaderboard/`);
        const players = await response.json();
        
        const container = document.getElementById('leaderboard-list');
        const medals = ['🥇', '🥈', '🥉'];
        
        container.innerHTML = players.map((player, index) => `
            <div class="leaderboard-item ${player.telegram_id === userId ? 'me' : ''}">
                <div class="rank">${medals[index] || (index + 1)}</div>
                <div class="player-info">
                    <div class="player-name">${player.username}</div>
                    <div class="player-stats">
                        💰 ${player.balance.toLocaleString()} | 📈 ${player.total_clicks.toLocaleString()} кликов
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки топа:', error);
    }
}

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
            } else if (tabName === 'friends') {
                loadReferralInfo(); 
            }
        });
    });
}

function showNotification(message, type = 'info') {
    tg.showAlert(message);
}

/**
 * Центральная функция управления состоянием блокировки платформой.
 * Обновляет флаг, баннер и кнопку одним вызовом.
 */
function setBlockedState(blocked, blockedBy) {
    const wasBlocked = isBlockedByPlatform;
    isBlockedByPlatform = blocked;

    const banner = document.getElementById('platform-block-banner');
    const platformName = document.getElementById('block-platform-name');
    const btn = document.getElementById('click-btn');

    if (blocked) {
        // Запомнить время блокировки (только при первом переходе в заблокированное состояние)
        if (!wasBlocked) {
            blockedSince = Date.now();
            console.warn(`⛔ Блокировка активирована: ${blockedBy} (${new Date(blockedSince).toLocaleTimeString()})`);
        }
        // Показать баннер
        if (banner) {
            if (platformName) {
                platformName.textContent = (blockedBy === 'minecraft') ? 'Minecraft ⛏️' : 'Telegram 📱';
            }
            banner.style.display = 'block';
        }
        // Заблокировать кнопку
        if (btn) {
            btn.disabled = true;
            btn.style.opacity = '0.4';
            btn.style.cursor = 'not-allowed';
            btn.style.pointerEvents = 'none';
        }
        // Сбросить буфер кликов
        clickBuffer = 0;
        if (syncTimeout) { clearTimeout(syncTimeout); syncTimeout = null; }
    } else {
        blockedSince = 0;
        // Скрыть баннер
        if (banner) banner.style.display = 'none';
        // Разблокировать кнопку
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
            btn.style.pointerEvents = 'auto';
        }
        if (wasBlocked) console.log('✅ Блокировка снята');
    }
}

function setupEventListeners() {
    document.getElementById('click-btn').addEventListener('click', handleClick);
    document.getElementById('upgrade-btn').addEventListener('click', handleUpgrade);
    document.getElementById('daily-btn').addEventListener('click', handleDailyBonus);
    
    document.getElementById('invite-btn').addEventListener('click', handleInvite);
    document.getElementById('copy-link-btn').addEventListener('click', handleCopyLink);
    
    document.querySelectorAll('.buy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const farmType = btn.dataset.type;
            handleBuyFarm(farmType);
        });
    });
}

init();
