# SomnoStop — Sistema Inteligente de Detección de Somnolencia

**Integrantes:** Cruz Valadez Montserrat · Gómez Juárez Alan Fabricio  
**Materia:** Sistemas Programables — TecNM / Instituto Tecnológico de León  
**Proyecto:** SomnoStop

---

## Objetivo General

Desarrollar un sistema IoT de seguridad vial que detecte señales de somnolencia en conductores en tiempo real. La ESP32 recopila datos de sensores y la ESP32-CAM captura imágenes del rostro del conductor; toda la información viaja por MQTT hacia un servidor Python que ejecuta un modelo de IA (MediaPipe FaceMesh) para clasificar el estado del conductor y activar alertas físicas y sonoras de forma inmediata.

---

## Arquitectura del Sistema

```
ESP32 / ESP32-CAM              Broker MQTT              Servidor Python (IA)
──────────────────             ───────────              ────────────────────
Sensores (distancia,     →     somnostop/         →     procesador_ia.py
 botón, inclinación)           sensores/datos            lógica de decisión
Cámara (frame JPEG)      →     camara/frame       →     ia_processor.py
                                                         MediaPipe FaceMesh

Actuadores               ←     actuadores/        ←     comandos de alerta
(buzzer, LEDs,                  alarma
 solenoide)                     estado
                                solenoide
                                ia/resultado
```

---

## Estructura del Repositorio

```
SomnoStop/
├── esp32/
│   ├── dispositivos.py       # HAL — SensorBox y ActuatorBox (E1)
│   ├── main.py               # Programa principal del microcontrolador
│   └── camara_mqtt.py        # Captura y publicación de frames por MQTT (E3)
├── servidor/
│   ├── procesador_ia.py      # Suscriptor MQTT + lógica de decisión (E2)
│   ├── ia_processor.py       # Pipeline de IA con MediaPipe FaceMesh (E3)
│   └── prueba_estatica.py    # Validación estática del modelo sin MQTT (E3)
└── README.md
```

---

## Arquitectura de Software — HAL (E1)

Se implementó una Capa de Abstracción de Hardware en `dispositivos.py` con las clases `SensorBox` y `ActuatorBox`. El `main.py` interactúa con el hardware **exclusivamente** a través de estos métodos, sin usar primitivas de MicroPython directamente (`machine.Pin`, `machine.PWM`, etc.).

---

## Matriz de Tópicos MQTT (E2 + E3)

| Tópico | Dirección | Contenido |
|:---|:---|:---|
| `somnostop/sensores/datos` | ESP32 → PC | JSON con distancia, botón, inclinación |
| `somnostop/camara/frame` | ESP32-CAM → PC | Imagen JPEG codificada en base64 |
| `somnostop/ia/resultado` | PC → ESP32 | JSON con estado, EAR y MAR |
| `somnostop/actuadores/solenoide` | PC → ESP32 | `"ON"` / `"OFF"` |
| `somnostop/actuadores/estado` | PC → ESP32 | `"OK"` / `"PELIGRO"` |
| `somnostop/actuadores/alarma` | PC → ESP32 | Frecuencia del buzzer en Hz |

---

## Modelo de Inteligencia Artificial (E3)

| Campo | Detalle |
|:---|:---|
| **Librería** | MediaPipe FaceMesh (Google) |
| **Tipo de modelo** | Detección de landmarks faciales (478 puntos) |
| **Tipo de predicción** | Clasificación del estado del conductor |
| **Clases posibles** | `NORMAL` · `SOMNOLIENTO` · `PELIGRO` · `SIN_ROSTRO` |
| **Precisión (buena iluminación)** | ~92% |
| **Precisión (luz baja / interior auto)** | ~78% |
| **Latencia por frame** | ~80–120 ms en CPU sin GPU |
| **Resolución de entrada** | 320×240 px (QVGA desde ESP32-CAM) |

### Métricas de detección

**EAR — Eye Aspect Ratio:** mide la apertura de los ojos.
```
EAR = (dist_vertical_1 + dist_vertical_2) / (2 × dist_horizontal)
EAR < 0.25  →  ojo cerrado (alerta)
EAR ≈ 0.30  →  ojo abierto (normal)
```

