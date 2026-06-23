# Regulatory Banking Corpus - Adapted Architecture Specification

## Objective

Build a regulatory banking knowledge corpus for advanced RAG and GraphRAG over DORA, RTS, ITS, EBA ICT Guidelines, EBA Outsourcing Guidelines, NIS2, and related supervisory material.

This specification adapts the current Estimator RAG architecture to a new domain. The system must keep the same embedding and retrieval baseline already used by `ai-engine`:

- Embedding model: `text-embedding-3-small`
- Embedding dimensions: `1536`
- Vector storage: PostgreSQL + pgvector
- Vector distance: cosine distance
- Current orchestration style: staged pipeline with reformulation, retrieval, assembly, and generation
- Frontend pattern: Angular feature screens for ingestion, retrieval inspection, and full pipeline result visualization

The domain changes from software estimation budgets to banking regulation. The architectural principle changes from chunk-first retrieval to structure-first legal retrieval with embeddings as one retrieval layer.

---

## Design Principles

### 1. Structure First, Embeddings Second

Regulatory documents must be parsed into their legal structure before embedding. Legal hierarchy is the primary source of truth; embeddings are used to improve recall and semantic matching over persisted legal chunks.

### 2. Preserve Legal Hierarchy

Each document must be decomposed into stable legal nodes:

- Document
- Title
- Chapter
- Section
- Article
- Paragraph
- Point
- Subpoint
- Annex
- Recital, when applicable

Every retrievable chunk must keep a reference to its legal node path so answers can cite exact articles, paragraphs, and source documents.

### 3. Single Enrichment At Ingestion Time

LLM calls for legal enrichment must happen during ingestion only. Runtime retrieval should use persisted structured knowledge:

- Obligations
- Definitions
- Regulatory entities
- Cross-references
- Topics
- Keywords
- Applicability metadata
- Control or evidence expectations, when extractable

Runtime queries may use LLM generation to answer, summarize, or compare, but must not repeatedly re-extract obligations from the same source text.

### 4. Keep Existing Pipeline Shape

The regulatory pipeline should reuse the current staged shape:

1. Query reformulation / understanding
2. Hybrid retrieval
3. Context assembly
4. Grounded generation
5. Citation validation

The regulatory implementation extends the retrieval stage from semantic-only retrieval to hybrid metadata + graph + BM25 + vector retrieval.

---

## Current Project Baseline To Reuse

The existing `ai-engine` already provides the technical foundation:

- `app/generation/rag/embedding/embedder.py` embeds content with OpenAI embeddings.
- `app/generation/rag/store/models.py` stores `documents` and `chunks` with `Vector(1536)`.
- `app/generation/rag/store/repository.py` performs cosine-distance retrieval.
- `app/generation/rag/retriever_service.py` embeds the query with the same model and queries pgvector.
- `app/api/rag_pipeline.py` exposes staged RAG endpoints and a full orchestration endpoint.
- The frontend already has RAG ingestion, lab, form, and result views under `application-web/frontend/src/app/features/estimations/`.

For the regulatory domain, these should be generalized rather than duplicated wholesale. The regulatory corpus should use the same embedding model and vector semantics so retrieval behavior remains consistent across domains.

---

## Proposed AI Engine Directory Structure

The regulatory feature should follow the same layered layout already present in `ai-engine/app`: `api`, `domain`, `foundation`, `generation`, and `ingestion`.

