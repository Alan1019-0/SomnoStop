"""
OBJETIVO: Gestión de Firebase y registro de eventos del sistema SomnoStop.
          Recibe datos por MQTT (telemetría, alertas de IA, cambios de actuadores)
          y los almacena en Firebase Realtime Database con timestamp. También
          escucha comandos remotos desde el dashboard para controlar actuadores.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop — Sistema Inteligente de Detección de Somnolencia
"""

import firebase_admin
from firebase_admin import credentials, db
import paho.mqtt.client as mqtt
import json
import time
import datetime

# ── Configuración Firebase ────────────────────────────────────────────────────
RUTA_CREDENCIALES = r"servidor\firebase_cred.json"
URL_DATABASE      = "https://somnostop2-default-rtdb.firebaseio.com"

# ── Configuración MQTT ────────────────────────────────────────────────────────
BROKER  = "192.168.1.65"
PUERTO  = 1883

TOPICO_SENSORES       = "somnostop/sensores/datos"
TOPICO_RESULTADO      = "somnostop/ia/resultado"
TOPICO_ACTUADOR       = "somnostop/actuadores/estado"
TOPICO_ALARMA         = "somnostop/actuadores/alarma"
TOPICO_SOLENOIDE      = "somnostop/actuadores/solenoide"
TOPICO_CONTROL_REMOTO = "somnostop/dashboard/control"

# ── Variables globales ────────────────────────────────────────────────────────
cliente_mqtt_global = None


def inicializar_firebase():
    try:
        cred = credentials.Certificate(RUTA_CREDENCIALES)
        firebase_admin.initialize_app(cred, {"databaseURL": URL_DATABASE})
        print(f"[FIREBASE] Conectado a: {URL_DATABASE}")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a Firebase: {e}")
        return False


def obtener_timestamp():
    ahora = datetime.datetime.now()
    return {
        "legible": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch":   time.time()
    }


def adc_a_cm(valor_adc):
    """
    Convierte el valor ADC (0-4095) a centímetros aproximados.
    El HC-SR04 mide de 2 cm a 400 cm.
    El ADC lee 0-4095 mapeado a 0-100 en dispositivos.py.
    Se remapea a 2-400 cm para mostrar valores realistas.
    """
    try:
        valor = float(valor_adc)
        # valor ya viene como porcentaje 0-100 desde dispositivos.py
        cm = 2 + (valor / 100.0) * 398
        return round(cm, 1)
    except:
        return 0


def registrar_telemetria(datos):
    ts = obtener_timestamp()

    # Convertir cabeceo (bool) a texto legible
    cabeceo = datos.get("cabeceo", False)
    inclinacion_texto = "Cabeceo detectado" if cabeceo else "Normal"

    # Convertir distancia ADC a cm
    distancia_cm = adc_a_cm(datos.get("distancia", 0))

    registro = {
        "tipo":        "telemetria",
        "distancia":   distancia_cm,
        "boton":       datos.get("boton", False),
        "inclinacion": inclinacion_texto,
        "cabeceo_raw": cabeceo,
        "timestamp":   ts["legible"],
        "epoch":       ts["epoch"]
    }
    try:
        db.reference("/eventos/telemetria").push(registro)

        db.reference("/estado_actual").update({
            "distancia":            distancia_cm,
            "boton":                datos.get("boton", False),
            "inclinacion":          inclinacion_texto,
            "online":               True,
            "ultima_actualizacion": ts["legible"]
        })
        print(f"[FIREBASE] Telemetría: dist={distancia_cm}cm | boton={datos.get('boton')} | cabeceo={cabeceo}")
    except Exception as e:
        print(f"[ERROR] Al guardar telemetría: {e}")


def registrar_alerta_ia(datos):
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
        db.reference("/eventos/alertas_ia").push(registro)

        db.reference("/estado_actual").update({
            "estado_conductor":     estado,
            "ear":                  datos.get("ear", 0.0),
            "mar":                  datos.get("mar", 0.0),
            "ultima_actualizacion": ts["legible"]
        })

        if estado in ["SOMNOLIENTO", "PELIGRO"]:
            print(f"[FIREBASE] ⚠️  Alerta IA: {estado} | EAR={datos.get('ear'):.3f} | MAR={datos.get('mar'):.3f}")
        else:
            print(f"[FIREBASE] Estado IA: {estado}")

    except Exception as e:
        print(f"[ERROR] Al guardar alerta IA: {e}")


def registrar_cambio_actuador(actuador, valor):
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
        print(f"[FIREBASE] Actuador: {actuador} = {valor}")
    except Exception as e:
        print(f"[ERROR] Al guardar actuador: {e}")


def escuchar_control_remoto(evento):
    if evento.data is None:
        return
    try:
        actuador = evento.data.get("actuador", "")
        valor    = evento.data.get("valor", "OFF")

        if actuador == "solenoide":
            cliente_mqtt_global.publish(TOPICO_SOLENOIDE, valor)
        elif actuador == "alarma":
            cliente_mqtt_global.publish(TOPICO_ALARMA, valor)
        elif actuador == "estado":
            cliente_mqtt_global.publish(TOPICO_ACTUADOR, valor)

        print(f"[CONTROL] Comando remoto: {actuador} = {valor}")

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


def al_conectar(cliente, datos_usuario, flags, codigo, properties=None):
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
        pass
    except Exception as e:
        print(f"[ERROR] Al procesar mensaje: {e}")


def iniciar():
    global cliente_mqtt_global

    print("=" * 55)
    print("  SomnoStop — Firebase Logger + Control Remoto")
    print("=" * 55)

    if not inicializar_firebase():
        return

    db.reference("/estado_actual").update({
        "online":               True,
        "ultima_actualizacion": obtener_timestamp()["legible"],
        "estado_conductor":     "NORMAL"
    })

    db.reference("/control_remoto").listen(escuchar_control_remoto)

    cliente_mqtt_global = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION1,
        client_id="somnostop_firebase"
    )
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
        print("        Verifica que Mosquitto esté corriendo.")


if __name__ == "__main__":
    iniciar()