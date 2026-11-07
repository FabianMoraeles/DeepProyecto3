# Resultados de la evaluación de DatoClaro

**Fecha de las corridas:** 2 de noviembre de 2026 (hora local)
**Partición:** `dev`, 102 preguntas de BIRD Mini-Dev en inglés
**Modelos comparados:** TF-IDF (baseline sin IA), Ollama · Qwen2.5-Coder 7B, Claude Haiku 5.5 y Claude Sonnet 5.5

> **Resumen:** Sonnet 5.5 fue el mejor modelo por un margen claro y estadísticamente significativo: **45 % de aciertos**, contra 27.5 % de Haiku y 19.6 % de Ollama. Entre Haiku y Ollama no hay diferencia demostrable. El baseline TF-IDF sacó 0 %, lo que confirma que los aciertos vienen de generar SQL nuevo y no de copiar ejemplos.

---

## 1. Qué se midió y cómo

### El examen
Cada pregunta de BIRD trae su **SQL correcto** (`gold_sql`), escrito y revisado por humanos. Es el "solucionario" y existe **antes** de que el modelo haga nada. Para cada pregunta:

1. El modelo genera su SQL **sin ver el solucionario**. `predict()` lo quita antes de construir el mensaje.
2. Se ejecutan **los dos** SQL en la misma base, en modo solo lectura.
3. Se comparan **los resultados**, no el texto. Si dan las mismas filas, es **acierto**.

Esta métrica se llama **Execution Accuracy (EX)**. Dos SQL escritos distinto que devuelven las mismas filas cuentan como acierto.

### Condiciones (iguales para los cuatro sistemas)
- **Mismas 102 preguntas** de `dev`: 31 simples, 49 moderadas y 22 difíciles.
- **Sin pistas:** no se le pasa al modelo el campo `evidence` de BIRD (por ejemplo, *"outpatient refers to Admission = '-'"*). Así se parece a un usuario real, pero el examen es más difícil que el modo estándar de BIRD.
- **Configuración por defecto del sistema:**
  - recuperación `lexical`, con 4 tablas candidatas más las tablas puente;
  - 3 ejemplos de la partición `kb`;
  - respuesta en JSON;
  - una reparación si el SQL falla;
  - aclaraciones permitidas.
- **Una corrida por modelo.** Claude no acepta `temperature=0`, así que los resultados pueden variar algunos puntos entre corridas.

---

## 2. El baseline: TF-IDF

### Qué es
Es un sistema **sin IA** que sirve de nota mínima. Busca en `kb` la pregunta más parecida a la del examen (por similitud de palabras TF-IDF) y **copia su SQL tal cual**. No genera nada nuevo.

### Para qué sirve
Si un modelo con IA no le gana al baseline, la IA no está aportando nada. Si le gana, demuestra que el modelo **genera** SQL adecuado a cada pregunta.

### Resultados

| Partición | Aciertos | Exactitud | IC 95 % |
|---|---|---|---|
| `dev` (102) | 0 / 102 | **0 %** | 0 – 0 % |
| `test` (222) | 2 / 220 válidas | **0.9 %** | 0 – 2.3 % |

Era lo esperado. Las preguntas del examen son distintas a las de `kb`, y las particiones se armaron agrupando preguntas casi gemelas (`group_id`) para que no haya "trampa". Copiar el SQL de una pregunta parecida casi nunca da el resultado correcto.

---

## 3. Qué es un "fallo"

**Cualquier pregunta que no sea acierto es fallo**, sin importar el motivo:

| Tipo de fallo | Qué pasó | ¿Es culpa del modelo? |
|---|---|---|
| **SQL incorrecto** | El SQL se ejecutó, pero devolvió filas distintas a las del solucionario. | Casi siempre sí |
| **Se negó** | Respondió "no puedo responder esto" en vez de dar SQL. | Depende: puede ser honesto (falta una tabla) o un error (negativa falsa). |
| **Pidió aclaración** | Respondió con una pregunta ("¿qué rango consideras normal?"). En el examen nadie le contesta. | Parcialmente. Sin las pistas de BIRD, a veces la duda es razonable. |
| **Error** | El SQL no se pudo ejecutar, tardó más de 5 s, el JSON vino mal formado o el contexto era demasiado grande. | Mixto |

