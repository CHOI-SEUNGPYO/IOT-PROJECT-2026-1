// 1. API 주소 및 전역 상태 관리 변수
// 💡 다른 컴퓨터의 API를 쓸 때 여기에 IP를 적으세요. (예: 'http://192.168.0.15:5000')
// 💡 같은 Flask 서버에서 구동할 때는 빈 문자열('')로 두면 됩니다.
const API_BASE_URL = 'http://localhost:8000';

let systemState = 'normal'; // 현재 상태: 'normal', 'waiting_for_user', 'alarm_sent'
let countdownTimer = null;
let timeLeft = 15;
let isPopupShowing = false;

// 2. YAMNet 위험 소리 매핑 사전 (룩업 테이블)
const SOUND_MESSAGE_MAP = {
    "yell": " 비명소리 감지! 괜찮으신가요?",
    "screaming": " 비명소리 감지! 괜찮으신가요?",
    "scream": " 비명소리 감지! 괜찮으신가요?",
    "siren": " 사이렌 소리 감지! 가스밸브가 열려있나요?",
    "glass breaking": " 유리 깨지는 소리 감지! 외부 침입을 확인하세요.",
    "explosion": " 폭발음 감지! 즉시 대피하세요.",
    "gunshot": " 총성 감지! 안전한 곳으로 몸을 피하세요.",
    "speech" : "asdfasdf"
};

// ==========================================
// 3. 다크 모드 토글
// ==========================================
function toggleTheme() {
    const body = document.body;
    const currentTheme = body.getAttribute('data-theme');
    body.setAttribute('data-theme', currentTheme === 'dark' ? 'light' : 'dark');
}

