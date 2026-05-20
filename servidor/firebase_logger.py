"""
OBJETIVO: Gestión de Firebase y registro de eventos del sistema SomnoStop.
          Recibe datos por MQTT (telemetría, alertas de IA, cambios de actuadores)
          y los almacena en Firebase Realtime Database con timestamp. También
          escucha comandos remotos desde el dashboard para controlar actuadores.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop — Sistema Inteligente de Detección de Somnolencia
"""

# ─────────────────────────────────────────────────────────────────────────────
# TIPOS DE EVENTOS REGISTRADOS EN FIREBASE:
#   1. telemetria   — lecturas de sensores (distancia, botón, inclinación)
#   2. alerta_ia    — resultados del modelo MediaPipe (estado, EAR, MAR)
#   3. actuador     — cambios de estado de buzzer, LED y solenoide
# ─────────────────────────────────────────────────────────────────────────────

import firebase_admin
from firebase_admin import credentials, db
import paho.mqtt.client as mqtt
import json
import time
import datetime

# ── Configuración Firebase ────────────────────────────────────────────────────
RUTA_CREDENCIALES = "firebase_cred.json"
URL_DATABASE      = "https://sistemas-programables-c2d9e-default-rtdb.firebaseio.com"

# ── Configuración MQTT ────────────────────────────────────────────────────────
BROKER  = "localhost"
PUERTO  = 1883

# Tópicos a escuchar
TOPICO_SENSORES  = "somnostop/sensores/datos"
TOPICO_RESULTADO = "somnostop/ia/resultado"
TOPICO_ACTUADOR  = "somnostop/actuadores/estado"
TOPICO_ALARMA    = "somnostop/actuadores/alarma"
TOPICO_SOLENOIDE = "somnostop/actuadores/solenoide"

# Tópico para recibir comandos remotos desde el dashboard
TOPICO_CONTROL_REMOTO = "somnostop/dashboard/control"

# ── Variables globales ────────────────────────────────────────────────────────
cliente_mqtt_global = None
ultimo_estado_sistema = {
    "estado":     "NORMAL",
    "distancia":  0,
    "inclinacion": 0,
    "boton":      False,
    "ear":        0.0,
    "mar":        0.0,
    "solenoide":  "OFF",
    "alarma":     "0",
    "online":     True,
    "ultima_actualizacion": ""
}


def inicializar_firebase():
    """
    Recibe:  nada
    Hace:    inicializa la conexión con Firebase usando el archivo de credenciales.
             Establece la URL de la Realtime Database.
    Devuelve: True si la conexión fue exitosa, False si hubo error.
    """
    try:
        cred = credentials.Certificate(RUTA_CREDENCIALES)
        firebase_admin.initialize_app(cred, {"databaseURL": URL_DATABASE})
        print(f"[FIREBASE] Conectado a: {URL_DATABASE}")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a Firebase: {e}")
        return False


def obtener_timestamp():
    """
    Recibe:  nada
    Hace:    genera una marca de tiempo en formato legible y en epoch.
    Devuelve: dict con 'legible' (string) y 'epoch' (float).
    """
    ahora = datetime.datetime.now()
    return {
        "legible": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch":   time.time()
    }


def registrar_telemetria(datos):
    """
    Recibe:  dict con datos de sensores (distancia, boton, inclinacion).
    Hace:    guarda el evento de telemetría en Firebase bajo /eventos/telemetria/
             con timestamp. Actualiza el nodo /estado_actual con los últimos valores.
    Devuelve: None
    """
    ts = obtener_timestamp()
    registro = {
        "tipo":       "telemetria",
        "distancia":  datos.get("distancia", 0),
        "boton":      datos.get("boton", False),
        "inclinacion": datos.get("inclinacion", 0),
        "timestamp":  ts["legible"],
        "epoch":      ts["epoch"]
    }
    try:
        db.reference("/eventos/telemetria").push(registro)

        # Actualizar estado actual (para el dashboard en tiempo real)
        db.reference("/estado_actual").update({
            "distancia":   datos.get("distancia", 0),
            "boton":       datos.get("boton", False),
            "inclinacion": datos.get("inclinacion", 0),
            "online":      True,
            "ultima_actualizacion": ts["legible"]
        })
        print(f"[FIREBASE] Telemetría guardada: {registro}")
    except Exception as e:
        print(f"[ERROR] Al guardar telemetría: {e}")


