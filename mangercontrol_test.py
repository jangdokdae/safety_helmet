from mpu6050 import mpu6050
import RPi.GPIO as GPIO
import time
from flask import Flask, jsonify, render_template
import gps
import threading
from pulsesensor import Pulsesensor
import paho.mqtt.client as mqtt
import json

# Flask 웹 서버 생성
app = Flask(__name__)

# MQTT 설정
mqtt_broker = "172.20.10.5"  # MQTT 브로커 IP
mqtt_port = 1883
mqtt_topic = "iot/sensor/data"

sensor_data_mqtt = {}  # MQTT 데이터 저장용

# GPIO 핀 설정
led_pin = 26
GPIO.setmode(GPIO.BCM)
GPIO.setup(led_pin, GPIO.OUT)

# 가속도 센서 초기화
sensor = mpu6050(0x68)

# 심박센서 초기화
p = Pulsesensor()
p.startAsyncBPM()

# 상태 변수 초기화
connection_lost = False
x_acceleration = y_acceleration = z_acceleration = 0.0
x_acceleration_prev = y_acceleration_prev = z_acceleration_prev = 0.0
momentary_acceleration = 0.0
acceleration_history = []
z_delta = 0.0
danger_active = False
heart_rate = 0
latitude = 0.0
longitude = 0.0

# MQTT 콜백 정의
def on_connect(client, userdata, flags, rc):
    print("MQTT 연결 결과 코드:", rc)
    client.subscribe(mqtt_topic)

def on_message(client, userdata, msg):
    global sensor_data_mqtt
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        sensor_data_mqtt = data  # 화면 갱신용 데이터 저장
        # 명령(command) 처리
        if 'command' in data:
            command = data['command']
            if command == 'led_on':
                GPIO.output(led_pin, GPIO.HIGH)
                print("LED ON (MQTT 수신)")
            elif command == 'led_off':
                GPIO.output(led_pin, GPIO.LOW)
                print("LED OFF (MQTT 수신)")
            else:
                print(f"알 수 없는 명령: {command}")
    except Exception as e:
        print("MQTT 메시지 처리 오류:", e)

# MQTT 클라이언트 설정
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(mqtt_broker, mqtt_port, 60)
mqtt_client.loop_start()

# 가속도 데이터 읽기 함수
def read_acceleration_data():
    global sensor, connection_lost
    global x_acceleration, y_acceleration, z_acceleration, z_delta
    global x_acceleration_prev, y_acceleration_prev, z_acceleration_prev
    global momentary_acceleration, acceleration_history, danger_active

    try:
        if connection_lost:
            sensor = mpu6050(0x68)
            connection_lost = False

        data = sensor.get_accel_data()
        x_acceleration = round(data['x'], 3)
        y_acceleration = round(data['y'], 3)
        z_acceleration = round(data['z'], 3)

        x_delta = x_acceleration - x_acceleration_prev
        y_delta = y_acceleration - y_acceleration_prev
        z_delta = abs(z_acceleration - z_acceleration_prev)

        momentary_acceleration = round((x_delta**2 + y_delta**2 + z_delta**2)**0.5, 3)

        x_acceleration_prev = x_acceleration
        y_acceleration_prev = y_acceleration
        z_acceleration_prev = z_acceleration

        acceleration_history.append(momentary_acceleration)
        if len(acceleration_history) > 100:
            acceleration_history.pop(0)

        # 낙하 감지 시 LED 및 MQTT 명령 전송
        if momentary_acceleration >= 9 and z_delta >= 9:
            GPIO.output(led_pin, GPIO.HIGH)
            danger_active = True
            mqtt_client.publish(mqtt_topic, json.dumps({'command': 'led_on'}))
        elif not danger_active:
            GPIO.output(led_pin, GPIO.LOW)
            mqtt_client.publish(mqtt_topic, json.dumps({'command': 'led_off'}))

        # 센서 데이터 전송
        payload = json.dumps({
            'x_acceleration': x_acceleration,
            'y_acceleration': y_acceleration,
            'z_acceleration': z_acceleration,
            'z_delta': z_delta,
            'momentary_acceleration': momentary_acceleration,
            'danger_active': danger_active,
            'heart_rate': heart_rate,
            'latitude': latitude,
            'longitude': longitude
        })
        mqtt_client.publish(mqtt_topic, payload)

    except Exception as e:
        print("센서 읽기 오류:", e)
        connection_lost = True
        x_acceleration = y_acceleration = z_acceleration = 0.0
        momentary_acceleration = 0.0
        danger_active = False

# 심박수 읽기 함수
def get_heart_rate():
    global heart_rate
    try:
        while True:
            bpm = p.BPM
            if bpm >= 0:
                heart_rate = bpm
            else:
                print("심박수 없음")
            time.sleep(1)
    except Exception as e:
        print("심박수 센서 오류:", e)
        p.stopAsyncBPM()

# GPS 데이터 읽기 함수
def get_gps_data():
    global latitude, longitude
    session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
    try:
        while True:
            report = session.next()
            if report['class'] == 'TPV':
                latitude = getattr(report, 'lat', 0.0)
                longitude = getattr(report, 'lon', 0.0)
            time.sleep(1)
    except Exception as e:
        print("GPS 오류:", e)

# 스레드로 센서 루프 및 데이터 수집 시작
gps_thread = threading.Thread(target=get_gps_data)
gps_thread.daemon = True
gps_thread.start()

heart_rate_thread = threading.Thread(target=get_heart_rate)
heart_rate_thread.daemon = True
heart_rate_thread.start()

# Flask 라우팅 설정
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    return jsonify(sensor_data_mqtt)

@app.route('/reset')
def reset_danger():
    global danger_active
    danger_active = False
    GPIO.output(led_pin, GPIO.LOW)
    mqtt_client.publish(mqtt_topic, json.dumps({'command': 'led_off'}))
    return jsonify({'status': 'reset'})

# 메인 실행부
if __name__ == '__main__':
    try:
        def sensor_loop():
            while True:
                read_acceleration_data()
                time.sleep(1)

        sensor_thread = threading.Thread(target=sensor_loop)
        sensor_thread.daemon = True
        sensor_thread.start()

        app.run(host='0.0.0.0', port=8000)

    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
