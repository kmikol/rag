from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts" / "rag"
EXAMPLES = CHART / "examples"


def test_helm_chart_lints_with_examples() -> None:
    value_sets = [
        None,
        EXAMPLES / "values.example.yaml",
        EXAMPLES / "values.cluster-home-arpa.example.yaml",
        EXAMPLES / "values.existing-storage.example.yaml",
    ]
    for values_path in value_sets:
        command = ["helm", "lint", str(CHART)]
        if values_path is not None:
            command.extend(["-f", str(values_path)])
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


def test_cluster_home_arpa_values_render_homelab_contract() -> None:
    docs = _helm_template(EXAMPLES / "values.cluster-home-arpa.example.yaml")

    pvc_names = {doc["metadata"]["name"] for doc in _find_kind(docs, "PersistentVolumeClaim")}
    assert "rag-rag-shared-storage" in pvc_names
    assert "rag-rag-qdrant-data" in pvc_names

    shared_pvc = _find_by_kind_name(docs, "PersistentVolumeClaim", "rag-rag-shared-storage")
    assert shared_pvc["spec"]["accessModes"] == ["ReadWriteMany"]
    assert shared_pvc["spec"]["storageClassName"] == "longhorn-r2"

    qdrant_pvc = _find_by_kind_name(docs, "PersistentVolumeClaim", "rag-rag-qdrant-data")
    assert qdrant_pvc["spec"]["storageClassName"] == "longhorn-r2"

    api = _find_by_kind_name(docs, "Deployment", "rag-rag-api")
    api_container = _container(api, "api-service")
    api_env = _env_by_name(api_container)
    assert api_env["RAG_API_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "rag-api-credentials"
    assert api_env["LLM_API_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "rag-llm-credentials"
    assert api_env["WATCH_ROOTS"]["value"] == "/data/watch"
    assert api_env["DOCUMENT_STORE_PATH"]["value"] == "/data/documents"
    assert _volume_mounts_by_name(api_container)["shared-storage"]["mountPath"] == "/data"

    worker = _find_by_kind_name(docs, "Deployment", "rag-rag-ingestion-worker")
    worker_container = _container(worker, "ingestion-worker")
    worker_env = _env_by_name(worker_container)
    assert worker_env["WATCH_ROOTS"]["value"] == "/data/watch"
    assert worker_env["DOCUMENT_STORE_PATH"]["value"] == "/data/documents"
    assert _volume_mounts_by_name(worker_container)["shared-storage"]["mountPath"] == "/data"

    embedding = _find_by_kind_name(docs, "Deployment", "rag-rag-embedding-service")
    embedding_env = _env_by_name(_container(embedding, "embedding-service"))
    assert (
        embedding_env["EMBEDDING_API_KEY"]["valueFrom"]["secretKeyRef"]["name"]
        == "rag-embedding-credentials"
    )

    ingress = _find_by_kind_name(docs, "Ingress", "rag-rag-api")
    hosts = {rule["host"] for rule in ingress["spec"]["rules"]}
    assert hosts == {"cluster.home.arpa", "cluster.example.ts.net"}


def test_existing_storage_values_mount_existing_claims_without_creating_them() -> None:
    docs = _helm_template(EXAMPLES / "values.existing-storage.example.yaml")

    assert not _find_kind(docs, "PersistentVolumeClaim")

    api = _find_by_kind_name(docs, "Deployment", "rag-rag-api")
    api_volumes = _volumes_by_name(api["spec"]["template"]["spec"])
    assert api_volumes["shared-storage"]["persistentVolumeClaim"]["claimName"] == "rag-corpus"

    worker = _find_by_kind_name(docs, "Deployment", "rag-rag-ingestion-worker")
    worker_volumes = _volumes_by_name(worker["spec"]["template"]["spec"])
    assert worker_volumes["shared-storage"]["persistentVolumeClaim"]["claimName"] == "rag-corpus"
    assert (
        worker_volumes["ingestion-worker-data"]["persistentVolumeClaim"]["claimName"]
        == "rag-worker-cache"
    )

    qdrant = _find_by_kind_name(docs, "Deployment", "rag-rag-qdrant")
    qdrant_volumes = _volumes_by_name(qdrant["spec"]["template"]["spec"])
    assert qdrant_volumes["qdrant-data"]["persistentVolumeClaim"]["claimName"] == "rag-qdrant"


def test_shared_storage_requires_created_or_existing_claim(tmp_path: Path) -> None:
    values_path = tmp_path / "invalid-shared-storage.yaml"
    values_path.write_text("sharedStorage:\n  enabled: true\n", encoding="utf-8")

    result = subprocess.run(
        ["helm", "template", "rag", str(CHART), "-f", str(values_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "If sharedStorage.enabled is true, either sharedStorage.create must be true "
        "or sharedStorage.existingClaim must be provided."
    ) in result.stderr


def _helm_template(values_path: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["helm", "template", "rag", str(CHART), "-f", str(values_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _find_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


def _find_by_kind_name(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    for doc in docs:
        if doc["kind"] == kind and doc["metadata"]["name"] == name:
            return doc
    raise AssertionError(f"missing {kind}/{name}")


def _container(workload: dict[str, Any], name: str) -> dict[str, Any]:
    for container in workload["spec"]["template"]["spec"]["containers"]:
        if container["name"] == name:
            return container
    raise AssertionError(f"missing container {name}")


def _env_by_name(container: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["name"]: entry for entry in container.get("env", [])}


def _volume_mounts_by_name(container: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["name"]: entry for entry in container.get("volumeMounts", [])}


def _volumes_by_name(pod_spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["name"]: entry for entry in pod_spec.get("volumes", [])}