def registrar_alerta_ia(datos):
    """
    Recibe:  dict con resultado de IA (estado, ear, mar).
    Hace:    guarda el evento de alerta IA en Firebase bajo /eventos/alertas_ia/
             solo si el estado es SOMNOLIENTO o PELIGRO (no guarda NORMAL para
             no saturar la base de datos). Actualiza /estado_actual.
    Devuelve: None
    """
    estado = datos.get("estado", "NORMAL")
    ts     = obtener_timestamp()

    registro = {
        "tipo":      "alerta_ia",
        "estado":    estado,
        "ear":       datos.get("ear", 0.0),
        "mar":       datos.get("mar", 0.0),
        "timestamp": ts["legible"],
        "epoch":     ts["epoch"]
    }

    try:
        # Guardar siempre en alertas para historial
        db.reference("/eventos/alertas_ia").push(registro)

        # Actualizar estado del sistema en tiempo real
        db.reference("/estado_actual").update({
            "estado_conductor": estado,
            "ear":              datos.get("ear", 0.0),
            "mar":              datos.get("mar", 0.0),
            "ultima_actualizacion": ts["legible"]
        })

        if estado in ["SOMNOLIENTO", "PELIGRO"]:
            print(f"[FIREBASE] ⚠️  Alerta IA guardada: {estado}")
        else:
            print(f"[FIREBASE] Estado IA: {estado} (guardado)")

    except Exception as e:
        print(f"[ERROR] Al guardar alerta IA: {e}")


def registrar_cambio_actuador(actuador, valor):
    """
    Recibe:  nombre del actuador (string) y su nuevo valor.
    Hace:    guarda el evento de cambio de actuador en Firebase bajo
             /eventos/actuadores/ con timestamp.
    Devuelve: None
    """
    ts = obtener_timestamp()
    registro = {
        "tipo":      "actuador",
        "actuador":  actuador,
        "valor":     valor,
        "timestamp": ts["legible"],
        "epoch":     ts["epoch"]
    }
    try:
        db.reference("/eventos/actuadores").push(registro)
        db.reference("/estado_actual/actuadores").update({
            actuador: valor,
            "ultima_actualizacion": ts["legible"]
        })
        print(f"[FIREBASE] Actuador guardado: {actuador} = {valor}")
    except Exception as e:
        print(f"[ERROR] Al guardar actuador: {e}")


def escuchar_control_remoto(evento):
    """
    Recibe:  evento de Firebase con el comando remoto desde el dashboard.
    Hace:    publica el comando por MQTT hacia la ESP32 para activar/desactivar
             el actuador seleccionado desde la interfaz web.
    Devuelve: None
    """
    if evento.data is None:
        return
    try:
        comando  = evento.data.get("comando", "")
        actuador = evento.data.get("actuador", "")
        valor    = evento.data.get("valor", "OFF")

        if actuador == "solenoide":
            cliente_mqtt_global.publish(TOPICO_SOLENOIDE, valor)
        elif actuador == "alarma":
            cliente_mqtt_global.publish(TOPICO_ALARMA, valor)

        print(f"[CONTROL] Comando remoto ejecutado: {actuador} = {valor}")

        # Registrar el comando en Firebase
        ts = obtener_timestamp()
        db.reference("/eventos/actuadores").push({
            "tipo":      "control_remoto",
            "actuador":  actuador,
            "valor":     valor,
            "origen":    "dashboard",
            "timestamp": ts["legible"],
            "epoch":     ts["epoch"]
        })
    except Exception as e:
        print(f"[ERROR] Al procesar control remoto: {e}")


