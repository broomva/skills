# Loaded by subprocesses whose PYTHONPATH holds this directory (tests only). With the fake
# Anthropic state configured, route urllib to the stub; without it, block the network.
import os
import urllib.request

if os.environ.get("FAKE_ANTHROPIC_STATE"):
    import fake_net

    fake_net.install()
elif os.environ.get("PROVIDER_MANAGER_TEST_GUARD"):
    import fake_net

    urllib.request.urlopen = fake_net.blocked_urlopen
