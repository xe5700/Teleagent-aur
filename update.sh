#!/usr/bin/env bash
# teleagent AUR 包自动更新脚本（本地与 CI 通用）
#
# 流程：
#   1) 快速检测官网是否发新版本（update.py --check，仅几次 HTTP 请求）
#   2) 无新版本 → 直接退出，不下载 800MB 安装包
#   3) 有新版本 → 下载两架构包、流式计算 SHA256、更新 PKGBUILD 与 .SRCINFO
#
# 配合 GitHub Actions 使用时，由 workflow 在脚本后根据 git diff 决定是否
# commit + push（见 .github/workflows/aur-update.yml）。
#
# 退出码：0 = 正常完成（无论是否发布新版本）；非 0 = 检测或更新失败。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "[update] 检测官网最新版本 ..."

# 1) 快速检测：update.py --check 打印"状态：已是最新"（无新版本）
#    或"状态：有新版本..."。命中前者则说明无需更新，直接跳过。
if python3 update.py --check 2>&1 | grep -q '已是最新'; then
    echo "[update] 无新版本，跳过（不下载安装包）。"
    exit 0
fi

echo "[update] 检测到新版本，下载并刷新 PKGBUILD/.SRCINFO ..."

# 2) 有新版本：下载两架构包 → 算哈希 → 更新文件
python3 update.py

# 3) 输出变更状态，供 CI 判断是否 git push
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git diff --quiet -- PKGBUILD .SRCINFO; then
        echo "UPDATE_STATUS=up-to-date"
    else
        echo "UPDATE_STATUS=new-version"
    fi
else
    echo "UPDATE_STATUS=not-a-git-repo"
fi
echo "[update] 完成。"