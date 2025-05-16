import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
import time
import json

LED_PIN = 26
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

mqtt_broker = "localhost"
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

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_broker, mqtt_port, 60)
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