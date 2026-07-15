from gateway_repository_service.settings import RepositoryServiceSettings


def test_repository_data_root_is_local_to_service() -> None:
    assert RepositoryServiceSettings().data_root.name == "repository"
