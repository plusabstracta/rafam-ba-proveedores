"""mappers â MÃ³dulos de transformaciÃ³n por entidad RAFAM â Paxapos.

Cada mapper encapsula la lÃ³gica de negocio especÃ­fica de una entidad:
  - Transformar filas crudas de Oracle al formato del migrator Paxapos
  - Persistir entity links a partir de la respuesta del API
  - Loguear estadÃ­sticas de la pasada

Los mappers son stateful (pueden acumular contadores entre batches)
pero NO hacen HTTP â ese es el rol del exporter/orchestrator.
"""
