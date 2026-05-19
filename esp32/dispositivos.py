# PROYECTO: SomnoStop - Sistema de Detección de Somnolencia
# INTEGRANTES: Cruz Valadez Montserrat, Gómez Juárez Alan Fabricio
# DESCRIPCIÓN: Biblioteca HAL que encapsula el control de sensores y actuadores 
# para facilitar su uso mediante el protocolo MQTT.

from machine import Pin, ADC, PWM
import time

class SensorBox:
    """
    Clase encargada de la gestión y estabilización de lecturas de sensores.
    """
    def __init__(self):
        # 1. Sensor de Distancia VL53L0X (Simulado vía ADC para este ejemplo)
        self.sensor_distancia = ADC(Pin(34))
        self.sensor_distancia.atten(ADC.ATTN_11DB)
        
        # 2. Botón de Seguridad (Confirmación de conciencia)
        self.boton_seguridad = Pin(35, Pin.IN, Pin.PULL_UP)
        
        # 3. Sensor de Movimiento (Simulado para detección de inclinación)
        self.sensor_movimiento = ADC(Pin(32))

    def obtener_distancia_cm(self):
        # Promedio móvil para estabilizar la lectura
        suma = 0
        for _ in range(5):
            suma += self.sensor_distancia.read()
            time.sleep(0.01)
        promedio = suma / 5
        return (promedio / 4095) * 100

    def verificar_boton_presionado(self):
        # Retorna True si el conductor presiona el botón
        return not self.boton_seguridad.value()

    def obtener_resumen_sensores(self):
        return {
            "distancia": self.obtener_distancia_cm(),
            "boton": self.verificar_boton_presionado(),
            "cabeceo": self.sensor_movimiento.read() > 2000
        }

class ActuatorBox:
    """
    Clase encargada del control de actuadores y señales de alerta.
    """
    def __init__(self):
        # 1. Solenoide de Alerta Física
        self.solenoide = Pin(27, Pin.OUT)
        
        # 2. LEDs de estado
        self.led_alerta = Pin(2, Pin.OUT)
        self.led_ok = Pin(4, Pin.OUT)
        
        # 3. Alarma Sonora (Zumbador)
        self.alarma_sonora = PWM(Pin(18))
        self.alarma_sonora.duty(0)

    def activar_alerta_fisica(self, activar):
        self.solenoide.value(1 if activar else 0)

    def gestionar_indicadores(self, estado):
        if estado == "PELIGRO":
            self.led_alerta.value(1)
            self.led_ok.value(0)
        else:
            self.led_alerta.value(0)
            self.led_ok.value(1)

    def sonar_alarma(self, frecuencia):
        if frecuencia > 0:
            self.alarma_sonora.freq(frecuencia)
            self.alarma_sonora.duty(512)
        else:
            self.alarma_sonora.duty(0)

    def estado_seguro(self):
        self.solenoide.value(0)
        self.led_alerta.value(0)
        self.led_ok.value(0)
        self.alarma_sonora.duty(0)