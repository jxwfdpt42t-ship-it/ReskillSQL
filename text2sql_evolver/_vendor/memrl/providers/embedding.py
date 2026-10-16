"""
Embedding provider implementations.

This module provides concrete implementations of the BaseEmbedder interface
for various embedding services including OpenAI, local models, etc.
"""

from typing import List, Optional, Any, Dict
import json
import threading
import time
from pathlib import Path
import numpy as np
from openai import OpenAI
try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except Exception:
    def retry(*args, **kwargs):
        def deco(fn):
            return fn
        return deco
    def stop_after_attempt(*args, **kwargs):
        return None
    def wait_exponential(*args, **kwargs):
        return None

from .base import BaseEmbedder, EmbedderError


class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI embedding provider using their embeddings API.
    
    Supports OpenAI's text-embedding models and any OpenAI-compatible
    embedding services.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "text-embedding-3-small",
        max_text_len: int = 8196,
        token_log_dir: Optional[str] = None,
        token_log_path: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Initialize OpenAI embedding provider.
        
        Args:
            api_key: API key for authentication
            base_url: Base URL for API (None for official OpenAI)
            model: Embedding model name
            max_text_len: Maximum characters allowed per query before chunking
            **kwargs: Additional configuration parameters
        """
        super().__init__(max_text_len=max_text_len, **kwargs)

        # Validate API key
        if not api_key or api_key.strip() == "":
            raise ValueError("API key cannot be empty")

        self.model = model
        self.base_url = base_url
        self._token_log_lock = threading.Lock()
        self._token_log_path = self._resolve_token_log_path(token_log_path, token_log_dir)

        # Initialize OpenAI client
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
            
        try:
            self.client = OpenAI(**client_kwargs)
        except Exception as e:
            raise EmbedderError(f"Failed to initialize OpenAI client: {e}")

    @staticmethod
    def _resolve_token_log_path(
        token_log_path: Optional[str],
        token_log_dir: Optional[str],
    ) -> Path:
        if token_log_path:
            path = Path(token_log_path)
        else:
            base_dir = token_log_dir or "local_cache"
            path = Path(base_dir) / "token_usage.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _usage_details_to_dict(details: Any) -> Dict[str, Any]:
        if details is None:
            return {}
        fields = [
            "reasoning_tokens",
            "audio_tokens",
            "text_tokens",
            "image_tokens",
            "cached_tokens",
            "accepted_prediction_tokens",
            "rejected_prediction_tokens",
        ]
        payload: Dict[str, Any] = {}
        for key in fields:
            val = getattr(details, key, None)
            if val is not None:
                payload[key] = val
        if payload:
            return payload
        try:
            if isinstance(details, dict):
                return details
            if hasattr(details, "model_dump"):
                return details.model_dump()
        except Exception:
            return {}
        return {}

    def _usage_to_dict(self, usage: Any) -> Dict[str, Any]:
        if usage is None:
            return {}
        payload: Dict[str, Any] = {}
        for key in ["prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"]:
            val = getattr(usage, key, None)
            if val is not None:
                payload[key] = val
        completion_details = getattr(usage, "completion_tokens_details", None)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        if completion_details is not None:
            payload["completion_tokens_details"] = self._usage_details_to_dict(completion_details)
        if prompt_details is not None:
            payload["prompt_tokens_details"] = self._usage_details_to_dict(prompt_details)
        if payload:
            return payload
        try:
            if isinstance(usage, dict):
                return usage
            if hasattr(usage, "model_dump"):
                return usage.model_dump()
        except Exception:
            return {}
        return {}

    def _log_token_usage(self, payload: Dict[str, Any]) -> None:
        if not self._token_log_path:
            return
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **payload}
        try:
            text = json.dumps(entry, ensure_ascii=False, default=str)
        except Exception:
            text = json.dumps({"ts": entry.get("ts"), "payload": str(payload)}, ensure_ascii=False)
        with self._token_log_lock:
            with open(self._token_log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for texts using OpenAI API.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbedderError: If embedding generation fails
        """
        if not texts:
            return []

        chunked_texts, counts = self._chunk_texts(texts)

        try:
            response = self.client.embeddings.create(
                input=chunked_texts,
                model=self.model
            )
            
            embeddings = [item.embedding for item in response.data]
            try:
                usage_payload = self._usage_to_dict(getattr(response, "usage", None))
                total_chars = sum(len(t) for t in texts if isinstance(t, str))
                total_chunk_chars = sum(len(t) for t in chunked_texts if isinstance(t, str))
                self._log_token_usage(
                    {
                        "provider": "embedding",
                        "model": getattr(response, "model", self.model),
                        "base_url": self.base_url,
                        "request_params": {
                            "input_count": len(texts),
                            "chunk_count": len(chunked_texts),
                        },
                        "prompt_stats": {
                            "input_chars": total_chars,
                            "chunk_chars": total_chunk_chars,
                        },
                        "usage": usage_payload,
                    }
                )
            except Exception:
                pass

            return self._merge_chunk_embeddings(embeddings, counts)
            
        except Exception as e:
            try:
                total_chars = sum(len(t) for t in texts if isinstance(t, str))
                total_chunk_chars = sum(len(t) for t in chunked_texts if isinstance(t, str))
                self._log_token_usage(
                    {
                        "provider": "embedding",
                        "model": self.model,
                        "base_url": self.base_url,
                        "request_params": {
                            "input_count": len(texts),
                            "chunk_count": len(chunked_texts),
                        },
                        "prompt_stats": {
                            "input_chars": total_chars,
                            "chunk_chars": total_chunk_chars,
                        },
                        "error": str(e),
                    }
                )
            except Exception:
                pass
            raise EmbedderError(f"Failed to generate embeddings: {e}")


