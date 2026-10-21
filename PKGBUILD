# Maintainer: xe5700 <xe5700@users.noreply.github.com>
# Contributor: xe5700 <xe5700@users.noreply.github.com>
#
# 上游信创 Linux 包在官方 CDN 按版本目录存放（版本化 URL，可复现、历史可追溯）：
#   https://cdn01.teleai.com.cn/packages/<ver>/TeleAgent-<ver>-<arch>.deb
# 最新版本号由固定重定向端点发现（服务端 302 始终指向最新版，update.py 自动处理，
# 下载同样走该端点，内容与上方版本化 URL 一致）。官方发新版后请运行仓库中的
# update.py 刷新 pkgver 与校验和。

pkgname=teleagent
pkgver=2.7.1
pkgrel=1
pkgdesc="星辰超级智能体 TeleAgent - 中国电信自研 AI 办公助手（桌面版）"
arch=('x86_64' 'aarch64')
url="https://www.teleai.com.cn/product/teleagent"
license=('LicenseRef-unknown')
depends=('gtk3' 'nss' 'libxss' 'libxtst' 'xdg-utils' 'at-spi2-core' 'libsecret' 'libnotify')
optdepends=('libappindicator-gtk3: 系统托盘图标支持')
provides=('teleagent')
conflicts=('teleagent')
# 重打包类包保持上游文件原样：不剥离符号、不生成 debug 子包
options=('!strip')
source=('teleagent-launcher.sh')
source_x86_64=("teleagent-${pkgver}-amd64.deb::https://cdn01.teleai.com.cn/packages/${pkgver}/TeleAgent-${pkgver}-amd64.deb")
source_aarch64=("teleagent-${pkgver}-arm64.deb::https://cdn01.teleai.com.cn/packages/${pkgver}/TeleAgent-${pkgver}-arm64.deb")
sha256sums=('4e1abfd03a9e160aa75cfb93400327e7d34c47f2c09d06af553f100ea3c8886a')
sha256sums_x86_64=('36c5e22cc5825c1850270d54dd5e89597f895e6f344723f714e86a4f94cc353d')
sha256sums_aarch64=('317abc8047e22695bb30067ab8e883a91f5f1189293cda357255a4fae4fdfd23')

package() {
    cd "$srcdir"

    case "$CARCH" in
        x86_64)  local _deb="teleagent-${pkgver}-amd64.deb" ;;
        aarch64) local _deb="teleagent-${pkgver}-arm64.deb" ;;
    esac

    # 从 deb（ar 归档）中提取 data.tar.xz 并解开到 pkgdir：
    # 提供 /opt/TeleAgent（Electron 自包含目录）、hicolor 图标、桌面文件
    bsdtar -x -f "$_deb" data.tar.xz
    bsdtar -x -C "$pkgdir" -f data.tar.xz

    # 安装启动器（内容等价于官方 postinst 生成的 teleagent-launcher）：
    # Wayland 会话强制走 XWayland、补齐 GTK_IM_MODULE、麒麟 arm64 Mali
    # libgbm 兼容修复，最后 exec 真正的二进制
    install -Dm755 teleagent-launcher.sh "$pkgdir/opt/TeleAgent/teleagent-launcher"

    # Electron chrome-sandbox 需要 setuid（与官方 postinst 行为一致）
    chmod 4755 "$pkgdir/opt/TeleAgent/chrome-sandbox"

    # 桌面入口改走启动器，保证 Wayland / 输入法修复在图形启动时同样生效
    # （等价于官方 postinst 对 teleagent.desktop 的 sed 处理）
    sed -i 's|^Exec=/opt/TeleAgent/teleagent|Exec=/opt/TeleAgent/teleagent-launcher|' \
        "$pkgdir/usr/share/applications/teleagent.desktop"

    # 命令行入口软链（等价于官方 update-alternatives / ln -sf）
    install -d "$pkgdir/usr/bin"
    ln -s /opt/TeleAgent/teleagent-launcher "$pkgdir/usr/bin/teleagent"
}
