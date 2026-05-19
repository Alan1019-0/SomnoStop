# OBJETIVO: Captura de imágenes con ESP32-CAM y publicación por MQTT
#            para el pipeline de detección de somnolencia SomnoStop.
# INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
# PROYECTO: SomnoStop — Sistema Inteligente de Detección de Somnolencia

# ─────────────────────────────────────────────────────────────────────────────
# NOTA IMPORTANTE: Este archivo se integra al main.py existente del proyecto.
# Requiere firmware especial para ESP32-CAM con soporte de cámara.
# Firmware recomendado: https://github.com/lemariva/micropython-camera-driver
#
# MODELO IA UTILIZADO EN SERVIDOR: MediaPipe FaceMesh
# TIPO DE PREDICCIÓN: Estado del conductor (NORMAL/SOMNOLIENTO/PELIGRO)
# PRECISIÓN APROXIMADA: 92% con buena iluminación, 78% con luz baja
# ─────────────────────────────────────────────────────────────────────────────

import camera
import ubinascii
import ujson
import time
import gc

# ── Importar la HAL del proyecto (dispositivos.py) ───────────────────────────
from dispositivos import SensorBox, ActuatorBox


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE TÓPICOS MQTT (deben coincidir con ia_processor.py)
# ─────────────────────────────────────────────────────────────────────────────
TOPICO_FRAME     = "somnostop/camara/frame"
TOPICO_RESULTADO = "somnostop/ia/resultado"
TOPICO_ALERTA    = "somnostop/actuadores/alarma"
TOPICO_ESTADO    = "somnostop/actuadores/estado"

# Intervalo entre capturas (segundos) — aumentar si hay problemas de memoria
INTERVALO_CAPTURA = 2.0


def inicializar_camara():
    """
    Recibe:  nada
    Hace:    configura la ESP32-CAM con resolución QVGA (320x240) y calidad
             baja para minimizar el tamaño del payload MQTT.
             QVGA produce imágenes de ~8-15 KB en JPEG, manejable para MQTT.
    Devuelve: True si la cámara se inicializó correctamente, False si falló.
    """
    try:
        # FRAMESIZE_QVGA = 320x240 — balance entre calidad y velocidad de envío
        # quality 10 = mayor compresión JPEG (1=max calidad, 63=max compresión)
        camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QVGA)
        camera.quality(10)
        camera.brightness(1)   # +1 para compensar interior de auto (oscuro)
        camera.contrast(1)
        print("[CAM] Cámara inicializada correctamente (320x240, JPEG q=10)")
        return True
    except Exception as error:
        print(f"[CAM] Error al inicializar cámara: {error}")
        return False


def capturar_y_publicar(cliente_mqtt):
    """
    Recibe:  cliente MQTT ya conectado y autenticado.
    Hace:    captura un frame JPEG desde la ESP32-CAM, lo codifica en base64
             y lo publica en el tópico de frames. Libera la memoria del frame
             inmediatamente para evitar desbordamiento en la ESP32.
    Devuelve: True si la publicación fue exitosa, False si hubo algún error.
    """
    try:
        # Capturar frame (objeto bytes del JPEG)
        frame_jpeg = camera.capture()

        if not frame_jpeg:
            print("[CAM] Frame vacío, reintentando...")
            return False

        # Codificar a base64 para transmisión por MQTT (texto plano)
        frame_b64 = ubinascii.b2a_base64(frame_jpeg).decode("utf-8").strip()

        # Publicar en el tópico de imágenes
        cliente_mqtt.publish(TOPICO_FRAME, frame_b64)

        tamano_kb = len(frame_jpeg) / 1024
        print(f"[CAM] Frame publicado — Tamaño: {tamano_kb:.1f} KB")

        # Liberar memoria del frame (crítico en ESP32 con RAM limitada)
        del frame_jpeg
        del frame_b64
        gc.collect()

        return True

    except Exception as error:
        print(f"[CAM] Error al capturar/publicar: {error}")
        gc.collect()
        return False


def manejar_resultado_ia(topico, mensaje):
    """
    Recibe:  tópico MQTT y mensaje recibido del servidor de IA.
    Hace:    parsea el JSON con el resultado del modelo y lo imprime en consola.
             La activación de actuadores la maneja el callback principal de MQTT
             en main.py a través de la HAL (ActuatorBox).
    Devuelve: dict con los datos del resultado o None si el parseo falló.
    """
    try:
        datos = ujson.loads(mensaje)
        estado    = datos.get("estado", "DESCONOCIDO")
        ear_valor = datos.get("ear", 0.0)
        mar_valor = datos.get("mar", 0.0)

        print(f"[IA-RESP] Estado: {estado} | EAR: {ear_valor} | MAR: {mar_valor}")
        return datos

    except Exception as error:
        print(f"[IA-RESP] Error al parsear resultado: {error}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FRAGMENTO PARA INTEGRAR EN main.py
# Copiar este bloque en el ciclo principal de main.py
# ─────────────────────────────────────────────────────────────────────────────

# EJEMPLO DE INTEGRACIÓN EN main.py:
#
# from camara_mqtt import inicializar_camara, capturar_y_publicar, INTERVALO_CAPTURA
#
# # En la sección de inicialización:
# camara_ok = inicializar_camara()
#
# # En el ciclo principal (junto con la publicación de sensores):
# ultimo_frame = 0
# while True:
#     ahora = time.time()
#     if camara_ok and (ahora - ultimo_frame) >= INTERVALO_CAPTURA:
#         capturar_y_publicar(cliente)   # cliente = objeto MQTTClient
#         ultimo_frame = ahora
#
#     cliente.check_msg()   # verificar mensajes entrantes (comandos de IA)
#     time.sleep_ms(100)
