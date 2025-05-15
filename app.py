from mpu6050 import mpu6050
import RPi.GPIO as GPIO
import time
from flask import Flask, jsonify, render_template, request
import gps
import threading
from pulsesensor import Pulsesensor
import mysql.connector

# Flask 애플리케이션 생성
app = Flask(__name__)

# MPU6050 가속도 센서 객체 생성
sensor = mpu6050(0x68)

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
z_delta = 0.0  
danger_active = False  
heart_rate = 0
latitude = 0
longitude = 0 

db_config = {
    'host': '192.168.137.202',
    'user': 'pi',
    'password': 'raspberrypi',
    'database': 'sensor_data'
}

def save_danger_to_database():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = """
        INSERT INTO danger_logs 
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


def save_summary_to_database():
    try:
        avg_accel = round(sum(acceleration_history) / len(acceleration_history), 3)
        max_accel = max(acceleration_history)
        avg_heart = heart_rate
        sample_count = len(acceleration_history)

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = """
        INSERT INTO summary_logs 
        (danger_active, avg_accel, max_accel, avg_heart_rate, sample_count)
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            danger_active,
            avg_accel,
            max_accel,
            avg_heart,
            sample_count
        ))
        conn.commit()
        cursor.close()
        conn.close()
        print("📊 요약 데이터 저장 완료")
    except Exception as e:
        print(f"❌ 요약 데이터 저장 실패: {e}")


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
            danger_active = True 
        elif(danger_active == False):
            GPIO.output(led_on, GPIO.LOW)
            print("LED 꺼짐")

    except Exception as e:
        print(f"Error reading acceleration data: {e}")
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
            print(report)

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

def save_danger_periodically():
    while True:
        read_acceleration_data()
        if danger_active:
            save_danger_to_database()
        time.sleep(1)  # 1초 간격

danger_thread = threading.Thread(target=save_danger_periodically)
danger_thread.daemon = True
danger_thread.start()

def save_summary_periodically():
    while True:
        if len(acceleration_history) >= 10:
            save_summary_to_database()
        time.sleep(10)

summary_thread = threading.Thread(target=save_summary_periodically)
summary_thread.daemon = True
summary_thread.start()

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
        save_danger_to_database()
    
    data = {
        'x_acceleration': x_acceleration,
        'y_acceleration': y_acceleration,
        'z_acceleration': z_acceleration,
        'z_delta': z_delta,
        'momentary_acceleration': momentary_acceleration,
        'danger_active': danger_active,
        'heart_rate': heart_rate,
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

@app.route('/danger_logs_by_date')
def danger_logs_by_date():
    date = request.args.get('date')  # YYYY-MM-DD 형식
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, x_accel, y_accel, z_accel, momentary_accel, heart_rate, danger_active 
        FROM danger_logs
        WHERE DATE(timestamp) = %s
        ORDER BY timestamp DESC
        LIMIT 50
    """, (date,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('danger_logs.html', logs=rows, selected_date=date)

@app.route('/summary_logs_by_date')
def summary_logs_by_date():
    date = request.args.get('date')
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, danger_active, avg_accel, max_accel, avg_heart_rate, sample_count
        FROM summary_logs
        WHERE DATE(timestamp) = %s
        ORDER BY timestamp DESC
        LIMIT 50
    """, (date,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('summary_logs.html', logs=rows, selected_date=date)

@app.route('/summary_logs')
def summary_logs_page():
    return render_template('summary_logs.html', logs=[], selected_date=None)

@app.route('/danger_logs')
def danger_logs_page():
    return render_template('danger_logs.html', logs=[], selected_date=None)

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=8000)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()