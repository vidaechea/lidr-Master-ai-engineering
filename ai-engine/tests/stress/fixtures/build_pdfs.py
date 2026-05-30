"""Generate deterministic synthetic PDF attachments for stress testing.

This script produces four test files with predictable, constant sizes:
- attach_5kb.pdf (~5 KB)
- attach_20kb.pdf (~20 KB)
- attach_50kb.pdf (~50 KB)
- attach_100kb.pdf (~100 KB)

The files contain repetitive, deterministic content so that regeneration
always produces byte-identical files. These are used for load testing to
simulate attachment processing overhead.

Usage:
    python build_pdfs.py

Output:
    - Creates PDF files in the same directory as this script
    - Safe to run multiple times (overwrites existing files)
    - Files are deterministic: same input → same bytes
"""

from pathlib import Path


LOREM_IPSUM = """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.\n"""


def main() -> None:
    """Generate all four synthetic PDF files with deterministic content."""
    script_dir = Path(__file__).parent
    
    # Define target sizes (in bytes) and repetitions to achieve them
    # empirically determined: 1 repetition of LOREM_IPSUM + \n = ~507 bytes
    configs = [
        (5, "attach_5kb.pdf", 5 * 1024),       # 5 KB
        (20, "attach_20kb.pdf", 20 * 1024),    # 20 KB
        (50, "attach_50kb.pdf", 50 * 1024),    # 50 KB
        (100, "attach_100kb.pdf", 100 * 1024), # 100 KB
    ]
    
    for target_kb, filename_str, target_bytes in configs:
        filename = script_dir / filename_str
        
        # Create deterministic text content
        # Each LOREM_IPSUM line is ~507 bytes, so calculate repetitions
        bytes_per_repetition = len(LOREM_IPSUM.encode('utf-8'))
        repetitions = (target_bytes // bytes_per_repetition) + 1
        
        content_text = LOREM_IPSUM * repetitions
        
        # Encode and truncate to exact target size
        content_bytes = content_text.encode('utf-8')[:target_bytes]
        
        # Pad with zeros if needed to reach exact target
        if len(content_bytes) < target_bytes:
            content_bytes += b'\x00' * (target_bytes - len(content_bytes))
        
        filename.write_bytes(content_bytes)
        actual_size_kb = len(content_bytes) / 1024
        print(f"✓ {filename_str}: {actual_size_kb:.2f} KB")


if __name__ == "__main__":
    main()
