"""Tests for file upload functionality."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from notebooklm_tools.core.exceptions import FileUploadError, FileValidationError


class TestFileValidation:
    """Test file validation before upload."""

    def test_nonexistent_file_raises_error(self):
        """Test that non-existent file raises FileValidationError."""
        from notebooklm_tools.core.sources import SourceMixin

        # Create a mock client with minimal setup
        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        with pytest.raises(FileValidationError, match="File not found"):
            client.add_file("test-notebook-id", "/nonexistent/file.pdf")

    def test_empty_file_raises_error(self):
        """Test that empty file raises FileValidationError."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(FileValidationError, match="empty"):
                client.add_file("test-notebook-id", temp_path)
        finally:
            Path(temp_path).unlink()

    def test_directory_raises_error(self):
        """Test that directory path raises FileValidationError."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        with tempfile.TemporaryDirectory() as tmpdir:  # noqa: SIM117
            with pytest.raises(FileValidationError, match="Not a regular file"):
                client.add_file("test-notebook-id", tmpdir)

    def test_unsupported_file_type_raises_error(self):
        """Test that unsupported file types raise FileValidationError."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        # Create a JSON file (unsupported type)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"test": "data"}')
            temp_path = f.name

        try:
            with pytest.raises(FileValidationError, match="Unsupported file type: .json"):
                client.add_file("test-notebook-id", temp_path)
        finally:
            Path(temp_path).unlink()

    # ──────────────────────────────────────────────────────────────────────
    # ATOM-2 (260515): auto_wrap_to_md — fence-wrap unsupported extensions
    # ──────────────────────────────────────────────────────────────────────

    def test_auto_wrap_default_is_strict(self):
        """`.py` + auto_wrap_to_md unset → existing FileValidationError (회귀 가드)."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello():\n    return 'world'\n")
            temp_path = f.name

        try:
            with pytest.raises(FileValidationError, match="Unsupported file type: .py"):
                client.add_file("test-notebook-id", temp_path)
        finally:
            Path(temp_path).unlink()

    def test_auto_wrap_unsupported_to_md_succeeds(self):
        """`.py` + auto_wrap_to_md=True → 3-step upload routed via {stem}.py.md."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        captured: dict[str, Any] = {}

        def _fake_register(notebook_id: str, filename: str) -> str:
            captured["filename"] = filename
            return "src-wrapped"

        def _fake_start(_nb_id: str, filename: str, file_size: int, _src_id: str) -> str:
            captured["upload_filename"] = filename
            captured["upload_size"] = file_size
            return "https://upload.example/url"

        def _fake_stream(_url: str, file_path: Path) -> None:
            captured["stream_path"] = Path(file_path)
            captured["stream_content"] = Path(file_path).read_text(encoding="utf-8")

        client._register_file_source = _fake_register  # type: ignore[attr-defined]
        client._start_resumable_upload = _fake_start  # type: ignore[attr-defined]
        client._upload_file_streaming = _fake_stream  # type: ignore[attr-defined]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def greet():\n    return 'hi'\n")
            temp_path = f.name

        try:
            result = client.add_file(
                "test-notebook-id", temp_path, auto_wrap_to_md=True
            )

            # Filename must be {stem}.py.md (matrix SSOT — 꼬리 .md = 가공 표식)
            assert captured["filename"].endswith(".py.md"), captured["filename"]
            assert captured["upload_filename"] == captured["filename"]
            assert result["title"] == captured["filename"]
            assert result["id"] == "src-wrapped"

            # Fence content must include python language hint + identifier banner
            content = captured["stream_content"]
            assert "```python" in content
            assert "def greet():" in content
            assert "Auto-fence-wrapped raw code" in content
        finally:
            Path(temp_path).unlink()

    def test_auto_wrap_uses_typescript_fence_for_ts(self):
        """`.ts` → fence with ``typescript`` language hint."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        captured: dict[str, str] = {}

        client._register_file_source = lambda _nb, _fn: "src-ts"  # type: ignore[attr-defined]
        client._start_resumable_upload = (  # type: ignore[attr-defined]
            lambda _nb, _fn, _sz, _sid: "https://upload.example/url"
        )

        def _capture_stream(_url: str, file_path: Path) -> None:
            captured["content"] = Path(file_path).read_text(encoding="utf-8")

        client._upload_file_streaming = _capture_stream  # type: ignore[attr-defined]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ts", delete=False, encoding="utf-8"
        ) as f:
            f.write("export const x: number = 1;\n")
            temp_path = f.name

        try:
            client.add_file("nb-1", temp_path, auto_wrap_to_md=True)
            assert "```typescript" in captured["content"]
        finally:
            Path(temp_path).unlink()

    def test_auto_wrap_cleanup_on_upload_failure(self):
        """Streaming upload failure → temp dir still cleaned up (try-finally)."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {}
        client.csrf_token = "test"
        client._session_id = "test"
        client._client = None

        captured: dict[str, Path] = {}

        client._register_file_source = lambda _nb, _fn: "src-fail"  # type: ignore[attr-defined]
        client._start_resumable_upload = (  # type: ignore[attr-defined]
            lambda _nb, _fn, _sz, _sid: "https://upload.example/url"
        )

        def _failing_stream(_url: str, file_path: Path) -> None:
            captured["wrapped_path"] = Path(file_path)
            raise FileUploadError("simulated network failure")

        client._upload_file_streaming = _failing_stream  # type: ignore[attr-defined]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("x = 1\n")
            temp_path = f.name

        try:
            with pytest.raises(FileUploadError, match="simulated network failure"):
                client.add_file("nb-1", temp_path, auto_wrap_to_md=True)

            # Load-bearing: temp dir must be cleaned up even on failure
            wrapped_path = captured["wrapped_path"]
            assert not wrapped_path.exists()
            assert not wrapped_path.parent.exists()
        finally:
            Path(temp_path).unlink()