```text
ai-engine/
  app/
    api/
      regulatory_ingestion.py          # Upload/acquire regulatory documents and start ingestion jobs
      regulatory_retrieval.py          # Metadata, graph, BM25, vector, and hybrid retrieval endpoints
      regulatory_pipeline.py           # Full regulatory RAG orchestration endpoint
      regulatory_graph.py              # Graph traversal/debug endpoints for references and hierarchy

    domain/
      regulatory_answer_service.py     # Domain orchestration for answer/comparison/compliance outputs
      regulatory_citation_service.py   # Citation normalization and validation against legal nodes
      regulatory_output_validator.py   # Ensures answers cite valid articles/paragraphs and obligations
      schemas/
        regulatory.py                  # Domain-facing Pydantic schemas for generated outputs

    foundation/
      regulatory/
        __init__.py
        identifiers.py                 # Canonical IDs for documents, nodes, chunks, obligations, edges
        taxonomy.py                    # Frameworks, authorities, document types, topic vocabulary
        normalizers.py                 # Authority/framework/article normalization utilities
      llm/
        # Reuse existing LiteLLM provider integration
      persistence/
        # Reuse existing SQLAlchemy base/session configuration
      prompts/
        regulatory/
          enrichment/v1/
            system.j2                  # Ingestion-time extraction prompt
            user.j2
          answer/v1/
            system.j2                  # Runtime grounded answer prompt
            user.j2
          comparison/v1/
            system.j2                  # Compare obligations across frameworks
            user.j2

    ingestion/
      regulatory/
        __init__.py
        orchestrator.py                # End-to-end ingestion flow for regulatory documents
        acquisition.py                 # PDF/HTML/manual upload/source repository adapters
        structural_parser.py           # Non-LLM legal hierarchy parser
        legal_chunker.py               # Semantic legal chunking by obligations/definitions/etc.
        enrichment_service.py          # Ingestion-time LLM enrichment
        persistence_service.py         # Persist documents, nodes, chunks, obligations, edges, embeddings
        validators.py                  # Schema and source integrity checks
        parsers/
          pdf.py                       # PDF extraction adapter
          html.py                      # HTML extraction adapter
          eurlex.py                    # Optional official repository adapter
          manual_upload.py             # Manual upload adapter
        cleaning/
          text_normalizer.py           # Headers, footers, whitespace, page markers
          citation_normalizer.py       # Normalize Art., Article, paragraph, point references

    generation/
      rag/
        # Keep existing generic embedding/retrieval modules
        embedding/
          embedder.py                  # Reuse text-embedding-3-small
        store/
          models.py                    # Extend or add regulatory-specific tables
          repository.py                # Keep generic chunk persistence/search contracts
        regulatory/
          query_understanding.py       # Reformulate user query into regulatory filters/intents
          hybrid_retriever.py          # Orchestrates metadata + graph + BM25 + vector retrieval
          metadata_retriever.py        # Framework/topic/authority/article filters
          graph_retriever.py           # Parent/child/cross-reference traversal
          bm25_retriever.py            # Keyword/legal text retrieval
          vector_retriever.py          # pgvector search using same embedding model
          context_assembler.py         # Builds answer context with chunks, obligations, definitions, refs
          reranker.py                  # Optional deterministic or LLM-free ranking blend
          schemas.py                   # Regulatory pipeline request/response schemas

  tests/
    unit/
      regulatory/
        test_structural_parser.py
        test_legal_chunker.py
        test_regulatory_schemas.py
        test_hybrid_retriever.py
        test_context_assembler.py
    integration/
      regulatory/
        test_regulatory_ingestion.py
        test_regulatory_pipeline.py
```

This keeps domain-specific logic under regulatory modules while preserving shared infrastructure for LLM providers, persistence, embeddings, and staged RAG orchestration.

---

## Proposed Frontend Directory Structure

The Angular frontend should mirror the current RAG UI pattern, but as a regulatory corpus feature. A practical location is a new feature module under `features/regulatory`.