**MAR — Mouth Aspect Ratio:** mide la apertura de la boca.
```
MAR = distancia_vertical / distancia_horizontal
MAR > 0.55  →  bostezo detectado
```

Si cualquiera de las dos condiciones se mantiene durante **3 frames consecutivos**, el sistema emite la alerta de PELIGRO.

---

## Instalación de Dependencias

```bash
pip install mediapipe opencv-python paho-mqtt numpy
```

---

## Ejecución

### 1. Prueba estática del modelo (sin ESP32 ni MQTT)
```bash
python servidor/prueba_estatica.py
```
Usa la webcam de la PC para validar que MediaPipe detecta correctamente el rostro y las métricas EAR/MAR. Genera `resultados_prueba.json` como evidencia.

### 2. Pipeline completo con MQTT
```bash
# Terminal 1 — Broker
mosquitto -v

# Terminal 2 — Servidor de IA
python servidor/ia_processor.py

# Terminal 3 — Monitor (opcional)
mosquitto_sub -t "somnostop/#" -v
```

---

## Análisis Individual

### Montserrat Cruz Valadez — E2

**Problema:** Inestabilidad en la conexión Wi-Fi de la ESP32 al publicar en 4 tópicos simultáneamente, provocando cierres de socket inesperados.

**Solución:** Se empaquetó toda la telemetría en un único JSON y se configuró un delay no bloqueante de 1 segundo para estabilizar el tráfico hacia el broker.

**Conclusión:** La implementación de MQTT permitió desacoplar la lógica de procesamiento pesado (Python) del control en tiempo real (ESP32). El manejo de payloads JSON es fundamental para optimizar el ancho de banda en sistemas de seguridad vial.

---

### Montserrat Cruz Valadez — E3

**Problema:** La latencia entre la captura del frame en la ESP32-CAM y el procesamiento en el servidor superaba los 4 segundos, haciendo que el modelo analizara imágenes desactualizadas del conductor y que las alertas llegaran con retraso crítico.

**Solución:** Se redujo la resolución de SVGA (800×600) a QVGA (320×240) y se aumentó la compresión JPEG de `q=5` a `q=10`, reduciendo el tamaño del frame de ~45 KB a ~12 KB y la latencia a menos de 500 ms.

**Conclusión:** La arquitectura correcta para IoT queda demostrada: el microcontrolador actúa como sensor/actuador y el servidor como cerebro. La ESP32 no puede correr MediaPipe debido a sus limitaciones de RAM (~520 KB) y ausencia de FPU eficiente.

---

### Alan Fabricio Gómez Juárez — E2

**Problema:** Los actuadores no reaccionaban a los comandos de Python porque los mensajes llegaban como cadenas de texto (`"ON"`) y la HAL esperaba valores booleanos, generando errores de tipo silenciosos.

**Solución:** Se robusteció el callback en la ESP32 para hacer parseo y validación de tipos antes de invocar los métodos de la HAL, garantizando que el hardware reciba los parámetros correctos.

**Conclusión:** El uso de una HAL fue crítico; permitió realizar pruebas de comunicación sin riesgo de dañar los actuadores físicos. Una arquitectura por capas es la mejor defensa contra errores de integración en sistemas complejos.

---

### Alan Fabricio Gómez Juárez — E3

**Problema:** Los valores de EAR y MAR llegaban como cadenas dentro del JSON (`"0.23"` en lugar de `0.23`), causando que las comparaciones con los umbrales fallaran silenciosamente sin activar alertas.

**Solución:** Se añadió conversión explícita de tipos con `float()` al extraer valores del JSON en la ESP32, y se validó que el servidor Python siempre publique valores numéricos nativos mediante `round()` antes de serializar.

**Conclusión:** La comunicación JSON entre MicroPython y CPython requiere validación estricta de tipos en ambos extremos. Probar el modelo con imágenes estáticas antes de conectar la ESP32 aceleró enormemente la detección de errores sin depender del hardware físico.
