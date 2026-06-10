# Veilgit

`veilgit` is a zero-dependency Python script that adds transparent file encryption to any git repository. 

It automatically encrypts selected files before they are pushed to the remote server, while keeping them readable as plain text on your local machine.

![veilgit](img/veilgit.1.600x450.png)

## The Problem

When maintaining open-source projects or public repositories, you often have private know-how, internal notes, or sensitive assets that you do not want to publish. However, you still want to version-control these files and back them up securely on the same remote server (like GitHub) alongside your public code. Keeping two separate repositories is tedious and breaks the context of your work.

## The Solution

`veilgit` leverages git's built-in `clean` and `smudge` filter mechanism — a standard git
feature that lets you run arbitrary transformations on file content as it moves between the
working directory and the git object store.

### What `veil_setup.py` configures

Running `veil_setup.py` writes two things into the target repository:

**`.gitattributes`** — tells git which files should use the filter:
```
docs/private/**  filter=veil  diff=veil
secrets/**       filter=veil  diff=veil
```

**`.git/config`** (local, never pushed) — defines the filter commands:
```ini
[filter "veil"]
    clean  = gzip -9 | age -r age1yourpublickey...
    smudge = age --decrypt -i ~/.config/age/myrepo_key.txt | gzip -d
    required = true

[diff "veil"]
    textconv = age --decrypt -i ~/.config/age/myrepo_key.txt | gzip -d
```

### What happens during normal git use

You use git **exactly as you always do** — `veilgit` is completely transparent:

```
Your working copy          git index / history        Remote (GitHub)
─────────────────          ────────────────────────   ────────────────
notes.md  (plaintext)
    │
    │  git add notes.md
    │  ── clean filter runs ──►  gzip -9 | age -r pubkey
    │                            stores encrypted blob
    │                                    │
    │                                    │  git commit && git push
    │                                    ├──────────────────────►  encrypted blob
    │
    │  git checkout / git pull
    │  ◄── smudge filter runs ──  age --decrypt | gzip -d
notes.md  (plaintext)
```

| Action | What you type | What git does under the hood |
|--------|---------------|------------------------------|
| Stage a file | `git add notes.md` | runs `clean`: plaintext → `gzip -9` → `age -r <pubkey>` → stores encrypted blob |
| Commit & push | `git commit` + `git push` | pushes encrypted blob; plaintext never leaves your machine |
| Pull or checkout | `git pull` / `git checkout` | runs `smudge`: encrypted blob → `age --decrypt` → `gzip -d` → plaintext in working copy |
| View diff | `git diff notes.md` | `textconv` decrypts on the fly; diff shows plaintext changes |
| Clone on a new machine | `git clone` + run `setup_veil.sh` | registers the filter with the local private key; subsequent checkouts auto-decrypt |

### What is stored in git history

Git history **only ever contains encrypted `.gz.age` blobs**. Even if you inspect the
object store directly (`git cat-file`), you see binary ciphertext — not plaintext.

```bash
# This is what you see in the git object store:
$ git show HEAD:docs/private/notes.md | xxd | head -3
00000000: 6167 6520 656e 6372 7970 7469 6f6e 2e76  age encryption.v
...
```

### Key storage

Your **private key** lives exclusively on your local machine (`~/.config/age/`), outside
the repository. The repository only contains public keys (recipients), which are safe to
commit and share. Without the matching private key, the encrypted blobs are unreadable.

```
~/.config/age/myrepo_key.txt    ← private key  — stays on your machine only
.veil/config.toml               ← public key + patterns — committed, encrypted
.gitattributes                  ← filter mapping — committed, plaintext
.git/config                     ← filter commands — local only, never pushed
```

## Prerequisites & Installation

`veilgit` itself is a single Python script (`veil_setup.py`) that requires **Python 3.8+** and zero external Python dependencies. 

