import alegra
import pytest


@pytest.fixture(autouse=True)
def setup_alegra():
    alegra.user = "develop@okchaty.com"
    alegra.token = "45a1bcb2cc25d9c60196"