Por eso "fallo" no siempre significa que el modelo razonó mal. La sección 6 desglosa las causas reales.

---

## 4. Tabla comparativa final

### Resultados generales (dev, 102 preguntas)

| | **TF-IDF** (sin IA) | **Ollama · Qwen 7B** | **Claude Haiku 5.5** | **Claude Sonnet 5.5** |
|---|---|---|---|---|
| **Aciertos** | 0 / 102 | 20 / 102 | 28 / 102 | **46 / 102** |
| **Exactitud (EX)** | **0 %** | **19.6 %** | **27.5 %** | **45.1 %** |
| IC 95 % | 0 – 0 % | 12.7 – 27.5 % | 18.6 – 35.3 % | 35.3 – 53.9 % |
| **Fallos** | 102 | 82 | 74 | **56** |
| Simples (31) | 0 | 12 | 12 | **20** |
| Moderadas (49) | 0 | 7 | 13 | **19** |
| Difíciles (22) | 0 | 1 | 3 | **7** |
| SQL ejecutados | 102 | 57 | 68 | **80** |
| Aciertos sobre lo ejecutado | 0 % | 35 % | 41 % | **58 %** |
| Pidió aclaración | — | 2 | **28** | 9 |
| Se negó | — | **35** | 6 | 11 |
| Errores | — | 8 | 0 | 2 |
| Tiempo por pregunta (mediana / p95) | 0.13 / 0.27 s | **0.74 / 1.2 s** | 3.1 / 5.8 s | 3.9 / 7.4 s |
| Costo de las 102 preguntas | USD 0 | USD 0 | **USD 0.05** | **USD 0.80** |
| Costo por acierto | — | USD 0 | USD 0.002 | USD 0.017 |
| Dónde corre | Local | Local | Nube (Anthropic) | Nube (Anthropic) |
| Privacidad | Total | Total | Envía la pregunta y el esquema, nunca las filas | Igual que Haiku |

### ¿Las diferencias son reales? (prueba pareada de McNemar)
Compara a dos modelos **sobre las mismas preguntas** y cuenta cuántas acertó solo uno de los dos.

| Comparación | Solo acertó el 1.º | Solo acertó el 2.º | p | ¿Diferencia real? |
|---|---|---|---|---|
| Sonnet contra Haiku | 20 | 2 | **0.0001** | ✅ Sí |
| Sonnet contra Ollama | 32 | 6 | **< 0.0001** | ✅ Sí |
| Haiku contra Ollama | 17 | 9 | 0.17 | ❌ No se puede afirmar |

Un p < 0.05 indica que la diferencia es muy difícil de explicar por azar.

### Aciertos por base de datos

| Base | Preguntas | Ollama | Haiku | Sonnet |
|---|---|---|---|---|
| Vida universitaria (`student_club`) | 9 | 3 | 5 | **7** |
| Escuelas de California (`california_schools`) | 6 | 2 | 4 | **5** |
| Comunidad de código (`codebase_community`) | 10 | 2 | 5 | **6** |
| Superhéroes (`superhero`) | 11 | 4 | 4 | **6** |
| Toxicología (`toxicology`) | 8 | 1 | **4** | **4** |
| Consumo y pagos (`debit_card_specializing`) | 7 | 0 | 1 | **4** |
| Fútbol europeo (`european_football_2`) | 11 | 1 | 0 | **3** |
| Finanzas (`financial`) | 6 | 2 | 0 | **3** |
| Fórmula 1 (`formula_1`) | 14 | 2 | **3** | **3** |
| Investigación clínica (`thrombosis_prediction`) | 9 | **3** | 1 | **3** |
| Juegos de cartas (`card_games`) | 11 | 0 | 1 | **2** |

---

## 5. ¿Cuál modelo fue mejor?