class TestFileUploadProtocol:
    """Test the 3-step upload protocol."""

    def test_register_file_source_success(self):
        """Test successful file registration (step 1)."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None

        # Mock the HTTP client and response
        mock_response = Mock()
        mock_response.text = ')]}\'\n100\n[["wrb.fr","o4cbdc","[[[[\\"source-id-123\\"]]]]",null,null,null,"generic"]]'
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        mock_http_client = Mock()
        mock_http_client.post = Mock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):
            source_id = client._register_file_source("notebook-123", "test.pdf")

        assert source_id == "source-id-123"
        mock_http_client.post.assert_called_once()

    def test_register_file_source_failure(self):
        """Test file registration failure."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None

        # Mock response with no source ID
        mock_response = Mock()
        mock_response.text = ')]}\'\n100\n[["wrb.fr","o4cbdc","null",null,null,null,"generic"]]'
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        mock_http_client = Mock()
        mock_http_client.post = Mock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http_client):  # noqa: SIM117
            with pytest.raises(FileUploadError, match="Failed to get SOURCE_ID"):
                client._register_file_source("notebook-123", "test.pdf")

    def test_start_resumable_upload_success(self):
        """Test starting resumable upload session (step 2)."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None
        client.UPLOAD_URL = "https://notebooklm.google.com/upload/_/"

        # Mock response with upload URL
        mock_response = Mock()
        mock_response.headers = {"x-goog-upload-url": "https://upload.url/session123"}
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.post = Mock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch.object(client, "_get_httpx_cookies", return_value=httpx.Cookies()):
                upload_url = client._start_resumable_upload(
                    "notebook-123", "test.pdf", 1024, "source-id-123"
                )

        assert upload_url == "https://upload.url/session123"

    def test_start_resumable_upload_no_url(self):
        """Test upload session start without upload URL in response."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None
        client.UPLOAD_URL = "https://notebooklm.google.com/upload/_/"

        # Mock response without upload URL
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client.post = Mock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch.object(client, "_get_httpx_cookies", return_value=httpx.Cookies()):  # noqa: SIM117
                with pytest.raises(FileUploadError, match="Failed to get upload URL"):
                    client._start_resumable_upload(
                        "notebook-123", "test.pdf", 1024, "source-id-123"
                    )

    def test_upload_file_streaming_success(self):
        """Test streaming file upload (step 3)."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content for upload")
            temp_path = Path(f.name)

        try:
            # Mock successful upload
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()

            with patch("httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.__enter__ = Mock(return_value=mock_client)
                mock_client.__exit__ = Mock(return_value=False)
                mock_client.post = Mock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                with patch.object(client, "_get_httpx_cookies", return_value=httpx.Cookies()):
                    client._upload_file_streaming("https://upload.url/session123", temp_path)

            # Verify post was called
            mock_client.post.assert_called_once()
        finally:
            temp_path.unlink()


class TestAddFileIntegration:
    """Test the full add_file method integration."""

    def test_add_file_orchestrates_three_steps(self):
        """Test that add_file correctly orchestrates all three steps."""
        from notebooklm_tools.core.sources import SourceMixin

        client = SourceMixin.__new__(SourceMixin)
        client.cookies = {"test": "cookie"}
        client.csrf_token = "test-csrf"
        client._session_id = "test-session"
        client._client = None

        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content")
            temp_path = Path(f.name)

        try:
            # Mock all three steps
            with (
                patch.object(
                    client, "_register_file_source", return_value="source-id-123"
                ) as mock_register,
                patch.object(
                    client, "_start_resumable_upload", return_value="https://upload.url/session"
                ) as mock_start,
                patch.object(client, "_upload_file_streaming") as mock_upload,
            ):
                result = client.add_file("notebook-123", temp_path)

            # Verify all three steps were called
            mock_register.assert_called_once_with("notebook-123", temp_path.name)
            mock_start.assert_called_once()
            mock_upload.assert_called_once_with("https://upload.url/session", temp_path)

            # Verify result
            assert result["id"] == "source-id-123"
            assert result["title"] == temp_path.name
        finally:
            temp_path.unlink()


@pytest.mark.e2e
class TestFileUploadE2E:
    """E2E tests for file upload - requires NOTEBOOKLM_E2E=1."""

    def test_upload_text_file(self, temp_notebook):
        """Test uploading a text file (requires real authentication)."""
        from notebooklm_tools.core.auth import load_cached_tokens
        from notebooklm_tools.core.client import NotebookLMClient

        # Load real auth
        tokens = load_cached_tokens()
        if not tokens:
            pytest.skip("No authentication tokens available")

        client = NotebookLMClient(
            cookies=tokens.cookies, csrf_token=tokens.csrf_token, session_id=tokens.session_id
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content for NotebookLM upload.")
            temp_path = f.name

        try:
            result = client.add_file(temp_notebook.id, temp_path)
            assert result["id"] is not None
            assert result["title"].endswith(".txt")
        finally:
            Path(temp_path).unlink()


@pytest.fixture
def temp_notebook():
    """Create a temporary notebook for E2E tests."""
    from notebooklm_tools.core.auth import load_cached_tokens
    from notebooklm_tools.core.client import NotebookLMClient

    # Load real auth
    tokens = load_cached_tokens()
    if not tokens:
        pytest.skip("No authentication tokens available")

    client = NotebookLMClient(
        cookies=tokens.cookies, csrf_token=tokens.csrf_token, session_id=tokens.session_id
    )
    notebook = client.create_notebook(title="Test Upload Notebook")

    yield notebook

    # Cleanup
    try:  # noqa: SIM105
        client.delete_notebook(notebook.id)
    except Exception:
        pass  # Ignore cleanup errors
