from mpu6050 import mpu6050
import RPi.GPIO as GPIO
import time
from flask import Flask, jsonify, render_template
import gps
import threading
from pulsesensor import Pulsesensor
import time
import mysql.connector

# Flask 애플리케이션 생성
app = Flask(__name__)

# MPU6050 가속도 센서 객체 생성
sensor = mpu6050(0x68)

# GPIO 핀 번호 설정
led_on = 26
# GPIO 핀 모드 설정
GPIO.setmode(GPIO.BCM)
GPIO.setup(led_on, GPIO.OUT)

p = Pulsesensor()
p.startAsyncBPM()
connection_lost = False
x_acceleration = 0.0
y_acceleration = 0.0
z_acceleration = 0.0
x_acceleration_prev = 0.0
y_acceleration_prev = 0.0
z_acceleration_prev = 0.0
momentary_acceleration = 0.0
acceleration_history = []
z_delta = 0.0  # z_delta 변수 초기화
danger_active = False  # 위험 상태를 추적하는 변수
heart_rate = 0  # 심박수 변수 초기화
latitude = 0
longitude = 0  # GPS 데이터 변수 초기화

def save_to_database():
    try:
        conn = mysql.connector.connect(
            host='192.168.137.202',   # 또는 localhost
            user='pi',               # 사용자 계정
            password='rapsberrypi',
            database='sensor_data'
        )
        cursor = conn.cursor()
        query = """
        INSERT INTO acceleration_logs 
        (x_accel, y_accel, z_accel, z_delta, momentary_accel, heart_rate, danger_active, latitude, longitude)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            x_acceleration,
            y_acceleration,
            z_acceleration,
            z_delta,
            momentary_acceleration,
            heart_rate,
            danger_active,
            latitude if latitude != 0.0 else None,
            longitude if longitude != 0.0 else None
        ))
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ 데이터 저장 완료")
    except Exception as e:
        print(f"❌ 데이터 저장 실패: {e}")


def read_acceleration_data():
    global sensor, connection_lost, x_acceleration, y_acceleration, z_acceleration, z_delta
    global x_acceleration_prev, y_acceleration_prev, z_acceleration_prev
    global momentary_acceleration, acceleration_history, danger_active

    try:
        if connection_lost:
            # 연결이 끊겼을 때는 초기화 후
            sensor = mpu6050(0x68)
            connection_lost = False  # 재연결 성공 시 플래그 리셋
        # 가속도 센서에서 데이터 읽기
        accelerometer_data = sensor.get_accel_data()
        x_acceleration = round(accelerometer_data['x'], 3)
        y_acceleration = round(accelerometer_data['y'], 3)
        z_acceleration = round(accelerometer_data['z'], 3)

        # 순간 가속도 계산
        x_delta = x_acceleration - x_acceleration_prev
        y_delta = y_acceleration - y_acceleration_prev
        z_delta = abs(z_acceleration - z_acceleration_prev)
        print("x 가속도: %d" % x_acceleration)
        print("y 가속도: %d" % y_acceleration)
        print("z 가속도: %d" % z_acceleration)
        
        momentary_acceleration = round((x_delta**2 + y_delta**2 + z_delta**2)**0.5, 3)
        print("순간 가속도: %d" % momentary_acceleration)
        
        # 이전 가속도 값을 현재 값으로 업데이트
        x_acceleration_prev = x_acceleration
        y_acceleration_prev = y_acceleration
        z_acceleration_prev = z_acceleration

        # 순간 가속도 저장 (최대 100개의 데이터만 저장)
        acceleration_history.append(momentary_acceleration)
        if len(acceleration_history) > 100:
            acceleration_history.pop(0)

        if (momentary_acceleration >= 9 and z_delta >= 9):
            GPIO.output(led_on, GPIO.HIGH)
            print("LED 켜짐")
            danger_active = True  # 위험 상태 활성화
        elif(danger_active == False):
            GPIO.output(led_on, GPIO.LOW)
            print("LED 꺼짐")

    except Exception as e:
        print(f"Error reading acceleration data: {e}")
        # 연결이 끊겼거나 오류가 발생한 경우에는 다시 연결 시도
        connection_lost = True
        x_acceleration = y_acceleration = z_acceleration = 0.0
        momentary_acceleration = 0.0
        danger_active = False  # 위험 상태 비활성화



def get_heart_rate():
    global heart_rate

    try:
        while True:
            bpm = p.BPM
            if bpm >= 0:
                heart_rate = bpm
                print("BPM: %d" % bpm)
            else:
                print("No Heartbeat found")
            time.sleep(1)
    except Exception as e:
        print(f"Error reading heart rate: {e}")
        p.stopAsyncBPM()


def get_gps_data():
    global latitude, longitude
    session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)

    try:
        while True:
            report = session.next()
            print(report)  # 전체 report 출력

            if getattr(report, 'class', None) == 'TPV':
                lat = getattr(report, 'lat', 0.0)
                lon = getattr(report, 'lon', 0.0)

                if lat != 0.0 and lon != 0.0:
                    latitude = lat
                    longitude = lon
                    print(f"Latitude: {latitude}, Longitude: {longitude}")

            time.sleep(1)
    except Exception as e:
        print(f"Error in GPS loop: {e}")


# GPS 데이터 수집을 위한 스레드 시작
gps_thread = threading.Thread(target=get_gps_data)
gps_thread.daemon = True
gps_thread.start()

heart_rate_thread = threading.Thread(target=get_heart_rate)
heart_rate_thread.daemon = True
heart_rate_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    read_acceleration_data()
    
    if danger_active:
        save_to_database()
    
    data = {
        'x_acceleration': x_acceleration,
        'y_acceleration': y_acceleration,
        'z_acceleration': z_acceleration,
        'z_delta': z_delta,
        'momentary_acceleration': momentary_acceleration,
        'danger_active': danger_active,  # 위험 상태 정보 추가
        'heart_rate': heart_rate,  # 심박수 정보 추가
        'latitude': latitude if latitude != 0.0 else None,
        'longitude': longitude if longitude != 0.0 else None
    }
    return jsonify(data)


@app.route('/reset')
def reset_danger():
    global danger_active
    danger_active = False
    GPIO.output(led_on, GPIO.LOW)
    return jsonify({'status': 'reset'})

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8000)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
