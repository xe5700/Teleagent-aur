#!/bin/bash
# 由安装脚本（after-install-linux.tpl）生成，请勿手工编辑。
# 作用：修掉残缺 Mali libgbm 导致的 "undefined symbol: gbm_bo_map" 启动失败。

APP_BIN='/opt/TeleAgent/teleagent'
APP_LIBGBM_DIR='/opt/TeleAgent/libgbm-compat'

# 判断 so 是否导出 gbm_bo_map，只认 binutils 读出来的动态符号表；
# 两个工具都没有时由调用方改问动态链接器（ldd -r），不做字节级猜测。
gbm_defines_bo_map() {
    lib_path="$1"
    [ -e "$lib_path" ] || return 1

    if command -v nm >/dev/null 2>&1; then
        lib_syms=$(nm -D --defined-only "$lib_path" 2>/dev/null)
        if [ -n "$lib_syms" ]; then
            printf '%s\n' "$lib_syms" | grep -Eq '[[:space:]]gbm_bo_map(@|$)'
            return
        fi
    fi

    if command -v readelf >/dev/null 2>&1; then
        lib_syms=$(readelf -sW --dyn-syms "$lib_path" 2>/dev/null)
        if [ -n "$lib_syms" ]; then
            printf '%s\n' "$lib_syms" |
                grep -Eq '[[:space:]](GLOBAL|WEAK)[[:space:]]+(DEFAULT|PROTECTED|HIDDEN)[[:space:]]+[0-9]+[[:space:]]+gbm_bo_map(@|$)'
            return
        fi
    fi
    return 1
}

# 只有「当前会被链接器选中的 libgbm 提供不了 gbm_bo_map，而通用目录里的那份可以」
# 才改查找顺序；其余环境（含所有 x86_64 机器）原样直通。两条判据都是实证——
# 有 binutils 就读符号表，没有就直接问动态链接器，不按路径猜。
fix_broken_gbm_lookup() {
    # 已知只有麒麟/Kirin arm64 + Mali 驱动会踩到，先按架构挡掉其他 Linux 机器。
    [ "$(uname -m)" = 'aarch64' ] || return 0
    command -v ldd >/dev/null 2>&1 || return 0

    # 用 ldd 而不是猜路径：它走的就是动态链接器自身的搜索规则（含 ld.so.cache）。
    # 已知的坏布局是 /usr/lib/aarch64-linux-gnu/mali/libgbm.so.1（软链到 libmali.so.0），
    # 但这里不写死该路径：换个目录摆放的镜像同样能被下面的符号判据兜住。
    resolved_gbm=$(ldd "$APP_BIN" 2>/dev/null | sed -n 's|^[[:space:]]*libgbm\.so\.1 => \(/[^ ]*\).*|\1|p' | head -n 1)
    [ -n "$resolved_gbm" ] || return 0

    generic_gbm_dir='/usr/lib/aarch64-linux-gnu'
    generic_gbm_lib="$generic_gbm_dir/libgbm.so.1"
    # 选中的已经是通用目录那份 → 没有别的可换，直通。
    [ "$resolved_gbm" != "$generic_gbm_lib" ] || return 0
    [ -e "$APP_LIBGBM_DIR/libgbm.so.1" ] || return 0

    if command -v nm >/dev/null 2>&1 || command -v readelf >/dev/null 2>&1; then
        gbm_defines_bo_map "$resolved_gbm" && return 0
        gbm_defines_bo_map "$generic_gbm_lib" || return 0
    else
        # 没有 binutils 就问动态链接器本身：ldd -r 会做重定位并打印真正解析不了的符号，
        # 也就是这次故障的直接观测。-r 要遍历整个二进制的重定位、开销不小，所以只在
        # 走到这一支时才付（正常机器在上面几行就返回了）。
        ldd -r "$APP_BIN" 2>&1 | grep -q 'undefined symbol: gbm_bo_map' || return 0
    fi

    # 私有目录里只有指向通用 libgbm 的一个软链，避免把整个系统 multiarch
    # 目录提前后连带改掉 EGL/GLES 等其他驱动库的选择。
    LD_LIBRARY_PATH="$APP_LIBGBM_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LD_LIBRARY_PATH
    echo "TeleAgent: $resolved_gbm 提供不了 gbm_bo_map，已通过 $APP_LIBGBM_DIR 改用 $generic_gbm_lib" >&2
}

# Wayland 会话下强制走 XWayland，以及补齐 GTK 输入法模块。
#
# 这两件事**只能在这里做**：Electron 在执行 main.js 之前就已经选定 Ozone 平台、
# 初始化完 GTK，主进程里的 app.commandLine.appendSwitch('ozone-platform', 'x11') 与
# process.env.GTK_IM_MODULE = ... 都赶不上（麒麟 V10 SP1 / UKUI-wayland 实测：日志里
# forceX11ForWayland 是 true，进程却仍跑在原生 Wayland 上 —— fcitx 4 不支持 Wayland
# 文本输入协议，输入法切不了；带父窗的模态 GTK 文件对话框也弹不出来。命令行直传
# --ozone-platform=x11 后两个问题一起消失）。electron/utils/linux-window-compat.ts
# 里的同名判定保留为兜底（直接跑 /opt/<Product>/<executable> 时仍会走到），改这边记得同步。
#
# TELEAGENT_KEEP_WAYLAND=1 保留原生 Wayland，用于 A/B 定位。
if [ "$TELEAGENT_KEEP_WAYLAND" != '1' ] && [ -n "$DISPLAY" ] &&
   { [ "$XDG_SESSION_TYPE" = 'wayland' ] || [ -n "$WAYLAND_DISPLAY" ]; }; then
    # 调用方显式指定过就尊重，不覆盖。
    case " $* " in
        *' --ozone-platform='*) ;;
        *) set -- --ozone-platform=x11 "$@" ;;
    esac
fi

# GTK 在进程启动阶段读 GTK_IM_MODULE 决定加载哪个输入法模块。发行版给 Qt 配了输入法
# 却漏配这一项时，表现是界面正常但中文打不进去。已设值一律尊重，判定与
# linux-window-compat.ts 的 resolveGtkImModule() 保持一致（只认 fcitx / fcitx5 / ibus）。
if [ -z "$GTK_IM_MODULE" ]; then
    case "$XMODIFIERS" in
        *@im=fcitx*) export GTK_IM_MODULE=fcitx ;;
        *@im=ibus*) export GTK_IM_MODULE=ibus ;;
        *)
            case "$QT_IM_MODULE" in
                fcitx*) export GTK_IM_MODULE=fcitx ;;
                ibus) export GTK_IM_MODULE=ibus ;;
            esac
            ;;
    esac
fi

fix_broken_gbm_lookup

exec "$APP_BIN" "$@"