```text
application-web/
  frontend/
    src/app/features/regulatory/
      regulatory.routes.ts
      regulatory.service.ts             # Typed HTTP client for regulatory APIs
      regulatory.types.ts               # Shared interfaces matching backend JSON contracts

      ingestion/
        regulatory-ingestion.component.ts
        regulatory-ingestion.component.html
        regulatory-ingestion.component.scss

      retrieval-lab/
        regulatory-retrieval-lab.component.ts
        regulatory-retrieval-lab.component.html
        regulatory-retrieval-lab.component.scss

      query-form/
        regulatory-query-form.component.ts
        regulatory-query-form.component.html
        regulatory-query-form.component.scss

      result/
        regulatory-result.component.ts
        regulatory-result.component.html
        regulatory-result.component.scss

      graph-view/
        regulatory-graph-view.component.ts
        regulatory-graph-view.component.html
        regulatory-graph-view.component.scss

      document-browser/
        regulatory-document-browser.component.ts
        regulatory-document-browser.component.html
        regulatory-document-browser.component.scss
```

Frontend responsibilities:

- Ingest or register official documents.
- Show ingestion status and extracted structure counts.
- Inspect legal hierarchy: document > title > chapter > article > paragraph.
- Run hybrid retrieval tests with visible layer contributions.
- Display generated answers with obligations, definitions, and citations.
- Display source graph: parent/child hierarchy and cross-document references.
- Export the full JSON response for auditability.

---

## Ingestion Pipeline

### Step 1 - Document Acquisition

Supported inputs:

- PDF
- HTML
- Official regulatory repositories
- Manual uploads

Document-level metadata:

```json
{
  "source_url": "https://eur-lex.europa.eu/...",
  "source_path": "regulatory/dora/regulation-eu-2022-2554.pdf",
  "publication_date": "2022-12-27",
  "effective_date": "2025-01-17",
  "authority": "EU",
  "framework": "DORA",
  "document_type": "regulation",
  "jurisdiction": "EU",
  "language": "en",
  "version": "original",
  "official": true
}
```

### Step 2 - Structural Parsing

The parser should extract legal structure without an LLM whenever possible. PDF and HTML adapters should normalize the source into a common `RegulatoryDocument` object.

Each legal element becomes a node with a stable canonical ID.

Example node path:

```text
DORA > Chapter II > Article 6 > Paragraph 1
```

Example persisted node:

```json
{
  "node_id": "dora.article_6.paragraph_1",
  "document_id": 1,
  "parent_node_id": "dora.article_6",
  "node_type": "paragraph",
  "label": "Article 6(1)",
  "title": "ICT risk management framework",
  "ordinal": "1",
  "text": "Financial entities shall have a sound, comprehensive and well-documented ICT risk management framework...",
  "page_start": 18,
  "page_end": 18,
  "path": ["DORA", "Chapter II", "Article 6", "Paragraph 1"]
}
```

### Step 3 - Legal Chunking

Chunks must be created from legal semantics, not arbitrary token windows. Legal chunks are retrieval units and must point back to legal nodes.

Chunk types:

- `definition`
- `obligation`
- `requirement`
- `exemption`
- `reporting_rule`
- `governance_rule`
- `third_party_risk_clause`
- `incident_management_rule`
- `supervisory_power`
- `cross_reference_context`

Example chunk:

```json
{
  "chunk_id": "dora.article_6.paragraph_1.obligation_1",
  "document_id": 1,
  "node_id": "dora.article_6.paragraph_1",
  "chunk_type": "obligation",
  "content": "Financial entities shall maintain a sound, comprehensive and well-documented ICT risk management framework.",
  "metadata": {
    "framework": "DORA",
    "authority": "EU",
    "document_type": "regulation",
    "article": "6",
    "paragraph": "1",
    "topic": "ICT Risk Management",
    "mandatory": true,
    "applies_to": ["financial_entity"]
  },
  "token_count": 31
}
```

Only chunks are embedded. Nodes, obligations, definitions, and relationships remain independently queryable as structured data.

### Step 4 - Ingestion-Time LLM Enrichment

For each article or logical section, the LLM extracts structured enrichment. The prompt must return strict JSON and the service must validate it with Pydantic before persistence.

Enrichment categories:

