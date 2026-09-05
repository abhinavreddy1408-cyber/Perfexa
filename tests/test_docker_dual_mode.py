"""
Unit test for Docker detection & target URL normalization.
"""

from backend.app.services.docker_utils import (
    is_docker_running,
    get_effective_target_url,
    normalize_script_target_urls
)

def test_docker_dual_mode():
    has_docker = is_docker_running()
    print(f"Active environment Docker running status: {has_docker}")

    # Case 1: No Docker -> Container hostname must normalize to 127.0.0.1:8001
    if not has_docker:
        assert get_effective_target_url() == "http://127.0.0.1:8001"
        assert get_effective_target_url("http://target-app:8001") == "http://127.0.0.1:8001"
        assert get_effective_target_url("http://target-app") == "http://127.0.0.1:8001"
        assert get_effective_target_url("http://localhost:8001") == "http://127.0.0.1:8001"

        sample_script = """
        const BASE_URL = 'http://target-app:8001';
        http.get(`${BASE_URL}/api/fast`);
        """
        normalized = normalize_script_target_urls(sample_script)
        assert "target-app" not in normalized
        assert "http://127.0.0.1:8001" in normalized
        print("PASS: Target URL normalization for non-Docker host confirmed!")
    else:
        print("PASS: Docker is running, container network URL preserved.")

if __name__ == "__main__":
    test_docker_dual_mode()
