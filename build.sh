#!/usr/bin/env bash
# teleagent AUR 包双架构构建脚本
#
# 在 x86_64 主机上也能构建 aarch64 包：本包不含任何编译步骤（把官方 deb 解包
# 重打包为 pacman 包），无需交叉工具链或 QEMU。脚本通过「临时 HOME + 用户级
# makepkg.conf 覆盖 CARCH」让 makepkg 以目标架构视角选择 source 与包元数据，
# 不修改系统或用户的全局配置。
#
# 用法：
#   ./build.sh              # 构建全部架构（x86_64 + aarch64）
#   ./build.sh amd64        # 只构建 x86_64 包（等价 ./build.sh x86_64）
#   ./build.sh arm64        # 只构建 aarch64 包（等价 ./build.sh aarch64）
#
# 离线加速：仓库根目录若已有落地名缓存（teleagent-<ver>-<tag>.deb）或官方命名
# deb（TeleAgent-<ver>-<tag>.deb，脚本会自动复制为落地名），makepkg 直接复用；
# 否则自动从官网 CDN 下载（约 400MB/架构）。
#
# 产物：dist/teleagent-<ver>-<rel>-<arch>.pkg.tar.zst
# 安装：pacman -U dist/teleagent-<ver>-<rel>-<arch>.pkg.tar.zst
#
# 说明：使用 makepkg -d（--nodeps）跳过依赖检查——重打包过程不运行上游二进制，
# 无需真实安装 gtk3 等依赖；包元数据仍完整记录 depends，安装时由 pacman 解析。

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

pkgver="$(sed -n 's/^pkgver=//p' PKGBUILD)"
pkgrel="$(sed -n 's/^pkgrel=//p' PKGBUILD)"
if [[ -z $pkgver || -z $pkgrel ]]; then
    echo "错误：无法从 PKGBUILD 读取 pkgver/pkgrel" >&2
    exit 1
fi

# 参数解析：同时接受 deb 命名（amd64/arm64）与 pacman 命名（x86_64/aarch64）
targets=()
for arg in "$@"; do
    case "$arg" in
        amd64|x86_64)  targets+=(x86_64) ;;
        arm64|aarch64) targets+=(aarch64) ;;
        *)
            echo "错误：未知架构 '$arg'（可用：amd64/x86_64、arm64/aarch64）" >&2
            exit 1
            ;;
    esac
done
if [[ ${#targets[@]} -eq 0 ]]; then
    targets=(x86_64 aarch64)
fi

mkdir -p dist src .temp

for pacarch in "${targets[@]}"; do
    if [[ $pacarch == x86_64 ]]; then tag=amd64; else tag=arm64; fi
    echo "==> 构建 ${pacarch}（deb 架构 tag: ${tag}）"

    # 离线缓存：makepkg 优先使用仓库根目录的落地名文件（srcdir 内为指向它的软链），
    # 故将官方命名 deb 复制/硬链为落地名放在根目录，即可跳过下载
    cachefile="teleagent-${pkgver}-${tag}.deb"
    if [[ ! -e $cachefile ]]; then
        for cand in "TeleAgent-${pkgver}-${tag}.deb"; do
            if [[ -f $cand ]]; then
                echo "    复用本地包：$cand -> $cachefile"
                ln "$cand" "$cachefile" 2>/dev/null || cp "$cand" "$cachefile"
                break
            fi
        done
    fi

    # 临时 HOME：用户级 makepkg.conf 只覆盖 CARCH，其余继承 /etc/makepkg.conf
    # （makepkg 的 conf 查找顺序：/etc/makepkg.conf -> XDG_CONFIG_HOME/pacman/makepkg.conf）
    fake_home="$repo_dir/.temp/home-${pacarch}"
    mkdir -p "$fake_home/.config/pacman"
    printf 'CARCH="%s"\n' "$pacarch" > "$fake_home/.config/pacman/makepkg.conf"

    HOME="$fake_home" \
    XDG_CONFIG_HOME="$fake_home/.config" \
    SRCDEST="$repo_dir/src" \
    PKGDEST="$repo_dir/dist" \
    makepkg -d -f

    # 定位产物（兼容自定义 PKGEXT 的包后缀）
    pkg_file="$(ls dist/teleagent-${pkgver}-${pkgrel}-${pacarch}.pkg.tar.* 2>/dev/null | head -n 1 || true)"
    if [[ -z $pkg_file ]]; then
        echo "错误：构建 ${pacarch} 后未在 dist/ 找到产物" >&2
        exit 1
    fi
    echo "==> 完成：$pkg_file（$(du -h "$pkg_file" | cut -f1)）"
    echo
done

echo "全部构建完成，产物列表："
ls -lh dist/teleagent-*.pkg.tar.* 2>/dev/null
echo
echo "安装示例：pacman -U dist/teleagent-${pkgver}-${pkgrel}-<arch>.pkg.tar.zst"
