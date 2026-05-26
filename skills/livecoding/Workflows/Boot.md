# Boot — TidalCycles + SuperDirt + Hydra

The boot ritual. Same order every session — muscle-memorized within a week.

## Pre-flight check (do this first)

Run these and confirm before booting:

```bash
brew --version                                       # Homebrew present
ls /Applications/SuperCollider.app                   # SuperCollider installed
ls ~/Library/Application\ Support/SuperCollider/downloaded-quarks/SuperDirt 2>/dev/null && echo "SuperDirt ✓" || echo "SuperDirt MISSING"
ghc --version && cabal --version                     # Haskell toolchain
ghci -e 'import Sound.Tidal.Context' 2>&1 | head -3  # Tidal library
ls /Applications/Visual\ Studio\ Code.app            # VS Code
code --list-extensions | grep -i tidal               # Tidal extension
```

Any line that fails → fix that first.

## First-time install (if pre-flight fails)

Run these only when needed; each is minutes-long:

```bash
# SuperCollider
brew install --cask supercollider

# Haskell toolchain
curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | sh
source ~/.ghcup/env

# TidalCycles library
cabal update && cabal install tidal --lib

# VS Code Tidal extension
code --install-extension tidalcycles.vscode-tidalcycles
```

For **SuperDirt** (must be done inside SuperCollider.app, not the shell):

1. Open SuperCollider.app
2. In an editor window, paste and evaluate (`Cmd-Return` on the line):
   ```supercollider
   Quarks.install("SuperDirt", "v1.7.3");
   ```
3. Wait ~5–10 min (downloads ~3 GB of Dirt-Samples)
4. `Language → Recompile Class Library` (`Cmd-Shift-L`)
5. Verify: `SuperDirt.start;` should not error

## Boot sequence (every session)

1. **Start SuperCollider.app**
2. In an SC editor window, evaluate (`Cmd-Return` on the line):
   ```supercollider
   SuperDirt.start;
   ```
   Wait for the post window to say SuperDirt is listening on port 57120.
3. **Open VS Code**, open a `.tidal` file (create one if needed: `session.tidal`)
4. Command palette (`Cmd-Shift-P`) → `TidalCycles: Boot Tidal`
5. Watch the integrated terminal — should show:
   ```
   > Listening for messages on port 6010
   ```
6. **First sound**: in the `.tidal` file, type:
   ```haskell
   d1 $ s "bd*4"
   ```
   Place cursor on the line, `Shift-Enter`. Kick drum every quarter beat.
7. To stop: `hush` then `Shift-Enter`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No sound on `d1 $ s "bd*4"` | SuperDirt not started | Re-run `SuperDirt.start;` in SC |
| `could not connect to host on port 6010` | Tidal boot didn't run | VS Code → cmd palette → `TidalCycles: Boot Tidal` |
| Audio crackles / dropouts | SC hardware buffer too small | In SC: `Server.default.options.hardwareBufferSize_(512); Server.default.reboot` |
| `ghci` not found in VS Code | PATH not inherited | Quit VS Code, relaunch from terminal (`code .`) so PATH carries through |
| `Could not resolve dependencies` during `cabal install tidal` | GHC newer than Tidal's tested matrix | `ghcup install ghc 9.6.6 && ghcup set ghc 9.6.6 && cabal install tidal --lib` |
| `Quarks.install` hangs | Git auth prompt blocking | `git config --global url."https://github.com/".insteadOf git@github.com:` then retry |

## Agent invocation pattern

When invoked:

1. Run the pre-flight commands first; report what passes/fails as a single table
2. For any missing prereq, **show** the install command but do NOT execute brew/cabal without explicit user OK (they take minutes and require user attention)
3. Once prereqs pass, walk steps 1-6 sequentially
4. If the user reports "no sound", run through the troubleshooting table top-to-bottom

Don't generate patterns before confirming the stack is booted — patterns delivered into a non-running stack just produce frustration.
