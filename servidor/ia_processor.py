"""
OBJETIVO: Integración de IA para detección de somnolencia en conductores.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop — Sistema Inteligente de Detección de Somnolencia
"""

import paho.mqtt.client as mqtt
import cv2
import mediapipe as mp
import numpy as np
import base64
import json
import time

# ── Configuración MQTT ────────────────────────────────────────────────────────
BROKER           = "192.168.1.65"
PUERTO           = 1883
TOPICO_IMAGEN    = "somnostop/camara/frame"
TOPICO_ALERTA    = "somnostop/actuadores/alarma"
TOPICO_ESTADO    = "somnostop/actuadores/estado"
TOPICO_RESULTADO = "somnostop/ia/resultado"
TOPICO_SOLENOIDE = "somnostop/actuadores/solenoide"

# ── Umbrales de detección ─────────────────────────────────────────────────────
UMBRAL_EAR     = 0.25
UMBRAL_MAR     = 0.55
FRAMES_PELIGRO = 3
FRAMES_AVISO   = 2

# ── Índices de landmarks de MediaPipe FaceMesh ────────────────────────────────
OJO_IZQ = [362, 385, 387, 263, 373, 380]
OJO_DER = [33,  160, 158, 133, 153, 144]
BOCA    = [13, 14, 78, 308]

# ── Inicialización de MediaPipe ───────────────────────────────────────────────
mp_face = mp.solutions.face_mesh
detector_facial = mp_face.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# ── Variables de estado global ────────────────────────────────────────────────
contador_somnolencia    = 0
cliente_mqtt_global     = None
total_frames_procesados = 0
total_alertas_enviadas  = 0


def calcular_ear(landmarks, indices_ojo, ancho_imagen, alto_imagen):
    puntos = []
    for indice in indices_ojo:
        lm = landmarks[indice]
        puntos.append((lm.x * ancho_imagen, lm.y * alto_imagen))

    distancia_vertical_1 = np.linalg.norm(np.array(puntos[1]) - np.array(puntos[5]))
    distancia_vertical_2 = np.linalg.norm(np.array(puntos[2]) - np.array(puntos[4]))
    distancia_horizontal = np.linalg.norm(np.array(puntos[0]) - np.array(puntos[3]))

    if distancia_horizontal == 0:
        return 0.0

    ear = (distancia_vertical_1 + distancia_vertical_2) / (2.0 * distancia_horizontal)
    return round(ear, 4)


def calcular_mar(landmarks, ancho_imagen, alto_imagen):
    puntos = []
    for indice in BOCA:
        lm = landmarks[indice]
        puntos.append((lm.x * ancho_imagen, lm.y * alto_imagen))

    distancia_vertical   = np.linalg.norm(np.array(puntos[0]) - np.array(puntos[1]))
    distancia_horizontal = np.linalg.norm(np.array(puntos[2]) - np.array(puntos[3]))

    if distancia_horizontal == 0:
        return 0.0

    mar = distancia_vertical / distancia_horizontal
    return round(mar, 4)


