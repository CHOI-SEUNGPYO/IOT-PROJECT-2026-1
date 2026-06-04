import os
import sqlite3
from datetime import datetime
from typing import List
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import requests
from fastapi.middleware.cors import CORSMiddleware 

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("alerts.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            sound_type TEXT,
            confidence REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 전역 상태 관리 변수
current_system_status = {
    "status": "normal",
    "detected_sound": "-",
    "probability": 0.0,
    "timestamp": ""
}

class AlertData(BaseModel):
    timestamp: datetime
    sound_type: str
    confidence: float


# 1. AI 모델이 위험 소리를 최초로 찔러주는 입구
@app.post("/api/alert")
async def receive_alert(data: AlertData):
    global current_system_status
    
    # DB 기록 생성
    conn = sqlite3.connect("alerts.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (timestamp, sound_type, confidence) VALUES (?, ?, ?)",
        (data.timestamp.isoformat(), data.sound_type, data.confidence)
    )
    conn.commit()
    conn.close()

    # 정상 상태일 때 처음 들어온 위험 신호만 수용 (락 기능)
    if current_system_status["status"] == "normal":
        current_system_status["status"] = "danger"
        current_system_status["detected_sound"] = data.sound_type
        current_system_status["probability"] = float(data.confidence)
        current_system_status["timestamp"] = data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n⚠️ [위험 감지] {data.sound_type} -> 프론트의 확인을 기다립니다.")
    
    return {"status": "success", "message": "위험 상태 전환 완료"}


# 2. 프론트엔드가 1초마다 실시간 조회를 해가는 곳
@app.get("/api/current_status")
def get_current_status():
    return current_system_status


# 3. [NEW] 프론트에서 15초 타이머가 진짜 끝났을 때 알림을 쏘라고 명령하는 곳
@app.post("/api/trigger_alarm")
def trigger_alarm():
    global current_system_status
    
    # 이미 조치가 완료되었거나 정상 상태라면 통과
    if current_system_status["status"] != "danger":
        return {"status": "ignored", "message": "이미 처리되었거나 위험 상태가 아닙니다."}
        
    print(" [최종 미응답 발생] 프론트엔드 통보에 의해 외부 알림을 전송합니다.")
    
    # 1. 텔레그램 발송
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    telegram_msg = (
        f" [위험 상황 최종 미응답] \n"
        f"보호자가 15초 동안 응답하지 않아 비상 알림이 발송되었습니다.\n\n"
        f"감지된 소리: {current_system_status['detected_sound']}\n"
        f"감지 확률: {current_system_status['probability'] * 100:.1f}%\n"
        f"발생 시간: {current_system_status['timestamp']}"
    )
    try: requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": telegram_msg})
    except Exception as e: print(f"텔레그램 실패: {e}")

    # 2. 슬랙 발송
    SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
    slack_msg = (
        f" *[위험 상황 최종 미응답]* \n"
        f"• 사용자가 15초간 응답하지 않아 비상 알림이 발송되었습니다.\n"
        f"• *소리 종류:* {current_system_status['detected_sound']}\n"
        f"• *감지 확률:* {current_system_status['probability'] * 100:.1f}%\n"
        f"• *발생 시간:* {current_system_status['timestamp']}"
    )
    try: requests.post(SLACK_WEBHOOK_URL, json={"text": slack_msg})
    except Exception as e: print(f"슬랙 실패: {e}")

    # 최종 알림 완료 상태로 변경
    current_system_status["status"] = "alarm_sent"
    return {"status": "success", "message": "텔레그램 및 슬랙 비상 알림 발송 완료"}



# 4. 사용자가 웹 화면에서 "괜찮습니다" 버튼을 눌렀을 때 호출되는 곳
@app.post("/api/report_fine")
def report_fine():
    global current_system_status
    current_system_status = {
        "status": "normal",
        "detected_sound": "-",
        "probability": 0.0,
        "timestamp": ""
    }
    print(" [안전 확인] 시스템이 정상화되었습니다. 타이머가 무효화됩니다.")
    return {"status": "success", "message": "정상 모니터링 상태로 복구 완료"}



# 5. 그래프 및 히스토리 API (유지)
@app.get("/api/chart_data")
def get_chart_data():
    conn = sqlite3.connect("alerts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, confidence FROM alerts ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    rows.reverse()
    times = [datetime.fromisoformat(r[0]).strftime("%H:%M") for r in rows] if rows else ["현재"]
    probabilities = [round(r[1], 2) for r in rows] if rows else [0.0]
    return {"labels": times, "data": probabilities}

@app.get("/api/history")
def get_alert_history():
    conn = sqlite3.connect("alerts.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, sound_type, confidence FROM alerts ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    history = [{"timestamp": r[0], "sound_type": r[1], "confidence": r[2]} for r in rows]
    return {"status": "success", "total_records": len(history), "data": history}

@app.get("/")
def read_root():
    return {"status": "success", "message": "FastAPI 데이터 통신 서버 가동 중"}