### 🥇 Claude Sonnet 5.5: el mejor
- **Acierta 18 preguntas más que Haiku** y la diferencia es significativa (p = 0.0001). De las 22 preguntas en que discreparon, Sonnet acertó 20.
- **Escribe mejor SQL:** el 58 % de sus consultas ejecutadas fueron correctas, contra 41 % de Haiku.
- **Duda menos:** pidió aclaración 9 veces, contra 28 de Haiku. Cuando faltan pistas, hace una suposición razonable en vez de preguntar.
- Gana o empata en las 11 bases.
- **Contra:** cuesta unas 17 veces más por pregunta que Haiku. Aun así, las 102 preguntas salen en menos de un dólar.

### 🥈 Claude Haiku 5.5 y Ollama · Qwen 7B: empate técnico
Haiku saca 8 puntos más (27.5 % contra 19.6 %), pero con p = 0.17 **no se puede afirmar que sea mejor**. Cada uno tiene su perfil:

| | Haiku | Ollama |
|---|---|---|
| Ventaja | Mejor en preguntas moderadas y difíciles (13 + 3 contra 7 + 1) | Gratis, 4 veces más rápido y totalmente privado |
| Debilidad | Pide aclaración demasiado (28 veces) | Se niega de más (35 veces) |

### Último: TF-IDF
0 %, como se esperaba. Confirma que el resultado de los otros tres viene de **generar** SQL, no de copiar.

---

## 6. Análisis de los fallos

### 6.1 Por qué Ollama falló más

| Causa | Fallos | Sonnet acertó de esas |
|---|---|---|
| Se negó a responder | 35 | 12 |
| SQL incorrecto | 37 | 14 |
| Error técnico | 8 | — |
| Pidió aclaración | 2 | — |

**a) Se niega de más (35).**
- **17 negativas falsas por "seguridad":** el modelo creyó que le pedían escribir o romper reglas. Por ejemplo:
  > *"What's the nationality of the customer who spent 548.4 in 2012/8/24?"*
  > Ollama: *"La solicitud no es una consulta de lectura sobre el esquema proporcionado."*

  Es una pregunta normal de solo lectura. El prompt de sistema incluye reglas de seguridad ("rechaza solicitudes de escritura, archivos, secretos…") y un modelo de 7B las **aplica de más**.
- **8 veces dijo que faltaba una tabla o columna**, pero recibió **exactamente las mismas tablas que Sonnet**. No fue culpa del buscador: el modelo no supo leer el esquema.
- **10 por otros motivos**, entre ellos considerar ambigua la pregunta.

**b) Entiende peor el esquema (37 SQL incorrectos).** Ejecuta un SQL válido, pero elige mal las tablas o columnas. Por ejemplo, con *"What is the total amount of money spent for food?"*:
```sql
-- Solucionario de BIRD (Sonnet escribió exactamente esto):
SELECT SUM(spent) FROM budget WHERE category = 'Food'
-- Ollama:
SELECT SUM(cost) AS total_spent FROM expense WHERE expense_description LIKE '%food%'
```

**c) Límites técnicos (8).**
- **4 por contexto "demasiado grande":** el código limita a Ollama a 6500 bytes. Por eso Fútbol europeo falla con Ollama.
- **4 por JSON mal formado,** incluso después del segundo intento.

**Causa de fondo:** Qwen2.5-Coder tiene **7 mil millones de parámetros** y corre en una PC. Sigue peor las instrucciones largas y con matices, entiende peor las bases con muchas tablas y se confunde al mezclar idiomas: el prompt está en español y las preguntas de BIRD en inglés.

### 6.2 Por qué se negaron Haiku y Sonnet

| Modelo | Negativas | Motivo |
|---|---|---|
| Ollama | 35 | 17 por "escritura" (falsas), 8 por "falta una tabla" (falsas), 10 por otros motivos |
| Haiku | 6 | Las 6: falta una tabla o columna |
| Sonnet | 11 | Las 11: falta una tabla o columna |

Se revisó cada negativa de Haiku y Sonnet contra el solucionario. **En todas era verdad:** la tabla necesaria no estaba entre las que el buscador les pasó. Por ejemplo:
> *"List the long name of teams with above-average build-up play passing in 2012."*
> Sonnet: *"No puedo responder con el esquema proporcionado: la pregunta necesita el atributo de pase en la construcción de juego (buildUpPlayPassing)…"*

