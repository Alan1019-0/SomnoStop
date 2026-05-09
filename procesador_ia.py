"""
OBJETIVO: Procesar telemetría y emitir comandos de seguridad.
INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
PROYECTO: SomnoStop
"""

import paho.mqtt.client as mqtt
import json
import time

BROKER = "broker.hivemq.com"

def al_recibir_mensaje(client, userdata, msg):
    try:
        marca_tiempo = time.strftime("%Y-%m-%d %H:%M:%S")
        carga = json.loads(msg.payload.decode())
        print(f"[{marca_tiempo}] Sensores: {carga}")
        
        # Lógica de decisión
        if carga['distancia'] < 20 or carga['cabeceo']:
            client.publish("somnostop/actuadores/solenoide", "ON")
            client.publish("somnostop/actuadores/estado", "PELIGRO")
            client.publish("somnostop/actuadores/alarma", "1000")
        else:
            client.publish("somnostop/actuadores/solenoide", "OFF")
            client.publish("somnostop/actuadores/estado", "OK")
            client.publish("somnostop/actuadores/alarma", "0")
            
    except Exception as e:
        print(f"Error: {e}")

servidor = mqtt.Client()
servidor.on_message = al_recibir_mensaje
servidor.connect(BROKER, 1883, 60)
servidor.subscribe("somnostop/sensores/datos")
print("Servidor SomnoStop escuchando...")
servidor.loop_forever()