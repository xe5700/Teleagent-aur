#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""teleagent AUR 包自动更新脚本（纯 Python + requests，无需浏览器）

工作原理：
  1. 版本发现：官方提供长期固定的重定向端点（服务端始终 302 指向当前最新版 deb）：
       x64:   https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-x64
       arm64: https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-arm64
     从重定向目标文件名（形如 TeleAgent-2.5.2-amd64.deb）解析出最新版本号。
  2. 版本号与 PKGBUILD 当前 pkgver 相同时直接退出，不下载、不哈希。
  3. 有新版本时下载两架构包（继续走重定向端点，服务端指向的就是最新版，内容
     与 PKGBUILD source 里的 CDN 版本化 URL 一致），流式计算 SHA256。
  4. 更新 PKGBUILD（pkgver/pkgrel/sha256sums），调用 makepkg 重新生成 .SRCINFO。

用法：
  python3 update.py                 # 完整流程：查最新版 → 对比 → 下载 → 更新
  python3 update.py --check         # 仅查询官网最新版本，不做任何修改
  python3 update.py --local DIR     # 使用本地已下载的 deb（目录内官方命名文件）
  python3 update.py --force         # 版本未变时也强制重算校验和并刷新文件
  python3 update.py --version 2.6.0 # 手动指定版本号（跳过在线获取）
  python3 update.py --save          # 下载的 deb 保存到 ./pkg-cache/ 供 makepkg 复用

依赖：python3、requests（pip install requests）、makepkg（更新 .SRCINFO 时需要）
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("[错误] 缺少 requests 库，请先安装：pip install requests")

# 官方固定重定向端点（URL 永不变，版本由服务端重定向目标决定）
REDIRECT_URLS = {
    "amd64": "https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-x64",
    "arm64": "https://agent.teleai.com.cn/superCowork/sapi/api/download/redirect/linux-arm64",
}
# 重定向目标文件名形如 TeleAgent-2.5.2-amd64.deb
VERSION_RE = {
    "amd64": re.compile(r"TeleAgent-(\d+(?:\.\d+)*)-amd64\.deb", re.I),
    "arm64": re.compile(r"TeleAgent-(\d+(?:\.\d+)*)-arm64\.deb", re.I),
}
# --local 模式接受的本地文件名（官方命名 / PKGBUILD 落地命名）
LOCAL_NAME_RE = {
    "amd64": re.compile(r"(?:TeleAgent|teleagent)-(\d+(?:\.\d+)*)-amd64\.deb"),
    "arm64": re.compile(r"(?:TeleAgent|teleagent)-(\d+(?:\.\d+)*)-arm64\.deb"),
}
CHUNK = 1 << 20  # 1 MiB


def die(msg: str) -> "None":
    sys.exit(f"[错误] {msg}")


def fetch_latest_versions(session: "requests.Session", manual: str) -> dict:
    """从重定向端点获取各架构最新版本号；manual 非空则直接采用。"""
    if manual:
        return {"amd64": manual, "arm64": manual}
    versions = {}
    for arch, url in REDIRECT_URLS.items():
        try:
            r = session.get(url, allow_redirects=False, timeout=30)
            if r.status_code not in (301, 302, 303, 307, 308):
                raise RuntimeError(f"未返回重定向（HTTP {r.status_code}）")
            location = urllib.parse.unquote(r.headers.get("Location", ""))
            m = VERSION_RE[arch].search(location)
            if m:
                versions[arch] = m.group(1)
                continue
            # 兜底：跟随重定向，从最终 URL 或 Content-Disposition 里找文件名
            r2 = session.get(url, stream=True, timeout=(10, 60))
            probe = urllib.parse.unquote(str(r2.url)) + " " + r2.headers.get("Content-Disposition", "")
            r2.close()
            m = VERSION_RE[arch].search(probe)
            if m:
                versions[arch] = m.group(1)
                continue
            raise RuntimeError("重定向响应中解析不到版本号")
        except Exception as e:
            die(f"获取 {arch} 最新版本失败：{e}\n       可用 --version 手动指定后重试。")
    if versions["amd64"] != versions["arm64"]:
        print(f"[警告] 两架构版本不一致：x64={versions['amd64']} arm64={versions['arm64']}，以 x64 为 pkgver。")
    return versions


