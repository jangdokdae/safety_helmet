import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
import time
import json

LED_PIN = 26
BUTTON_PIN = 3      # 버튼 연결 GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
# 버튼은 풀업(pull-up)으로, 누르면 GND에 연결되었다고 가정
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

mqtt_broker = "192.168.137.98"
mqtt_port = 1883
mqtt_topic = "iot/sensor/data"

def on_connect(client, userdata, flags, rc):
    print("MQTT connected:", rc)
    client.subscribe(mqtt_topic)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        if 'command' in data:
            command = data['command']
            if command == 'led_on':
                GPIO.output(LED_PIN, GPIO.HIGH)
                print("LED ON (from MQTT)")
            elif command == 'led_off':
                GPIO.output(LED_PIN, GPIO.LOW)
                print("LED OFF (from MQTT)")
    except Exception as e:
        print("Error handling MQTT message:", e)

# 버튼 눌림 이벤트 콜백
def button_pressed(channel):
    print("Button pressed! Publishing led_off command...")
    # 로컬 LED 끄기
    GPIO.output(LED_PIN, GPIO.LOW)
    # MQTT로도 발행
    payload = json.dumps({'command': 'led_off'})
    
    client.publish(mqtt_topic, payload)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_broker, mqtt_port, 60)

# 버튼 이벤트 감지 설정 (떨림 방지 200ms)
GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING,
                      callback=button_pressed, bouncetime=200)

client.loop_start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Program interrupted")
finally:
    client.loop_stop()
    client.disconnect()
    GPIO.cleanup()
