# DatoClaro

Haz preguntas en español sobre datos educativos y universitarios. Obtén tablas, gráficos y resultados que puedes descargar como CSV.

## Instalación

Necesitas Python 3.13 y al menos 3 GB libres para los datos. Guarda el proyecto en una carpeta local, fuera de iCloud o OneDrive, para evitar cargas lentas.

**Windows (PowerShell):**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tasks.py fetch-data
.\.venv\Scripts\python.exe run.py
```

**macOS / Linux:**

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tasks.py fetch-data
.venv/bin/python run.py
```

Abre **http://localhost:8501**, selecciona una fuente de datos y pulsa **Analizar pregunta**.

Para volver a iniciar la aplicación, ejecuta únicamente el último comando de tu sistema.

## Usar IA

**Sin configurar nada:** el modo guiado ejecuta seis preguntas preparadas sobre datos reales. No genera respuestas con IA.

**Con Claude:** copia `.env.example` a `.env` y añade tu clave:

```dotenv
ANTHROPIC_API_KEY=tu_clave
```

Reinicia la aplicación y selecciona **Claude API**. Las llamadas requieren saldo en la cuenta del proveedor. No compartas el archivo `.env`.

**Con Ollama:** instala [Ollama](https://ollama.com/), inicia su servicio y descarga el modelo:

```text
ollama pull qwen2.5-coder:7b-instruct
```

Selecciona **Ollama local** en la aplicación.

## Datos y documentación

Los datos se descargan de [BIRD Mini-Dev](https://huggingface.co/datasets/birdsql/bird_mini_dev): 500 preguntas y 11 bases SQLite, con licencia CC BY-SA 4.0. Consulta la [atribución](data/NOTICE.md).

- [Fuentes de datos](docs/data_sources.md)
- [Arquitectura](docs/architecture.md)
- [Evaluación y pruebas](docs/evaluation.md)
- [Despliegue y solución de problemas](docs/deployment.md)
