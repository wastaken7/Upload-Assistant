# Shell Completions

If you have installed Upload Assistant globally using `uv` (e.g., `uv tool install .`), the application is available in your terminal as the `ua` command.

We have built-in support for **dynamic shell completions** using `argcomplete`. This allows you to press `[TAB]` while typing a `ua` command to see suggestions for flags, trackers, and arguments.

```bash
$ ua --[TAB]
--audio-spectrogram         --help                      --site-upload
--audio-spectrogram-tracks  --infohash                  --tmp-dir
...
```

## Prerequisites

Because you installed Upload Assistant in an isolated environment using `uv`, the `argcomplete` helper scripts are not automatically added to your global `$PATH`. You must install the `argcomplete` utility globally on your system first:

```bash
uv tool install argcomplete
# OR using pip:
pip install --user argcomplete
# OR using apt (Debian/Ubuntu):
sudo apt install python3-argcomplete
```

There are two main ways to enable completions in your shell: **Static File Registration** (recommended for zero startup overhead) and **Dynamic Registration**. In both methods, the completions themselves are always fetched dynamically when you press `[TAB]`.

---

## Method 1: Static File Registration (Recommended)

This is the recommended method. It generates the shell hook once and saves it as a file. This ensures that Python is **not** executed when your terminal opens, resulting in zero startup overhead.

### Fish

Fish natively supports lazy-loading completion scripts from a specific directory. You can save the hook statically:

```fish
mkdir -p ~/.config/fish/completions
register-python-argcomplete --shell fish ua > ~/.config/fish/completions/ua.fish
```

### Bash

If you have the `bash-completion` package installed, Bash can lazy-load completions when a command is invoked:

```bash
mkdir -p ~/.local/share/bash-completion/completions
register-python-argcomplete ua > ~/.local/share/bash-completion/completions/ua
```

### Zsh

Zsh can lazy-load completions by placing them in a directory tracked by your `$fpath`:

```zsh
mkdir -p ~/.zfunc
register-python-argcomplete ua > ~/.zfunc/_ua
```

_Note: You must ensure `~/.zfunc` is added to your `$fpath` in your `~/.zshrc` before `compinit` is called:_

```zsh
fpath=(~/.zfunc $fpath)
autoload -U compinit bashcompinit
compinit
bashcompinit
```

---

## Method 2: Dynamic Registration

If you prefer not to manage static files, you can dynamically evaluate the completion script or use global activation.

### Option A: Global Lazy Activation (Bash/Zsh)

`argcomplete` provides a global hook that automatically intercepts any compatible Python script. Run this command once:

```bash
activate-global-python-argcomplete --user
```

This updates `~/.bash_completion` and the user-level Zsh configuration. It has zero overhead at startup and will automatically trigger completions for `ua`.

### Option B: Immediate `eval` (All Shells)

You can directly evaluate the hook in your shell configuration file (e.g., `~/.bashrc`, `~/.zshrc`, or `~/.config/fish/config.fish`).
_Note: This will add ~100-200ms of lag when opening a new terminal, as it must execute Python to generate the hook during shell startup._

**Bash:**

```bash
eval "$(register-python-argcomplete ua)"
```

**Zsh:**

```zsh
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete ua)"
```

**Fish:**

```fish
register-python-argcomplete --shell fish ua | source
```
