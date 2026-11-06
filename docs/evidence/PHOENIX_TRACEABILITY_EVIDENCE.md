# Evidencias de trazabilidad – ADA Study
## Arize Phoenix | Proyecto final AI Engineering

### 1. Objetivo

Se utiliza Arize Phoenix para observar y analizar las ejecuciones del sistema multiagente ADA Study.

Las trazas permiten inspeccionar el recorrido de cada consulta, las decisiones del Supervisor, la recuperación de evidencia mediante RAG, la intervención del modelo de lenguaje, la validación de resultados y la generación de la respuesta final.

Las capturas de evidencia están organizadas en `docs/evidence/capturas/` y documentan cinco escenarios reales de ejecución (TC-02, TC-03, TC-04, TC-05 y TC-06). Además, cada escenario cuenta con un documento Word en esta misma carpeta que reproduce la evidencia con su narrativa de ejecución.

---

## 2. TC-02 – Consulta respondida con evidencia documental

**Consulta ejecutada:**

«Según el documento de Historia, ¿cuáles fueron las causas de la Revolución de Mayo?»

**Resultado:** respuesta completa, fundamentada en documentos recuperados y validada por el sistema.

| Archivo | Contenido y evidencia que demuestra |
|---|---|
| `capturas/TC-02-full-trace.png` | Vista general de la traza. Muestra el recorrido completo por LangGraph: Supervisor, Researcher, Tutor, Validator y Synthesizer. También permite observar la invocación del modelo y los tiempos de ejecución. |
| `capturas/TC-02-researcher-output.png` | Resultado de la recuperación RAG. Muestra cinco fragmentos recuperados mediante BM25, pertenecientes a `Historia_5to_Grado_Guia_Completa.pdf`, con identificación de documentos, páginas y contenido. |
| `capturas/TC-02-supervisor-routing.png` | Decisión del Supervisor de continuar hacia el Tutor porque se recuperó evidencia suficiente para elaborar una respuesta pedagógica. |
| `capturas/TC-02-tutor-output.png` | Respuesta generada por el Tutor mediante Groq (`openai/gpt-oss-120b`). Incluye explicación y referencias a los fragmentos utilizados. La ejecución registró 2.795 tokens. |
| `capturas/TC-02-validator-validation.png` | Validación estructurada de la respuesta. Los ocho controles finalizaron en PASS, sin errores, advertencias, reintentos ni necesidad de revisión humana. |
| `capturas/TC-02-synthesizer-output.png` | Resultado final consolidado. Muestra la respuesta completa, su estado y las referencias documentales conservadas después de la validación. |

**Controles del Validator (los ocho en PASS):** `research_artifact_present`, `study_response_present`, `evidence_contract`, `response_contract`, `cited_subset_of_evidence`, `complete_has_references`, `complete_has_pertinent_evidence`, `gaps_acknowledged`.

## 3. TC-03 – Registro de ejecución RAG con Phoenix

**Consulta ejecutada:** «¿Qué temas se estudian en Historia de quinto grado?»

**Resultado:** evidencia suficiente, respuesta publicada con estado `complete` e incorporada al historial de la conversación. **Trace ID:** `2ac3eba9fbc8491abde2b4584a8bffd5`.

| Archivo | Contenido y evidencia que demuestra |
|---|---|
| `capturas/TC-03-01-trace-overview.png` | Vista general de la traza de `POST /api/study`: respuesta HTTP 200, ejecución del flujo LangGraph y tiempos de los nodos. |
| `capturas/TC-03-02-langgraph-output.png` | Salida del flujo LangGraph: consulta exacta, historial y artefacto de investigación. |
| `capturas/TC-03-03-supervisor-routing.png` | Primera decisión del Supervisor: enrutar al Researcher porque todavía no hay evidencia recuperada. |
| `capturas/TC-03-04-researcher-retrieval.png` | Resultado del Researcher: BM25 recupera cinco fragmentos; el filtro de pertinencia acepta cuatro y descarta uno. |
| `capturas/TC-03-05-supervisor-to-tutor.png` | Segunda decisión del Supervisor: con evidencia disponible, enrutar al Tutor para generar la respuesta. |
| `capturas/TC-03-06-tutor-llm.png` | El Tutor ejecuta el LLM: `provider=groq`, `model=openai/gpt-oss-120b`, invocación completada. |
| `capturas/TC-03-07-validator.png` | El Validator aprueba la respuesta: ocho controles en PASS, sin errores ni advertencias. |
| `capturas/TC-03-08-synthesizer.png` | El Synthesizer registra la publicación aprobada: `validation_approved=true`, `published_status=complete`, referencias incluidas. |

---

## 4. TC-04 – Consulta sin evidencia suficiente

**Consulta ejecutada:**

«¿Qué dice la mitosis?»

**Resultado:** el sistema identifica que el corpus disponible no contiene evidencia suficiente y evita generar una respuesta sin fundamento.

