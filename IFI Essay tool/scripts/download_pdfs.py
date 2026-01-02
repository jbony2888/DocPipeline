#!/usr/bin/env python3
"""
download_pdfs.py

Robust bulk PDF downloader for Ninja Forms CSV exports.

USAGE EXAMPLES:

1. Auto-detect prefix mode (recommended):
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com --out ./downloads

2. Manual prefix mode:
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com \
       --prefix /wp-content/uploads/ninja-forms/ --out ./downloads

3. Dry run (preview URLs without downloading):
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com --dry-run

4. Force overwrite existing files:
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com --force

5. Limit downloads for testing:
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com --limit 10

6. Concurrent downloads (4 threads):
   python download_pdfs.py --csv nf-subs-2.csv --base https://example.com --concurrency 4
"""

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Optional
from urllib.parse import urljoin, quote

try:
    import requests
except ImportError:
    print("ERROR: requests library is required. Install with: pip install requests")
    sys.exit(1)


def normalize_path(path: str) -> str:
    """
    Normalize a relative path:
    - Strip leading/trailing whitespace
    - Remove leading slashes
    - Prevent path traversal
    - Normalize slashes
    """
    path = path.strip().strip('/')
    # Prevent path traversal
    path = path.replace('../', '').replace('..\\', '')
    # Normalize slashes
    path = path.replace('\\', '/')
    return path


def extract_pdf_paths_from_csv(csv_path: str) -> List[str]:
    """
    Extract all unique PDF paths from CSV, preserving first-seen order.
    Handles multiple paths per cell (comma/newline separated).
    """
    seen = set()
    paths = []
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            for cell in row:
                if not cell or not cell.strip():
                    continue
                
                # Split by comma or newline
                candidates = re.split(r'[,\n]+', cell)
                
                for candidate in candidates:
                    candidate = candidate.strip().strip('"\'')
                    
                    # Check if ends with .pdf (case-insensitive)
                    if candidate.lower().endswith('.pdf'):
                        normalized = normalize_path(candidate)
                        
                        if normalized and normalized not in seen:
                            seen.add(normalized)
                            paths.append(normalized)
    
    return paths


def construct_url(base: str, prefix: str, relative_path: str) -> str:
    """
    Construct full URL from base, prefix, and relative path.
    Safely encodes path segments without encoding slashes.
    """
    # Ensure base ends without slash
    base = base.rstrip('/')
    
    # Ensure prefix starts and ends with slash
    if prefix:
        if not prefix.startswith('/'):
            prefix = '/' + prefix
        if not prefix.endswith('/'):
            prefix = prefix + '/'
    
    # URL-encode path segments safely
    path_parts = relative_path.split('/')
    encoded_parts = [quote(part, safe='') for part in path_parts]
    encoded_path = '/'.join(encoded_parts)
    
    # Construct full URL
    full_url = f"{base}{prefix}{encoded_path}"
    
    return full_url