# ── Callbacks MQTT ────────────────────────────────────────────────────────────

def al_conectar(cliente, datos_usuario, flags, codigo):
    """
    Recibe:  cliente MQTT y código de resultado de conexión.
    Hace:    suscribe a todos los tópicos relevantes al conectar.
    Devuelve: None
    """
    if codigo == 0:
        print(f"[MQTT] Conectado al broker {BROKER}:{PUERTO}")
        cliente.subscribe(TOPICO_SENSORES)
        cliente.subscribe(TOPICO_RESULTADO)
        cliente.subscribe(TOPICO_ACTUADOR)
        cliente.subscribe(TOPICO_ALARMA)
        cliente.subscribe(TOPICO_SOLENOIDE)
        cliente.subscribe(TOPICO_CONTROL_REMOTO)
        print(f"[MQTT] Suscrito a todos los tópicos SomnoStop")
    else:
        print(f"[ERROR] Conexión MQTT fallida. Código: {codigo}")


def al_recibir_mensaje(cliente, datos_usuario, mensaje):
    """
    Recibe:  cliente MQTT y mensaje recibido.
    Hace:    enruta el mensaje al registro de Firebase correspondiente
             según el tópico de origen.
    Devuelve: None
    """
    topico  = mensaje.topic
    payload = mensaje.payload.decode("utf-8")

    try:
        if topico == TOPICO_SENSORES:
            datos = json.loads(payload)
            registrar_telemetria(datos)

        elif topico == TOPICO_RESULTADO:
            datos = json.loads(payload)
            registrar_alerta_ia(datos)

        elif topico == TOPICO_ACTUADOR:
            registrar_cambio_actuador("estado_led", payload)

        elif topico == TOPICO_ALARMA:
            registrar_cambio_actuador("buzzer_hz", payload)

        elif topico == TOPICO_SOLENOIDE:
            registrar_cambio_actuador("solenoide", payload)

    except json.JSONDecodeError:
        # Algunos tópicos mandan texto plano, no JSON
        pass
    except Exception as e:
        print(f"[ERROR] Al procesar mensaje: {e}")


# ── Punto de entrada ──────────────────────────────────────────────────────────

def iniciar():
    """
    Recibe:  nada
    Hace:    inicializa Firebase y MQTT, configura el listener de control remoto
             y entra en el bucle de escucha indefinido.
    Devuelve: None
    """
    global cliente_mqtt_global

    print("=" * 55)
    print("  SomnoStop — Firebase Logger + Control Remoto")
    print("=" * 55)

    if not inicializar_firebase():
        return

    # Marcar sistema como online al arrancar
    db.reference("/estado_actual").update({
        "online": True,
        "ultima_actualizacion": obtener_timestamp()["legible"],
        "estado_conductor": "NORMAL"
    })

    # Escuchar comandos remotos del dashboard en tiempo real
    db.reference("/control_remoto").listen(escuchar_control_remoto)

    # Inicializar MQTT
    cliente_mqtt_global = mqtt.Client(client_id="somnostop_firebase")
    cliente_mqtt_global.on_connect = al_conectar
    cliente_mqtt_global.on_message = al_recibir_mensaje

    try:
        cliente_mqtt_global.connect(BROKER, PUERTO, keepalive=60)
        cliente_mqtt_global.loop_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Firebase logger detenido.")
        db.reference("/estado_actual").update({"online": False})
        cliente_mqtt_global.disconnect()
    except ConnectionRefusedError:
        print("[ERROR] No se pudo conectar al broker MQTT.")
        print("        Verifica que Mosquitto esté corriendo: mosquitto -v")


if __name__ == "__main__":
    iniciar()
