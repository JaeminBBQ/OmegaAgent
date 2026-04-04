"""PDF parsing and text extraction for research papers."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFParser:
    """Parse PDF files and extract metadata and text."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """Initialize parser with chunking parameters.
        
        Args:
            chunk_size: Target size for text chunks (in characters)
            chunk_overlap: Overlap between chunks for context continuity
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_metadata(self, pdf_path: Path) -> Dict[str, any]:
        """Extract metadata from PDF.
        
        Returns:
            Dict with title, authors, year, doi, page_count
        """
        doc = pymupdf.open(pdf_path)
        metadata = doc.metadata or {}
        
        # Extract basic metadata
        title = metadata.get("title", "")
        authors = metadata.get("author", "")
        
        # If no title in metadata, try to extract from first page
        if not title:
            title = self._extract_title_from_first_page(doc)
        
        # Parse authors into list
        author_list = self._parse_authors(authors)
        
        # Try to extract year from metadata or first page
        year = self._extract_year(doc, metadata)
        
        # Try to extract DOI
        doi = self._extract_doi(doc)
        
        page_count = len(doc)
        
        doc.close()
        
        return {
            "title": title or pdf_path.stem,  # Fallback to filename
            "authors": author_list,
            "year": year,
            "doi": doi,
            "page_count": page_count,
        }

    def extract_text_chunks(
        self,
        pdf_path: Path,
    ) -> List[Dict[str, any]]:
        """Extract text from PDF and chunk it.
        
        Returns:
            List of dicts with: content, page_number, chunk_index
        """
        doc = pymupdf.open(pdf_path)
        
        # Extract text from all pages
        full_text = ""
        page_boundaries = [0]  # Track where each page starts in full_text
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            full_text += text + "\n\n"
            page_boundaries.append(len(full_text))
        
        doc.close()
        
        # Chunk the text
        chunks = self._chunk_text(full_text, page_boundaries)
        
        return chunks

    def compute_content_hash(self, pdf_path: Path) -> str:
        """Compute SHA256 hash of first 5 pages for duplicate detection."""
        doc = pymupdf.open(pdf_path)
        
        # Extract text from first 5 pages
        text = ""
        for page_num in range(min(5, len(doc))):
            page = doc[page_num]
            text += page.get_text()
        
        doc.close()
        
        # Compute hash
        return hashlib.sha256(text.encode()).hexdigest()

    def _extract_title_from_first_page(self, doc: pymupdf.Document) -> str:
        """Try to extract title from first page using heuristics."""
        if len(doc) == 0:
            return ""
        
        first_page = doc[0]
        
        # Method 1: Find text with largest font size
        blocks = first_page.get_text("dict")["blocks"]
        
        # Collect all text at each font size
        font_texts = {}
        for block in blocks:
            if "lines" not in block:
                continue
            
            for line in block["lines"]:
                for span in line["spans"]:
                    font_size = span.get("size", 0)
                    text = span.get("text", "").strip()
                    if text and font_size > 0:
                        if font_size not in font_texts:
                            font_texts[font_size] = []
                        font_texts[font_size].append(text)
        
        # Get text from largest font size
        if font_texts:
            max_font_size = max(font_texts.keys())
            title_parts = font_texts[max_font_size]
            title_text = " ".join(title_parts)
            
            # Clean up and validate
            title_text = re.sub(r'\s+', ' ', title_text).strip()
            
            # Check if it looks like a valid title (at least 10 chars, not all numbers)
            if len(title_text) >= 10 and not title_text.replace(' ', '').isdigit():
                return title_text[:200]
        
        # Method 2: Fallback - extract first substantial line from plain text
        plain_text = first_page.get_text()
        lines = [line.strip() for line in plain_text.split('\n') if line.strip()]
        
        for line in lines[:10]:  # Check first 10 lines
            # Skip very short lines, page numbers, dates
            if len(line) >= 15 and not re.match(r'^[\d\s\-/]+$', line):
                return line[:200]
        
        return ""

    def _parse_authors(self, authors_str: str) -> List[str]:
        """Parse author string into list."""
        if not authors_str:
            return []
        
        # Split by common delimiters
        authors = re.split(r'[,;]|\sand\s', authors_str)
        
        # Clean and filter
        authors = [a.strip() for a in authors if a.strip()]
        
        return authors[:10]  # Limit to 10 authors

    def _extract_year(
        self,
        doc: pymupdf.Document,
        metadata: Dict,
    ) -> Optional[int]:
        """Extract publication year."""
        # Try metadata first
        creation_date = metadata.get("creationDate", "")
        if creation_date:
            year_match = re.search(r'(\d{4})', creation_date)
            if year_match:
                year = int(year_match.group(1))
                if 1900 <= year <= 2100:
                    return year
        
        # Try first page
        if len(doc) > 0:
            text = doc[0].get_text()
            # Look for 4-digit year in first 1000 chars
            year_matches = re.findall(r'\b(19\d{2}|20\d{2})\b', text[:1000])
            if year_matches:
                return int(year_matches[0])
        
        return None

    def _extract_doi(self, doc: pymupdf.Document) -> Optional[str]:
        """Extract DOI from PDF."""
        if len(doc) == 0:
            return None
        
        # Check first 2 pages
        for page_num in range(min(2, len(doc))):
            text = doc[page_num].get_text()
            
            # DOI pattern: 10.xxxx/xxxxx
            doi_match = re.search(r'10\.\d{4,}/[^\s]+', text)
            if doi_match:
                doi = doi_match.group(0)
                # Clean up trailing punctuation
                doi = re.sub(r'[.,;)\]]+$', '', doi)
                return doi
        
        return None

    def _chunk_text(
        self,
        text: str,
        page_boundaries: List[int],
    ) -> List[Dict[str, any]]:
        """Chunk text with overlap, tracking page numbers."""
        chunks = []
        chunk_index = 0
        start = 0
        
        while start < len(text):
            # Find chunk end
            end = start + self.chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end in last 100 chars
                search_start = max(start, end - 100)
                sentence_end = text.rfind('. ', search_start, end)
                if sentence_end != -1:
                    end = sentence_end + 1
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                # Find which page this chunk is on
                page_num = 0
                for i, boundary in enumerate(page_boundaries):
                    if start >= boundary:
                        page_num = i
                
                chunks.append({
                    "content": chunk_text,
                    "page_number": page_num,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1
            
            # Move to next chunk with overlap
            start = end - self.chunk_overlap
            if start <= 0:
                start = end
        
        return chunks
