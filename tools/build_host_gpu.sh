#!/usr/bin/env bash
# Fallback: build the Mac-side GPU driver (KosmicKrisp Vulkan-on-Metal + virglrenderer
# with Venus) from pinned upstream sources. install.sh normally downloads the prebuilt
# copy instead; this takes roughly 15-30 minutes and needs Xcode command line tools.
# Output: private/host-runtime/{libvulkan_kosmickrisp.dylib,libvirglrenderer.1.dylib}
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="${BMW_GPU_BUILD_ROOT:-$root/.local/gpu-build}"
mesa_commit=81d869ccd506ed4edf371bfaba700dc01e54723b
mkdir -p "$work" "$root/private/host-runtime"
brew install llvm spirv-llvm-translator spirv-tools libclc vulkan-headers vulkan-loader libepoxy ninja pkg-config

if [[ ! -d "$work/mesa-mirror-$mesa_commit" ]]; then
    curl -fL "https://github.com/chaotic-cx/mesa-mirror/archive/$mesa_commit.tar.gz" -o "$work/mesa.tar.gz"
    printf '46ea0277ecf2553fa7a7fc980b09b705c043a69e29b1f63a937e07dd580e5353  %s\n' "$work/mesa.tar.gz" | shasum -a 256 -c -
    tar -xzf "$work/mesa.tar.gz" -C "$work"
fi
[[ -d "$work/venv" ]] || python3 -m venv "$work/venv"
"$work/venv/bin/pip" install -q 'mako==1.4.3' 'packaging==26.3' 'pyyaml==6.0.3' 'meson==1.12.1'
export PATH="$work/venv/bin:/opt/homebrew/opt/llvm/bin:$PATH"
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
export CC=/usr/bin/clang CXX=/usr/bin/clang++ OBJC=/usr/bin/clang OBJCXX=/usr/bin/clang++
export PKG_CONFIG_PATH=/opt/homebrew/opt/llvm/lib/pkgconfig:/opt/homebrew/opt/spirv-llvm-translator/lib/pkgconfig:/opt/homebrew/opt/spirv-tools/lib/pkgconfig:/opt/homebrew/opt/libclc/share/pkgconfig
if [[ ! -f "$work/build/build.ninja" ]]; then
    meson setup "$work/build" "$work/mesa-mirror-$mesa_commit" \
        --prefix="$work/install" --buildtype=release -Dplatforms=macos \
        -Dvulkan-drivers=kosmickrisp -Dgallium-drivers= -Dopengl=false -Dzstd=disabled --prefer-static
fi
ninja -C "$work/build"

virgl="$work/virglrenderer-0.10.4e-krunkit"
if [[ ! -d "$virgl" ]]; then
    curl -fL https://gitlab.freedesktop.org/slp/virglrenderer/-/archive/0.10.4e-krunkit/virglrenderer-0.10.4e-krunkit.tar.gz -o "$work/virgl.tar.gz"
    printf '09d000623fbdb966cb604eb48c962a0815e8142383e6066d6494809335b76dbb  %s\n' "$work/virgl.tar.gz" | shasum -a 256 -c -
    tar -xzf "$work/virgl.tar.gz" -C "$work"
    # Link against the standard Vulkan loader (which loads KosmicKrisp) instead of MoltenVK.
    perl -0pi -e "s/add_project_link_arguments\('-lMoltenVK', language : 'c'\)/add_project_link_arguments('-L\/opt\/homebrew\/opt\/vulkan-loader\/lib', '-lvulkan', language : 'c')/; s/-I\/opt\/homebrew\/opt\/molten-vk\/libexec\/include/-I\/opt\/homebrew\/opt\/vulkan-headers\/include/" "$virgl/meson.build"
    grep -q -- "-lvulkan" "$virgl/meson.build" || { echo 'virglrenderer patch did not apply' >&2; exit 1; }
fi
[[ -f "$work/virgl-build/build.ninja" ]] || meson setup "$work/virgl-build" "$virgl" \
    --prefix="$work/virgl-install" --buildtype=release -Dvenus=true -Drender-server=false
ninja -C "$work/virgl-build"

cp "$work/build/src/kosmickrisp/vulkan/libvulkan_kosmickrisp.dylib" "$root/private/host-runtime/"
cp "$work/virgl-build/src/libvirglrenderer.1.dylib" "$root/private/host-runtime/"
ln -sfn libvirglrenderer.1.dylib "$root/private/host-runtime/libvirglrenderer.dylib"
printf 'Built Mac GPU driver into %s\n' "$root/private/host-runtime"