La columna está en la tabla `Team_Attributes`, que el buscador léxico no seleccionó, porque *"build-up play"* no comparte palabras con el nombre de la tabla. Haiku y Sonnet **dijeron la verdad en vez de inventar**, que es lo que pide el prompt. Estos fallos son del **buscador**, no del modelo.

### 6.3 Las aclaraciones de Haiku (28)
Muchas preguntas de BIRD dependen de las pistas que no se le pasan al modelo, como:
- *"¿Qué rango de bilirrubina (T-BIL) consideras normal?"*
- *"¿Qué valor de la columna Thrombosis corresponde a 'más grave'?"*

Preguntar es correcto en la app, con un usuario real. En un examen automático nadie responde, así que cuenta como fallo. El proyecto ya trae el experimento **I5**, que apaga las aclaraciones para medir este efecto.

### 6.4 Errores del solucionario de BIRD
Algunos "fallos" son en realidad **errores de BIRD**. Por ejemplo:
> *"What is the ratio of **outpatient to inpatient** followed up treatment among all the 'SLE' diagnosed patient?"*
> Pista de BIRD: *inpatient = `Admission = '+'`; outpatient = `Admission = '-'`*

```sql
-- Solucionario de BIRD: '+' / '-'  → inpatient / outpatient (al revés de lo que pide la pregunta)
SELECT SUM(CASE WHEN Admission = '+' THEN 1.0 ELSE 0 END) / SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) FROM Patient WHERE Diagnosis = 'SLE'
-- Sonnet: '-' / '+'  → outpatient / inpatient (lo que la pregunta pide)
SELECT CAST(SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) AS REAL) / SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) FROM Patient WHERE Diagnosis = 'SLE'
```
Sonnet tenía razón, pero cuenta como fallo porque la comparación es contra el solucionario. **La exactitud real de cada modelo es algo más alta que la medida.**

---

## 7. Limitaciones

1. **Sin pistas (`evidence`).** Las cifras **no se pueden comparar** con la tabla de posiciones oficial de BIRD, donde se usan las pistas.
2. **Una sola corrida por modelo.** Claude no acepta `temperature=0`, así que la misma pregunta puede dar resultados distintos. Para el informe final conviene repetir y reportar la variación.
3. **Solo 102 preguntas.** Los intervalos de confianza son anchos (±8–9 puntos).
4. **Solo `dev`.** La partición `test` (222 preguntas) se reserva para el número final, para no ajustar el sistema mirando el examen.
5. **Posible contaminación.** BIRD es público desde 2023 y los modelos pudieron verlo durante su entrenamiento.
6. **Errores en el solucionario de BIRD** (sección 6.4).
7. **Corrida descartada.** Una primera corrida de Haiku sacó 22.5 %, porque el antivirus Kaspersky bloqueó 11 conexiones a la API. Se configuró una exclusión para `api.anthropic.com` y se repitió; la corrida válida no tuvo ningún error de conexión.

---

## 8. Recomendaciones

**Para la feria:**
- Usar **Haiku** en la demo en vivo. Es barato, responde en unos 3 s y con preguntas claras en español funciona bien.
- Escribir preguntas que digan **qué columnas mostrar** y que no tengan un "o" que obligue a elegir entre dos interpretaciones (ver la sección 9).
- Con Ollama, evitar **Fútbol europeo** por el límite de contexto.

**Mejoras gratuitas** (no usan IA y benefician a los tres modelos):
1. **Mejorar el buscador de tablas:** subir `top_k` de 4 a 6 o probar la recuperación `semantic`. Recuperaría negativas como las de `Team_Attributes`.
2. **Subir el límite de contexto de Ollama** de 6500 bytes a ~25 000. El modelo acepta 8192 tokens.
3. **Suavizar las reglas de seguridad del prompt para Ollama.** La protección real está en el motor SQL de solo lectura, no en el prompt.

