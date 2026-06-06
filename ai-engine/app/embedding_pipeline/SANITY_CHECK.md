# Embedding Pipeline Sanity Check

Fecha: 2026-05-30

Este sanity check no es una validacion formal del modelo: es un minimo aceptable que demuestra que el pipeline funciona end-to-end y que los embeddings discriminan razonablemente entre textos cercanos y lejanos.

## Resultados

| Pareja | Descripcion | Similaridad coseno |
|---|---|---:|
| A | Textos semanticamente cercanos | 0.5957 |
| B | Textos no relacionados | 0.1920 |
| C | Textos genericos y ambiguos | 0.5407 |

## Comentario breve

La pareja B sale claramente baja (0.1920), lo cual encaja muy bien con la expectativa de textos lejanos.
La pareja A queda en 0.5957: es alta en terminos relativos frente a B, aunque se queda apenas por debajo del umbral orientativo de 0.6.
La pareja C (0.5407) resulta interesante porque, pese a ser generica, mantiene una cercania notable por compartir contexto tecnico de software.
En conjunto, el comportamiento es razonable para un sanity check rapido, y deja buen material para discutir calibracion de umbrales en directo.