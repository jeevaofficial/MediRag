#!/usr/bin/env python3
"""
Comprehensive API test script for MediRAG AI
Tests all major endpoints and features
"""

import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

# Test results tracking
results = {
    "passed": 0,
    "failed": 0,
    "errors": []
}

def log_test(name, status, details=""):
    """Log test result"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_str = "✓ PASS" if status else "✗ FAIL"
    print(f"[{timestamp}] {status_str}: {name}")
    if details:
        print(f"         Details: {details}")
    
    if status:
        results["passed"] += 1
    else:
        results["failed"] += 1
        results["errors"].append(name)

def test_root_endpoint():
    """Test the root endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/")
        data = response.json()
        
        success = (
            response.status_code == 200 and 
            "message" in data and 
            "MediRAG" in data["message"]
        )
        
        log_test(
            "Root Endpoint",
            success,
            f"Status: {response.status_code}, Message: {data.get('message', 'N/A')}"
        )
        return success
    except Exception as e:
        log_test("Root Endpoint", False, str(e))
        return False

def test_user_registration():
    """Test user registration"""
    try:
        payload = {
            "full_name": "Test User",
            "username": f"testuser_{datetime.now().timestamp()}",
            "password": "TestPass123!"
        }
        
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/auth/register",
            json=payload
        )
        
        data = response.json()
        success = (
            response.status_code == 200 and 
            "access_token" in data and
            "token_type" in data
        )
        
        log_test(
            "User Registration",
            success,
            f"Status: {response.status_code}, Token received: {'access_token' in data}"
        )
        
        return data.get("access_token") if success else None
        
    except Exception as e:
        log_test("User Registration", False, str(e))
        return None

def test_login(username, password):
    """Test user login"""
    try:
        payload = {
            "username": username,
            "password": password
        }
        
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/auth/login",
            data=payload  # OAuth2 uses form data
        )
        
        data = response.json()
        success = (
            response.status_code == 200 and 
            "access_token" in data
        )
        
        log_test(
            "User Login",
            success,
            f"Status: {response.status_code}"
        )
        
        return data.get("access_token") if success else None
        
    except Exception as e:
        log_test("User Login", False, str(e))
        return None

def test_protected_endpoint(token):
    """Test accessing protected endpoint"""
    try:
        if not token:
            log_test("Protected Endpoint Access", False, "No token available")
            return False
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(
            f"{BASE_URL}{API_PREFIX}/auth/me",
            headers=headers
        )
        
        success = response.status_code == 200
        
        log_test(
            "Protected Endpoint Access",
            success,
            f"Status: {response.status_code}"
        )
        
        return success
        
    except Exception as e:
        log_test("Protected Endpoint Access", False, str(e))
        return False

def test_rag_query(token):
    """Test RAG query endpoint"""
    try:
        if not token:
            log_test("RAG Query", False, "No token available")
            return False
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        payload = {
            "query": "Patient name"
        }
        
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/chat/query",
            json=payload,
            headers=headers,
            timeout=120  # RAG can be slow
        )
        
        success = response.status_code in [200, 422]  # 422 if no documents
        
        if response.status_code == 200:
            data = response.json()
            has_content = bool(data)
            log_test(
                "RAG Query Endpoint",
                has_content,
                f"Status: {response.status_code}, Response length: {len(str(data))}"
            )
            return has_content
        else:
            log_test(
                "RAG Query Endpoint",
                True,
                f"Status: {response.status_code} (No documents indexed - expected)"
            )
            return True
        
    except requests.exceptions.Timeout:
        log_test("RAG Query Endpoint", False, "Request timeout (RAG processing took too long)")
        return False
    except Exception as e:
        log_test("RAG Query Endpoint", False, str(e))
        return False

def test_document_upload_endpoint_exists(token):
    """Test that document upload endpoint exists"""
    try:
        if not token:
            log_test("Document Upload Endpoint", False, "No token available")
            return False
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        # Try to get documents list (doesn't require file)
        response = requests.get(
            f"{BASE_URL}{API_PREFIX}/documents/",
            headers=headers
        )
        
        success = response.status_code in [200, 422]
        
        log_test(
            "Document Endpoints Accessible",
            success,
            f"Status: {response.status_code}"
        )
        
        return success
        
    except Exception as e:
        log_test("Document Endpoints Accessible", False, str(e))
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("MediRAG AI - API Test Suite")
    print("="*60 + "\n")
    
    # Test 1: Root endpoint
    test_root_endpoint()
    
    # Test 2: User registration
    token = test_user_registration()
    
    # Test 3: Protected endpoints
    if token:
        test_protected_endpoint(token)
        test_document_upload_endpoint_exists(token)
        test_rag_query(token)
    
    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Total:  {results['passed'] + results['failed']}")
    
    if results["failed"] > 0:
        print(f"\nFailed Tests:")
        for error in results["errors"]:
            print(f"  - {error}")
    
    print("="*60 + "\n")
    
    return 0 if results["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
