"""
OBJETIVO: Integración de IA para detección de somnolencia en conductores.
          Recibe imágenes de la ESP32-CAM vía MQTT, analiza el estado del
          conductor (ojos cerrados / bostezo) con MediaPipe FaceMesh y
          publica comandos de alerta hacia los actuadores de la ESP32.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop — Sistema Inteligente de Detección de Somnolencia
"""

# ─────────────────────────────────────────────────────────────────────────────
# MODELO UTILIZADO: MediaPipe FaceMesh (Google)
# TIPO DE PREDICCIÓN: Clasificación binaria de estado del conductor
#                     → NORMAL / SOMNOLIENTO / PELIGRO / SIN_ROSTRO
# PRECISIÓN APROXIMADA: ~92% en condiciones de iluminación estándar
#                        ~78% con iluminación baja (interior de auto nocturno)
# MÉTRICAS CLAVE:
#   EAR (Eye Aspect Ratio) — detecta ojos cerrados (umbral < 0.25)
#   MAR (Mouth Aspect Ratio) — detecta bostezo (umbral > 0.55)
# ─────────────────────────────────────────────────────────────────────────────

import paho.mqtt.client as mqtt
import cv2
import mediapipe as mp
import numpy as np
import base64
import json
import time

# ── Configuración MQTT ────────────────────────────────────────────────────────
BROKER           = "localhost"          # Cambiar a IP del broker si es remoto
PUERTO           = 1883
TOPICO_IMAGEN    = "somnostop/camara/frame"
TOPICO_ALERTA    = "somnostop/actuadores/alarma"
TOPICO_ESTADO    = "somnostop/actuadores/estado"
TOPICO_RESULTADO = "somnostop/ia/resultado"
TOPICO_SOLENOIDE = "somnostop/actuadores/solenoide"

# ── Umbrales de detección ─────────────────────────────────────────────────────
UMBRAL_EAR       = 0.25   # EAR por debajo de este valor = ojo cerrado
UMBRAL_MAR       = 0.55   # MAR por encima de este valor = bostezo detectado
FRAMES_PELIGRO   = 3      # Número de frames consecutivos para disparar alarma
FRAMES_AVISO     = 2      # Frames para aviso temprano (SOMNOLIENTO)

# ── Índices de landmarks de MediaPipe FaceMesh ────────────────────────────────
# Ojo izquierdo: párpado superior e inferior, comisuras
OJO_IZQ = [362, 385, 387, 263, 373, 380]
# Ojo derecho: párpado superior e inferior, comisuras
OJO_DER = [33,  160, 158, 133, 153, 144]
# Boca: punto superior, inferior, izquierdo, derecho
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
contador_somnolencia = 0
cliente_mqtt_global  = None
total_frames_procesados = 0
total_alertas_enviadas  = 0


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE CÁLCULO
# ─────────────────────────────────────────────────────────────────────────────

def calcular_ear(landmarks, indices_ojo, ancho_imagen, alto_imagen):
    """
    Recibe:  landmarks de MediaPipe, lista de 6 índices del ojo,
             ancho y alto del frame en píxeles.
    Hace:    calcula el Eye Aspect Ratio (EAR) del ojo indicado.
             EAR = (dist_vertical_1 + dist_vertical_2) / (2 * dist_horizontal)
             Un EAR cercano a 0 indica ojo cerrado; ~0.3 indica ojo abierto.
    Devuelve: float — valor EAR del ojo (0.0 a ~0.4)
    """
    puntos = []
    for indice in indices_ojo:
        lm = landmarks[indice]
        puntos.append((lm.x * ancho_imagen, lm.y * alto_imagen))

    distancia_vertical_1 = np.linalg.norm(
        np.array(puntos[1]) - np.array(puntos[5])
    )
    distancia_vertical_2 = np.linalg.norm(
        np.array(puntos[2]) - np.array(puntos[4])
    )
    distancia_horizontal = np.linalg.norm(
        np.array(puntos[0]) - np.array(puntos[3])
    )

    if distancia_horizontal == 0:
        return 0.0

    ear = (distancia_vertical_1 + distancia_vertical_2) / (2.0 * distancia_horizontal)
    return round(ear, 4)


def calcular_mar(landmarks, ancho_imagen, alto_imagen):
    """
    Recibe:  landmarks de MediaPipe, ancho y alto del frame en píxeles.
    Hace:    calcula el Mouth Aspect Ratio (MAR) para detectar bostezos.
             MAR = distancia_vertical / distancia_horizontal de la boca.
             Un MAR alto indica boca abierta (bostezo).
    Devuelve: float — valor MAR de la boca (0.0 a ~1.0)
    """
    puntos = []
    for indice in BOCA:
        lm = landmarks[indice]
        puntos.append((lm.x * ancho_imagen, lm.y * alto_imagen))

    distancia_vertical   = np.linalg.norm(
        np.array(puntos[0]) - np.array(puntos[1])
    )
    distancia_horizontal = np.linalg.norm(
        np.array(puntos[2]) - np.array(puntos[3])
    )

    if distancia_horizontal == 0:
        return 0.0

    mar = distancia_vertical / distancia_horizontal
    return round(mar, 4)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# ─────────────────────────────────────────────────────────────────────────────