def sha256_stream(resp) -> str:
    """流式读取响应体并计算 SHA256，避免大文件占用内存。"""
    h = hashlib.sha256()
    for chunk in resp.iter_content(CHUNK):
        if chunk:
            h.update(chunk)
    return h.hexdigest()


def download_and_hash(session: "requests.Session", arch: str, save_dir: Path) -> tuple:
    """下载指定架构的包并返回 (sha256, 本地文件或 None)。"""
    url = REDIRECT_URLS[arch]
    dest = None
    try:
        r = session.get(url, stream=True, timeout=(10, 60))
        r.raise_for_status()
        if save_dir:
            # 优先用重定向目标文件名，拿不到就用端点名
            name = VERSION_RE[arch].search(urllib.parse.unquote(str(r.url)))
            fname = f"TeleAgent-{name.group(1)}-{arch}.deb" if name else url.rsplit("/", 1)[-1]
            dest = save_dir / fname
        if dest:
            h = hashlib.sha256()
            with dest.open("wb") as f:
                for chunk in r.iter_content(CHUNK):
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
            print(f"  {arch}: 已下载 {dest}（SHA256 {h.hexdigest()}）")
            return h.hexdigest(), dest
        # 不落盘，边读边算
        h = sha256_stream(r)
        print(f"  {arch}: SHA256 {h}")
        return h, None
    except Exception as e:
        die(f"下载 {arch} 包失败：{e}")


def find_local_deb(local_dir: Path, arch: str) -> tuple:
    """在本地目录查找现成的 deb，返回 (版本号, 文件路径)。"""
    for f in sorted(local_dir.iterdir()):
        m = LOCAL_NAME_RE[arch].match(f.name)
        if m and f.is_file():
            return m.group(1), f
    die(f"--local 目录 {local_dir} 中找不到 {arch} 架构的 deb（形如 TeleAgent-x.y.z-{arch}.deb）")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def update_pkgbuild(pkgbuild: Path, version: str, sums: dict, force: bool) -> bool:
    """更新 PKGBUILD 中的 pkgver/pkgrel/sha256sums，返回是否发生修改。"""
    text = pkgbuild.read_text(encoding="utf-8")
    current = re.search(r"^pkgver=(\S+)", text, re.M)
    if not current:
        die("PKGBUILD 中找不到 pkgver= 行")
    old = current.group(1)
    if old == version and not force:
        print(f"[信息] PKGBUILD 已是最新版本 {old}，无需更新（--force 可强制刷新）。")
        return False

    def repl_pkgver(m):
        return f"pkgver={version}"

    def repl_pkgrel(m):
        return "pkgrel=1"

    new = re.sub(r"^pkgver=\S+$", repl_pkgver, text, flags=re.M)
    new = re.sub(r"^pkgrel=\S+$", repl_pkgrel, new, flags=re.M)
    # makepkg 架构标识为 x86_64/aarch64（CARCH 命名），对应 deb 的 amd64/arm64
    new = re.sub(r"^sha256sums_x86_64=\('.*'\)$",
                 lambda m: f"sha256sums_x86_64=('{sums['amd64']}')", new, flags=re.M)
    new = re.sub(r"^sha256sums_aarch64=\('.*'\)$",
                 lambda m: f"sha256sums_aarch64=('{sums['arm64']}')", new, flags=re.M)

    if (f"pkgver={version}" not in new
            or f"sha256sums_x86_64=('{sums['amd64']}')" not in new
            or f"sha256sums_aarch64=('{sums['arm64']}')" not in new):
        die("PKGBUILD 更新校验失败（替换结果与预期不符），文件未写入。请检查 PKGBUILD 格式。")
    pkgbuild.write_text(new, encoding="utf-8")
    print(f"[完成] PKGBUILD 已更新：pkgver {old} -> {version}，pkgrel 重置为 1，两架构校验和已刷新。")
    return True


