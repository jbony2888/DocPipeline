"""
Unit tests for PDF multi-entry detection and splitting.
"""

import os
import tempfile
import pytest
from pathlib import Path
from pipeline.pdf_splitter import (
    analyze_pdf_structure,
    detect_entry_boundaries,
    should_split_pdf,
    split_pdf_into_groups,
    _classify_page,
    _detect_page_pattern
)


def create_test_pdf(pages_content: list, output_path: str):
    """
    Create a test PDF with specified text content per page.
    
    Args:
        pages_content: List of text strings, one per page
        output_path: Path to save the PDF
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        pytest.skip("PyMuPDF not installed")
    
    pdf = fitz.open()
    
    for page_text in pages_content:
        # Create a new page (A4 size)
        page = pdf.new_page(width=595, height=842)
        
        # Insert text
        # Use a simple layout: text starting at (50, 50)
        rect = fitz.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, page_text, fontsize=11, align=0)
    
    pdf.save(output_path)
    pdf.close()


class TestPageClassification:
    """Test page classification logic."""
    
    def test_classify_metadata_page(self):
        """Test that metadata pages are correctly classified."""
        metadata_text = """
        Student Name: John Doe
        School: Lincoln Elementary
        Grade: 5
        Teacher: Ms. Smith
        Phone: 773-555-1234
        Email: parent@example.com
        """
        
        result = _classify_page(metadata_text)
        assert result == "metadata"
    
    def test_classify_essay_page(self):
        """Test that essay pages are correctly classified."""
        essay_text = """
        My father is the most important person in my life. He works very hard every day
        to provide for our family. When I was younger, he would wake up early every morning
        to make sure I had breakfast before school. He always helped me with my homework,
        even when he was tired from work. My father taught me the value of hard work and
        dedication. He came to this country with nothing, but through determination and
        perseverance, he built a good life for us. I want to be just like him when I grow up.
        He is my hero and my inspiration. Every day I learn something new from him about
        being a good person and working hard to achieve my dreams.
        """
        
        result = _classify_page(essay_text)
        assert result == "essay"
    
    def test_classify_unknown_page(self):
        """Test that ambiguous pages are classified as unknown."""
        ambiguous_text = "Page 1"
        
        result = _classify_page(ambiguous_text)
        assert result == "unknown"


class TestPatternDetection:
    """Test pattern detection logic."""
    
    def test_detect_metadata_essay_pattern(self):
        """Test detection of metadata-essay alternating pattern."""
        page_types = ["metadata", "essay", "metadata", "essay"]
        
        pattern, confidence = _detect_page_pattern(page_types)
        
        assert pattern == "metadata_essay"
        assert confidence >= 0.6
    
    def test_detect_essay_metadata_pattern(self):
        """Test detection of essay-metadata alternating pattern."""
        page_types = ["essay", "metadata", "essay", "metadata"]
        
        pattern, confidence = _detect_page_pattern(page_types)
        
        assert pattern == "essay_metadata"
        assert confidence >= 0.6
    
    def test_detect_no_pattern(self):
        """Test that inconsistent pages return no pattern."""
        page_types = ["metadata", "metadata", "essay", "essay"]
        
        pattern, confidence = _detect_page_pattern(page_types)
        
        # Should not detect a clear pattern
        assert confidence < 0.6 or pattern is None


class TestBoundaryDetection:
    """Test entry boundary detection."""
    
    def test_single_page_pdf(self):
        """Test that single-page PDFs are treated as single-entry."""
        pages_text = ["Some text"]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        assert len(groups) == 1
        assert groups[0] == (0, 0)
        assert confidence == 1.0
    
    def test_two_page_pdf(self):
        """Test that two-page PDFs are treated as single-entry."""
        pages_text = ["Page 1", "Page 2"]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        assert len(groups) == 1
        assert groups[0] == (0, 1)
        assert confidence == 1.0
    
    def test_four_page_multi_entry(self):
        """Test detection of 4-page PDF with 2 entries."""
        pages_text = [
            "Student Name: Alice\nSchool: Lincoln\nGrade: 5",  # Metadata
            "My father is amazing and wonderful. He works very hard every single day to provide for our family and make sure we have everything we need. When I was younger, he would wake up early every morning to make breakfast and help me get ready for school. Even when he was tired from working long hours, he always found time to help me with my homework and play games with me. I love my father very much and I am grateful for everything he does.",  # Essay
            "Student Name: Bob\nSchool: Washington\nGrade: 6",  # Metadata
            "My dad is my hero and my best friend. He teaches me so many important things about life and helps me become a better person every single day. He came to this country with nothing but hope and determination, and through hard work he built a good life for our family. I want to be just like him when I grow up because he is the strongest and kindest person I know."  # Essay
        ]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        assert len(groups) == 2
        assert groups[0] == (0, 1)
        assert groups[1] == (2, 3)
        assert confidence >= 0.6


class TestPDFAnalysis:
    """Test full PDF analysis."""
    
    def test_analyze_single_entry_pdf(self):
        """Test analysis of single-entry PDF."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Create 2-page PDF (single entry)
            pages = [
                "Student Name: Test Student\nSchool: Test School\nGrade: 5",
                "This is my essay about my father. He is great..."
            ]
            create_test_pdf(pages, tmp_path)
            
            analysis = analyze_pdf_structure(tmp_path)
            
            assert analysis.page_count == 2
            assert not analysis.is_multi_entry
            assert len(analysis.detected_groups) == 1
        finally:
            os.unlink(tmp_path)
    
    def test_analyze_multi_entry_pdf(self):
        """Test analysis of multi-entry PDF."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Create 4-page PDF (2 entries)
            pages = [
                "Student Name: Alice Smith\nSchool: Lincoln Elementary\nGrade: 5\nTeacher: Ms. Johnson",
                "My father works very hard every single day to provide for our family. He wakes up early in the morning before the sun rises and comes home late at night. Despite being tired, he always makes time to help me with my homework and play games with me on weekends.",
                "Student Name: Bob Martinez\nSchool: Washington Middle School\nGrade: 6\nTeacher: Mr. Davis",
                "My dad is my hero and my best friend. He came to this country when he was young and worked multiple jobs to support his family. He taught me the importance of education and hard work. Every day he shows me what it means to be a good person through his actions."
            ]
            create_test_pdf(pages, tmp_path)
            
            analysis = analyze_pdf_structure(tmp_path)
            
            assert analysis.page_count == 4
            assert analysis.is_multi_entry
            assert len(analysis.detected_groups) == 2
            assert analysis.confidence >= 0.7
        finally:
            os.unlink(tmp_path)
    
    def test_should_split_decision(self):
        """Test split decision logic."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Create clear multi-entry PDF
            pages = [
                "Student Name: Alice\nSchool: Test School\nGrade: 5\nPhone: 555-1234",
                "My father is wonderful. He works hard and cares for our family every single day. I am grateful for everything he does for us and I want to make him proud.",
                "Student Name: Bob\nSchool: Another School\nGrade: 6\nPhone: 555-5678",
                "My dad is my role model. He teaches me important lessons about life and helps me become a better person every day through his example and guidance."
            ]
            create_test_pdf(pages, tmp_path)
            
            analysis = analyze_pdf_structure(tmp_path)
            
            assert should_split_pdf(analysis)
        finally:
            os.unlink(tmp_path)


