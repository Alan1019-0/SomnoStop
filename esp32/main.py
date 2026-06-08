"""
OBJETIVO: Gestionar telemetría de sensores y control de actuadores mediante MQTT.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop
"""

import time
import ujson
import network
from umqtt.simple import MQTTClient
from dispositivos import SensorBox, ActuatorBox

WIFI_SSID = "INFINITUM7045_2.4"
WIFI_PASS = "xGsuu62FVD"
BROKER_MQTT = "192.168.1.73"
CLIENTE_ID = "ESP32_SomnoStop_EquipoMT"

sensores = SensorBox()
actuadores = ActuatorBox()

def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        print("Esperando conexión...")
        time.sleep(1)
    print("Conectado:", wlan.ifconfig())

def procesar_mensaje(topic, msg):
    tema = topic.decode()
    comando = msg.decode()
    if "solenoide" in tema:
        actuadores.activar_alerta_fisica(True if comando == "ON" else False)
    elif "estado" in tema:
        actuadores.gestionar_indicadores(comando)
    elif "alarma" in tema:
        actuadores.sonar_alarma(int(comando))

conectar_wifi()
cliente = MQTTClient(CLIENTE_ID, BROKER_MQTT)
cliente.set_callback(procesar_mensaje)
cliente.connect()
cliente.subscribe("somnostop/actuadores/#")

while True:
    try:
        datos = sensores.obtener_resumen_sensores()
        cliente.publish("somnostop/sensores/datos", ujson.dumps(datos))
        cliente.check_msg()
        time.sleep(1)
    except Exception as e:
        print("Error de conexión:", e)
        time.sleep(5)
        cliente.connect()