def regenerate_srcinfo(repo_dir: Path) -> None:
    """调用 makepkg 重新生成 .SRCINFO。"""
    makepkg = shutil.which("makepkg")
    if not makepkg:
        print("[警告] 未找到 makepkg，请手动执行：makepkg --printsrcinfo > .SRCINFO")
        return
    try:
        out = subprocess.run(
            [makepkg, "--printsrcinfo"], cwd=repo_dir,
            check=True, capture_output=True, text=True,
        )
        for required in ("sha256sums_x86_64", "sha256sums_aarch64"):
            if required not in out.stdout:
                die(f".SRCINFO 生成结果中缺少 {required}，PKGBUILD 可能格式异常，已中止。")
        (repo_dir / ".SRCINFO").write_text(out.stdout, encoding="utf-8")
        print(f"[完成] .SRCINFO 已重新生成（{repo_dir / '.SRCINFO'}）。")
    except subprocess.CalledProcessError as e:
        die(f"makepkg --printsrcinfo 失败：{e.stderr.strip() or e}")


def main() -> None:
    repo_dir = Path(__file__).resolve().parent
    pkgbuild = repo_dir / "PKGBUILD"
    if not pkgbuild.exists():
        die(f"未找到 {pkgbuild}，请将 update.py 放在 AUR 仓库根目录运行。")

    ap = argparse.ArgumentParser(description="teleagent AUR 包自动更新脚本")
    ap.add_argument("--check", action="store_true", help="仅查询官网最新版本，不做任何修改")
    ap.add_argument("--force", action="store_true", help="版本未变时也强制重算校验和并刷新文件")
    ap.add_argument("--version", metavar="VER", help="手动指定版本号（跳过在线获取）")
    ap.add_argument("--local", metavar="DIR", help="使用本地目录中已下载的 deb 包，跳过下载")
    ap.add_argument("--save", action="store_true", help="下载的 deb 保存到 ./pkg-cache/ 供 makepkg 复用")
    ap.add_argument("--no-srcinfo", action="store_true", help="不重新生成 .SRCINFO")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "aur-teleagent-updater/1.0"

    if args.check:
        versions = fetch_latest_versions(session, args.version)
        current = re.search(r"^pkgver=(\S+)", pkgbuild.read_text(encoding="utf-8"), re.M).group(1)
        print(f"官网最新版本：{versions['amd64']}（x64={versions['amd64']} arm64={versions['arm64']}）")
        print(f"PKGBUILD 当前版本：{current}")
        print("状态：已是最新" if current == versions["amd64"] else "状态：有新版本，可运行 python3 update.py 更新")
        return

    save_dir = repo_dir / "pkg-cache" if args.save else None
    if save_dir:
        save_dir.mkdir(exist_ok=True)

    # 第一步：确定上游最新版本号（在线或本地文件名），不读文件内容、不下载
    versions, local_files = {}, {}
    if args.local:
        local_dir = Path(args.local).resolve()
        if not local_dir.is_dir():
            die(f"--local 目录不存在：{local_dir}")
        for arch in ("amd64", "arm64"):
            versions[arch], local_files[arch] = find_local_deb(local_dir, arch)
        if versions["amd64"] != versions["arm64"]:
            print(f"[警告] 本地两架构版本不一致：{versions}，以 x64 为 pkgver。")
    else:
        versions = fetch_latest_versions(session, args.version)

    # 第二步：版本号相同则直接退出，不下载、不哈希
    current = re.search(r"^pkgver=(\S+)", pkgbuild.read_text(encoding="utf-8"), re.M).group(1)
    if current == versions["amd64"] and not args.force:
        print(f"[信息] PKGBUILD 已是最新版本 {current}，无需更新（--force 可强制刷新）。")
        return

    # 第三步：计算两架构包的 SHA256
    sums = {}
    if args.local:
        for arch in ("amd64", "arm64"):
            print(f"[本地] {arch}: {local_files[arch].name}（版本 {versions[arch]}），计算 SHA256 ...")
            sums[arch] = sha256_file(local_files[arch])
    else:
        print(f"[信息] 官网最新版本 {versions['amd64']}，开始下载并计算校验和：")
        for arch in ("amd64", "arm64"):
            sums[arch], _ = download_and_hash(session, arch, save_dir)

    # 第四步：更新 PKGBUILD 与 .SRCINFO
    if update_pkgbuild(pkgbuild, versions["amd64"], sums, args.force) and not args.no_srcinfo:
        regenerate_srcinfo(repo_dir)
        print()
        print("后续步骤（发布/更新 AUR 包）：")
        print("  git add PKGBUILD .SRCINFO && git commit -m 'upgpkg: teleagent %s'" % versions["amd64"])
        print("  git push")


if __name__ == "__main__":
    main()