class LocalEmbedder(BaseEmbedder):
    """
    Local embedding provider using sentence-transformers.
    
    This provider runs embeddings locally without requiring API calls,
    useful for offline usage or when API costs are a concern.
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: Optional[str] = None,
        max_text_len: int = 8196,
        **kwargs: Any
    ) -> None:
        """
        Initialize local embedding provider.
        
        Args:
            model_name: Sentence-transformer model name
            device: Device to run on ('cpu', 'cuda', etc.)
            **kwargs: Additional configuration parameters
        """
        super().__init__(max_text_len=max_text_len, **kwargs)
        
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbedderError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        try:
            self.model = SentenceTransformer(model_name, device=device)
        except Exception as e:
            raise EmbedderError(f"Failed to load model {model_name}: {e}")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using local sentence-transformer model.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbedderError: If embedding generation fails
        """
        if not texts:
            return []

        chunked_texts, counts = self._chunk_texts(texts)
        try:
            embeddings = self.model.encode(chunked_texts, convert_to_tensor=False)
            
            # Ensure we return lists, not numpy arrays, and keep a 2D structure
            if isinstance(embeddings, np.ndarray):
                if embeddings.ndim == 1:
                    embeddings_list = [embeddings.tolist()]
                else:
                    embeddings_list = embeddings.tolist()
            else:
                # sentence-transformers may return List[np.ndarray] or List[List[float]]
                if chunked_texts and not isinstance(embeddings[0], (list, tuple, np.ndarray)):
                    # Single embedding returned as flat list
                    embeddings_list = [list(embeddings)]
                else:
                    embeddings_list = [
                        emb.tolist() if hasattr(emb, 'tolist') else list(emb)
                        for emb in embeddings
                    ]
            return self._merge_chunk_embeddings(embeddings_list, counts)
                       
        except Exception as e:
            raise EmbedderError(f"Failed to generate embeddings: {e}")


class MockEmbedder(BaseEmbedder):
    """
    Mock embedder for testing purposes.
    
    Returns random or predefined embeddings without making actual API calls.
    """
    
    def __init__(
        self,
        embedding_dim: int = 384,
        fixed_embeddings: Optional[dict] = None,
        max_text_len: int = 8196,
        **kwargs: Any
    ) -> None:
        """
        Initialize mock embedder.
        
        Args:
            embedding_dim: Dimension of generated embeddings
            fixed_embeddings: Dict mapping texts to fixed embeddings
            **kwargs: Additional configuration parameters
        """
        super().__init__(max_text_len=max_text_len, **kwargs)
        self.embedding_dim = embedding_dim
        self.fixed_embeddings = fixed_embeddings or {}
        np.random.seed(42)  # For reproducible testing
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings."""
        chunked_texts, counts = self._chunk_texts(texts)
        embeddings = []
        
        for text in chunked_texts:
            if text in self.fixed_embeddings:
                embeddings.append(self.fixed_embeddings[text])
            else:
                # Generate deterministic "embedding" based on text hash
                text_hash = hash(text) % (2**31)
                np.random.seed(text_hash)
                embedding = np.random.normal(0, 1, self.embedding_dim).tolist()
                embeddings.append(embedding)
        
        return self._merge_chunk_embeddings(embeddings, counts)


class AverageEmbedder:
    """
    Utility class for averaging embeddings (used in AveFact strategy).
    
    This is not a full embedder but a helper for the AveFact retrieval strategy
    which averages keyword embeddings to create query vectors.
    """
    
    @staticmethod
    def average_embeddings(embeddings: List[List[float]]) -> List[float]:
        """
        Compute the average of multiple embeddings.
        
        Args:
            embeddings: List of embedding vectors
            
        Returns:
            Average embedding vector
            
        Raises:
            ValueError: If embeddings list is empty
        """
        if not embeddings:
            raise ValueError("Cannot average empty list")
        
        # Convert to numpy for easier computation
        embeddings_array = np.array(embeddings)
        average_embedding = np.mean(embeddings_array, axis=0)
        
        return average_embedding.tolist()
    
    @staticmethod
    def weighted_average_embeddings(
        embeddings: List[List[float]], 
        weights: List[float]
    ) -> List[float]:
        """
        Compute weighted average of embeddings.
        
        Args:
            embeddings: List of embedding vectors
            weights: List of weights for each embedding
            
        Returns:
            Weighted average embedding vector
        """
        if len(embeddings) != len(weights):
            raise ValueError("Number of embeddings must match number of weights")
        
        embeddings_array = np.array(embeddings)
        weights_array = np.array(weights).reshape(-1, 1)
        
        weighted_sum = np.sum(embeddings_array * weights_array, axis=0)
        total_weight = np.sum(weights_array)
        
        return (weighted_sum / total_weight).tolist()