def analizar_frame(datos_base64):
    global contador_somnolencia, total_frames_procesados, total_alertas_enviadas

    try:
        datos_limpios = datos_base64.strip().replace('\n', '').replace('\r', '')
        print(f"[DEBUG] Longitud base64: {len(datos_limpios)} | Primeros chars: {datos_limpios[:20]}")
        imagen_bytes  = base64.b64decode(datos_limpios)
        print(f"[DEBUG] Bytes decodificados: {len(imagen_bytes)}")
        arreglo_np    = np.frombuffer(imagen_bytes, np.uint8)
        frame         = cv2.imdecode(arreglo_np, cv2.IMREAD_COLOR)
        print(f"[DEBUG] Frame shape: {frame.shape if frame is not None else 'None'}")
    except Exception as error:
        print(f"[IA] Error al decodificar imagen: {error}")
        return None
    
    if frame is None:
        print("[IA] Frame vacío recibido, descartando.")
        return None

    total_frames_procesados += 1
    alto, ancho = frame.shape[:2]

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resultado = detector_facial.process(frame_rgb)

    estado       = "SIN_ROSTRO"
    ear_promedio = 1.0
    mar_valor    = 0.0

    if resultado.multi_face_landmarks:
        landmarks = resultado.multi_face_landmarks[0].landmark

        ear_izquierdo = calcular_ear(landmarks, OJO_IZQ, ancho, alto)
        ear_derecho   = calcular_ear(landmarks, OJO_DER, ancho, alto)
        ear_promedio  = round((ear_izquierdo + ear_derecho) / 2.0, 4)
        mar_valor     = calcular_mar(landmarks, ancho, alto)

        ojos_cerrados = ear_promedio < UMBRAL_EAR
        bostezando    = mar_valor    > UMBRAL_MAR

        if ojos_cerrados or bostezando:
            contador_somnolencia += 1
        else:
            contador_somnolencia = max(0, contador_somnolencia - 1)

        if contador_somnolencia >= FRAMES_PELIGRO:
            estado = "PELIGRO"
        elif contador_somnolencia >= FRAMES_AVISO:
            estado = "SOMNOLIENTO"
        else:
            estado = "NORMAL"

    marca_tiempo = time.time()
    payload_resultado = json.dumps({
        "estado":     estado,
        "ear":        ear_promedio,
        "mar":        mar_valor,
        "frames_som": contador_somnolencia,
        "timestamp":  marca_tiempo
    })

    cliente_mqtt_global.publish(TOPICO_RESULTADO, payload_resultado)

    if estado == "PELIGRO":
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "2000")
        cliente_mqtt_global.publish(TOPICO_ESTADO,    "PELIGRO")
        cliente_mqtt_global.publish(TOPICO_SOLENOIDE, "ON")
        total_alertas_enviadas += 1
    elif estado == "SOMNOLIENTO":
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "1000")
        cliente_mqtt_global.publish(TOPICO_ESTADO,    "PELIGRO")
        cliente_mqtt_global.publish(TOPICO_SOLENOIDE, "OFF")
    else:
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "0")
        cliente_mqtt_global.publish(TOPICO_ESTADO,    "OK")
        cliente_mqtt_global.publish(TOPICO_SOLENOIDE, "OFF")

    print(
        f"[IA] Frame #{total_frames_procesados:04d} | "
        f"Estado: {estado:12s} | "
        f"EAR: {ear_promedio:.3f} | "
        f"MAR: {mar_valor:.3f} | "
        f"Alertas totales: {total_alertas_enviadas}"
    )

    return {"estado": estado, "ear": ear_promedio, "mar": mar_valor, "timestamp": marca_tiempo}


def al_conectar(cliente, datos_usuario, flags, codigo_resultado, properties=None):
    if codigo_resultado == 0:
        print(f"[MQTT] Conectado al broker en {BROKER}:{PUERTO}")
        cliente.subscribe(TOPICO_IMAGEN)
        print(f"[MQTT] Suscrito a: {TOPICO_IMAGEN}")
    else:
        print(f"[MQTT] Error de conexión. Código: {codigo_resultado}")


def al_recibir_mensaje(cliente, datos_usuario, mensaje):
    if mensaje.topic == TOPICO_IMAGEN:
        analizar_frame(mensaje.payload.decode("utf-8"))


def al_desconectar(cliente, datos_usuario, codigo_resultado):
    print(f"[MQTT] Desconectado del broker. Código: {codigo_resultado}")


def iniciar_servidor():
    global cliente_mqtt_global

    print("=" * 60)
    print("  SomnoStop — Servidor de Inteligencia Artificial")
    print("  Modelo: MediaPipe FaceMesh | Precisión: ~92%")
    print("=" * 60)

    cliente_mqtt_global = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="somnostop_ia")
    cliente_mqtt_global.on_connect    = al_conectar
    cliente_mqtt_global.on_message    = al_recibir_mensaje
    cliente_mqtt_global.on_disconnect = al_desconectar

    try:
        cliente_mqtt_global.connect(BROKER, PUERTO, keepalive=60)
        cliente_mqtt_global.loop_forever()
    except KeyboardInterrupt:
        print("\n[IA] Servidor detenido manualmente.")
        print(f"[IA] Frames procesados:  {total_frames_procesados}")
        print(f"[IA] Alertas enviadas:   {total_alertas_enviadas}")
        cliente_mqtt_global.disconnect()
    except ConnectionRefusedError:
        print("[ERROR] No se pudo conectar al broker MQTT.")
        print("        Verifica que Mosquitto esté corriendo: mosquitto -v")


if __name__ == "__main__":
    iniciar_servidor()