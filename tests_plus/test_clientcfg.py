"""build_client: flags beat dotenv values beat the local default; hosted needs a key."""

import unittest

from ic_plus.clientcfg import LOCAL_URL, build_client


class TestBuildClient(unittest.TestCase):
    def test_local_defaults_to_ollama_and_needs_a_model(self) -> None:
        client, missing = build_client("local", None, None, {})
        self.assertIsNone(client)
        self.assertEqual(missing, ["model"])
        client, missing = build_client("local", None, "llama3.2", {})
        self.assertEqual((missing, client.base_url), ([], LOCAL_URL))  # type: ignore[union-attr]

    def test_flags_beat_the_dotenv_values(self) -> None:
        env = {"LLM_BASE_URL": "http://env/v1", "LLM_MODEL": "env-model"}
        client, _ = build_client("local", "http://flag/v1", "flag-model", env)
        assert client is not None
        self.assertEqual((client.base_url, client.model), ("http://flag/v1", "flag-model"))

    def test_hosted_needs_url_model_and_key(self) -> None:
        self.assertEqual(build_client("hosted", None, None, {})[1], ["url", "model", "key"])
        env = {"LLM_BASE_URL": "http://h/v1", "LLM_MODEL": "m", "LLM_API_KEY": "secret-key"}
        client, missing = build_client("hosted", None, None, env)
        self.assertEqual(missing, [])
        self.assertNotIn("secret-key", repr(client))

    def test_local_never_sends_the_key(self) -> None:
        env = {"LLM_MODEL": "m", "LLM_API_KEY": "secret-key"}
        client, _ = build_client("local", None, None, env)
        assert client is not None
        self.assertIsNone(client._key)


if __name__ == "__main__":
    unittest.main()
