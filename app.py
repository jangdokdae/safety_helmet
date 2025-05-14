from mpu6050 import mpu6050
import RPi.GPIO as GPIO
import time
from flask import Flask, jsonify, render_template
import gps
import threading
from pulsesensor import Pulsesensor
import paho.mqtt.client as mqtt
import json

# Flask 애플리케이션 생성
app = Flask(__name__)

# MQTT 설정
mqtt_broker = "localhost"  # 필요시 브로커 주소 변경
mqtt_port = 1883
mqtt_topic = "iot/sensor/data"

sensor_data_mqtt = {}  # 수신한 MQTT 데이터를 저장

# GPIO 핀 설정
led_on = 26
GPIO.setmode(GPIO.BCM)
GPIO.setup(led_on, GPIO.OUT)

# 센서 초기화
sensor = mpu6050(0x68)
p = Pulsesensor()
p.startAsyncBPM()

# 초기 값 설정
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


# MQTT 콜백 함수 정의
def on_connect(client, userdata, flags, rc):
    print("MQTT 연결됨:", rc)
    client.subscribe(mqtt_topic)

def on_message(client, userdata, msg):
    global sensor_data_mqtt
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        sensor_data_mqtt = data  # 웹 페이지에 보여줄 데이터 저장

        # MQTT 메시지에 "command" 필드가 있을 경우 처리
        if 'command' in data:
            command = data['command']
            if command == 'led_on':
                GPIO.output(led_on, GPIO.HIGH)
                print("LED 켜짐 (MQTT 명령)")
            elif command == 'led_off':
                GPIO.output(led_on, GPIO.LOW)
                print("LED 꺼짐 (MQTT 명령)")
            else:
                print(f"알 수 없는 명령: {command}")

    except Exception as e:
        print("MQTT 메시지 오류:", e)


# MQTT 클라이언트 설정 및 시작
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(mqtt_broker, mqtt_port, 60)
mqtt_client.loop_start()


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

        if momentary_acceleration >= 9 and z_delta >= 9:
            GPIO.output(led_on, GPIO.HIGH)
            danger_active = True
        elif not danger_active:
            GPIO.output(led_on, GPIO.LOW)

        # MQTT로 데이터 퍼블리시
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
        print("가속도 센서 오류:", e)
        connection_lost = True
        x_acceleration = y_acceleration = z_acceleration = 0.0
        momentary_acceleration = 0.0
        danger_active = False


def get_heart_rate():
    global heart_rate
    try:
        while True:
            bpm = p.BPM
            if bpm >= 0:
                heart_rate = bpm
            else:
                print("No Heartbeat")
            time.sleep(1)
    except Exception as e:
        print("심박수 오류:", e)
        p.stopAsyncBPM()


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


# 스레드 시작
gps_thread = threading.Thread(target=get_gps_data)
gps_thread.daemon = True
gps_thread.start()

heart_rate_thread = threading.Thread(target=get_heart_rate)
heart_rate_thread.daemon = True
heart_rate_thread.start()

# Flask 라우트 정의
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
    GPIO.output(led_on, GPIO.LOW)
    return jsonify({'status': 'reset'})


# 메인 실행
if __name__ == '__main__':
    try:
        # 주기적으로 센서 데이터 읽기 (별도 스레드)
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
