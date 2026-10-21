"""Per-account Codex homes. Selection is metadata; a running process owns its auth file.

The caller holds the provider-manager lock for registry mutations. Launchers read the atomic
registry once and exec with a concrete CODEX_HOME; they never follow a mutable home symlink.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pm_store


def root():
    return Path(os.environ.get("PROVIDER_MANAGER_CODEX_ROOT") or Path.home() / ".local/share/broomva/codex")


def registry():
    path = root() / "accounts.json"
    if not path.exists():
        if any((root() / name).exists() and any((root() / name).iterdir())
               for name in ("homes", "threads", "launches")):
            raise pm_store.StoreError("Codex registry is missing while retained homes or session pins exist; restore accounts.json before refreshing any backup")
        return {"accounts": {}, "selected": None}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
            raise ValueError("accounts must be an object")
        for email, entry in data["accounts"].items():
            if not isinstance(entry, dict) or entry.get("email") != email or not Path(entry["home"]).is_absolute():
                raise ValueError("invalid account entry")
        if data.get("selected") is not None and data["selected"] not in data["accounts"]:
            raise ValueError("selected account is missing")
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise pm_store.StoreError("Cannot read Codex account registry: %s" % exc) from exc


def save(data):
    folder = root()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "accounts.json"
    fd, name = tempfile.mkstemp(prefix=".accounts-", dir=folder)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(data, out, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def entry(email):
    return registry()["accounts"].get(email.lower())


def selected():
    data = registry()
    return data["accounts"].get(data.get("selected"))


def register(email, account_id, home, select=False):
    email = email.lower()
    home = Path(home).resolve(strict=True)
    auth = pm_store.read_codex_auth(home / "auth.json")
    if auth.status != "ok" or pm_store.extract_codex_identity((auth.data or {}).get("tokens")).get("email") != email:
        raise pm_store.StoreError("Codex home does not hold the expected account: %s" % email)
    data = registry()
    if any(Path(value["home"]).resolve() == home and key != email
           for key, value in data["accounts"].items()):
        raise pm_store.StoreError("Codex home is already registered to another account")
    data["accounts"][email] = {"email": email, "id": account_id, "home": str(home)}
    if select or not data.get("selected"):
        data["selected"] = email
    save(data)
    return data["accounts"][email]


def select(email):
    data = registry()
    email = email.lower()
    if email not in data["accounts"]:
        raise pm_store.StoreError("Codex account has no isolated home: %s" % email)
    home = Path(data["accounts"][email]["home"])
    auth = pm_store.read_codex_auth(home / "auth.json")
    if auth.status != "ok" or pm_store.extract_codex_identity((auth.data or {}).get("tokens")).get("email") != email:
        raise pm_store.StoreError("Codex home is unreadable or its account changed: %s" % email)
    data["selected"] = email
    save(data)
    return home


def new_home(email, auth, shared_home):
    """Create an unpublished generation. Never modify an existing home or duplicate its grant."""
    save(registry())  # establish ownership metadata before any generation can exist
    folder = root() / "homes"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    tag = hashlib.sha256(email.lower().encode()).hexdigest()[:16]
    home = Path(tempfile.mkdtemp(prefix=tag + "-", dir=folder))
    try:
        # Auth, databases, logs and session state remain local to this generation. Configuration
        # and instruction files are copied; skill/rule directories are shared read views.
        shared_home = Path(shared_home)
        for name in ("AGENTS.md", "managed_config.toml"):
            source = shared_home / name
            if source.is_file():
                shutil.copy2(source, home / name)
        config = shared_home / "config.toml"
        content = config.read_text() if config.is_file() else ""
        lines, in_table = [], False
        for line in content.splitlines():
            if line.lstrip().startswith("["):
                in_table = True
            if not in_table and line.split("=", 1)[0].strip() == "cli_auth_credentials_store":
                continue
            lines.append(line)
        (home / "config.toml").write_text('cli_auth_credentials_store = "file"\n' + "\n".join(lines) + "\n")
        os.chmod(home / "config.toml", 0o600)
        for name in ("skills", "rules", "prompts"):
            source = shared_home / name
            if source.is_dir():
                (home / name).symlink_to(source.resolve(), target_is_directory=True)
        if not pm_store.write_codex_auth(auth, home / "auth.json"):
            raise pm_store.StoreError("Cannot write new Codex account home")
        return home
    except BaseException:
        shutil.rmtree(home)
        raise


def launch(binary, args):
    actual_binary = Path(binary).expanduser().resolve()
    if actual_binary == (root() / "bin/codex").resolve():
        raise pm_store.StoreError("Real Codex binary resolves to the selection launcher")
    account = selected()
    if not account:
        raise pm_store.StoreError("No Codex account selected; use provider-manager switch --provider codex EMAIL")
    agent_id = os.environ.get("PASEO_AGENT_ID")
    if agent_id:
        # A resumed Paseo agent retains its original generation, even after a new selection or login.
        folder = root() / "launches"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = folder / (hashlib.sha256(agent_id.encode()).hexdigest() + ".json")
        fd, temporary = tempfile.mkstemp(prefix=".pin-", dir=folder)
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(account, out)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            account = json.loads(target.read_text())
        finally:
            os.unlink(temporary)
    home = Path(account["home"]).resolve(strict=True)
    auth = pm_store.read_codex_auth(home / "auth.json")
    if auth.status != "ok" or pm_store.extract_codex_identity((auth.data or {}).get("tokens")).get("email") != account["email"]:
        raise pm_store.StoreError("Pinned Codex account home is unreadable or changed identity")
    # User-supplied CODEX_HOME and credential-store config cannot redirect the pinned session.
    # Codex command-line -c values override config.toml; incompatible overrides are refused.
    position, command = 0, None
    value_options = {"-c", "--config", "--enable", "--disable", "--remote", "--remote-auth-token-env",
                     "-i", "--image", "-m", "--model", "--local-provider", "-p", "--profile",
                     "-s", "--sandbox", "-a", "--ask-for-approval", "-C", "--cd", "--add-dir"}
    switches = {"--oss", "--strict-config", "--approve-for-me", "--dangerously-bypass-approvals-and-sandbox",
                "--dangerously-bypass-hook-trust", "--worktree", "--search", "--no-alt-screen",
                "--no-daemon", "-h", "--help", "-V", "--version"}
    while position < len(args):
        value = args[position]
        if value == "--":
            break  # remaining text is an interactive prompt, not a subcommand
        option = value.split("=", 1)[0]
        if option in value_options:
            argument = value.split("=", 1)[1] if "=" in value else (args[position + 1] if position + 1 < len(args) else None)
            if argument is None:
                raise pm_store.StoreError("Missing value for Codex option %s" % option)
            if option in ("-c", "--config") and argument.split("=", 1)[0].strip() == "cli_auth_credentials_store":
                if argument.split("=", 1)[-1].strip().strip('"\'') != "file":
                    raise pm_store.StoreError("Managed Codex sessions require the file credential store")
            position += 1 if "=" in value else 2
            if option in ("-i", "--image"):
                commands = {"agents", "exec", "e", "review", "login", "logout", "mcp", "plugin", "app-server",
                            "remote-control", "app", "completion", "update", "doctor", "sandbox", "debug",
                            "apply", "a", "resume", "queue", "archive", "delete", "migrate-rollouts", "unarchive",
                            "fork", "cloud", "exec-server", "features", "help"}
                while position < len(args) and not args[position].startswith("-") and args[position] not in commands:
                    position += 1
            continue
        if value in switches:
            position += 1
            continue
        # Clap also accepts attached short option values, for example -pwork and -cmodel=x.
        if value[:2] in value_options and len(value) > 2 and not value.startswith("--"):
            if value[:2] == "-c" and value[2:].split("=", 1)[0].strip() == "cli_auth_credentials_store":
                if value.split("=", 1)[-1].strip().strip('"\'') != "file":
                    raise pm_store.StoreError("Managed Codex sessions require the file credential store")
            position += 1
            continue
        if value.startswith("-"):
            raise pm_store.StoreError("Unsupported global Codex option %s; update the account launcher" % value)
        command = value
        break
    if command == "logout" or (command == "login" and args[position + 1:position + 2] != ["status"]):
        raise pm_store.StoreError("Use provider-manager login-headless --provider codex; direct login/logout revokes this home's grant")
    # Credential overrides after the subcommand are also parsed as config options by Codex.
    for index, value in enumerate(args):
        override = (args[index + 1] if index + 1 < len(args) else "") if value in ("-c", "--config") else (
            value[2:] if value.startswith("-c") and not value.startswith("--") else
            value[len("--config="):] if value.startswith("--config=") else "")
        if override.split("=", 1)[0].strip() == "cli_auth_credentials_store" and override.split("=", 1)[-1].strip().strip('"\'') != "file":
            raise pm_store.StoreError("Managed Codex sessions require the file credential store")
    if command == "app-server":
        import pm_codex_proxy
        raise SystemExit(pm_codex_proxy.run(binary, args, home, account))
    env = dict(os.environ, CODEX_HOME=str(home))
    os.execve(str(Path(binary).resolve(strict=True)),
              [str(binary), "-c", 'cli_auth_credentials_store="file"', *args], env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Real Codex executable, never this launcher")
    args, rest = parser.parse_known_args()
    if rest[:1] == ["--"]:
        rest = rest[1:]
    try:
        launch(args.binary, rest)
    except (pm_store.StoreError, OSError, ValueError, KeyError, TypeError) as exc:
        print("codex-account: %s" % exc, file=sys.stderr)
        raise SystemExit(1)


def install_launcher(binary):
    """Install a separate executable; never replace a vendor binary or an active process."""
    import shlex
    actual = Path(binary).expanduser().resolve(strict=True)
    output = root() / "bin/codex"
    if actual == output.resolve():
        raise pm_store.StoreError("The real Codex binary must not be the selection launcher")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = "#!/bin/sh\nexec %s %s --binary %s -- \"$@\"\n" % (
        shlex.quote(sys.executable), shlex.quote(str(Path(__file__).resolve())), shlex.quote(str(actual)))
    fd, temporary = tempfile.mkstemp(prefix=".launcher-", dir=output.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(command)
        os.chmod(temporary, 0o700)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(output)


if __name__ == "__main__":
    main()