However, your system must have the following underlying tools installed:
- [age](https://github.com/FiloSottile/age) (includes `age-keygen`)
- `gzip`
- `git`

**On Debian/Ubuntu:**
```bash
sudo apt install age gzip git python3
```

**On macOS:**
```bash
brew install age
```

## Platform Support

| Platform | Support level | Notes |
|----------|---------------|-------|
| **Linux** | ✅ First-class | Generates `setup_veil.sh`; language auto-detected from `LANG` / `LC_ALL` |
| **macOS** | ✅ First-class | Generates `setup_veil.sh`; language auto-detected from `LANG` |
| **Windows** | ⚠️ Best-effort | Generates `setup_veil.py` instead of `.sh`; private key stored in `%APPDATA%\age\`; language auto-detected from the system locale; `gzip` and `age` must be installed manually (see [age releases](https://github.com/FiloSottile/age/releases)) |

On Windows, run the setup script with:
```powershell
python .veil\setup_veil.py C:\path\to\private_key.txt
```

## Quick Start

1. **Initialize your repository** (if you haven't already):
   ```bash
   git init my-project
   ```

2. **Run the interactive setup wizard:**
   ```bash
   python veil_setup.py my-project
   ```
   The wizard will check your dependencies, let you choose which file patterns to encrypt (e.g., `*.md`, `secrets/**`), generate or select an `age` key pair, and configure the git filters.

3. **Commit the configuration:**
   After the setup finishes, commit the newly generated `.gitattributes` and `.veil/` directory to save the configuration for you and your collaborators.
   ```bash
   cd my-project
   git add .gitattributes .veil/
   git commit -m "chore: setup veilgit transparent encryption"
   ```

## Interface and Usage

You can control `veilgit` using various CLI flags to modify the configuration without going through the full interactive wizard.

| Command | Description |
|---------|-------------|
| `python veil_setup.py <repo>` | Run the full interactive setup wizard (steps 0–6). |
| `python veil_setup.py <repo> --dry-run` | Simulate the setup process. Prints planned actions without writing any files. |
| `python veil_setup.py <repo> --show-config` | Print the current `.veil/config.toml` configuration. |
| `python veil_setup.py <repo> --add-pattern '*.md'` | Add a new glob pattern to the existing configuration. |
| `python veil_setup.py <repo> --remove-pattern '*.md'`| Remove a glob pattern from the existing configuration. |
| `python veil_setup.py <repo> --reinit` | Re-write the local `.git/config` filters based on the existing `.veil/config.toml`. |
| `python veil_setup.py -l cs <repo>` | Run the wizard in a specific language (supported: `en`, `de`, `fr`, `sp`, `cs`, `pl`). |
| `python veil_setup.py --version` | Print the version of the script. |

## Multi-language Support

`veilgit` is fully localized and can communicate with you in multiple languages during the interactive setup and in CLI messages.

Currently supported languages:
- English (`en`) - Default
- German (`de`)
- French (`fr`)
- Spanish (`sp`)
- Czech (`cs`)
- Polish (`pl`)

The active language is resolved automatically in the following priority:
1. **CLI Parameter:** Using the `-l` or `--lang` flag (e.g., `python veil_setup.py -l cs <repo>`).
2. **Configuration File:** If previously set in `.veil/config.toml` (e.g., `language = "cs"`).
3. **Operating System Locale:** Detected automatically from your OS environment variables (like `LANG` on Linux/macOS) or system settings (on Windows).
4. **Fallback:** English (`en`).

## Collaborating with Others

`veilgit` supports multiple recipients. You can easily grant access to your team members:

1. Ask your collaborator for their public `age` key (`age1...`).
2. Run `python veil_setup.py <repo>` and add their public key when prompted.
3. Commit and push the updated `.veil/config.toml` and `.git/config` filters.
4. Your collaborator simply clones the repository and runs the generated setup script, providing their own private key:
   ```bash
   bash .veil/setup_veil.sh /path/to/their/private_key.txt
   ```

## Security Considerations

- **Never commit your private key.** Keep it safely backed up in a password manager or an encrypted drive.
- **Public keys are safe to share.** They are only used to encrypt data, not to decrypt it.
- **Git history is permanent.** If you accidentally commit a plain text file before configuring `veilgit`, it will remain in the git history even if you encrypt it later. Always verify your `.gitattributes` are set up correctly before committing sensitive data.

## Development

If you want to contribute to `veilgit` or run the test suite:

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
pytest tests/ -m unit
pytest tests/ -m integration

# Run linters and type checkers
ruff check .
ruff format --check .
mypy veil_setup.py --strict
```

## Cursor IDE & AI Agents

This project uses the Agentic Project Management (APM) workflow for development, which is powered by a shared configuration library mounted as a git submodule in the `.cursor/` directory.

If you are developing `veilgit` using the [Cursor IDE](https://cursor.sh/), the `.cursor` submodule provides:
- **Curated Rules (`.mdc` files):** Enforce consistent coding standards, clean code, SOLID principles, and strict type checking.
- **Agent Skills:** Specialized workflows for AI agents (e.g., scaffolding, testing, and debugging).
- **APM Workflow:** A structured process dividing work between a Planner (architect), a Coder (developer), and a Human (reviewer).

To ensure the AI agents have access to these rules and skills, initialize the submodule after cloning the repository:

```bash
git submodule update --init --recursive
```

For more details on the APM workflow and how the AI agents are orchestrated, see the documentation inside the `.cursor/` directory.