def detect_prefix(base: str, test_path: str, timeout: int = 10) -> Optional[str]:
    """
    Auto-detect the correct uploads prefix by testing common paths.
    Returns the first working prefix or None.
    """
    common_prefixes = [
        "/wp-content/uploads/ninja-forms/",
        "/wp-content/uploads/ninja_forms/",
        "/wp-content/uploads/ninjaforms/",
        "/wp-content/uploads/nf-uploads/",
        "/wp-content/uploads/nf_uploads/",
        "/wp-content/uploads/ninja-forms-uploads/",
        "/wp-content/uploads/",
    ]
    
    print(f"🔍 Auto-detecting prefix using test file: {test_path}")
    
    for prefix in common_prefixes:
        url = construct_url(base, prefix, test_path)
        print(f"   Trying: {prefix} ... ", end='', flush=True)
        
        try:
            # Try HEAD first
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 405:
                # HEAD not allowed, try GET with Range
                headers = {'Range': 'bytes=0-1023'}
                response = requests.get(url, headers=headers, timeout=timeout, 
                                      stream=True, allow_redirects=True)
            
            if response.status_code == 200:
                print(f"✅ SUCCESS")
                return prefix
            else:
                print(f"❌ {response.status_code}")
        
        except requests.exceptions.RequestException as e:
            print(f"❌ {type(e).__name__}")
    
    return None


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(url: str, output_path: Path, max_retries: int = 3, 
                 timeout: int = 30) -> Tuple[int, int, Optional[str]]:
    """
    Download a file with retries and exponential backoff.
    Returns: (status_code, bytes_downloaded, error_message)
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 200:
                # Create parent directories
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Download with streaming
                bytes_downloaded = 0
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                
                return (response.status_code, bytes_downloaded, None)
            else:
                return (response.status_code, 0, f"HTTP {response.status_code}")
        
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                return (0, 0, "Timeout after retries")
        
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                return (0, 0, str(e))
    
    return (0, 0, "Unknown error")


def download_single_pdf(args: Tuple[str, str, Path, bool]) -> dict:
    """
    Download a single PDF and return manifest row.
    Args: (relative_path, url, output_dir, force_overwrite)
    """
    relative_path, url, output_dir, force_overwrite = args
    
    output_path = output_dir / relative_path
    
    result = {
        'relative_path': relative_path,
        'final_url': url,
        'status_code': '',
        'bytes': '',
        'sha256': '',
        'saved_to': str(output_path),
        'error': ''
    }
    
    # Check if file exists
    if output_path.exists() and not force_overwrite:
        # Skip, but compute hash from existing file
        try:
            file_size = output_path.stat().st_size
            file_hash = compute_sha256(output_path)
            result['status_code'] = 'SKIPPED'
            result['bytes'] = str(file_size)
            result['sha256'] = file_hash
            return result
        except Exception as e:
            result['error'] = f"Error reading existing file: {e}"
            return result
    
    # Download
    status_code, bytes_downloaded, error = download_file(url, output_path)
    
    result['status_code'] = str(status_code) if status_code else 'ERROR'
    result['bytes'] = str(bytes_downloaded) if bytes_downloaded else ''
    
    if error:
        result['error'] = error
    elif status_code == 200 and output_path.exists():
        try:
            result['sha256'] = compute_sha256(output_path)
        except Exception as e:
            result['error'] = f"Downloaded but failed to compute hash: {e}"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Bulk PDF downloader for Ninja Forms exports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--csv', required=True, help='Path to CSV export')
    parser.add_argument('--base', required=True, help='Base site URL (e.g. https://example.com)')
    parser.add_argument('--prefix', help='Uploads prefix (e.g. /wp-content/uploads/ninja-forms/)')
    parser.add_argument('--out', default='./downloads', help='Output directory')
    parser.add_argument('--limit', type=int, help='Limit number of downloads')
    parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    parser.add_argument('--dry-run', action='store_true', help='Preview URLs without downloading')
    parser.add_argument('--concurrency', type=int, default=1, help='Number of concurrent downloads')
    
    args = parser.parse_args()
    
    # Validate CSV exists
    if not os.path.exists(args.csv):
        print(f"ERROR: CSV file not found: {args.csv}")
        sys.exit(1)
    
    # Extract PDF paths from CSV
    print(f"📄 Reading CSV: {args.csv}")
    pdf_paths = extract_pdf_paths_from_csv(args.csv)
    print(f"✅ Found {len(pdf_paths)} unique PDF paths")
    
    if not pdf_paths:
        print("ERROR: No PDF paths found in CSV")
        sys.exit(1)
    
    # Limit if specified
    if args.limit:
        pdf_paths = pdf_paths[:args.limit]
        print(f"🔢 Limited to {len(pdf_paths)} paths")
    
    # Auto-detect or use manual prefix
    if args.prefix:
        prefix = args.prefix
        print(f"✅ Using manual prefix: {prefix}")
    else:
        print(f"🔍 Auto-detecting prefix...")
        prefix = detect_prefix(args.base, pdf_paths[0])
        
        if not prefix:
            print("\n❌ ERROR: Could not auto-detect prefix.")
            print("   Please provide --prefix explicitly.")
            print("\n   Example: --prefix /wp-content/uploads/ninja-forms/")
            sys.exit(1)
        
        print(f"\n✅ Detected prefix: {prefix}")
    
    # Construct URLs
    urls = [(path, construct_url(args.base, prefix, path)) for path in pdf_paths]
    
    # Dry run mode
    if args.dry_run:
        print(f"\n🔍 DRY RUN - First 20 URLs:\n")
        for path, url in urls[:20]:
            print(f"   {path}")
            print(f"   → {url}\n")
        print(f"Total: {len(urls)} URLs")
        return
    
    # Create output directory
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download PDFs
    print(f"\n📥 Downloading {len(urls)} PDFs to {output_dir}...")
    print(f"   Concurrency: {args.concurrency}")
    print(f"   Force overwrite: {args.force}\n")
    
    manifest_rows = []
    missing_files = []
    
    # Prepare download args
    download_args = [(path, url, output_dir, args.force) for path, url in urls]
    
    if args.concurrency > 1:
        # Concurrent downloads
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {executor.submit(download_single_pdf, arg): arg[0] 
                      for arg in download_args}
            
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                manifest_rows.append(result)
                
                # Progress
                status = result['status_code']
                path = result['relative_path']
                
                if status == '200':
                    print(f"   [{i}/{len(urls)}] ✅ {path}")
                elif status == 'SKIPPED':
                    print(f"   [{i}/{len(urls)}] ⏭️  {path} (already exists)")
                else:
                    print(f"   [{i}/{len(urls)}] ❌ {path} - {result['error']}")
                    missing_files.append(f"{path} - {result['error']}")
    else:
        # Sequential downloads
        for i, arg in enumerate(download_args, 1):
            result = download_single_pdf(arg)
            manifest_rows.append(result)
            
            status = result['status_code']
            path = result['relative_path']
            
            if status == '200':
                print(f"   [{i}/{len(urls)}] ✅ {path}")
            elif status == 'SKIPPED':
                print(f"   [{i}/{len(urls)}] ⏭️  {path} (already exists)")
            else:
                print(f"   [{i}/{len(urls)}] ❌ {path} - {result['error']}")
                missing_files.append(f"{path} - {result['error']}")
    
    # Write manifest
    manifest_path = output_dir / 'download_manifest.csv'
    print(f"\n📝 Writing manifest to {manifest_path}")
    
    with open(manifest_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['relative_path', 'final_url', 'status_code', 'bytes', 'sha256', 'saved_to', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)
    
    # Write missing files
    if missing_files:
        missing_path = output_dir / 'missing.txt'
        print(f"📝 Writing {len(missing_files)} missing files to {missing_path}")
        
        with open(missing_path, 'w', encoding='utf-8') as f:
            for missing in missing_files:
                f.write(f"{missing}\n")
    
    # Summary
    success_count = sum(1 for r in manifest_rows if r['status_code'] == '200')
    skipped_count = sum(1 for r in manifest_rows if r['status_code'] == 'SKIPPED')
    failed_count = len(missing_files)
    
    print(f"\n✅ COMPLETE!")
    print(f"   Success: {success_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Failed: {failed_count}")
    print(f"\n📁 Output: {output_dir}")


if __name__ == '__main__':
    main()


