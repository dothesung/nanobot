---
name: github
description: "Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries."
metadata: {"nanobot":{"emoji":"🐙","requires":{"bins":["gh"]},"install":[{"id":"brew","kind":"brew","formula":"gh","bins":["gh"],"label":"Install GitHub CLI (brew)"},{"id":"apt","kind":"apt","package":"gh","bins":["gh"],"label":"Install GitHub CLI (apt)"}]}}
---

# GitHub Skill

Use the `gh` CLI to interact with GitHub. Always specify `--repo owner/repo` when not in a git directory, or use URLs directly.

## Cài đặt & Xác thực

### Cài đặt `gh` CLI
```bash
# macOS
brew install gh

# Ubuntu/Debian
sudo apt install gh

# Kiểm tra phiên bản
gh --version
```

### Xác thực (Authentication)
```bash
# Login tương tác (mở trình duyệt)
gh auth login

# Login bằng token
echo "ghp_xxxx" | gh auth login --with-token

# Kiểm tra trạng thái auth
gh auth status

# Đổi account
gh auth switch
```

## Repository Management

### Clone & Create
```bash
# Clone repo
gh repo clone owner/repo

# Tạo repo mới
gh repo create my-project --public --description "My project"

# Fork repo
gh repo fork owner/repo --clone
```

### Xem thông tin repo
```bash
# Thông tin repo hiện tại
gh repo view

# Xem repo bất kỳ
gh repo view owner/repo

# Liệt kê repos
gh repo list owner --limit 20
```

## Pull Requests

### Tạo & Quản lý PR
```bash
# Tạo PR
gh pr create --title "Feature X" --body "Description" --base main

# List PRs
gh pr list --repo owner/repo

# Xem PR
gh pr view 55 --repo owner/repo

# Merge PR
gh pr merge 55 --squash --repo owner/repo
```

### Check CI status on a PR
```bash
gh pr checks 55 --repo owner/repo
```

### Workflow Runs
```bash
# List recent workflow runs
gh run list --repo owner/repo --limit 10

# View a run and see which steps failed
gh run view <run-id> --repo owner/repo

# View logs for failed steps only
gh run view <run-id> --repo owner/repo --log-failed
```

## Issues

### Tạo & Quản lý Issues
```bash
# Tạo issue
gh issue create --title "Bug report" --body "Description" --repo owner/repo

# List issues
gh issue list --repo owner/repo --state open

# Xem issue
gh issue view 123 --repo owner/repo

# Comment
gh issue comment 123 --body "Fixed in PR #456" --repo owner/repo

# Đóng issue
gh issue close 123 --repo owner/repo

# Gán labels
gh issue edit 123 --add-label "bug,priority:high" --repo owner/repo
```

## Search

### Tìm kiếm repos, issues, code
```bash
# Search repos
gh search repos "crawl4ai language:python" --limit 10

# Search issues
gh search issues "bug label:critical" --repo owner/repo

# Search code
gh search code "function_name" --repo owner/repo
```

## Releases & Gist

### Releases
```bash
# List releases
gh release list --repo owner/repo

# Tạo release
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes" --repo owner/repo

# Download release assets
gh release download v1.0.0 --repo owner/repo
```

### Gist
```bash
# Tạo gist
gh gist create file.py --public --desc "My snippet"

# List gists
gh gist list

# Xem gist
gh gist view <gist-id>
```

## API for Advanced Queries

The `gh api` command is useful for accessing data not available through other subcommands.

```bash
# Get PR with specific fields
gh api repos/owner/repo/pulls/55 --jq '.title, .state, .user.login'

# Get repo info
gh api repos/owner/repo --jq '{name, stars: .stargazers_count, forks: .forks_count}'

# List contributors
gh api repos/owner/repo/contributors --jq '.[].login'

# Get latest release
gh api repos/owner/repo/releases/latest --jq '.tag_name'
```

## JSON Output

Most commands support `--json` for structured output. You can use `--jq` to filter:

```bash
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'

# PR with details
gh pr list --repo owner/repo --json number,title,state,author --jq '.[] | "\(.number) [\(.state)] \(.title) by \(.author.login)"'
```

## Tips
- Dùng `--repo owner/repo` khi không ở trong git directory
- Dùng `--json` + `--jq` để lấy dữ liệu structured
- Dùng `gh api` cho những thao tác nâng cao không có subcommand
- Để cào nội dung web từ GitHub (README, code), dùng tool `crawler` (xem skill `crawl4ai`)
