"""Offline tests: no downloads, Ollama calls, desktop actions or training."""
import io
import json
from unittest.mock import MagicMock

import numpy as np
from PIL import Image
import pytest

import cleanup_grounding_etl as etl
from concept_cortex import ConceptCortex
from hyperdimensional import FHRRHyperdimensionalEngine


def test_annotations_decode_incrementally_with_unicode():
    rows = [{"instruction": "ação" * 20000}, {"elements": []}]
    assert list(etl.iter_annotations(io.BytesIO(json.dumps(rows, ensure_ascii=False).encode()))) == rows


@pytest.mark.parametrize("bbox", [[0.7, 0, 0.2, 1], [0, 0, 1.1, 1], [0, 0, float("nan"), 1]])
def test_invalid_annotation_crops_are_rejected(bbox):
    with pytest.raises(ValueError):
        etl.crop_element(Image.new("RGB", (100, 100)), bbox)


def test_crop_uses_normalized_dataset_coordinates():
    crop = etl.crop_element(Image.new("RGB", (100, 200)), [0.1, 0.2, 0.5, 0.6])
    assert crop.size == (40, 80)


def test_range_reader_crosses_split_boundaries(monkeypatch):
    def open_range(request, timeout):
        start, end = map(int, request.get_header("Range").removeprefix("bytes=").split("-"))
        data = b"abc" if "/aa?" in request.full_url else b"def"
        response = io.BytesIO(data[start:end + 1])
        response.status = 206
        response.headers = {"Content-Range": f"bytes {start}-{end}/3"}
        return response
    monkeypatch.setattr(etl.urllib.request, "urlopen", open_range)
    archive = etl.RemoteArchive([("aa", 3), ("ab", 3)], root="https://example.invalid/")
    archive.seek(2)
    assert archive.read(3) == b"cde"
    assert archive.tell() == 5


def test_grounding_persists_deduplicates_and_restores_cleanup(tmp_path):
    path = str(tmp_path / "grounding.db")
    vsa = FHRRHyperdimensionalEngine(dim=64)
    cortex = ConceptCortex(vsa, MagicMock(), db_path=path, dim=64)
    element = {"bbox": [0, 0, 1, 1], "instruction": "Save"}
    image = Image.new("RGB", (10, 10))
    try:
        assert etl.store_exemplar(cortex, image, element, "Save button", "BUTTON", "one.png", tmp_path)
        assert not etl.store_exemplar(cortex, image, element, "Save button", "BUTTON", "one.png", tmp_path)
        assert len(vsa.cleanup_keys) == 1
        assert cortex._conn.execute("SELECT exemplar_count FROM concept_invariants WHERE concept_key='ELEMENTO_BUTTON'").fetchone() == (1,)
        metadata = json.loads(cortex._conn.execute("SELECT metadata_json FROM grounding_cleanup").fetchone()[0])
        assert metadata["ncd_verified"] is False
        assert list(tmp_path.glob("*.png"))
    finally:
        cortex.close()
    restored_vsa = FHRRHyperdimensionalEngine(dim=64)
    restored = ConceptCortex(restored_vsa, MagicMock(), db_path=path, dim=64)
    try:
        assert list(restored_vsa.cleanup_keys) == list(vsa.cleanup_keys)
        np.testing.assert_allclose(restored_vsa.cleanup_matrix, vsa.cleanup_matrix)
    finally:
        restored.close()
