# Dobot Magician - Controlador en Python para Ubuntu / Linux

Este proyecto proporciona un entorno modular, seguro y listo para producción para controlar el brazo robótico **Dobot Magician** en **Ubuntu** usando Python 3.

---

## 🚀 Características

- **Control Cartesiano y Articular:** Movimientos absolutos (`move_to`) y relativos (`move_rel`), homing (`home`) y lectura en tiempo real de coordenadas y articulaciones (`get_pose`).
- **Modos PTP Configurables:** Soporte para movimiento lineal (`MOVL_XYZ`) y articular (`MOVJ_XYZ`).
- **Dibujo con Marcador y Trayectorias Suaves:** Módulo de dibujo para trazos vectoriales sobre papel, generador geométrico (caritas felices, círculos, arcos), control de cota de contacto (`z_draw`) y cota de tránsito en el aire (`z_hover`).
- **Asistente de Calibración de Marcador:** Comando interactivo para hallar la altura milimétrica exacta donde la punta toca el papel sin dañar el marcador ni el robot.
- **Control de Efectores:** Soporte para ventosa de succión neumática (`suck`) y pinza/gripper (`grip`).
- **Sistema de Seguridad Integrado (`SafetyLimits`):** Verifica automáticamente que las coordenadas solicitadas no excedan el radio físico de trabajo (160 mm a 330 mm) ni bajen de cotas peligrosas para la mesa (evita colisiones mecánicas).
- **Modo Simulación / Mock:** Permite desarrollar, probar algoritmos y ejecutar scripts sin necesidad de tener el robot físico conectado (`mock=True` o flag `--mock`).
- **CLI Amigable con Rich:** Comandos de consola `dobot scan`, `dobot status`, `dobot move`, `dobot suction`, `dobot demo`, `dobot draw-face`, `dobot calibrate-pen`.
- **Reglas udev para Ubuntu:** Configuración automática de permisos de acceso serie sin requerir `sudo`.

---

## 📁 Estructura del Proyecto

```text
dobot-magician/
├── .venv/                      # Entorno virtual de Python
├── examples/                   # Scripts de demostración prácticos
│   ├── 01_scan_ports.py        # Diagnóstico y detección de puertos USB
│   ├── 02_basic_movement.py    # Movimientos cartesianos básicos y relativos
│   ├── 03_pick_and_place.py    # Rutina completa de agarre y depósito
│   ├── 04_mock_simulation.py   # Simulación y validación de límites de seguridad
│   └── 05_draw_smiley.py       # Trazado de carita feliz con marcador
├── src/
│   └── dobot_controller/
│       ├── __init__.py
│       ├── cli.py              # Línea de comandos (Typer + Rich)
│       ├── connection.py       # Detección y filtrado de puertos serie / permisos
│       ├── controller.py       # DobotController de alto nivel con Context Manager
│       ├── drawing.py          # Generador de trayectorias y rutinas de dibujo
│       ├── mock.py             # Simulador en memoria del robot
│       └── safety.py           # Validaciones de límites geométricos
├── tests/
│   └── test_dobot_controller.py# Suite de 14 pruebas unitarias con pytest
├── udev/
│   └── 99-dobot.rules          # Reglas udev para CP210x y CH340
├── pyproject.toml              # Definición del paquete e instalador pip
├── pytest.ini                  # Configuración de pruebas aisladas
├── requirements.txt            # Dependencias del proyecto
├── run_tests.sh                # Script para ejecutar pruebas
└── setup_udev.sh               # Script para instalar permisos udev en Ubuntu
```

---

## 🛠️ Instalación y Configuración

### 1. Activar el entorno virtual

El proyecto ya cuenta con su entorno configurado en `.venv`:

```bash
cd master-projects/dobot-magician
source .venv/bin/activate
```

O si necesitas recrearlo:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Permisos en Ubuntu (Grupo `dialout`)

Para que tu usuario pueda comunicarse con el puerto serie USB sin `sudo`:

```bash
# 1. Asignar usuario al grupo dialout (si aún no lo está)
sudo usermod -a -G dialout $USER

# 2. (Opcional) Instalar reglas udev persistentes
sudo ./setup_udev.sh
```

---

## 💻 Uso desde la Línea de Comandos (CLI)

