import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import numpy as np
import csv
import requests
import subprocess  # ⭐ PyAudio 대신 리눅스 기본 프로그램을 부르기 위해 추가
from datetime import datetime
from collections import deque

# tflite-runtime 및 tensorflow.lite 지원을 위한 유연한 로드 구조
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        import tensorflow as tf
        tflite = tf.lite

class YamnetAudioDetector:
    def __init__(self, model_path=None, classifier_model_path=None, csv_path=None):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = model_path or os.path.join(current_dir, "yamnet.tflite")
        classifier_model_path = classifier_model_path or os.path.join(current_dir, "fall_classifier.tflite")
        csv_path = csv_path or os.path.join(current_dir, "yamnet_class_map.csv")

        # YAMNet 모델 로드
        self.interpreter = tflite.Interpreter(model_path=model_path, num_threads=1)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        
        # 1024차원 임베딩 텐서의 인덱스 검색 (양자화 정보 포함)
        self.embedding_tensor_index = None
        self.embedding_scale = 1.0
        self.embedding_zero_point = 0
        
        all_tensors = self.interpreter.get_tensor_details()
        for tensor in all_tensors:
            shape = tensor.get('shape')
            if shape is not None and list(shape) == [1, 1, 1, 1024]:
                self.embedding_tensor_index = tensor['index']
                quant = tensor.get('quantization', (1.0, 0))
                # (scale, zero_point) 형태 파싱
                self.embedding_scale = float(quant[0][0]) if isinstance(quant[0], (np.ndarray, list)) else float(quant[0])
                self.embedding_zero_point = int(quant[1][0]) if isinstance(quant[1], (np.ndarray, list)) else int(quant[1])
                break
                
        if self.embedding_tensor_index is None:
            raise ValueError("YAMNet 모델 내부에서 1024차원 임베딩 텐서(shape: [1,1,1,1024])를 찾을 수 없습니다.")
        
        # 분류기 모델 로드
        self.classifier_interpreter = tflite.Interpreter(model_path=classifier_model_path, num_threads=1)
        self.classifier_interpreter.allocate_tensors()
        self.classifier_input_details = self.classifier_interpreter.get_input_details()
        self.classifier_output_details = self.classifier_interpreter.get_output_details()
        
        # 디바운싱 및 설정 정보
        self.consecutive_triggers = 0
        self.THRESHOLD = 0.6
        self.TARGET_API_URL = "http://127.0.0.1:8000/api/alert"
        
        # 모니터링 로그 출력용 YAMNet 클래스 맵 로드
        self.class_names = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                self.class_names.append(row[2])
                
        self.MIC_RATE = 48000
        self.YAMNET_RATE = 16000
        self.RECORD_SECONDS = 2
        
        # ⭐ 리눅스 내장 녹음기(arecord)에서 사용할 마이크 장치명 (card 2 이므로 plughw:2,0)
        # plughw를 쓰면 하드웨어 충돌을 리눅스가 알아서 다 막아줍니다.
        self.ALSA_DEVICE = "plughw:2,0"

    def run_forever(self):
        print(f"⏳ [디버그] PyAudio를 버리고 리눅스 내장 마이크로 우회 접속 시도 중...")
        
        # 1. Linux 기본 녹음 프로그램(arecord)을 백그라운드로 실행
        record_cmd = [
            "arecord",
            "-D", self.ALSA_DEVICE,
            "-c", "1",                # 1채널 (모노)
            "-r", str(self.MIC_RATE), # 48000Hz
            "-f", "S16_LE",           # 16bit 포맷
            "-t", "raw"               # 순수 음성 데이터만 추출
        ]
        
        try:
            # 파이썬에서 arecord를 켜고, 그 데이터가 나오는 파이프를 파이썬과 연결
            process = subprocess.Popen(record_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"❌ 마이크 실행 실패: {e}")
            return
            
        print("🎙️ [AI 탐지기] 실시간 소리 감시 시스템 가동 중... (종료하려면 Ctrl+C)")
        
        # 2초 동안 쌓일 데이터의 크기 (48000Hz * 2초 * 2바이트)
        bytes_to_read = int(self.MIC_RATE * self.RECORD_SECONDS * 2)
        
        try:
            while True:
                # 2. 안전하게 뚫어둔 파이프를 통해 2초치 데이터를 한 번에 가져옴
                raw_data = process.stdout.read(bytes_to_read)
                
                if not raw_data or len(raw_data) < bytes_to_read:
                    continue

                # 3. 바이트 데이터를 numpy 배열로 변환
                audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # 4. Numpy 선형 보간법으로 안전하게 리샘플링 (48000 -> 16000)
                duration = self.RECORD_SECONDS
                new_num_samples = int(duration * self.YAMNET_RATE)
                old_time = np.linspace(0, duration, len(audio_data))
                new_time = np.linspace(0, duration, new_num_samples)
                resampled_data = np.interp(new_time, old_time, audio_data).astype(np.float32)
                
                # 5. 배열 크기 딱 맞추기
                expected_size = np.prod(self.input_details[0]['shape'])
                if len(resampled_data) >= expected_size:
                    input_data = resampled_data[:expected_size]
                else:
                    input_data = np.pad(resampled_data, (0, expected_size - len(resampled_data)))
                    
                input_data = np.reshape(input_data, self.input_details[0]['shape'])
                
                # 6. YAMNet AI 모델 추론 (피처 추출기 역할)
                self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
                self.interpreter.invoke()
                scores = self.interpreter.get_tensor(self.output_details[0]['index'])
                
                # 1024차원 양자화 임베딩 추출 및 역양자화 (float32 변환)
                raw_emb = self.interpreter.get_tensor(self.embedding_tensor_index) # [1, 1, 1, 1024]
                float_emb = (raw_emb.astype(np.float32) - self.embedding_zero_point) * self.embedding_scale
                float_emb = np.reshape(float_emb, (1024,))
                
                # 모니터링/참고용 Top 클래스 확인
                mean_scores = np.mean(scores, axis=0)
                top_idx = np.argmax(mean_scores)
                class_name = self.class_names[top_idx]
                yamnet_confidence = float(mean_scores[top_idx])
                
                # 7. 커스텀 분류기로 낙상 예측 수행 (1프레임 단위 실시간 예측)
                classifier_input = np.expand_dims(float_emb, axis=0).astype(np.float32) # [1, 1024]
                self.classifier_interpreter.set_tensor(self.classifier_input_details[0]['index'], classifier_input)
                self.classifier_interpreter.invoke()
                classifier_output = self.classifier_interpreter.get_tensor(self.classifier_output_details[0]['index'])
                
                confidence = float(classifier_output[0][0])
                
                # 8. 디바운싱 로직 (연속 2회 임계값 이상인 경우 최종 낙상 판정)
                if confidence >= self.THRESHOLD:
                    self.consecutive_triggers += 1
                else:
                    self.consecutive_triggers = 0
                    
                if self.consecutive_triggers >= 2:
                    print(f"🚨 [위험 감지] 최종 위험 상황 포착! 낙상 확률: {confidence * 100:.1f}% (소리 경향: {class_name})")
                    alert_payload = {
                        "timestamp": datetime.now().isoformat(),
                        "sound_type": "Fall", # 낙상/위험 감지
                        "confidence": confidence
                    }
                    try:
                        response = requests.post(self.TARGET_API_URL, json=alert_payload)
                        print(f"📡 [백엔드 전송 성공] 서버 응답: {response.status_code}")
                    except Exception as e:
                        print(f"❌ [백엔드 전송 실패] 서버가 꺼져있거나 주소가 잘못됨")
                else:
                    status_str = f"주의 (누적 1회)" if self.consecutive_triggers == 1 else "안전함"
                    print(f". (현재 {status_str} - 낙상 확률: {confidence * 100:.1f}%, 소리: {class_name} {yamnet_confidence * 100:.1f}%)")

        except KeyboardInterrupt:
            print("\n👋 시스템을 안전하게 종료합니다.")
        finally:
            process.terminate()

if __name__ == "__main__":
    detector = YamnetAudioDetector()
    detector.run_forever()
