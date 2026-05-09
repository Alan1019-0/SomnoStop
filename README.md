# SomnoStop: Sistema Inteligente de Detección de Somnolencia

### Información del Proyecto
- **Integrantes:** - Cruz Valadez Montserrat
  - Gómez Juárez Alan Fabricio
- **Materia:** Sistemas Programables
- **Proyecto:** SomnoStop (Integración Total MQTT)

---

### Objetivo
Establecer un ecosistema de comunicación definitivo mediante el protocolo MQTT, conectando una ESP32 con un servidor en Python. El sistema integra sensores de distancia y movimiento para detectar fatiga, activando alertas físicas y sonoras de manera desacoplada mediante una arquitectura HAL.

---

### Arquitectura de Software (Validación HAL)
Se ha implementado una **Capa de Abstracción de Hardware (HAL)** en el archivo `dispositivos.py`. Esto garantiza que la lógica de comunicación MQTT no tenga acceso directo a los pines del hardware, permitiendo una mayor escalabilidad y facilidad de mantenimiento.

---

### Matriz de Tópicos MQTT

| Dispositivo | Tópico | Dirección | Función |
| :--- | :--- | :--- | :--- |
| Telemetría General | `somnostop/sensores/datos` | ESP32 -> PC | Envío de JSON (Distancia, Botón, Inclinación). |
| Solenoide (Alerta) | `somnostop/actuadores/solenoide` | PC -> ESP32 | Comando "ON"/"OFF" para activación física. |
| Estado de Sistema | `somnostop/actuadores/estado` | PC -> ESP32 | Comando "OK"/"PELIGRO" para control de LEDs. |
| Alarma Sonora | `somnostop/actuadores/alarma` | PC -> ESP32 | Valor de frecuencia (Hz) para el zumbador. |

---

### Análisis Individual y Conclusiones

#### Montserrat Cruz (Problemas y Soluciones)
- **Problema Detectado:** Durante las pruebas iniciales, se detectó inestabilidad en la conexión Wi-Fi de la ESP32 al intentar publicar en 4 tópicos simultáneamente, lo que provocaba cierres de socket inesperados.
- **Solución Aplicada:** Se implementó una estructura de datos tipo JSON para empaquetar toda la telemetría en un solo mensaje. Además, se configuró un delay no bloqueante de 1 segundo para estabilizar el tráfico hacia el broker HiveMQ.
- **Conclusión Personal:** La implementación de MQTT permitió desacoplar la lógica de procesamiento pesado (Python) del control de tiempo real (ESP32). Aprendí que el manejo de payloads en formato JSON es fundamental para optimizar el ancho de banda en sistemas de seguridad vial.

#### Alan Gómez (Problemas y Soluciones)
- **Problema Detectado:** Al recibir comandos desde Python, los actuadores no reaccionaban porque los mensajes llegaban como cadenas de texto ("ON") y la HAL esperaba valores booleanos, lo que generaba errores de tipo de dato en la ejecución.
- **Solución Aplicada:** Se robusteció la función `callback` en la ESP32 para realizar un parseo de datos y validación de tipos antes de invocar los métodos de la HAL, garantizando que el hardware reciba los parámetros correctos.
- **Conclusión Personal:** El uso de una HAL fue crítico; permitió realizar pruebas de comunicación sin riesgo de dañar los actuadores físicos. Comprendí que una arquitectura por capas es la mejor defensa contra errores de integración en sistemas programables complejos.