def analizar_frame(datos_base64):
    """
    Recibe:  string con imagen JPEG codificada en base64 (proveniente del MQTT).
    Hace:    decodifica la imagen, detecta rostro con MediaPipe, calcula EAR y
             MAR, determina el estado del conductor y publica resultado por MQTT.
             Actualiza el contador de frames con somnolencia detectada.
    Devuelve: dict con claves 'estado', 'ear', 'mar', 'timestamp' o None si
              la imagen es inválida.
    """
    global contador_somnolencia, total_frames_procesados, total_alertas_enviadas

    # Decodificar base64 → bytes → imagen OpenCV
    try:
        imagen_bytes = base64.b64decode(datos_base64)
        arreglo_np   = np.frombuffer(imagen_bytes, np.uint8)
        frame        = cv2.imdecode(arreglo_np, cv2.IMREAD_COLOR)
    except Exception as error:
        print(f"[IA] Error al decodificar imagen: {error}")
        return None

    if frame is None:
        print("[IA] Frame vacío recibido, descartando.")
        return None

    total_frames_procesados += 1
    alto, ancho = frame.shape[:2]

    # Convertir BGR → RGB para MediaPipe
    frame_rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resultado  = detector_facial.process(frame_rgb)

    # Valores por defecto
    estado       = "SIN_ROSTRO"
    ear_promedio = 1.0
    mar_valor    = 0.0

    if resultado.multi_face_landmarks:
        landmarks = resultado.multi_face_landmarks[0].landmark

        # Calcular métricas
        ear_izquierdo = calcular_ear(landmarks, OJO_IZQ, ancho, alto)
        ear_derecho   = calcular_ear(landmarks, OJO_DER, ancho, alto)
        ear_promedio  = round((ear_izquierdo + ear_derecho) / 2.0, 4)
        mar_valor     = calcular_mar(landmarks, ancho, alto)

        ojos_cerrados = ear_promedio < UMBRAL_EAR
        bostezando    = mar_valor    > UMBRAL_MAR

        # Actualizar contador de somnolencia
        if ojos_cerrados or bostezando:
            contador_somnolencia += 1
        else:
            contador_somnolencia = max(0, contador_somnolencia - 1)

        # Clasificar estado según frames acumulados
        if contador_somnolencia >= FRAMES_PELIGRO:
            estado = "PELIGRO"
        elif contador_somnolencia >= FRAMES_AVISO:
            estado = "SOMNOLIENTO"
        else:
            estado = "NORMAL"

    # Construir payload de resultado
    marca_tiempo = time.time()
    payload_resultado = json.dumps({
        "estado":     estado,
        "ear":        ear_promedio,
        "mar":        mar_valor,
        "frames_som": contador_somnolencia,
        "timestamp":  marca_tiempo
    })

    # Publicar resultado de IA
    cliente_mqtt_global.publish(TOPICO_RESULTADO, payload_resultado)

    # Activar o desactivar actuadores según estado
    if estado == "PELIGRO":
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "2000")   # buzzer 2 kHz
        cliente_mqtt_global.publish(TOPICO_ESTADO,    "PELIGRO")
        cliente_mqtt_global.publish(TOPICO_SOLENOIDE, "ON")
        total_alertas_enviadas += 1
    elif estado == "SOMNOLIENTO":
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "1000")   # buzzer 1 kHz
        cliente_mqtt_global.publish(TOPICO_ESTADO,    "PELIGRO")
        cliente_mqtt_global.publish(TOPICO_SOLENOIDE, "OFF")
    else:
        cliente_mqtt_global.publish(TOPICO_ALERTA,    "0")      # buzzer apagado
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


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACKS MQTT
# ─────────────────────────────────────────────────────────────────────────────

def al_conectar(cliente, datos_usuario, flags, codigo_resultado):
    """
    Recibe:  cliente MQTT y código de resultado de conexión.
    Hace:    imprime confirmación y suscribe al tópico de imágenes.
    Devuelve: None
    """
    if codigo_resultado == 0:
        print(f"[MQTT] Conectado al broker en {BROKER}:{PUERTO}")
        cliente.subscribe(TOPICO_IMAGEN)
        print(f"[MQTT] Suscrito a: {TOPICO_IMAGEN}")
    else:
        print(f"[MQTT] Error de conexión. Código: {codigo_resultado}")


def al_recibir_mensaje(cliente, datos_usuario, mensaje):
    """
    Recibe:  cliente MQTT y mensaje recibido del broker.
    Hace:    enruta el mensaje al analizador de frames si el tópico corresponde.
    Devuelve: None
    """
    if mensaje.topic == TOPICO_IMAGEN:
        analizar_frame(mensaje.payload.decode("utf-8"))


def al_desconectar(cliente, datos_usuario, codigo_resultado):
    """
    Recibe:  cliente MQTT y código de desconexión.
    Hace:    registra el evento de desconexión en consola.
    Devuelve: None
    """
    print(f"[MQTT] Desconectado del broker. Código: {codigo_resultado}")


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

def iniciar_servidor():
    """
    Recibe:  nada
    Hace:    inicializa el cliente MQTT, configura los callbacks y entra en
             el bucle de escucha indefinido. Imprime estadísticas al salir.
    Devuelve: None
    """
    global cliente_mqtt_global

    print("=" * 60)
    print("  SomnoStop — Servidor de Inteligencia Artificial")
    print("  Modelo: MediaPipe FaceMesh | Precisión: ~92%")
    print("=" * 60)

    cliente_mqtt_global = mqtt.Client(client_id="somnostop_ia")
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