| Archivo | Contenido y evidencia que demuestra |
|---|---|
| `capturas/TC-04-insufficient-evidence.png` | Traza de la ejecución completa. El Researcher no recupera evidencia, el Tutor no invoca el LLM y el sistema devuelve `insufficient_evidence`. La respuesta incluye la explicación de la limitación, sin referencias inventadas. |

Esta ejecución demuestra el manejo de evidencia insuficiente y la prevención de respuestas no fundamentadas. La validación del resultado final también fue satisfactoria.

---

## 5. TC-05 – Consulta comparativa con evidencia documental

**Consulta ejecutada:** «¿Qué diferencias había entre los mayas, los mexicas y los incas?»

**Resultado:** evidencia suficiente (5 fragmentos recuperados, 5 aceptados, 0 descartados), respuesta publicada con estado `complete` y cinco referencias. **Trace ID:** `2776035f876f4d18bb460df21834f84e`.

| Archivo | Contenido y evidencia que demuestra |
|---|---|
| `capturas/TC-05-01-trace-overview.png` | Vista general de la traza y recorrido de ejecución. |
| `capturas/TC-05-02-execution-attributes.png` | Detalle de la ejecución y sus atributos. |
| `capturas/TC-05-03-retrieval.png` | Detalle del procesamiento de recuperación de evidencia. |
| `capturas/TC-05-04-span-metadata.png` | Información del span y sus metadatos. |
| `capturas/TC-05-05-generation.png` | Detalle de la etapa de generación de respuesta. |
| `capturas/TC-05-06-attributes.png` | Atributos y datos registrados durante la ejecución. |
| `capturas/TC-05-07-validation.png` | Detalle de validación y resultado. |
| `capturas/TC-05-08-phoenix-view.png` | Vista complementaria de la traza en Phoenix. |

---

## 6. TC-06 – Persistencia conversacional

**Objetivo:** verificar que una conversación conserve su identidad y el hilo del LangGraph Checkpointer después de reiniciar el servidor.

**Identificadores registrados:**

| Momento | Trace ID | Resultado |
|---|---|---|
| Consulta inicial | `c7ebc869427b47c7990bd70fdd3a6889` | Interacción registrada |
| Antes del reinicio | `cbd5e084f3fc42418203a1cc5c6f0818` | Mismo `conversation_id` |
| Después del reinicio | `0a77dabdaf4447d6bdcac19a02efd857` | Mismo `conversation_id` e hilo |

`conversation_id` / hilo del Checkpointer: `conv-09ee30ca-09f8-4594-9842-37e8707f6ad4`.

**Resultado:** la tercera interacción, realizada después de reiniciar Uvicorn, conservó el mismo `conversation_id` y el mismo hilo persistente. Las consultas de seguimiento terminaron con estado `insufficient_evidence`; este resultado no invalida el objetivo de la prueba, que evalúa la persistencia del hilo y la continuidad de la identidad conversacional.

| Archivo | Contenido y evidencia que demuestra |
|---|---|
| `capturas/TC-06-01-trace-overview.png` | Vista general de la traza LangGraph y del contexto conversacional. |
| `capturas/TC-06-02-supervisor-routing.png` | Detalle de la decisión del Supervisor. |
| `capturas/TC-06-03-researcher-filter.png` | Detalle del Researcher: cinco fragmentos descartados por pertinencia. |
| `capturas/TC-06-04-graph-transition.png` | Detalle de la transición del grafo posterior al Researcher. |
| `capturas/TC-06-05-tutor-no-llm.png` | Detalle del Tutor: `insufficient_evidence` y LLM no invocado. |
| `capturas/TC-06-06-supervisor-to-validator.png` | Detalle de la transición del Supervisor hacia Validator. |
| `capturas/TC-06-07-validator.png` | Detalle del Validator: validación aprobada. |
| `capturas/TC-06-08-synthesizer.png` | Detalle del Synthesizer: publicación con estado `insufficient_evidence`. |

---

## 7. Arquitectura observable

Las ejecuciones permiten observar el siguiente flujo:

**Supervisor → Researcher → Supervisor → Tutor → Supervisor → Validator → Synthesizer**

El recorrido puede variar según el resultado de la investigación. Cuando no se recupera evidencia suficiente, el sistema evita ejecutar el Tutor y continúa hacia la validación y síntesis del resultado de insuficiencia.

## 8. Alcance de las evidencias

Las capturas documentan ejecuciones reales observadas en Arize Phoenix. Permiten verificar:

- Orquestación multiagente mediante LangGraph.
- Decisiones y enrutamiento del Supervisor.
- Recuperación documental mediante BM25.
- Generación mediante un modelo LLM cuando corresponde.
- Validación de contratos, referencias y evidencia.
- Síntesis de respuestas finales.
- Manejo de consultas sin evidencia suficiente.
- Tiempos de ejecución y métricas de utilización del modelo.

**Nota:** estas evidencias corresponden a los escenarios y consultas identificados en cada sección. No implican que todas las funcionalidades de recuperación o persistencia estén demostradas por estas capturas.