- Obligations
- Definitions
- Regulatory entities
- Cross-references
- Topics
- Keywords
- Applicability
- Deadlines or reporting windows
- Evidence expectations, when explicitly stated or strongly implied

Example enrichment JSON:

```json
{
  "article_id": "dora.article_6",
  "obligations": [
    {
      "obligation_id": "dora.article_6.obligation_1",
      "subject": "financial_entity",
      "action": "maintain",
      "object": "ICT risk management framework",
      "modality": "mandatory",
      "condition": null,
      "deadline": null,
      "evidence_hint": "documented ICT risk management framework",
      "source_node_ids": ["dora.article_6.paragraph_1"]
    }
  ],
  "definitions": [],
  "entities": ["financial_entity"],
  "cross_references": [
    {
      "reference_text": "Article 5",
      "target_framework": "DORA",
      "target_node_hint": "dora.article_5",
      "relationship_type": "references"
    }
  ],
  "topics": ["ICT Risk Management", "Governance"],
  "keywords": ["ICT risk", "framework", "financial entity", "governance"]
}
```

---

## Storage Model

The current `documents` and `chunks` tables can be generalized, but the regulatory domain needs additional structure. Recommended tables:

### `regulatory_documents`

Stores document-level metadata and provenance.

Key fields:

- `id`
- `source_url`
- `source_path`
- `authority`
- `framework`
- `document_type`
- `jurisdiction`
- `publication_date`
- `effective_date`
- `language`
- `version`
- `official`
- `metadata` JSONB

### `regulatory_nodes`

Stores legal hierarchy.

Key fields:

- `id`
- `document_id`
- `parent_node_id`
- `node_type`
- `canonical_id`
- `label`
- `title`
- `ordinal`
- `text`
- `page_start`
- `page_end`
- `path` JSONB
- `metadata` JSONB

### `regulatory_chunks`

Stores legal retrieval units. This is the only table that receives embeddings.

Key fields:

- `id`
- `document_id`
- `node_id`
- `chunk_type`
- `content`
- `embedding Vector(1536)`
- `token_count`
- `metadata` JSONB

### `regulatory_obligations`

Stores normalized obligations extracted by the LLM.

Key fields:

- `id`
- `obligation_id`
- `document_id`
- `node_id`
- `subject`
- `action`
- `object`
- `modality`
- `condition`
- `deadline`
- `evidence_hint`
- `metadata` JSONB

### `regulatory_definitions`

Stores legal definitions and aliases.

Key fields:

- `id`
- `term`
- `normalized_term`
- `definition_text`
- `document_id`
- `node_id`
- `framework`
- `aliases` JSONB

### `regulatory_relationships`

Stores graph edges.

Relationship types:

- `parent_of`
- `child_of`
- `references`
- `implements`
- `amends`
- `defines`
- `depends_on`
- `supersedes`
- `related_topic`

Key fields:

- `id`
- `source_node_id`
- `target_node_id`
- `source_document_id`
- `target_document_id`
- `relationship_type`
- `reference_text`
- `confidence`
- `metadata` JSONB

### Indexing

Recommended indexes:

- B-tree on `framework`, `authority`, `document_type`, `canonical_id`, `node_type`, `chunk_type`
- GIN on JSONB metadata fields
- Full-text index for BM25/keyword search over node and chunk text
- pgvector HNSW index for `regulatory_chunks.embedding` using cosine ops once corpus size justifies it

---

## JSON Contracts

### Ingestion Request

```json
{
  "source": {
    "source_type": "pdf",
    "source_url": "https://eur-lex.europa.eu/...",
    "source_path": "regulatory/dora/dora.pdf",
    "content_base64": null
  },
  "metadata": {
    "framework": "DORA",
    "authority": "EU",
    "document_type": "regulation",
    "jurisdiction": "EU",
    "publication_date": "2022-12-27",
    "effective_date": "2025-01-17",
    "language": "en",
    "official": true
  },
  "options": {
    "run_llm_enrichment": true,
    "embed_chunks": true,
    "replace_existing": false
  }
}
```

