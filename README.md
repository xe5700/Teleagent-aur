# teleagent (AUR)

星辰超级智能体 TeleAgent 桌面版（中国电信自研 AI 办公助手）的 Arch Linux / AUR 打包，
支持 `x86_64` 与 `aarch64`（信创）双架构。

- 官网：https://www.teleai.com.cn/product/teleagent
- 版本：基于官方信创 Linux deb 包（`/opt/TeleAgent` 自包含 Electron 应用）
- 上游下载（分工如下，内容一致）：
  - PKGBUILD source 用**版本化 CDN URL**（可复现、历史可追溯）：
    `https://cdn01.teleai.com.cn/packages/<ver>/TeleAgent-<ver>-<arch>.deb`
  - update.py 用**固定重定向端点**发现并下载最新版（服务端始终 302 到最新版）：
    - x64:   `https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-x64`
    - arm64: `https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-arm64`

## 仓库文件

| 文件 | 说明 |
| --- | --- |
| `PKGBUILD` | AUR 打包脚本（解包 deb → 安装 → 生成启动器/软链/桌面入口） |
| `.SRCINFO` | 由 `makepkg --printsrcinfo` 生成 |
| `teleagent-launcher.sh` | 启动器，内容等价于官方 postinst 生成的 `teleagent-launcher`（Wayland 强制 XWayland、GTK 输入法修复、麒麟 arm64 Mali libgbm 兼容） |
| `update.py` | 自动更新脚本（纯 Python + requests，无需无头浏览器） |
| `update.sh` | 更新入口（本地 / CI 通用）：先快速检测版本，有新版本才下载算哈希并刷新 |
| `.github/workflows/aur-update.yml` | GitHub Actions 定时自动更新，检测到新版本自动 commit + push |

## 构建

```bash
makepkg -si          # 下载官方 deb（约 400MB/架构）并安装
# 加速：提前把对应架构的 deb 放进 ./src/（文件名形如 teleagent-<ver>-<arch>.deb）
```

## 构建 pacman 安装包（build.sh）

```bash
./build.sh              # 构建 x86_64 + aarch64 两个 pacman 包
./build.sh amd64        # 只构建 x86_64 包（等价 ./build.sh x86_64）
./build.sh arm64        # 只构建 aarch64 包（x86_64 主机直接可建，无需交叉工具链/QEMU）
```

- 产物输出到 `dist/teleagent-<ver>-<rel>-<arch>.pkg.tar.zst`，安装：`pacman -U dist/...`
- aarch64 构建原理：本包无编译步骤（仅解包重打包），脚本以临时 HOME + 用户级
  makepkg.conf 覆盖 `CARCH`，让 makepkg 按目标架构选择 source 与元数据，不碰全局配置
- 离线加速：仓库根目录有官方命名 deb（`TeleAgent-<ver>-<tag>.deb`）时自动复用，
  否则 makepkg 自动下载
- 构建使用 `makepkg -d`（重打包不运行上游二进制，无需真实安装依赖）；PKGBUILD 已设
  `!strip` 保持上游文件原样，不生成 debug 子包

## 官方发新版后更新 AUR 包

```bash
python3 update.py                 # 全自动：查最新版 → 版本相同直接跳过 → 下载 → 刷新 PKGBUILD/.SRCINFO
python3 update.py --check         # 只看官网最新版本号
python3 update.py --local DIR     # 用本地已下载的 deb 算校验和，跳过下载（省 800MB 流量）
python3 update.py --force         # 版本未变也强制刷新校验和
python3 update.py --save          # 下载的包留存在 ./pkg-cache/ 供 makepkg 复用
python3 update.py --version 2.6.0 # 手动指定版本号（端点解析失败时兜底）
```

然后提交发布：

```bash
git add PKGBUILD .SRCINFO
git commit -m 'upgpkg: teleagent x.y.z'
git push
```

## CI 自动更新（GitHub Actions）

仓库提供开箱即用的定时自动更新：

- `update.sh`：**通用入口**（本地 / CI 均可）。先 `update.py --check` 快速检测官网版本，
  无新版本直接退出（**不下载**约 800MB 安装包）；有新版本才下载算哈希并刷新
  `PKGBUILD` / `.SRCINFO`。
- `.github/workflows/aur-update.yml`：每天 08:00 UTC（北京 16:00）自动运行，也可在
  Actions 页面手动触发；检测到新版本时自动 `git commit` + `git push`（用仓库的
  `GITHUB_TOKEN`，无需额外 secret）。

```bash
./update.sh            # 本地手动更新（效果等同 update.py 全流程，但会先做快速版本检测）
```

把仓库推送到 GitHub 后，workflow 即自动生效。

## 与官方 deb 的行为差异

- 不使用 `update-alternatives`，直接 `ln -s /usr/bin/teleagent -> /opt/TeleAgent/teleagent-launcher`
- 不创建 UOS/麒麟风格的桌面快捷方式，不安装 AppArmor profile（Ubuntu 特有）
- 桌面入口 `Exec` 同官方一样指向 `teleagent-launcher`，Wayland/输入法修复行为一致
- 依赖映射：`libgtk-3-0→gtk3`、`libnss3→nss`、`libatspi2.0-0→at-spi2-core`、
  `libappindicator3-1→libappindicator-gtk3`（AUR，列为可选依赖）等

> AI生成