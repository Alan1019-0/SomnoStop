# OBJETIVO: Captura de imágenes con ESP32-CAM y publicación por MQTT
# INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
# PROYECTO: SomnoStop

import camera
import ubinascii
import time
import gc
import network
from umqtt.simple import MQTTClient

WIFI_SSID = "Alan`s iPhone"
WIFI_PASS = "luismiguapo1"
BROKER_MQTT = "172.20.10.4"
CLIENTE_ID = "ESP32CAM_SomnoStop"

TOPICO_FRAME     = "somnostop/camara/frame"
TOPICO_RESULTADO = "somnostop/ia/resultado"
INTERVALO_CAPTURA = 2.0

def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        print("Esperando conexión...")
        time.sleep(1)
    print("CAM conectada:", wlan.ifconfig())

def callback_vacio(topic, msg):
    pass

def inicializar_camara():
    try:
        cam = camera.Camera()
        cam.init()
        cam.reconfigure(frame_size=camera.FrameSize.QVGA, pixel_format=camera.PixelFormat.JPEG)
        print("[CAM] Cámara inicializada correctamente")
        return cam
    except Exception as error:
        print(f"[CAM] Error al inicializar cámara: {error}")
        return None
    
def capturar_y_publicar(cliente_mqtt, cam):
    try:
        frame_jpeg = cam.capture()
        if not frame_jpeg:
            print("[CAM] Frame vacío, reintentando...")
            return False
        frame_b64 = ubinascii.b2a_base64(frame_jpeg).decode("utf-8").strip()
        cliente_mqtt.publish(TOPICO_FRAME, frame_b64)
        print(f"[CAM] Frame publicado — {len(frame_jpeg)/1024:.1f} KB")
        del frame_jpeg
        del frame_b64
        gc.collect()
        return True
    except Exception as error:
        print(f"[CAM] Error: {error}")
        gc.collect()
        return False

# ── Main ──────────────────────────────────────────────────────────────────────
conectar_wifi()
cliente = MQTTClient(CLIENTE_ID, BROKER_MQTT)
cliente.set_callback(callback_vacio)
cliente.connect()
cliente.subscribe(TOPICO_RESULTADO)

cam = inicializar_camara()
ultimo_frame = 0

while True:
    try:
        ahora = time.time()
        if cam and (ahora - ultimo_frame) >= INTERVALO_CAPTURA:
            capturar_y_publicar(cliente, cam)
            ultimo_frame = ahora
        cliente.check_msg()
        time.sleep_ms(100)
    except Exception as e:
        print("Error:", e)
        time.sleep(5)
        cliente.connect()