// ==========================================
// 4. 실시간 상태 확인 (1초마다 실행)
// ==========================================
async function fetchStatus() {
    // 🚨 대기 중이거나 알림 완료 상태일 때는 서버 데이터를 가져와서 화면을 갱신하지 않음 (화면 잠금)
    if (systemState !== 'normal') return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/current_status`);
        if (!response.ok) throw new Error(`HTTP 에러! 상태코드: ${response.status}`);

        const data = await response.json();

        const box = document.getElementById('statusBox');
        if (!box) return; // 해당 페이지에 상태 박스가 없으면 종료

        // 데이터 화면 표시
        document.getElementById('statusSound').innerText = data.detected_sound;
        document.getElementById('statusProb').innerText = (data.probability * 100).toFixed(1);

        if (data.status === 'danger') {
            triggerDangerSequence(data.detected_sound);
        } else {
            box.className = 'card status-normal';
            document.getElementById('statusTitle').innerText = '✅ 정상 상태';
            const fineBtn = document.getElementById('fineBtn');
            if (fineBtn) fineBtn.style.display = 'none';
        }
    } catch (e) {
        console.error("상태 업데이트 실패:", e);
        const title = document.getElementById('statusTitle');
        if (title) title.innerText = '⚠️ 서버 연결 끊김';
    }
}

// ==========================================
// 5. 위험 감지 시퀀스 (타이머 및 게이지 작동)
// ==========================================
function triggerDangerSequence(soundType) {
    systemState = 'waiting_for_user';
    const totalTime = 15;
    timeLeft = totalTime;

    if (countdownTimer) clearInterval(countdownTimer);

    const box = document.getElementById('statusBox');
    const title = document.getElementById('statusTitle');
    const fineBtn = document.getElementById('fineBtn');
    const timerContainer = document.getElementById('timerContainer');
    const timerBar = document.getElementById('timerBar');

    if (box) box.className = 'card status-danger';
    if (title) title.innerText = '⚠️ 위험 감지!';
    if (fineBtn) {
        fineBtn.style.display = 'inline-block';
        fineBtn.innerText = `✅ 괜찮습니다 (${timeLeft}초 남음)`;
        fineBtn.style.color = '#e74c3c';
    }

    if (timerContainer && timerBar) {
        timerContainer.style.display = 'block';
        timerBar.style.width = '100%';
    }

    if (!isPopupShowing) {
        triggerDangerPopup(soundType);
    }

    // 1초마다 카운트다운 다운 및 게이지 축소
    countdownTimer = setInterval(() => {
        timeLeft--;

        if (fineBtn) {
            fineBtn.innerText = `✅ 괜찮습니다 (${timeLeft}초 남음)`;
        }

        if (timerBar) {
            timerBar.style.width = `${(timeLeft / totalTime) * 100}%`;
        }

        if (timeLeft <= 0) {
            clearInterval(countdownTimer);
            triggerAlarmSent();
        }
    }, 1000);
}

// ==========================================
// 6. 알림 전송 완료 처리
// ==========================================
async function triggerAlarmSent() {
    systemState = 'alarm_sent';

    const box = document.getElementById('statusBox');
    const title = document.getElementById('statusTitle');
    const fineBtn = document.getElementById('fineBtn');
    const timerContainer = document.getElementById('timerContainer');

    if (box) box.style.backgroundColor = '#8B0000';
    if (title) title.innerText = '🚨 외부 알림 전송 완료!';
    if (timerContainer) timerContainer.style.display = 'none';

    if (fineBtn) {
        fineBtn.style.display = 'inline-block';
        fineBtn.innerText = '🔄 확인 (모니터링 재개)';
        fineBtn.style.color = '#8B0000';
    }

    // 🎯 [팀원이 추가할 코드] 화면 타이머가 0초가 되었을 때 백엔드에 진짜 문자 쏘라고 명령하기!
    try {
        await fetch(`${API_BASE_URL}/api/trigger_alarm`, { method: 'POST' });
        console.log("백엔드에 최종 비상 알림 발송 명령 전송 완료");
    } catch (e) {
        console.error("비상 알림 명령 전송 실패:", e);
    }

    alert("응답 시간이 초과되어 보호자 및 관리자에게 알림이 전송되었습니다.");
}

// ==========================================
// 7. 안전 상태 보고 및 모니터링 복구 (버튼 클릭 시)
// ==========================================
async function reportFine() {
    if (systemState === 'alarm_sent') {
        alert("전송된 알림 상황을 확인했습니다. 모니터링을 다시 시작합니다.");
    } else {
        if (countdownTimer) clearInterval(countdownTimer);
        alert("안전 상태로 보고되었습니다. 모니터링을 재개합니다.");
    }

    // 💡 백엔드 서버에 사용자가 확인했음을 POST 신호로 전송
    try {
        await fetch(`${API_BASE_URL}/api/report_fine`, { method: 'POST' });
        console.log("서버에 안전 상태 보고 완료");
    } catch (e) {
        console.error("서버에 안전 상태 전송 실패:", e);
    }

    // 프론트엔드 상태 초기화 및 복구
    systemState = 'normal';

    const box = document.getElementById('statusBox');
    const timerContainer = document.getElementById('timerContainer');
    const title = document.getElementById('statusTitle');
    const fineBtn = document.getElementById('fineBtn');

    if (box) {
        box.style.backgroundColor = '';
        box.className = 'card status-normal';
    }
    if (title) title.innerText = '✅ 정상 상태';
    if (fineBtn) {
        fineBtn.style.display = 'none';
        fineBtn.style.color = '';
    }
    if (timerContainer) timerContainer.style.display = 'none';
}

// ==========================================
// 8. 토스트 팝업 표시
// ==========================================
function triggerDangerPopup(soundType) {
    const popup = document.getElementById('dangerPopup');
    if (!popup) return;

    const lowerSound = soundType.toLowerCase();
    const matchedKey = Object.keys(SOUND_MESSAGE_MAP).find(key => lowerSound.includes(key));

    if (!matchedKey) return;

    popup.innerText = SOUND_MESSAGE_MAP[matchedKey];
    popup.classList.add('show');
    isPopupShowing = true;

    setTimeout(() => {
        popup.classList.remove('show');
        setTimeout(() => {
            isPopupShowing = false;
        }, 500);
    }, 4000);
}

// ==========================================
// 9. Chart.js 그래프 렌더링
// ==========================================
async function renderChart() {
    const canvas = document.getElementById('probChart');
    if (!canvas) return;

    try {
        const res = await fetch(`${API_BASE_URL}/api/chart_data`);
        if (!res.ok) throw new Error("차트 데이터 로드 실패");
        const data = await res.json();

        const ctx = canvas.getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '위험 감지 확률',
                    data: data.data,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.2)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { maxTicksLimit: 5, maxRotation: 0, minRotation: 0 } },
                    y: { beginAtZero: true, max: 1 }
                }
            }
        });
    } catch (e) {
        console.error("차트 렌더링 중 오류:", e);
    }
}

// ==========================================
// 10. 시스템 구동 및 초기화
// ==========================================
setInterval(fetchStatus, 1000);
fetchStatus();
renderChart();
