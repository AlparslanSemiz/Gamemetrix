from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def test_runtime_images_and_actions_are_immutable() -> None:
    for dockerfile in ("backend/Dockerfile", "frontend/Dockerfile"):
        for line in _read(dockerfile).splitlines():
            if line.startswith("FROM "):
                assert "@sha256:" in line

    compose = _read("docker-compose.yml")
    for line in compose.splitlines():
        if line.strip().startswith("image:"):
            assert "@sha256:" in line

    workflow = _read(".github/workflows/ci.yml")
    for line in workflow.splitlines():
        if "uses:" in line:
            reference = line.split("uses:", 1)[1].split("#", 1)[0].strip()
            assert "@" in reference
            assert len(reference.rsplit("@", 1)[1]) == 40


def test_compose_requires_separate_app_role_and_hardens_public_services() -> None:
    compose = _read("docker-compose.yml")

    assert "${ENV:?Set ENV" in compose
    assert "${APP_DB_USER:?Set APP_DB_USER" in compose
    assert "${APP_DB_PASSWORD:?Set APP_DB_PASSWORD" in compose
    assert "postgresql+psycopg://${POSTGRES_USER" not in compose
    assert compose.count("read_only: true") >= 3
    assert compose.count("no-new-privileges:true") >= 3
    assert compose.count("- ALL") >= 3
    assert 'user: "101:101"' in compose


def test_application_images_drop_root_and_origin_logs_exclude_queries() -> None:
    assert "USER gamemetrix" in _read("backend/Dockerfile")
    assert "USER node" in _read("frontend/Dockerfile")

    nginx = _read("nginx.conf")
    assert '"$request"' not in nginx
    assert "$request_method $uri $server_protocol" in nginx


def test_production_deploy_preserves_protected_environment_boundary() -> None:
    deploy = _read("ops/deploy-production.sh")
    wrapper = _read("ops/deploy-server-wrapper.sh")

    assert "set -Eeuo pipefail" in deploy
    assert '[[ "${EUID}" -ne 0 ]]' in deploy
    assert "600:root:root" in deploy
    assert 'sudo -u "$git_user" git pull --ff-only origin main' in deploy
    assert '"${compose[@]}" config --quiet' in deploy
    assert '"${compose[@]}" up -d --wait --wait-timeout 240 db backend' in deploy
    assert '"${compose[@]}" up -d --wait --wait-timeout 240 frontend' in deploy
    assert '"${compose[@]}" up -d --wait --wait-timeout 240 nginx' in deploy
    assert "Deployment completed successfully." in deploy
    assert "exec sudo -n bash" in wrapper