**Para el informe:**
- Correr los experimentos **I5** (sin aclaraciones) e **I6** (sistema completo) con `scripts/experiments.py`. Requiere configurar `DATOCLARO_PRICES_JSON` en `.env`.
- Reportar el número final en `test` una sola vez, al terminar los ajustes.

---

## 9. Preguntas de demo verificadas

Se probaron 3 veces cada una con Haiku y se comprobaron consultando la base directamente.

| Base | Pregunta | Resultado |
|---|---|---|
| Fórmula 1 | ¿Cuáles son los 10 pilotos con más victorias en la historia de la Fórmula 1? Para cada uno muestra su nombre completo, su nacionalidad, el número de carreras que ganó y el número total de carreras en las que participó, ordenados de más a menos victorias. | ✅ 3/3 idéntico: Michael Schumacher (alemán, 91 victorias, 308 carreras), Lewis Hamilton (británico, 60, 202) |
| Vida universitaria | Para cada evento, ¿cuántos miembros asistieron y cuánto dinero se gastó en total en ese evento? Muestra el nombre del evento, la cantidad de asistentes y el gasto total, ordenado del evento con más asistentes al de menos. | ✅ 3/3 idéntico: Registration (30, USD 295.12), Yearly Kickoff (30, USD 449.13) |
| Educación | Por escuela: ¿cuál obtuvo el mejor y cuál el peor promedio del SAT en matemáticas? | ✅ 5/5: Mission San Jose High (699) y Gompers Continuation (289) |
| Educación | ⚠️ En qué escuela **o** condado se obtuvo el mejor y el peor resultado en el SAT en matemática? | ❌ Pidió aclaración 5/5: es ambigua |
| Educación | ⚠️ Por condado, ¿cuántas escuelas tiene cada uno…? | ⚠️ Respondió, pero con números distintos en cada intento. Evitarla. |

---

## 10. Cómo reproducir

```powershell
# Baseline TF-IDF (gratis, ~15 s)
python tasks.py eval --baseline --split dev

# Claude Haiku 5.5 (~USD 0.05, ~5 min)
$env:DATOCLARO_PROVIDER='anthropic'; $env:DATOCLARO_MODEL='claude-haiku-5-5'
python tasks.py eval --predictor app.pipeline:predict --split dev

# Claude Sonnet 5.5 (~USD 0.80, ~10 min)
$env:DATOCLARO_PROVIDER='anthropic'; $env:DATOCLARO_MODEL='claude-sonnet-5-5'
python tasks.py eval --predictor app.pipeline:predict --split dev

# Ollama (gratis; requiere Ollama corriendo con qwen2.5-coder:7b-instruct)
$env:DATOCLARO_PROVIDER='ollama'; $env:DATOCLARO_MODEL='qwen2.5-coder:7b-instruct'
python tasks.py eval --predictor app.pipeline:predict --split dev

# Prueba pareada entre dos corridas
python tasks.py compare artifacts/runs/<corrida_A> artifacts/runs/<corrida_B>
```

### Corridas usadas en este documento
Están en `artifacts/runs/`. Cada carpeta guarda las predicciones, las calificaciones, el resumen y un manifiesto con las huellas SHA-256 del código y los datos.

| Sistema | Partición | Carpeta |
|---|---|---|
| TF-IDF | dev | `20261103T003923Z-33bc673d` |
| TF-IDF | test | `20261103T003333Z-17c146c6` |
| Ollama · Qwen 7B | dev | `20261103T004640Z-f0332a96` |
| Claude Haiku 5.5 | dev | `20261103T010149Z-bc5497ce` (válida) |
| Claude Haiku 5.5 | dev | `20261103T004404Z-13081b52` (descartada: 11 errores de conexión) |
| Claude Sonnet 5.5 | dev | `20261103T010316Z-ccccdec1` |

Las corridas se hicieron con cambios todavía sin commit: el glosario de `app/retrieval.py` y `max_tokens` en `app/config.py` y `app/llm.py`. El manifiesto de cada corrida registra la huella del código exacto que se usó. Para que el repositorio coincida con estos resultados, conviene hacer commit de esos cambios.