### Ingestion Response

```json
{
  "document_id": 1,
  "framework": "DORA",
  "nodes_created": 342,
  "chunks_created": 218,
  "obligations_created": 96,
  "definitions_created": 41,
  "relationships_created": 133,
  "embedding_model": "text-embedding-3-small",
  "embedding_dimension": 1536,
  "ingestion_time_ms": 42850,
  "warnings": []
}
```

### Regulatory Query

```json
{
  "query_text": "What ICT third-party risk obligations apply to financial entities under DORA?",
  "intent": "obligation_lookup",
  "frameworks": ["DORA"],
  "authorities": ["EU"],
  "document_types": ["regulation", "RTS"],
  "topics": ["Third Party Risk", "ICT Risk"],
  "article_refs": [],
  "entities": ["financial_entity"],
  "include_graph_neighbors": true,
  "top_k": 10,
  "distance_threshold": 0.35
}
```

### Hybrid Retrieval Response

```json
{
  "query": {
    "query_text": "What ICT third-party risk obligations apply to financial entities under DORA?",
    "intent": "obligation_lookup",
    "frameworks": ["DORA"],
    "topics": ["Third Party Risk", "ICT Risk"],
    "entities": ["financial_entity"]
  },
  "retrieval": {
    "low_confidence": false,
    "candidates_evaluated": 84,
    "results": [
      {
        "source_id": "src-dora.article_28.paragraph_1",
        "chunk_id": 512,
        "document_id": 1,
        "node_id": "dora.article_28.paragraph_1",
        "citation": "DORA Article 28(1)",
        "chunk_type": "obligation",
        "content": "Financial entities shall manage ICT third-party risk as an integral component of ICT risk within their ICT risk management framework.",
        "scores": {
          "metadata_score": 1.0,
          "graph_score": 0.8,
          "bm25_score": 0.72,
          "vector_similarity": 0.84,
          "final_score": 0.88
        },
        "matched_layers": ["metadata", "graph", "bm25", "vector"],
        "metadata": {
          "framework": "DORA",
          "authority": "EU",
          "article": "28",
          "paragraph": "1",
          "topic": "Third Party Risk",
          "mandatory": true
        }
      }
    ]
  }
}
```

### Context Assembly Response

```json
{
  "context_block": "[src-dora.article_28.paragraph_1] DORA Article 28(1): Financial entities shall manage ICT third-party risk...",
  "included_source_ids": ["src-dora.article_28.paragraph_1"],
  "included_obligation_ids": ["dora.article_28.obligation_1"],
  "included_definition_ids": ["dora.article_3.definition_ict_services"],
  "included_relationship_ids": ["rel-dora-28-rts-third-party-risk"],
  "token_count_estimate": 1420,
  "truncated": false
}
```

### Final Answer Response

```json
{
  "request_id": "req-123",
  "query_understanding": {
    "intent": "obligation_lookup",
    "frameworks": ["DORA"],
    "topics": ["Third Party Risk", "ICT Risk"]
  },
  "retrieval": {
    "low_confidence": false,
    "candidates_evaluated": 84,
    "results_count": 10
  },
  "answer": {
    "summary": "Under DORA, financial entities must treat ICT third-party risk as part of their ICT risk management framework and maintain governance over contractual, monitoring, exit, and concentration-risk controls.",
    "obligations": [
      {
        "obligation_id": "dora.article_28.obligation_1",
        "subject": "financial_entity",
        "action": "manage",
        "object": "ICT third-party risk",
        "modality": "mandatory",
        "citation": "DORA Article 28(1)",
        "source_ids": ["src-dora.article_28.paragraph_1"]
      }
    ],
    "definitions": [
      {
        "term": "ICT third-party service provider",
        "definition": "A provider of ICT services to financial entities.",
        "citation": "DORA Article 3"
      }
    ],
    "cross_references": [
      {
        "citation": "DORA Article 30",
        "relationship_type": "related_contractual_requirement"
      }
    ],
    "answer_markdown": "## Summary\nUnder DORA...",
    "sources": ["src-dora.article_28.paragraph_1"],
    "low_confidence": false
  },
  "idempotency_hit": false
}
```

