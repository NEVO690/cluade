"""Open-source models AVEN Local runs on the user's own computer.

All files are Qwen3 models (Apache-2.0 licence) in GGUF format. Each download
is pinned to an exact repository revision and verified against its SHA-256
checksum, so a changed or tampered file is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFile:
    key: str
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str
    label: str  # e.g. "Qwen3 4B"

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}"

    @property
    def size_text(self) -> str:
        return f"{self.size / 1_000_000_000:.1f} GB"


MODEL_FILES: dict[str, ModelFile] = {
    "qwen3-1.7b": ModelFile(
        key="qwen3-1.7b",
        repo="ggml-org/Qwen3-1.7B-GGUF",
        revision="daeb8e2d528a760970442092f6bf1e55c3b659eb",
        filename="Qwen3-1.7B-Q4_K_M.gguf",
        size=1_282_439_264,
        sha256="d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5",
        label="Qwen3 1.7B",
    ),
    "qwen3-4b": ModelFile(
        key="qwen3-4b",
        repo="ggml-org/Qwen3-4B-GGUF",
        revision="2f3b082b1356a6123f7ed71e65aea340da25d53c",
        filename="Qwen3-4B-Q4_K_M.gguf",
        size=2_497_280_640,
        sha256="ab27b9bfa375a178d6cba48f3ad892b94b7739659dcc7aae8058ce0ffed6b328",
        label="Qwen3 4B",
    ),
    "qwen3-8b": ModelFile(
        key="qwen3-8b",
        repo="Qwen/Qwen3-8B-GGUF",
        revision="7c41481f57cb95916b40956ab2f0b139b296d974",
        filename="Qwen3-8B-Q4_K_M.gguf",
        size=5_027_783_488,
        sha256="d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785",
        label="Qwen3 8B",
    ),
}


@dataclass(frozen=True)
class LocalModel:
    file: ModelFile
    thinking: bool  # Qwen3 "thinking mode": reasons before answering (better, slower)


# AVEN model -> local model. AVEN 1.0 and AVEN Core share one download.
LOCAL_MODELS: dict[str, LocalModel] = {
    "aven-light": LocalModel(MODEL_FILES["qwen3-1.7b"], thinking=False),
    "aven-core": LocalModel(MODEL_FILES["qwen3-4b"], thinking=False),
    "aven-1": LocalModel(MODEL_FILES["qwen3-4b"], thinking=True),
    "aven-ultra": LocalModel(MODEL_FILES["qwen3-8b"], thinking=True),
}
DEFAULT_LOCAL_MODEL = "aven-light"