El paquete incluye el comando `dobot` instalado en el entorno:

### 1. Escanear puertos y diagnosticar hardware
```bash
dobot scan
```

### 2. Consultar posición actual y articulaciones
Con el robot conectado físicamente:
```bash
dobot status
```
O en modo simulado:
```bash
dobot status --mock
```

### 3. Mover a una coordenada cartesiana
```bash
dobot move --x 230 --y 0 --z 40 --r 0
```

### 4. Controlar la ventosa de succión
```bash
dobot suction on
dobot suction off
```

### 5. Calibración a Home
```bash
dobot home
```

### 6. Ejecutar rutina de demostración (Pick & Place)
```bash
dobot demo
# O en simulación:
dobot demo --mock
```

### 7. Calibrar la altura de contacto del marcador
Si no conoces la altura exacta $Z$ donde el marcador toca la hoja de papel, ejecuta el asistente interactivo:
```bash
dobot calibrate-pen
```
Te permite descender milimétricamente el marcador (`-5`, `-1`, `-0.2`) hasta hacer contacto ligero, e imprime la altura óptima.

### 8. Dibujar la Carita Feliz
```bash
# Prueba segura en el aire (a 35 mm sobre la mesa, sin tocar papel):
dobot draw-face --air-draw

# Dibujar sobre papel con la altura Z calibrada (ej. Z = 0 mm):
dobot draw-face --z-draw 0.0 --z-hover 15.0

# O en modo simulación (sin conectar hardware):
dobot draw-face --mock
```

---

## 🐍 Uso desde Python (API)

### Ejemplo Básico con Context Manager

```python
from dobot_controller import DobotController

# Conexión automática al puerto detectado (ej. /dev/ttyUSB0)
with DobotController() as bot:
    # Obtener pose actual
    pose = bot.get_pose()
    print(f"X={pose['x']} mm, Y={pose['y']} mm, Z={pose['z']} mm")

    # Mover a posición segura
    bot.move_to(x=220.0, y=0.0, z=50.0, wait=True)

    # Desplazamiento relativo (+30 mm en eje Y)
    bot.move_rel(dy=30.0, wait=True)
```

### Dibujar una Carita Feliz con el Marcador

```python
from dobot_controller import DobotController
from dobot_controller.drawing import draw_smiley_face

with DobotController() as bot:
    draw_smiley_face(
        bot=bot,
        center_x=220.0,       # Centro en X (mm)
        center_y=0.0,         # Centro en Y (mm)
        radius=30.0,          # Radio de la cara (mm)
        z_draw=0.0,           # Altura de contacto sobre papel
        z_hover=15.0,         # Altura para levantar el marcador en el aire
        velocity=35.0         # Velocidad lineal de dibujo (mm/s)
    )
```

O ejecutando directamente el script de ejemplo:
```bash
python examples/05_draw_smiley.py --air-draw
python examples/05_draw_smiley.py --z-draw 0.0
```

### Rutina de Pick & Place

```python
from dobot_controller import DobotController

with DobotController() as bot:
    bot.pick_and_place(
        pick_pos=(220.0, -80.0, 10.0),   # Punto A
        place_pos=(220.0, 80.0, 10.0),   # Punto B
        safe_z=60.0,                      # Altura de viaje
        dwell_seconds=0.5,
        use_gripper=False                 # Usa succión por defecto
    )
```

### Modo Simulación (Sin Hardware)

```python
from dobot_controller import DobotController

with DobotController(mock=True) as bot:
    bot.move_to(x=250.0, y=30.0, z=40.0)
    print("Pose simulada:", bot.get_pose())
```

---

## 🧪 Pruebas Unitarias

Ejecuta el script de pruebas automatizado:

```bash
./run_tests.sh
```

Las 14 pruebas unitarias validan:
- Geometría de trabajo y límites de seguridad (`SafetyLimits`).
- Intercepción de posiciones fuera de alcance o peligrosas para la mesa.
- Simulador en memoria (`MockDobot`) y control de efectores (succión y gripper).
- Generación de trayectorias geométricas de dibujo (cabeza, ojos, sonrisa).
- Comandos CLI (`scan`, `status`, `move`, `demo`, `draw-face`).