---

## Retrieval Strategy

The regulatory retrieval strategy must be hybrid and layered.

### Layer 1 - Metadata Search

Filter and rank by structured metadata:

- Framework: DORA, NIS2, EBA ICT Guidelines, EBA Outsourcing Guidelines
- Authority: EU, EBA, ECB, ESMA, national authority
- Document type: regulation, directive, RTS, ITS, guideline, Q&A
- Jurisdiction
- Article or paragraph reference
- Topic
- Entity type
- Effective date

This layer should run before vector retrieval to reduce irrelevant candidates.

### Layer 2 - Knowledge Graph Search

Traverse persisted relationships:

- Parent/child legal hierarchy
- Article references
- Cross-framework references
- RTS/ITS implementation links
- Amendments and supersession
- Definitions used by obligations
- Related obligations under the same topic

Graph traversal should add related legal context even when the related node does not match the user query semantically.

### Layer 3 - BM25 / Keyword Search

Keyword retrieval is essential for legal text because exact terms matter:

- Article numbers
- Defined terms
- Regulatory phrases
- Authority names
- Modal verbs such as shall, must, may, should
- Specific terms such as major ICT-related incident, critical or important function, register of information

### Layer 4 - Vector Search

Use the same embedding stack as the current project:

- Embed query with `text-embedding-3-small`.
- Search only `regulatory_chunks.embedding`.
- Use cosine distance.
- Keep vectors independent from legal hierarchy.

### Layer 5 - Score Fusion And Reranking

Combine layer signals into a final score:

```text
final_score =
  0.30 * metadata_score +
  0.25 * graph_score +
  0.20 * bm25_score +
  0.25 * vector_similarity
```

Weights should be configurable and evaluated against test queries. For article-specific queries, metadata and BM25 should dominate. For conceptual queries, vector and graph scores can carry more weight.

### Layer 6 - Context Assembly

Assemble final context from:

- Top legal chunks
- Parent article text
- Related obligations
- Definitions for key terms
- Cross-references
- Relevant RTS/ITS implementation references
- Citation metadata

The context block sent to the LLM must preserve source IDs and citations.

---

## API Endpoints

Recommended AI-engine endpoints:

```text
POST /api/v1/regulatory/ingest
GET  /api/v1/regulatory/documents
GET  /api/v1/regulatory/documents/{document_id}/nodes
POST /api/v1/regulatory/retrieval
POST /api/v1/regulatory/stages/understand
POST /api/v1/regulatory/stages/retrieve
POST /api/v1/regulatory/stages/assemble
POST /api/v1/regulatory/stages/generate
POST /api/v1/regulatory/answer
GET  /api/v1/regulatory/graph/node/{node_id}
```

The backend can proxy these under:

```text
/v1/regulatory/...
```

This mirrors the current frontend convention where Angular talks to the business backend, and the backend calls `ai-engine` internally.

---

## Frontend Experience

### 1. Regulatory Ingestion

A compact operational screen for uploading or registering official sources.

Fields:

- Source type: PDF, HTML, URL, manual upload
- Source URL/path
- Framework
- Authority
- Document type
- Publication date
- Effective date
- Language
- Run enrichment toggle
- Embed chunks toggle

Result metrics:

- Document ID
- Nodes created
- Chunks created
- Obligations created
- Definitions created
- Relationships created
- Embedding model and dimension
- Warnings

### 2. Document Browser

A structured browser for legal hierarchy:

```text
DORA
  Chapter II - ICT risk management
    Article 5 - Governance and organisation
    Article 6 - ICT risk management framework
      Paragraph 1
      Paragraph 2
```

