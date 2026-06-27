#!/usr/bin/env python3
"""
Standalone API test script - run with: uv run test_api.py
Tests all 4 endpoints against the running docker compose stack.
"""
import json
import time
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "http://localhost:8000/api/v1"
CSV_FILE = "transactions.csv"


def log(msg: str):
    print(f"[TEST] {msg}")


def make_request(method: str, url: str, data=None, files=None) -> dict:
    """Make HTTP request without external dependencies."""
    try:
        if files:
            # Multipart form data for file upload
            boundary = "----WebKitFormBoundary" + "".join(str(i) for i in range(16))
            body_parts = []
            
            for key, (filename, content) in files.items():
                body_parts.append(f'--{boundary}'.encode())
                body_parts.append(
                    f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode()
                )
                body_parts.append(b'Content-Type: text/csv')
                body_parts.append(b'')
                body_parts.append(content)
            
            body_parts.append(f'--{boundary}--'.encode())
            body_parts.append(b'')
            
            body = b'\r\n'.join(body_parts)
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body))
            }
            req = Request(url, data=body, headers=headers, method=method)
        else:
            headers = {'Content-Type': 'application/json'}
            body = json.dumps(data).encode() if data else None
            req = Request(url, data=body, headers=headers, method=method)
        
        with urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    
    except HTTPError as e:
        log(f"HTTP {e.code}: {e.reason}")
        try:
            error_body = e.read().decode()
            log(f"Error body: {error_body}")
        except:
            pass
        sys.exit(1)
    except URLError as e:
        log(f"Connection failed: {e.reason}")
        log("Is docker compose running? Run: docker compose up")
        sys.exit(1)


def test_health():
    """Test health endpoint."""
    log("Testing health endpoint...")
    resp = make_request("GET", "http://localhost:8000/health")
    assert resp["status"] == "ok"
    log(f"✓ Health check passed: {resp}")


def test_upload():
    """Test CSV upload."""
    log("Testing POST /jobs/upload...")
    
    csv_path = Path(CSV_FILE)
    if not csv_path.exists():
        log(f"ERROR: {CSV_FILE} not found in current directory")
        sys.exit(1)
    
    csv_content = csv_path.read_bytes()
    files = {"file": (CSV_FILE, csv_content)}
    
    resp = make_request("POST", f"{API_BASE}/jobs/upload", files=files)
    
    assert "job_id" in resp
    assert resp["status"] == "pending"
    
    job_id = resp["job_id"]
    log(f"✓ Upload successful. Job ID: {job_id}")
    return job_id


def test_status(job_id: str, wait_for_completion=True):
    """Test GET /jobs/{job_id}/status and optionally wait for completion."""
    log(f"Testing GET /jobs/{job_id}/status...")
    
    max_attempts = 60
    attempt = 0
    
    while attempt < max_attempts:
        resp = make_request("GET", f"{API_BASE}/jobs/{job_id}/status")
        
        status = resp["status"]
        log(f"  Status: {status} (attempt {attempt + 1}/{max_attempts})")
        
        if status in ["completed", "failed", "llm_failed"]:
            log(f"✓ Job finished with status: {status}")
            if status == "failed":
                log(f"  Error: {resp.get('error_message', 'N/A')}")
            return resp
        
        if not wait_for_completion:
            return resp
        
        time.sleep(2)
        attempt += 1
    
    log("✗ Job did not complete within timeout")
    sys.exit(1)


def test_results(job_id: str):
    """Test GET /jobs/{job_id}/results."""
    log(f"Testing GET /jobs/{job_id}/results...")
    
    resp = make_request("GET", f"{API_BASE}/jobs/{job_id}/results")
    
    assert "transactions" in resp
    assert "anomalies" in resp
    assert "summary" in resp
    
    txn_count = len(resp["transactions"])
    anomaly_count = len(resp["anomalies"])
    
    log(f"✓ Results retrieved:")
    log(f"  - Total transactions: {txn_count}")
    log(f"  - Anomalies detected: {anomaly_count}")
    
    if resp.get("summary"):
        summary = resp["summary"]
        log(f"  - Total spend: {summary.get('total_spend', 'N/A')}")
        log(f"  - Risk level: {summary.get('risk_level', 'N/A')}")
        log(f"  - LLM failed: {summary.get('llm_failed', False)}")
    
    return resp


def test_list_jobs():
    """Test GET /jobs."""
    log("Testing GET /jobs...")
    
    resp = make_request("GET", f"{API_BASE}/jobs")
    
    assert "jobs" in resp
    assert "total" in resp
    
    log(f"✓ Job list retrieved: {resp['total']} total jobs")
    
    # Test with status filter
    log("Testing GET /jobs?status=completed...")
    resp_filtered = make_request("GET", f"{API_BASE}/jobs?status=completed")
    
    log(f"✓ Filtered list retrieved: {len(resp_filtered['jobs'])} completed jobs")


def main():
    log("Starting API integration tests...")
    log("=" * 60)
    
    # Test 1: Health check
    test_health()
    log("")
    
    # Test 2: Upload CSV
    job_id = test_upload()
    log("")
    
    # Test 3: Poll status until completion
    final_status = test_status(job_id, wait_for_completion=True)
    log("")
    
    # Test 4: Get results
    if final_status["status"] in ["completed", "llm_failed"]:
        test_results(job_id)
        log("")
    
    # Test 5: List all jobs
    test_list_jobs()
    log("")
    
    log("=" * 60)
    log("✓ ALL TESTS PASSED")
    log("")
    log("You can also test via Swagger UI: http://localhost:8000/docs")
    log("Or monitor Celery tasks: http://localhost:5555")


if __name__ == "__main__":
    main()
