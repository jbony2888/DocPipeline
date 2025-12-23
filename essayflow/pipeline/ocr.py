"""
OCR provider abstraction with stub implementation.
Real OCR providers can be added later by implementing the OcrProvider protocol.
"""

from typing import Protocol
from pipeline.schema import OcrResult


class OcrProvider(Protocol):
    """Protocol for OCR providers."""
    
    def process_image(self, image_path: str) -> OcrResult:
        """Process an image and return OCR results."""
        ...


class StubOcrProvider:
    """
    Stub OCR provider that simulates handwritten text recognition.
    Returns realistic handwritten-style output with typical OCR characteristics.
    """
    
    def process_image(self, image_path: str) -> OcrResult:
        """
        Simulates OCR processing of handwritten essay submission.
        
        Args:
            image_path: Path to image file (not actually read in stub)
            
        Returns:
            OcrResult with simulated handwritten text
        """
        # Simulate typical handwritten essay submission
        simulated_text = """Name: Andrick Vargas Hernandez
School: Lincoln Middle School
Grade: 8

My father has always been someone I look up to. He came to this country
with nothing but hope and determination. When I was young, I remember
watching him leave for work before sunrise and return after dark.

He worked construction jobs, sometimes two or three at a time, to make
sure our family had everything we needed. Even when he was tired, he
would help me with my homework and tell me stories about his childhood
in Mexico.

What inspires me most is how he never complained. He taught me that
hard work and education are the keys to success. Because of him, I
want to become an engineer and build things that help people, just
like he does every day.

My father may not have a college degree, but he is the smartest and
bravest person I know. He is my hero."""

        lines = simulated_text.strip().split('\n')
        
        return OcrResult(
            text=simulated_text.strip(),
            confidence_avg=0.65,  # Typical for handwriting
            lines=lines
        )


def get_ocr_provider(name: str = "stub") -> OcrProvider:
    """
    Factory function to get OCR provider by name.
    
    Args:
        name: Provider name ("stub" for now)
        
    Returns:
        OcrProvider instance
    """
    if name == "stub":
        return StubOcrProvider()
    else:
        raise ValueError(f"Unknown OCR provider: {name}")