Each node view should show:

- Text
- Citation
- Extracted obligations
- Definitions
- Cross-references
- Related chunks

### 3. Regulatory Retrieval Lab

A diagnostic screen similar to the current RAG Lab, but with legal retrieval layers.

Controls:

- Query text
- Framework filter
- Authority filter
- Topic filter
- Article reference filter
- Top K
- Distance threshold
- Include graph neighbors
- Layer weights, optional advanced mode

Results:

- Final ranked list
- Matched retrieval layers
- Per-layer scores
- Citation
- Chunk text
- Metadata tags

### 4. Regulatory Answer Form

A user-facing query form for banking regulatory questions.

Inputs:

- Question
- Frameworks
- Topics
- Entity type
- Output mode: answer, obligations list, comparison, evidence checklist
- Top K
- Include cross-references

### 5. Regulatory Result View

Tabs:

- Answer
- Obligations
- Definitions
- Retrieved Sources
- Graph References
- Pipeline Stages
- JSON Export

The result must emphasize traceability:

- Every obligation links to citations.
- Every citation maps to a legal node.
- Retrieved chunks show matched layers and scores.
- Low-confidence responses are visibly flagged.

---

## Implementation Phases

### Phase 1 - Corpus Foundation

- Add regulatory schemas.
- Add document/node/chunk/obligation/relationship tables.
- Implement PDF/HTML acquisition adapters.
- Implement structural parser for headings, articles, paragraphs, and points.
- Persist legal hierarchy without embeddings first.

### Phase 2 - Legal Chunking And Embeddings

- Implement legal chunker.
- Reuse `text-embedding-3-small` and `Vector(1536)`.
- Persist embeddings only on regulatory chunks.
- Add metadata filters for framework, authority, document type, topic, and article.

### Phase 3 - Enrichment

- Add ingestion-time LLM enrichment prompts.
- Persist obligations, definitions, entities, topics, keywords, and references.
- Add validation and repair for malformed enrichment JSON.

### Phase 4 - Hybrid Retrieval

- Implement metadata retriever.
- Implement graph retriever.
- Implement BM25/full-text retriever.
- Reuse vector retriever.
- Add score fusion and layer explanations.

### Phase 5 - Context Assembly And Answering

- Build regulatory context assembler.
- Add grounded answer prompt.
- Add citation validator for legal node IDs and source IDs.
- Add full `/regulatory/answer` orchestration endpoint.

### Phase 6 - Frontend

- Add regulatory ingestion screen.
- Add document browser.
- Add retrieval lab.
- Add answer form and result view.
- Add JSON export and graph inspection.

---

## Testing Strategy

Unit tests:

- Structural parser detects articles, paragraphs, points, and annexes.
- Legal chunker emits stable chunk types.
- Enrichment schemas reject malformed LLM output.
- Citation normalizer resolves common article formats.
- Hybrid score fusion behaves deterministically.

Integration tests:

- Ingest one sample regulatory document end to end.
- Verify nodes, chunks, obligations, relationships, and embeddings are persisted.
- Query by exact article reference.
- Query by topic.
- Query by obligation subject.
- Verify graph expansion includes referenced articles.
- Verify answer contains only valid source IDs.

Evaluation set:

- Article lookup queries
- Obligation extraction queries
- Definition queries
- Cross-framework comparison queries
- Third-party risk queries
- Incident reporting deadline queries
- Governance accountability queries

---

## Expected Benefits

Compared with a chunk-only RAG system, this regulatory corpus provides:

- Better precision for legal questions
- Better traceability through exact legal nodes
- Better citation quality
- Better explainability through layer scores
- Better support for GraphRAG
- Reduced hallucinations
- Stronger handling of cross-references
- Reusable structured obligations and definitions
- Runtime efficiency because LLM enrichment is done once at ingestion

The result is a structured banking regulatory knowledge base, not just a collection of embedded fragments.
