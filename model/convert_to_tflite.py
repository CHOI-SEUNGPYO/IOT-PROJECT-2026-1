import os
import tensorflow as tf

current_dir = os.path.dirname(os.path.abspath(__file__))
h5_path = os.path.join(current_dir, "fall_lstm_model.h5")
tflite_path = os.path.join(current_dir, "fall_lstm_model.tflite")

try:
    print("[INFO] Loading Keras model...")
    model = tf.keras.models.load_model(h5_path)
    model.summary()

    print("[INFO] Rebuilding model with LSTM unrolled=True...")
    # 모델 설정을 변경하여 LSTM 레이어를 unroll 시킴 (Flex ops 방지)
    config = model.get_config()
    
    # Sequential 모델일 경우 레이어 리스트를 돌며 LSTM을 찾아 unroll=True 설정
    if 'layers' in config:
        for layer in config['layers']:
            # config['layers'] 구조에 따라 처리
            layer_config = layer.get('config', {})
            if layer.get('class_name') == 'LSTM' or 'lstm' in layer.get('config', {}).get('name', '').lower():
                layer_config['unroll'] = True
                print(f"  -> Set unroll=True for layer: {layer_config.get('name')}")
    
    # 변경된 config로 새 모델 생성 및 가중치 복사
    unrolled_model = tf.keras.models.Sequential.from_config(config)
    unrolled_model.build(input_shape=(None, 6, 1024))
    unrolled_model.set_weights(model.get_weights())
    unrolled_model.summary()

    print("[INFO] Converting to TFLite (Standard Builtins only)...")
    converter = tf.lite.TFLiteConverter.from_keras_model(unrolled_model)
    
    # Flex ops (SELECT_TF_OPS) 제외하고 순수 TFLite BUILTINS만 타겟팅
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
    
    tflite_model = converter.convert()

    print(f"[INFO] Saving TFLite model to: {tflite_path}")
    with open(tflite_path, "wb") as f:
        f.write(tflite_model)

    print("[SUCCESS] Conversion completed successfully!")

except Exception as e:
    print(f"[ERROR] Error during conversion: {e}")
