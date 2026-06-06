from __future__ import annotations

import tiktoken

from app.embedding_pipeline.schemas import Budget, Chunk


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text using a fixed-size sliding window over characters."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step

    return chunks


class JSONStructuralChunker:
    """
    Chunker that creates one chunk per budget component.
    
    Granularity: one BudgetComponent = one Chunk.
    Chunks include parent budget context and component details.
    Metadata is filterable and not embedded.
    """

    def __init__(self) -> None:
        """Initialize the chunker with tiktoken encoder."""
        self.encoder = tiktoken.encoding_for_model("text-embedding-3-small")

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        """
        Convert budgets into chunks where each component becomes a chunk.
        
        Args:
            budgets: List of Budget objects to chunk.
            
        Returns:
            List of Chunk objects, one per BudgetComponent.
        """
        chunks: list[Chunk] = []
        
        for budget in budgets:
            for component in budget.components:
                # Build chunk text with parent budget context and component details
                chunk_text = self._build_chunk_text(budget, component)
                
                # Calculate token count
                token_count = len(self.encoder.encode(chunk_text))
                
                # Build metadata (filterable, not embedded)
                metadata = {
                    "budget_id": budget.budget_id,
                    "component_id": component.component_id,
                    "client_sector": budget.client_metadata.sector,
                    "main_technology": budget.main_technology,
                    "year": budget.year,
                    "complexity": component.complexity,
                    "estimated_hours": component.estimated_hours,
                }
                
                # Create chunk
                chunk = Chunk(
                    chunk_id=f"{budget.budget_id}::{component.component_id}",
                    text=chunk_text,
                    metadata=metadata,
                    token_count=token_count,
                )
                
                chunks.append(chunk)
        
        return chunks

    def _build_chunk_text(self, budget: Budget, component) -> str:
        """
        Build the chunk text with budget context and component details.
        
        This combines parent budget context with component-level details
        to avoid losing context about which client/sector/year a component belongs to.
        """
        tech_stack_str = ", ".join(component.tech_stack) if component.tech_stack else "N/A"
        
        text = (
            f"[Project: {budget.project_summary}]\n"
            f"[Client sector: {budget.client_metadata.sector} | Year: {budget.year} | Main tech: {budget.main_technology}]\n"
            f"\n"
            f"Component: {component.name}\n"
            f"Description: {component.description}\n"
            f"Tech stack: {tech_stack_str}\n"
            f"Complexity: {component.complexity}\n"
            f"Estimated hours: {component.estimated_hours}"
        )
        
        return text