class TestPDFSplitting:
    """Test PDF splitting functionality."""
    
    def test_split_pdf_into_groups(self):
        """Test splitting a PDF into separate files."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        
        output_dir = tempfile.mkdtemp()
        
        try:
            # Create 4-page PDF
            pages = [
                "Student: Alice\nSchool: Lincoln\nGrade: 5",
                "Alice's essay content here...",
                "Student: Bob\nSchool: Washington\nGrade: 6",
                "Bob's essay content here..."
            ]
            create_test_pdf(pages, tmp_path)
            
            # Split into 2 groups
            groups = [(0, 1), (2, 3)]
            artifacts = split_pdf_into_groups(
                pdf_path=tmp_path,
                groups=groups,
                output_dir=output_dir,
                base_filename="test"
            )
            
            assert len(artifacts) == 2
            
            # Check first split
            assert artifacts[0].group_index == 0
            assert artifacts[0].page_start == 0
            assert artifacts[0].page_end == 1
            assert os.path.exists(artifacts[0].output_pdf_path)
            
            # Check second split
            assert artifacts[1].group_index == 1
            assert artifacts[1].page_start == 2
            assert artifacts[1].page_end == 3
            assert os.path.exists(artifacts[1].output_pdf_path)
            
            # Verify split PDFs have correct page counts
            import fitz
            pdf1 = fitz.open(artifacts[0].output_pdf_path)
            assert len(pdf1) == 2
            pdf1.close()
            
            pdf2 = fitz.open(artifacts[1].output_pdf_path)
            assert len(pdf2) == 2
            pdf2.close()
            
        finally:
            os.unlink(tmp_path)
            import shutil
            shutil.rmtree(output_dir)


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_odd_page_count(self):
        """Test that odd-page PDFs (>3) are treated as single-entry with low confidence."""
        pages_text = ["Page 1", "Page 2", "Page 3", "Page 4", "Page 5"]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        assert len(groups) == 1
        assert groups[0] == (0, 4)
        assert confidence < 0.7  # Low confidence for odd page count
    
    def test_three_page_pdf(self):
        """Test that 3-page PDFs are treated as single-entry."""
        pages_text = ["Page 1", "Page 2", "Page 3"]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        assert len(groups) == 1
        assert groups[0] == (0, 2)
    
    def test_ambiguous_pattern(self):
        """Test that ambiguous patterns result in single-entry with low confidence."""
        pages_text = [
            "Some text",
            "More text",
            "Even more text",
            "Final text"
        ]
        
        groups, confidence = detect_entry_boundaries(pages_text)
        
        # Should default to single-entry when pattern is unclear
        if confidence < 0.7:
            assert len(groups) == 1
